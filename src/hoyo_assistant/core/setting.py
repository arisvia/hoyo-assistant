import os
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from . import log, t
from .setting_schema import HoyoConfig, HoyoSettings

config: dict[str, Any] = HoyoConfig().model_dump()
config_raw: dict[str, Any] = deepcopy(config)
runtime_overrides: dict[str, Any] = {}

config_path: str | None = None
path: str | None = None  # Directory of config file

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
        for key, value in node.items():
            lower_key = str(key).lower()
            is_cloud_token = parent_key == "cloud" and isinstance(value, str)
            if (
                is_cloud_token
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
    global config, config_path, path, runtime_overrides

    if overrides is not None:
        runtime_overrides = deepcopy(overrides)

    # 1. Determine which file to load
    target_file = config_file or config_path

    if not target_file:
        target_file = _find_default_config_file()

    # 2. Load from file if found
    file_data: dict[str, Any] = {}
    if target_file and os.path.exists(target_file):
        try:
            log.info(t("config.loading", path=target_file))
            with open(target_file, encoding="utf-8") as f:
                file_data = yaml.safe_load(f) or {}

            config_path = target_file
            path = os.path.dirname(target_file)
        except Exception as e:
            log.error(t("config.load_fail", path=target_file, error=e))
            raise ValueError(f"Failed to load config file {target_file}: {e}") from e
    else:
        if target_file:
            log.warning(t("config.not_found", path=target_file))
        else:
            log.debug(t("config.not_found_generic"))

    try:
        settings: HoyoConfig
        if use_env:
            settings = HoyoSettings(**file_data)
        else:
            settings = HoyoConfig.model_validate(file_data)
        new_config = settings.model_dump()

        if runtime_overrides:
            new_config = _deep_merge_dict(new_config, runtime_overrides)

        config.clear()
        config.update(new_config)

        config_raw.clear()
        config_raw.update(new_config)

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


def _strip_none_push_values(data: dict[str, Any]) -> dict[str, Any]:
    """Remove None-valued push channels from config dict to keep YAML clean."""
    result = deepcopy(data)
    push = result.get("push")
    if isinstance(push, dict):
        channels = push.get("channels")
        if isinstance(channels, dict):
            cleaned_channels = {k: v for k, v in channels.items() if v is not None}
            if cleaned_channels:
                push["channels"] = cleaned_channels
            else:
                push.pop("channels", None)
        result["push"] = {k: v for k, v in push.items() if v is not None}
    return result


def save_config_sync(
    filepath: str | None = None, data: dict[str, Any] | None = None
) -> None:
    """Save config to file (synchronous).

    Uses exclude_defaults=True to keep the YAML clean — only writes fields
    that differ from schema defaults, matching the behavior of format/auto_fill.
    """
    target = filepath or config_path
    content = data or config

    if not target:
        log.debug(t("config.save_skip"))
        return

    try:
        settings = HoyoConfig.model_validate(content)
        save_data = settings.model_dump(exclude_defaults=True)
        save_data = _strip_none_push_values(save_data)

        with open(target, "w", encoding="utf-8") as f:
            yaml.dump(
                save_data,
                f,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            )
    except Exception as e:
        log.error(t("config.save_fail_target", path=target, error=e))


async def clear_cookie() -> None:
    """Clear CN cookie in config and save."""
    if "cn" in config:
        config["cn"]["cookie"] = ""
        await save_config()


async def clear_stoken() -> None:
    """Clear CN stoken in config and save."""
    if "cn" in config:
        config["cn"]["stoken"] = ""
        await save_config()


def _find_default_config_file() -> str | None:
    """Find default config file in standard locations."""
    candidates = [
        os.path.join(os.getcwd(), "config", "config.yaml"),
        os.path.join(os.getcwd(), "config.yaml"),
    ]

    project_root = Path(__file__).resolve().parents[3]
    candidates.append(str(project_root / "config" / "config.yaml"))

    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate

    return None


DEFAULT_CONFIG = HoyoConfig().model_dump()


def validate_config_file(filepath: str) -> tuple[bool, list[str]]:
    """Validate a config file strictly against the v2 schema (isolated from shell env)."""
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
    """Validate and format a local config file (without leaking shell env secrets)."""
    if not os.path.exists(filepath):
        return False, t("config.file_not_found", path=filepath)

    if not os.path.isfile(filepath):
        return False, t("config.path_not_file", path=filepath)

    try:
        with open(filepath, encoding="utf-8") as f:
            original_data = yaml.safe_load(f) or {}

        # Use HoyoConfig so shell environment variables are never persisted to disk
        settings = HoyoConfig.model_validate(original_data)
        filled_data = _strip_none_push_values(
            settings.model_dump(exclude_defaults=True)
        )

        if original_data == filled_data:
            return True, t("config.already_complete", path=filepath)

        if backup:
            backup_path = f"{filepath}.bak"
            with open(backup_path, "w", encoding="utf-8") as f:
                yaml.dump(
                    original_data,
                    f,
                    default_flow_style=False,
                    allow_unicode=True,
                    sort_keys=False,
                )
            log.info(t("config.backup_created", path=backup_path))

        with open(filepath, "w", encoding="utf-8") as f:
            yaml.dump(
                filled_data,
                f,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            )

        log.info(t("config.auto_filled", path=filepath))
        return True, t("config.auto_filled", path=filepath)

    except Exception as e:
        return False, t("config.auto_fill_fail", error=str(e))
