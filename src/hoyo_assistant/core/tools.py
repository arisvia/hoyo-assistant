import hashlib
import os
import random
import re
import string
import sys
import time
import uuid
from typing import Any, Final

from . import t
from .constants import (
    COOKIE_ORDER,
    DEFAULT_HEADERS,
    MIHOYOBBS_SALT,
    MIHOYOBBS_SALT_PASSPORT,
    MIHOYOBBS_SALT_WEB,
    MIHOYOBBS_SALT_X6,
    MIHOYOBBS_VERSION,
    EnvVar,
)

_TRUE_BOOL_VALUES: Final[frozenset[str]] = frozenset({"true", "1", "on", "yes"})
_FALSE_BOOL_VALUES: Final[frozenset[str]] = frozenset({"false", "0", "off", "no"})
_CI_ENV_VARS: Final[tuple[str, ...]] = (
    "CI",
    "GITHUB_ACTIONS",
    "GITLAB_CI",
    "JENKINS_URL",
    "BUILDKITE",
)

_lifecycle_id: str = ""


def md5(text: str) -> str:
    """
    计算输入文本的 MD5 哈希值。

    :param text: 输入的文本字符串。
    :return: 输入文本的 MD5 哈希值，以十六进制字符串表示。
    """
    _md5 = hashlib.md5()
    _md5.update(text.encode())
    return _md5.hexdigest()


# 随机文本
def random_text(num: int) -> str:
    """
    生成指定长度的随机文本。

    :param num: 随机文本的长度。
    :return: 生成的随机文本。
    """
    return "".join(random.sample(string.ascii_lowercase + string.digits, num))


def timestamp() -> int:
    """
    获取当前时间戳。

    :return: 当前时间戳。
    """
    return int(time.time())


def refresh_lifecycle_id() -> str:
    """刷新本次运行的 lifecycle_id（对应 x-rpc-lifecycle_id）。"""
    global _lifecycle_id
    _lifecycle_id = str(uuid.uuid4())
    return _lifecycle_id


def get_lifecycle_id() -> str:
    """获取本次运行的 lifecycle_id；若尚未初始化则自动生成一个 UUID。"""
    global _lifecycle_id
    if not _lifecycle_id:
        _lifecycle_id = str(uuid.uuid4())
    return _lifecycle_id


def get_ds(web: bool) -> str:
    """
    获取米游社的签名字符串，用于访问米游社API时的签名验证。

    :param web: 是否为网页端请求。如果为 True，则使用手机网页端的 salt；如果为 False，则使用移动端的 salt。
    :return: 返回一个字符串，格式为"时间戳,随机字符串,签名"。
    """
    n = MIHOYOBBS_SALT
    if web:
        n = MIHOYOBBS_SALT_WEB
    i = str(timestamp())
    r = random_text(6)
    c = md5(f"salt={n}&t={i}&r={r}")
    return f"{i},{r},{c}"


def get_ds2(query: str = "", body: str = "") -> str:
    """
    获取米游社的签名字符串，用于访问米游社API时的签名验证。

    :param query: 请求的查询参数
    :param body: 请求的主体内容
    :return: 返回一个字符串，格式为"时间戳,随机字符串,签名"。
    """
    n = MIHOYOBBS_SALT_X6
    i = str(timestamp())
    r = str(random.randint(100001, 200000))
    c = md5(f"salt={n}&t={i}&r={r}&b={body}&q={query}")
    return f"{i},{r},{c}"


def get_ds_passport(body: str = "", query: str = "") -> str:
    """获取通行证 V2 接口所需的 DS 签名字符串。"""
    i = str(timestamp())
    r = random_text(6)
    c = md5(f"salt={MIHOYOBBS_SALT_PASSPORT}&t={i}&r={r}&b={body}&q={query}")
    return f"{i},{r},{c}"


def get_device_id(cookie: str) -> str:
    """
    使用 cookie 通过 uuid v3 生成设备 ID。
    :param cookie: cookie

    :return: 设备 ID。
    """
    return str(uuid.uuid3(uuid.NAMESPACE_URL, cookie))


def get_item(raw_data: dict[str, Any]) -> str:
    """
    获取签到的奖励信息

    :param raw_data: 签到的奖励数据
    :return: 「签奖励名称」x数量
    """
    temp_name = raw_data["name"]
    temp_cnt = raw_data["cnt"]
    return f"「{temp_name}」x{temp_cnt}"


def time_conversion(minute: int) -> str:
    """
    将分钟转换为小时和分钟

    :param minute: 分钟
    :return: 小时和分钟
    """
    h = minute // 60
    s = minute % 60
    return t("system.time_format", h=h, s=s)


def parse_bool_str(value: str | None) -> bool | None:
    """Parse canonical boolean strings; return None when unset or unrecognized."""
    normalized = str(value or "").strip().lower()
    if normalized in _TRUE_BOOL_VALUES:
        return True
    if normalized in _FALSE_BOOL_VALUES:
        return False
    return None


def is_tty(*, require_stdin: bool = False, check_ci: bool = True) -> bool:
    """Return True when attached terminal streams are TTYs (outside CI if checked)."""
    if check_ci:
        for env_name in _CI_ENV_VARS:
            raw = os.getenv(env_name, "").strip()
            if raw and parse_bool_str(raw) is not False:
                return False

    stdout_tty = bool(getattr(getattr(sys, "stdout", None), "isatty", lambda: False)())
    if not stdout_tty:
        return False
    second = (
        getattr(sys, "stdin", None) if require_stdin else getattr(sys, "stderr", None)
    )
    return bool(getattr(second, "isatty", lambda: False)())


def use_rich_output(*, require_stdin: bool = False, check_ci: bool = False) -> bool:
    """Return True when output should emit ANSI colors / Rich markup."""
    mode = os.getenv(EnvVar.CLI_OUTPUT, "auto").strip().lower()
    if mode in {"plain", "text", "simple"}:
        return False
    if mode in {"rich", "pretty"}:
        return True
    parsed = parse_bool_str(mode)
    if parsed is not None:
        return parsed
    return is_tty(require_stdin=require_stdin, check_ci=check_ci)


def parse_cookie(cookie: str) -> dict[str, str]:
    """Parse a cookie header string into a dict (ignoring empty/malformed parts)."""
    result: dict[str, str] = {}
    for segment in re.split(r"[;\r\n]+", cookie or ""):
        text = segment.strip()
        if not text or "=" not in text:
            continue
        key, value = text.split("=", 1)
        key, value = key.strip(), value.strip()
        if key and value:
            result[key] = value
    return result


def format_cookie(
    fields: dict[str, str],
    *,
    canonical_order: tuple[str, ...] = COOKIE_ORDER,
    sep: str = ";",
    trailing_semicolon: bool = True,
) -> str:
    """Format a cookie dict back into a string with optional canonical ordering."""
    if canonical_order:
        ordered = [k for k in canonical_order if fields.get(k)]
        ordered += [k for k in fields if k not in canonical_order and fields[k]]
    else:
        ordered = [k for k, v in fields.items() if v]
    if not ordered:
        return ""
    rendered = sep.join(f"{k}={fields[k]}" for k in ordered)
    return f"{rendered};" if trailing_semicolon else rendered


def tidy_cookie(cookies: str) -> str:
    """Normalize whitespace and drop empty segments while preserving key order."""
    if ";" not in cookies and "\r" not in cookies and "\n" not in cookies:
        return cookies
    parsed = parse_cookie(cookies)
    if not parsed:
        return cookies
    return format_cookie(parsed, canonical_order=(), sep="; ", trailing_semicolon=False)


def resolve_user_agent(custom: str = "") -> str:
    """Resolve the effective User-Agent containing exactly one miHoYoBBS token.

    Empty/unset ``custom`` falls back to the default UA template (which already
    carries the ``miHoYoBBS/{version}`` suffix). A non-empty custom UA gets the
    suffix appended (deduped) so every endpoint speaks the same protocol.

    :param custom: user-provided UA string from the active account's ``user_agent``.
    :return: a UA string containing exactly one ``miHoYoBBS/{version}`` token.
    """
    ua = custom or ""
    if ua == "":
        return DEFAULT_HEADERS["User-Agent"]
    if "miHoYoBBS" in ua:
        i = ua.index("miHoYoBBS")
        if i > 0 and ua[i - 1] == " ":
            i -= 1
        return f"{ua[:i]} miHoYoBBS/{MIHOYOBBS_VERSION}"
    return f"{ua} miHoYoBBS/{MIHOYOBBS_VERSION}"


def get_useragent(useragent: str) -> str:
    """Return a User-Agent string normalized with a single miHoYoBBS suffix."""
    return resolve_user_agent(useragent)
