import os
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from . import log, t
from .setting_schema import HoyoConfig, HoyoSettings
from .tools import format_cookie, parse_cookie

config: dict[str, Any] = HoyoConfig().model_dump()
runtime_overrides: dict[str, Any] = {}
_overlay_diffs: list[tuple[tuple[str, ...], Any, Any]] = []
_current_account: dict[str, Any] | None = None

config_path: str | None = None

_SENSITIVE_KEYS = {
    "cookie",
    "stoken",
    "token",
    "password",
    "secret",
    "sendkey",
    "bot_token",
    "api_key",
    "authorization",
    "webhook",
    "key",
}
_SECRET_URL_TARGET_TYPES = {"wecomrobot", "webhook", "cqhttp"}


def set_current_account(account: dict[str, Any] | None) -> None:
    """Bind or clear the active account dict for the current execution scope."""
    global _current_account
    _current_account = account


def get_account() -> dict[str, Any]:
    """Return the active account dict (or sole configured account if unbound)."""
    if _current_account is not None:
        return _current_account
    accounts = config.get("accounts")
    if isinstance(accounts, list) and len(accounts) == 1:
        return dict(accounts[0]) if not isinstance(accounts[0], dict) else accounts[0]
    raise RuntimeError("No active account bound")


def _mask_secret(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    if len(text) <= 8:
        return "***"
    return f"{text[:4]}***{text[-2:]}"


def get_effective_config(redact: bool = True) -> Any:
    """Get current effective runtime config, optionally redacted."""
    current = deepcopy(config)
    if redact:
        return _walk(deepcopy(current))
    return current


def _walk(node: Any, parent_key: str = "") -> Any:
    if isinstance(node, dict):
        result = {}
        node_type = str(node.get("type", "")).strip().lower()
        for key, value in node.items():
            lower_key = str(key).lower()
            is_cloud_token = parent_key == "cloud" and isinstance(value, str)
            is_secret_url = (
                lower_key == "url"
                and isinstance(value, str)
                and (
                    node_type in _SECRET_URL_TARGET_TYPES
                    or "key=" in value.lower()
                    or "token=" in value.lower()
                )
            )
            if (
                is_cloud_token
                or is_secret_url
                or lower_key in _SENSITIVE_KEYS
                or lower_key.endswith("_token")
                or lower_key.endswith("_key")
            ):
                result[key] = _mask_secret(value)
            else:
                result[key] = _walk(value, lower_key)
        return result
    if isinstance(node, list):
        return [_walk(item, parent_key) for item in node]
    return node


def _collect_overlay_diffs(
    base: dict[str, Any],
    overlay: dict[str, Any],
    prefix: tuple[str, ...] = (),
) -> list[tuple[tuple[str, ...], Any, Any]]:
    """Record leaf paths where runtime env/overrides diverge from the file config."""
    diffs: list[tuple[tuple[str, ...], Any, Any]] = []
    all_keys = list(dict.fromkeys([*base.keys(), *overlay.keys()]))
    for key in all_keys:
        path_key = (*prefix, str(key))
        in_base = key in base
        in_overlay = key in overlay
        base_val = base.get(key)
        overlay_val = overlay.get(key)
        if (
            in_base
            and in_overlay
            and isinstance(base_val, dict)
            and isinstance(overlay_val, dict)
        ):
            diffs.extend(_collect_overlay_diffs(base_val, overlay_val, path_key))
        elif not in_base or not in_overlay or base_val != overlay_val:
            diffs.append(
                (
                    path_key,
                    deepcopy(base_val) if in_base else _MISSING,
                    deepcopy(overlay_val) if in_overlay else _MISSING,
                )
            )
    return diffs


_MISSING = object()


def _restore_overlay_diffs(data: dict[str, Any]) -> dict[str, Any]:
    """Revert unchanged env/override values back to file-backed values before saving."""
    if not _overlay_diffs:
        return data
    restored = deepcopy(data)
    for key_path, file_val, runtime_val in _overlay_diffs:
        cursor: Any = restored
        for part in key_path[:-1]:
            if not isinstance(cursor, dict) or part not in cursor:
                cursor = None
                break
            cursor = cursor[part]
        if not isinstance(cursor, dict):
            continue
        leaf = key_path[-1]
        current_val = cursor.get(leaf, _MISSING)
        if current_val == runtime_val:
            if file_val is _MISSING:
                cursor.pop(leaf, None)
            else:
                cursor[leaf] = deepcopy(file_val)
    return restored


def _deep_merge_dict(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge_dict(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def load_config(
    config_file: str | None = None,
    overrides: dict[str, Any] | None = None,
    use_env: bool = True,
) -> dict[str, Any]:
    """Load configuration from file or environment."""
    global config, config_path, runtime_overrides, _current_account

    _current_account = None
    _overlay_diffs.clear()

    if overrides is not None:
        runtime_overrides = deepcopy(overrides)

    target_file = config_file or config_path
    if target_file:
        target_file = str(os.path.expanduser(target_file))
    if not target_file:
        target_file = _find_default_config_file()

    file_data: dict[str, Any] = {}
    if target_file and os.path.exists(target_file):
        try:
            log.info(t("config.loading", path=target_file))
            with open(target_file, encoding="utf-8") as f:
                loaded = yaml.safe_load(f)
            if loaded is not None and not isinstance(loaded, dict):
                raise ValueError("Root config must be a mapping")
            file_data = loaded or {}

            config_path = target_file
        except Exception as e:
            log.error(t("config.load_fail", path=target_file, error=e))
            raise ValueError(f"Failed to load config file {target_file}: {e}") from e
    else:
        if target_file:
            log.warning(t("config.not_found", path=target_file))
        else:
            log.debug(t("config.not_found_generic"))

    try:
        # Always validate file_data strictly first so typos / legacy v2 keys are
        # caught even when HoyoSettings applies extra="ignore" for runtime env vars.
        file_model = HoyoConfig.model_validate(file_data)
        file_dump = file_model.model_dump()

        settings: HoyoConfig = HoyoSettings(**file_data) if use_env else file_model
        new_config = settings.model_dump()

        if runtime_overrides:
            new_config = _deep_merge_dict(new_config, runtime_overrides)

        _overlay_diffs.extend(_collect_overlay_diffs(file_dump, new_config))

        config.clear()
        config.update(new_config)

    except Exception as e:
        log.error(t("config.validation_fail", error=e))
        raise ValueError(f"Config validation failed: {e}") from e

    return config


def reload_config(
    config_file: str | None = None,
    overrides: dict[str, Any] | None = None,
    use_env: bool = True,
) -> None:
    """Reload configuration."""
    load_config(config_file=config_file, overrides=overrides, use_env=use_env)


async def save_config() -> None:
    """Save current config to file (async)."""
    if not config_path:
        log.debug(t("config.save_skip"))
        return

    try:
        import asyncio

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, save_config_sync, None, None)
        log.info(t("config.saved"))
    except Exception as e:
        log.error(t("config.save_fail", error=e))


_ACCOUNT_KEY_ORDER: tuple[str, ...] = (
    "name",
    "enable",
    "region",
    "push",
    "cookie",
    "lang",
    "user_agent",
    "device",
    "bbs",
    "games",
    "black_list",
    "custom_games",
    "cloud",
)


class _IndentDumper(yaml.SafeDumper):
    """SafeDumper that indents block sequence dashes under their parent mapping key."""

    def increase_indent(self, flow: bool = False, indentless: bool = False) -> Any:
        return super().increase_indent(flow=flow, indentless=False)


def _strip_none_push_values(data: dict[str, Any]) -> dict[str, Any]:
    """Remove None-valued entries under push/targets to keep YAML clean."""
    result = deepcopy(data)
    push = result.get("push")
    if isinstance(push, dict):
        targets = push.get("targets")
        if isinstance(targets, dict):
            cleaned_targets = {k: v for k, v in targets.items() if v is not None}
            if cleaned_targets:
                push["targets"] = cleaned_targets
            else:
                push.pop("targets", None)
        result["push"] = {k: v for k, v in push.items() if v is not None}
    return result


def _prepare_save_data(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize push values and account field ordering prior to YAML serialization."""
    result = _strip_none_push_values(data)
    accounts = result.get("accounts")
    if isinstance(accounts, list):
        reordered: list[Any] = []
        for acct in accounts:
            if isinstance(acct, dict):
                ordered = {k: acct[k] for k in _ACCOUNT_KEY_ORDER if k in acct}
                for k, v in acct.items():
                    if k not in ordered:
                        ordered[k] = v
                reordered.append(ordered)
            else:
                reordered.append(acct)
        result["accounts"] = reordered
    return result


def dump_yaml(data: dict[str, Any]) -> str:
    """Serialize config dict to clean YAML with indented lists and wide lines."""
    return yaml.dump(
        data,
        Dumper=_IndentDumper,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
        width=4096,
    )


def save_config_sync(
    filepath: str | None = None, data: dict[str, Any] | None = None
) -> None:
    """Save config to file (synchronous), keeping YAML minimal via exclude_defaults."""
    target = filepath or config_path
    content = data if data is not None else _restore_overlay_diffs(config)

    if not target:
        log.debug(t("config.save_skip"))
        return

    try:
        settings = HoyoConfig.model_validate(content)
        save_data = _prepare_save_data(settings.model_dump(exclude_defaults=True))
        if not save_data:
            save_data = {"enable": settings.enable, "accounts": []}

        parent_dir = os.path.dirname(target)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)
        Path(target).write_text(dump_yaml(save_data), encoding="utf-8")
    except Exception as e:
        log.error(t("config.save_fail_target", path=target, error=e))


async def clear_cookie() -> None:
    """Clear cookie in active account and save."""
    acct = get_account()
    acct["cookie"] = ""
    await save_config()


async def clear_stoken() -> None:
    """Remove stoken from active CN account's cookie string and save."""
    acct = get_account()
    raw = str(acct.get("cookie", ""))
    if not raw:
        return
    fields = parse_cookie(raw)
    if "stoken" not in fields:
        return
    fields.pop("stoken", None)
    new_cookie = format_cookie(fields)
    if new_cookie != raw:
        acct["cookie"] = new_cookie
        await save_config()


async def clear_cloud_token(game_key: str) -> None:
    """Clear cloud game token in active account and save."""
    acct = get_account()
    cloud = acct.get("cloud")
    if isinstance(cloud, dict) and game_key in cloud:
        cloud[game_key] = ""
        await save_config()


def get_default_config_path() -> str:
    """Return default config.yaml save path (next to frozen exe, else cwd)."""
    if getattr(sys, "frozen", False):
        return str(Path(sys.executable).resolve().parent / "config.yaml")
    return str(Path.cwd() / "config.yaml")


def ensure_config_initialized(config_file: str | None = None) -> tuple[str, bool]:
    """Ensure a config file exists on disk, bootstrapping a minimal file if absent."""
    global config_path, _current_account

    if config_file:
        target = str(os.path.expanduser(config_file))
    else:
        target = _find_default_config_file() or get_default_config_path()

    if os.path.exists(target):
        return target, False

    starter: dict[str, Any] = {"enable": True, "accounts": []}
    validated = HoyoConfig.model_validate(starter)
    parent_dir = os.path.dirname(target)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)
    Path(target).write_text(dump_yaml(starter), encoding="utf-8")

    _current_account = None
    _overlay_diffs.clear()
    config_path = target
    dumped = validated.model_dump()
    config.clear()
    config.update(dumped)

    log.info(t("config.initialized", path=target))
    return target, True


def _find_default_config_file() -> str | None:
    """Find default config file next to frozen executable, in cwd, or at repo root."""
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        candidates.extend([exe_dir / "config.yaml", exe_dir / "config.yml"])
        candidates.extend([Path.cwd() / "config.yaml", Path.cwd() / "config.yml"])
    else:
        candidates.extend([Path.cwd() / "config.yaml", Path.cwd() / "config.yml"])
        project_root = Path(__file__).resolve().parents[3]
        if (project_root / "pyproject.toml").is_file():
            candidates.extend(
                [project_root / "config.yaml", project_root / "config.yml"]
            )

    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if resolved.is_file():
            return str(candidate)

    return None


DEFAULT_CONFIG = HoyoConfig().model_dump()


def validate_config_file(filepath: str) -> tuple[bool, list[str]]:
    """Validate a config file strictly against the v3 schema (isolated from shell env)."""
    if not os.path.exists(filepath):
        return False, ["File not found"]

    try:
        with open(filepath, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        HoyoConfig.model_validate(data)
        return True, []
    except Exception as e:
        return False, [str(e)]


def auto_fill_config_file(filepath: str, backup: bool = True) -> tuple[bool, str]:
    """Validate, prune cookies, and format a local config file."""
    if not os.path.exists(filepath):
        return False, t("config.file_not_found", path=filepath)

    if not os.path.isfile(filepath):
        return False, t("config.path_not_file", path=filepath)

    try:
        original_text = Path(filepath).read_text(encoding="utf-8")
        original_data = yaml.safe_load(original_text) or {}

        settings = HoyoConfig.model_validate(original_data)
        filled_data = _prepare_save_data(settings.model_dump(exclude_defaults=True))
        rendered = dump_yaml(filled_data)

        if (
            original_text.replace("\r\n", "\n").strip()
            == rendered.replace("\r\n", "\n").strip()
        ):
            return True, t("config.already_complete", path=filepath)

        if backup:
            backup_path = f"{filepath}.bak"
            Path(backup_path).write_text(original_text, encoding="utf-8")
            log.info(t("config.backup_created", path=backup_path))

        Path(filepath).write_text(rendered, encoding="utf-8")

        log.info(t("config.auto_filled", path=filepath))
        return True, t("config.auto_filled", path=filepath)

    except Exception as e:
        return False, t("config.auto_fill_fail", error=str(e))
