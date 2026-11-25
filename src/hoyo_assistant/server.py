import asyncio
import sys
import threading
import time
from datetime import datetime, timedelta

from rich.console import Console
from rich.panel import Panel

from .core import log, setting, t, tools
from .core.models import ServerSettings
from .runner import run_accounts

_RICH_OUTPUT = tools.use_rich_output()
console = Console(no_color=not _RICH_OUTPUT, force_terminal=_RICH_OUTPUT)


def start_interactive_console(cfg: ServerSettings | None = None) -> None:
    """Start the interactive server console."""
    if cfg is None:
        cfg = ServerSettings()
    assert cfg is not None

    cfg.running = True
    if not cfg.daemon:
        console.clear()
    console.print(
        Panel(
            f"[bold green]{t('cli.task.server_console_title')}[/bold green]",
            border_style="green",
        )
    )

    console.print(f"[cyan]{t('cli.task.server_console_started')}[/cyan]")
    console.print(f"[cyan]{t('cli.task.server_next_run_immediate')}[/cyan]")

    # Run the first task synchronously in the main thread to avoid log/prompt clashes
    try:
        with cfg.task_lock:
            cfg.last_run = time.time()
            asyncio.run(execute_task(cfg))
    except Exception as e:
        log.error(t("cli.task.server_exec_error", error=str(e)))

    time.sleep(0.2)

    cfg.next_run = time.time() + cfg.interval
    next_dt = datetime.fromtimestamp(cfg.next_run)
    console.print(
        f"[dim]{t('cli.task.server_scheduler_next', next_run=next_dt.strftime('%Y-%m-%d %H:%M:%S'))}[/dim]"
    )

    scheduler_thread = threading.Thread(target=scheduler_loop, args=(cfg,), daemon=True)
    scheduler_thread.start()

    time.sleep(0.1)

    try:
        if cfg.daemon:
            while cfg.running and not cfg.stop_event.is_set():
                try:
                    cfg.stop_event.wait(timeout=1.0)
                except KeyboardInterrupt:
                    console.print(f"\n[yellow]{t('cli.task.server_stopping')}[/yellow]")
                    cfg.running = False
                    cfg.stop_event.set()
                    break
        else:
            while cfg.running:
                try:
                    cmd = (
                        console.input("[bold cyan]hoyo-server>[/bold cyan] ")
                        .strip()
                        .lower()
                    )
                except (EOFError, KeyboardInterrupt):
                    console.print(f"\n[yellow]{t('cli.task.server_stopping')}[/yellow]")
                    cfg.running = False
                    cfg.stop_event.set()
                    break

                if cmd in ["exit", "quit", "stop"]:
                    console.print(f"[yellow]{t('cli.task.server_stopping')}[/yellow]")
                    cfg.running = False
                    cfg.stop_event.set()
                    break
                elif cmd in ["help", "?"]:
                    print_help()
                elif cmd == "run":
                    console.print(f"[green]{t('cli.task.server_force_run')}[/green]")
                    cfg.next_run = 0
                elif cmd == "reload":
                    console.print(f"[green]{t('cli.task.server_reloading')}[/green]")
                    try:
                        with cfg.task_lock:
                            setting.reload_config(
                                config_file=cfg.config_path, use_env=cfg.use_env
                            )
                    except Exception as e:
                        log.error(t("cli.task.config_error", error=e))
                        console.print(
                            f"[red]{t('cli.task.config_error', error=e)}[/red]"
                        )
                elif cmd.startswith("interval "):
                    parts = cmd.split()
                    if len(parts) > 1 and parts[1].isdigit():
                        minutes = int(parts[1])
                        cfg.interval = minutes * 60
                        console.print(
                            f"[green]{t('cli.task.server_interval_set', minutes=cfg.interval // 60, seconds=cfg.interval)}[/green]"
                        )
                    else:
                        console.print(
                            f"[red]{t('cli.task.server_invalid_interval')}[/red]"
                        )
                elif cmd == "status":
                    next_run_dt = (
                        datetime.fromtimestamp(cfg.next_run)
                        if cfg.next_run > 0
                        else datetime.now()
                    )
                    time_left: timedelta | str = next_run_dt - datetime.now()
                    if (
                        isinstance(time_left, timedelta)
                        and time_left.total_seconds() < 0
                    ):
                        time_left = t("cli.task.server_status_running")
                    elif isinstance(time_left, timedelta):
                        time_left = str(time_left).split(".")[0]

                    last_run_str = t("cli.task.server_last_run_never")
                    if cfg.last_run > 0:
                        last_run_str = datetime.fromtimestamp(cfg.last_run).strftime(
                            "%Y-%m-%d %H:%M:%S"
                        )

                    console.print(
                        Panel(
                            t(
                                "cli.task.server_status_body",
                                interval=cfg.interval,
                                last_run=last_run_str,
                                next_run=next_run_dt.strftime("%Y-%m-%d %H:%M:%S"),
                                time_left=time_left,
                            ),
                            title=t("cli.task.server_status_title"),
                        )
                    )
                elif cmd == "":
                    pass
                else:
                    console.print(
                        f"[red]{t('cli.task.server_unknown_command', cmd=cmd)}[/red]"
                    )

    except Exception as e:
        log.error(t("cli.task.server_exec_error", error=str(e)))
    finally:
        cfg.running = False
        cfg.stop_event.set()
        scheduler_thread.join(timeout=5)
        sys.exit(0)


def print_help() -> None:
    console.print(
        Panel(
            t("cli.task.server_help_body"),
            title=t("cli.task.server_help_title"),
        )
    )


def scheduler_loop(cfg: ServerSettings) -> None:
    """Main scheduler loop running in a background thread."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    log.info(t("cli.task.server_scheduler_started", interval=cfg.interval))

    if cfg.next_run == 0:
        cfg.next_run = time.time()

    while cfg.running and not cfg.stop_event.is_set():
        now = time.time()
        if now >= cfg.next_run:
            log.info(t("cli.task.server_scheduler_running"))
            cfg.last_run = now

            try:
                with cfg.task_lock:
                    loop.run_until_complete(execute_task(cfg))
            except Exception as e:
                log.error(t("cli.task.server_exec_error", error=str(e)))

            cfg.next_run = time.time() + cfg.interval
            next_dt = datetime.fromtimestamp(cfg.next_run)
            log.info(
                t(
                    "cli.task.server_scheduler_next",
                    next_run=next_dt.strftime("%Y-%m-%d %H:%M:%S"),
                )
            )

        time.sleep(1)

    loop.close()
    log.info(t("cli.task.server_scheduler_stopped"))


async def execute_task(cfg: ServerSettings) -> None:
    """Execute unified account tasks and dispatch per-target push notifications."""
    start_time = time.time()

    try:
        status_code, _, _ = await run_accounts(
            config_path=cfg.config_path,
            use_env=cfg.use_env,
            send_push=True,
            allow_qr_login=False,
            force_reload=True,
        )
    except Exception as e:
        status_code = 1
        msg = t("cli.task.server_exec_error", error=str(e))
        log.error(msg)

    elapsed = time.time() - start_time
    log.info(t("cli.task.server_task_done", time=elapsed, status=status_code))
