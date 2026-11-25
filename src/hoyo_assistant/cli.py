import argparse
import asyncio
import json
import os
import sys
from contextlib import suppress
from typing import Any, cast

from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import __version__, runner, server
from .core import http, loghelper, qr_login, setting, t, tools
from .core.constants import QR_LOGIN_DEFAULT_TIMEOUT, EnvVar, StatusCode
from .core.models import ServerSettings
from .core.setting_schema import HoyoConfig, collect_config_warnings


def _configure_stdio_encoding() -> None:
    """Prefer UTF-8 console output to avoid emoji encoding failures on Windows."""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            with suppress(OSError, ValueError):
                reconfigure(encoding="utf-8", errors="replace")


_configure_stdio_encoding()


def _is_interactive_terminal() -> bool:
    return tools.is_tty(require_stdin=False, check_ci=False)


def _use_rich_output() -> bool:
    return tools.use_rich_output(require_stdin=False, check_ci=False)


RICH_OUTPUT = _use_rich_output()
console = Console(no_color=not RICH_OUTPUT, force_terminal=RICH_OUTPUT)


def cli_print(message: str, style: str | None = None) -> None:
    if "\x1b[" in message:
        console.print(Text.from_ansi(message), soft_wrap=True)
    elif style and RICH_OUTPUT:
        console.print(f"[{style}]{escape(message)}[/{style}]", highlight=False)
    else:
        console.print(message, markup=False, highlight=False, soft_wrap=True)


def cli_panel(
    message: str, title: str | None = None, border_style: str = "cyan"
) -> None:
    if RICH_OUTPUT:
        console.print(
            Panel(
                escape(message),
                title=escape(title) if title else None,
                border_style=border_style,
            ),
            highlight=False,
        )
    else:
        if title:
            console.print(f"[{title}]", markup=False, highlight=False)
        console.print(message, markup=False, highlight=False)


def print_banner() -> None:
    """Print the application banner."""
    if not RICH_OUTPUT:
        return

    title = t("cli.banner.title")
    subtitle = t("cli.banner.subtitle")
    console.print(
        Panel.fit(
            f"[bold cyan]{title}[/bold cyan]\n[dim]{subtitle}[/dim]",
            border_style="cyan",
        )
    )


async def run_tasks(
    config_path: str | None = None,
    account_filter: list[str] | None = None,
    allow_qr_login: bool | None = None,
) -> int:
    """Execute unified account run and return its StatusCode."""
    cli_print(t("cli.task.run_start"), style="green")
    try:
        run_code, run_msg, _ = await runner.run_accounts(
            config_path=config_path,
            account_filter=account_filter,
            allow_qr_login=allow_qr_login,
        )
        if run_msg:
            cli_panel(
                run_msg,
                title=t("cli.task.exec_report"),
                border_style=(
                    "green" if run_code == StatusCode.SUCCESS.value else "red"
                ),
            )
        return run_code
    except Exception as e:
        cli_print(t("cli.task.run_fail", error=e), style="red")
        sys.exit(1)


def _find_cn_target_account(account_selector: str) -> dict[str, Any]:
    """Resolve an existing CN account from `--account` selector or exit cleanly."""
    token = account_selector.strip().lower()
    all_accounts = setting.config.get("accounts") or []
    for idx, acct in enumerate(all_accounts):
        if isinstance(acct, dict) and runner.executor._matches_filter(
            acct, idx, {token}
        ):
            if acct.get("region") != "cn":
                cli_print(t("qr.cn_only"), style="red")
                sys.exit(1)
            return acct

    cli_print(t("qr.account_not_found", selector=account_selector), style="red")
    sys.exit(1)


async def login_command(
    config_path: str | None = None,
    account_selector: str | None = None,
    name: str | None = None,
    scope: qr_login.QRScope = "all",
    timeout: int = QR_LOGIN_DEFAULT_TIMEOUT,
) -> None:
    """Run interactive terminal QR-code login for a CN account."""
    if not qr_login.is_interactive_terminal():
        cli_print(t("qr.non_interactive"), style="red")
        sys.exit(1)

    resolved_path, created = setting.ensure_config_initialized(config_path)
    if created:
        cli_print(t("cli.task.config_initialized", path=resolved_path), style="green")
    else:
        try:
            setting.reload_config(config_file=resolved_path, overrides={})
        except ValueError as e:
            cli_print(t("cli.task.config_error", error=e), style="red")
            sys.exit(1)

    target_account: dict[str, Any] | None = None
    if account_selector:
        target_account = _find_cn_target_account(account_selector)

    device = target_account.get("device") if target_account else None
    try:
        async with http:
            result = await qr_login.qr_login_cn(
                scope=scope,
                timeout=timeout,
                device=device if isinstance(device, dict) else None,
                printer=cli_print,
                use_ansi=RICH_OUTPUT,
            )
            saved_acct, created_new = await qr_login.upsert_cn_account(
                result,
                target_account=target_account,
                scope=scope,
                name=name,
            )
    except TimeoutError as e:
        cli_print(str(e), style="yellow")
        sys.exit(1)
    except KeyboardInterrupt:
        cli_print(t("qr.cancelled"), style="yellow")
        sys.exit(1)
    except Exception as e:
        cli_print(t("qr.failed", error=e), style="red")
        sys.exit(1)

    msg_key = "qr.saved_new" if created_new else "qr.saved_overwrite"
    cli_print(
        t(
            msg_key,
            name=str(saved_acct.get("name") or result.uid),
            uid=result.uid,
            path=setting.config_path or resolved_path,
        ),
        style="green",
    )


def print_effective_config() -> None:
    """Print current effective config with redacted secrets."""
    effective = setting.get_effective_config(redact=True)
    payload = json.dumps(effective, ensure_ascii=False, indent=2)
    cli_panel(payload, title=t("cli.task.effective_config"), border_style="cyan")


def validate_config(config_path: str | None, show_effective: bool = False) -> bool:
    """Validate the configuration file at config_path against the schema."""
    if not config_path:
        config_path = setting.config_path or setting._find_default_config_file()

    if not config_path or not os.path.exists(config_path):
        cli_print(t("cli.task.config_missing"), style="red")
        return False

    cli_print(t("cli.task.validating", path=config_path), style="yellow")
    is_valid, errors = setting.validate_config_file(config_path)

    if is_valid:
        cli_print(t("cli.task.valid"), style="green")
        try:
            import yaml

            with open(config_path, encoding="utf-8") as f:
                raw_data = yaml.safe_load(f) or {}
            cfg_model = HoyoConfig.model_validate(raw_data)
            warnings = collect_config_warnings(cfg_model)
            if warnings:
                cli_print(t("cli.task.check_warnings"), style="yellow")
                for w in warnings:
                    console.print(f"  - {escape(w)}", highlight=False)
        except Exception:
            pass
    else:
        cli_print(t("cli.task.invalid"), style="red")
        for error in errors:
            console.print(f"  - {escape(error)}", highlight=False)

    if show_effective and is_valid:
        print_effective_config()
    return is_valid


def fill_config_command(config_path: str, create_backup: bool = True) -> None:
    """Auto-fill and format a config file."""
    if not config_path:
        cli_print(t("cli.task.config_missing"), style="red")
        return

    config_path = str(os.path.expanduser(config_path))

    cli_print(t("cli.task.validating", path=config_path), style="cyan")
    success, message = setting.auto_fill_config_file(config_path, backup=create_backup)

    if success:
        cli_print(message, style="green")
    else:
        cli_print(message, style="red")
        sys.exit(1)


def _summarize_account_cookie(acct: dict[str, Any]) -> str:
    """Return a redacted status summary for an account's cookie string."""
    raw = str(acct.get("cookie") or "").strip()
    if not raw:
        return t("cli.task.list_cookie_empty")
    if acct.get("region") != "cn":
        return t("cli.task.list_cookie_set")
    fields = tools.parse_cookie(raw)
    has_stoken = bool(fields.get("stoken"))
    has_web = bool(
        fields.get("ltoken_v2")
        or fields.get("ltoken")
        or fields.get("cookie_token_v2")
        or fields.get("cookie_token")
    )
    if has_stoken and has_web:
        return t("cli.task.list_cookie_stoken_web")
    if has_stoken:
        return t("cli.task.list_cookie_stoken_only")
    if has_web:
        return t("cli.task.list_cookie_web_only")
    return t("cli.task.list_cookie_set")


def _summarize_account_tasks(acct: dict[str, Any]) -> str:
    """Return a compact summary of enabled tasks for display in `list`."""
    items: list[str] = []
    if acct.get("region") == "cn":
        bbs = acct.get("bbs") or {}
        if isinstance(bbs, dict) and bbs.get("enable"):
            forums = bbs.get("forums") or []
            items.append(f"bbs({len(forums)})")

    games = [str(g) for g in (acct.get("games") or []) if g]
    custom = acct.get("custom_games") or {}
    if isinstance(custom, dict):
        games.extend(
            str(k)
            for k, spec in custom.items()
            if isinstance(spec, dict) and spec.get("enable", True)
        )
    if games:
        items.append("games:" + ",".join(games))

    cloud = acct.get("cloud") or {}
    if isinstance(cloud, dict):
        cloud_games = [str(k) for k, tok in cloud.items() if str(tok or "").strip()]
        if cloud_games:
            items.append("cloud:" + ",".join(cloud_games))

    return "; ".join(items) if items else "-"


def _summarize_account_push(acct: dict[str, Any], default_targets: list[str]) -> str:
    """Return resolved push target summary for display in `list`."""
    acct_push = acct.get("push")
    if acct_push is None:
        if default_targets:
            return t("cli.task.list_push_default", targets=",".join(default_targets))
        return t("cli.task.list_push_none")
    if not acct_push:
        return t("cli.task.list_push_off")
    return ",".join(str(x) for x in acct_push)


def list_accounts_command(config_path: str | None) -> None:
    """List configured accounts safely with redacted credential statuses."""
    resolved = config_path or setting.config_path or ""
    accounts = setting.config.get("accounts") or []
    if not accounts:
        cli_print(t("cli.task.list_empty", path=resolved), style="yellow")
        return

    push_cfg = setting.config.get("push") or {}
    default_targets = [
        str(x) for x in (push_cfg.get("default") or []) if str(x).strip()
    ]
    title = t("cli.task.list_title", count=len(accounts), path=resolved)

    rows: list[tuple[str, str, str, str, str, str, str]] = []
    for idx, acct in enumerate(accounts, start=1):
        if not isinstance(acct, dict):
            continue
        region = str(acct.get("region") or "?").strip()
        selector = f"{region}#{idx}"
        name = str(acct.get("name") or "").strip() or "-"
        enabled = (
            t("cli.task.list_enabled")
            if acct.get("enable", True)
            else t("cli.task.list_disabled")
        )
        tasks_str = _summarize_account_tasks(acct)
        cookie_str = _summarize_account_cookie(acct)
        push_str = _summarize_account_push(acct, default_targets)
        rows.append(
            (str(idx), selector, name, enabled, tasks_str, cookie_str, push_str)
        )

    if RICH_OUTPUT:
        table = Table(title=escape(title))
        table.add_column(t("cli.task.list_col_index"), justify="right")
        table.add_column(t("cli.task.list_col_selector"), style="cyan")
        table.add_column(t("cli.task.list_col_name"), style="bold")
        table.add_column(t("cli.task.list_col_status"))
        table.add_column(t("cli.task.list_col_tasks"))
        table.add_column(t("cli.task.list_col_cookie"))
        table.add_column(t("cli.task.list_col_push"))
        for row in rows:
            table.add_row(*(escape(cell) for cell in row))
        console.print(table, highlight=False)
    else:
        cli_print(title)
        for row in rows:
            idx_s, selector, name, enabled, tasks_s, cookie_s, push_s = row
            cli_print(
                f"[{idx_s}] {selector} | {name} | {enabled} | "
                f"{cookie_s} | {tasks_s} | push={push_s}"
            )


def _add_config_flag(
    target: argparse.ArgumentParser, *, suppress_defaults: bool = False
) -> None:
    """Attach shared `-c/--config` flag targeting `args.config`."""
    default_none: Any = argparse.SUPPRESS if suppress_defaults else None
    target.add_argument(
        "-c",
        "--config",
        dest="config",
        default=default_none,
        help=t("cli.parser.config"),
    )


def _add_logging_flags(
    target: argparse.ArgumentParser, *, suppress_defaults: bool = False
) -> None:
    """Attach shared logging flags to root or subcommand parsers."""
    default_unset: Any = argparse.SUPPRESS if suppress_defaults else False
    default_none: Any = argparse.SUPPRESS if suppress_defaults else None
    target.add_argument(
        "-d",
        "--debug",
        action="store_true",
        default=default_unset,
        help=t("cli.parser.debug"),
    )
    target.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default=default_none,
        help=t("cli.parser.log_level"),
    )
    target.add_argument(
        "--log-dir",
        default=default_none,
        help=t("cli.parser.log_dir"),
    )
    target.add_argument(
        "--no-log",
        action="store_true",
        default=default_unset,
        help=t("cli.parser.no_log"),
    )


def build_parser() -> argparse.ArgumentParser:
    """Build and return the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="hoyo-assistant",
        description=t("cli.parser.description"),
        epilog=t("cli.parser.epilog"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "-V", "--version", action="version", version=f"%(prog)s {__version__}"
    )
    _add_config_flag(parser, suppress_defaults=False)
    parser.add_argument(
        "-a", "--account", dest="accounts", nargs="+", help=t("cli.parser.account")
    )
    parser.add_argument("--no-qr", action="store_true", help=t("cli.parser.no_qr"))
    _add_logging_flags(parser, suppress_defaults=False)

    common_parent = argparse.ArgumentParser(add_help=False)
    _add_config_flag(common_parent, suppress_defaults=True)
    _add_logging_flags(common_parent, suppress_defaults=True)

    subparsers = parser.add_subparsers(dest="command", help=t("cli.parser.commands"))

    login_parser = subparsers.add_parser(
        "login",
        parents=[common_parent],
        help=t("cli.parser.login"),
        description=t("cli.parser.login"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    login_parser.add_argument(
        "-a",
        "--account",
        dest="login_account",
        help=t("cli.parser.login_account"),
    )
    login_parser.add_argument(
        "--name",
        dest="login_name",
        help=t("cli.parser.login_name"),
    )
    login_parser.add_argument(
        "--scope",
        choices=["all", "bbs", "cloud"],
        default="all",
        help=t("cli.parser.login_scope"),
    )
    login_parser.add_argument(
        "--timeout",
        type=int,
        default=QR_LOGIN_DEFAULT_TIMEOUT,
        help=t("cli.parser.login_timeout"),
    )

    server_parser = subparsers.add_parser(
        "server", parents=[common_parent], help=t("cli.parser.server")
    )
    server_parser.add_argument(
        "--interval",
        type=int,
        default=720,
        help=t("cli.parser.server_interval"),
    )
    server_parser.add_argument(
        "--daemon",
        action="store_true",
        help=t("cli.parser.server_daemon"),
    )

    check_parser = subparsers.add_parser(
        "check", parents=[common_parent], help=t("cli.parser.check")
    )
    check_parser.add_argument(
        "--effective",
        action="store_true",
        help=t("cli.parser.check_effective"),
    )

    fill_config_parser = subparsers.add_parser(
        "format", parents=[common_parent], help=t("cli.parser.format")
    )
    fill_config_parser.add_argument(
        "--no-backup", action="store_true", help=t("cli.parser.format_no_backup")
    )

    subparsers.add_parser("list", parents=[common_parent], help=t("cli.parser.list"))
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command is not None and getattr(args, "no_qr", False):
        parser.error(t("cli.parser.no_qr_run_only"))
    if args.command in ("check", "format", "server", "list") and getattr(
        args, "accounts", None
    ):
        parser.error(t("cli.parser.account_invalid_subcommand", cmd=args.command))
    if (
        args.command == "login"
        and getattr(args, "accounts", None)
        and len(args.accounts) > 1
        and not getattr(args, "login_account", None)
    ):
        parser.error(t("cli.parser.account_invalid_subcommand", cmd="login"))

    print_banner()

    log_dir = getattr(args, "log_dir", None)
    if log_dir:
        from pathlib import Path

        log_dir = str(Path(log_dir).resolve())
    no_log = getattr(args, "no_log", False)

    if args.debug:
        if log_dir or no_log:
            loghelper.setup_logger(
                "DEBUG",
                log_dir=log_dir,
                console_enable=not no_log,
                file_enable=not no_log,
            )
        else:
            loghelper.setup_logger("DEBUG")
    else:
        log_level = getattr(args, "log_level", None) or os.environ.get(
            EnvVar.LOG_LEVEL, "INFO"
        )
        loghelper.setup_logger(
            log_level=log_level,
            log_dir=log_dir,
            console_enable=not no_log,
            file_enable=not no_log,
        )

    is_server_command = args.command == "server"
    raw_config_path = getattr(args, "config", None)
    stripped_config_path = str(raw_config_path).strip() if raw_config_path else ""
    config_path = (
        str(os.path.expanduser(stripped_config_path)) if stripped_config_path else None
    )

    if args.command is None:
        resolved_path, created = setting.ensure_config_initialized(config_path)
        config_path = resolved_path
        if created:
            cli_print(
                t("cli.task.config_initialized", path=resolved_path), style="green"
            )

    if (
        is_server_command
        and config_path is None
        and setting._find_default_config_file() is None
    ):
        resolved_srv_path, created_srv = setting.ensure_config_initialized(None)
        config_path = resolved_srv_path
        if created_srv:
            cli_print(
                t("cli.task.config_initialized", path=resolved_srv_path),
                style="green",
            )

    if args.command not in ("check", "format", "login", "list"):
        try:
            setting.reload_config(config_file=config_path, overrides={})
        except ValueError as e:
            cli_print(t("cli.task.config_error", error=e), style="red")
            sys.exit(1)

    if args.command == "login":
        login_acct = getattr(args, "login_account", None)
        if not login_acct and getattr(args, "accounts", None):
            login_acct = args.accounts[0]
        try:
            asyncio.run(
                login_command(
                    config_path=config_path,
                    account_selector=login_acct,
                    name=getattr(args, "login_name", None),
                    scope=cast(qr_login.QRScope, getattr(args, "scope", "all")),
                    timeout=getattr(args, "timeout", QR_LOGIN_DEFAULT_TIMEOUT),
                )
            )
        except KeyboardInterrupt:
            cli_print(t("qr.cancelled"), style="yellow")
            sys.exit(1)
    elif args.command == "check":
        check_path = config_path or setting._find_default_config_file()
        if (
            getattr(args, "effective", False)
            and check_path
            and os.path.exists(check_path)
        ):
            with suppress(ValueError):
                setting.reload_config(config_file=check_path, overrides={})
        if not validate_config(check_path, getattr(args, "effective", False)):
            sys.exit(1)
    elif args.command == "format":
        format_path = config_path or setting._find_default_config_file()
        fill_config_command(format_path or "", not args.no_backup)
    elif args.command == "list":
        list_path = config_path or setting._find_default_config_file()
        if not list_path or not os.path.exists(list_path):
            cli_print(t("cli.task.config_missing"), style="red")
            sys.exit(1)
        try:
            setting.reload_config(config_file=list_path, overrides={})
        except ValueError as e:
            cli_print(t("cli.task.config_error", error=e), style="red")
            sys.exit(1)
        list_accounts_command(list_path)
    elif is_server_command:
        try:
            cli_print(t("cli.task.server_start"), style="green")
            if hasattr(server, "start_interactive_console"):
                interval_mins = getattr(args, "interval", 720)
                daemon_flag = bool(getattr(args, "daemon", False))
                if interval_mins == 720 and not daemon_flag:
                    cfg = ServerSettings(config_path=config_path)
                else:
                    cfg = ServerSettings(
                        config_path=config_path,
                        _interval=max(1, interval_mins) * 60,
                        daemon=daemon_flag,
                    )
                server.start_interactive_console(cfg)
            else:
                cli_print(t("cli.task.server_no_console"), style="red")
        except Exception as e:
            cli_print(t("cli.task.server_fail", error=e), style="red")
    else:
        allow_qr = False if getattr(args, "no_qr", False) else None
        try:
            rc = asyncio.run(
                run_tasks(
                    config_path=config_path,
                    account_filter=args.accounts,
                    allow_qr_login=allow_qr,
                )
            )
        except KeyboardInterrupt:
            cli_print(t("qr.cancelled"), style="yellow")
            sys.exit(1)
        if rc in (StatusCode.FAILURE.value, StatusCode.PARTIAL_FAILURE.value):
            sys.exit(rc)


if __name__ == "__main__":
    main()
