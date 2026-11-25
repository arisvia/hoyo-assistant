"""
Core module containing shared utilities, configuration, and networking logic.
"""

import os

from .constants import EnvVar, StatusCode
from .error import CookieError, StokenError
from .i18n import t
from .loghelper import log
from .request import http
from .setting import config
from .tools import parse_bool_str


def is_push_enabled() -> bool:
    """Check if push notifications are enabled.

    Priority: env var HOYO_ASSISTANT_PUSH__ENABLE > config push.enable
    """
    env_bool = parse_bool_str(os.getenv(EnvVar.PUSH_ENABLE))
    if env_bool is not None:
        return env_bool
    push_cfg = config.get("push")
    if isinstance(push_cfg, dict):
        return bool(push_cfg.get("enable"))
    return False


__all__ = [
    "StatusCode",
    "CookieError",
    "StokenError",
    "t",
    "log",
    "http",
    "config",
    "is_push_enabled",
]
