"""
Core module containing shared utilities, configuration, and networking logic.
"""

import os

from .constants import EnvVar, StatusCode
from .error import CaptchaError, CookieError, StokenError
from .i18n import t
from .loghelper import log
from .request import http
from .setting import config


def is_push_enabled() -> bool:
    """Check if push notifications are enabled.

    Priority: env var HOYO_ASSISTANT_PUSH__ENABLE > config push.enable
    """
    env_enable = str(os.getenv(EnvVar.PUSH_ENABLE, "")).strip().lower()
    if env_enable in {"true", "1", "on", "yes"}:
        return True
    if env_enable in {"false", "0", "off", "no"}:
        return False
    push_cfg = config.get("push")
    if isinstance(push_cfg, dict):
        return bool(push_cfg.get("enable"))
    return False


__all__ = [
    "StatusCode",
    "CookieError",
    "CaptchaError",
    "StokenError",
    "t",
    "log",
    "http",
    "config",
    "is_push_enabled",
]
