import json
import re
from copy import deepcopy
from typing import cast

from . import CookieError, StokenError, config, http, log, setting, t, tools
from .constants import (
    API_BBS_GET_COOKIE_TOKEN,
    API_PASSPORT_EXCHANGE,
    COOKIE_ERROR_SENTINEL,
    DEFAULT_HEADERS,
    MIHOYOBBS_APP_ID,
    MIHOYOBBS_APP_UA,
    MIHOYOBBS_CLIENT_TYPE,
    MIHOYOBBS_PASSPORT_VERSION,
    MIHOYOBBS_SYS_VERSION,
    MIHOYOBBS_VERSION,
    RetCode,
)

headers = deepcopy(DEFAULT_HEADERS)
headers.pop("DS")
headers.pop("Origin")
headers.pop("Referer")

_COOKIE_ORDER = (
    "ltoken",
    "ltuid",
    "account_id",
    "cookie_token",
    "login_ticket",
    "ltoken_v2",
    "ltuid_v2",
    "ltmid_v2",
    "cookie_token_v2",
    "account_id_v2",
    "account_mid_v2",
)

# When V2 fields exist, mirror them onto the V1 alias keys (matching MiYoUShe WebView injection)
_V2_TO_V1_ALIASES = (
    ("ltoken_v2", "ltoken"),
    ("ltuid_v2", "ltuid"),
    ("account_id_v2", "account_id"),
    ("cookie_token_v2", "cookie_token"),
)


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


def format_cookie(fields: dict[str, str]) -> str:
    """Format a cookie dict back into a canonical cookie string."""
    ordered = [k for k in _COOKIE_ORDER if fields.get(k)]
    ordered += [k for k in fields if k not in _COOKIE_ORDER and fields[k]]
    if not ordered:
        return ""
    return ";".join(f"{k}={fields[k]}" for k in ordered) + ";"


def sync_cookie_aliases(fields: dict[str, str]) -> bool:
    """Mirror V2 cookie tokens onto their legacy V1 alias keys.

    Returns True if any field was modified.
    """
    changed = False
    for v2_key, v1_key in _V2_TO_V1_ALIASES:
        value = fields.get(v2_key)
        if value and fields.get(v1_key) != value:
            fields[v1_key] = value
            changed = True
    return changed


async def login() -> None:
    cn_cfg = config["cn"]
    if not cn_cfg["cookie"]:
        await setting.clear_cookie()
        raise CookieError(t("account.missing_cookie"))

    if cn_cfg["stoken"] == "":
        raise StokenError(t("account.missing_stoken"))
    uid = get_uid()
    if uid is None:
        await setting.clear_cookie()
        raise CookieError(t("account.missing_uid"))
    cn_cfg["stuid"] = uid
    if require_mid():
        extracted_mid = get_mid()
        if extracted_mid:
            cn_cfg["mid"] = extracted_mid
    log.info(t("account.login_ok"))
    log.info(t("account.saving_config"))
    await setting.save_config()

    # V2 stoken: fill missing ltoken_v2 / cookie_token_v2 via Passport V2 exchange
    if require_cookie_token() and cn_cfg.get("mid"):
        await build_account_cookie()

    # V1 stoken: verify / fetch cookie_token via legacy endpoint
    if require_stoken():
        log.info(t("account.fetching_stoken"))
        header = deepcopy(headers)
        header["cookie"] = get_stoken_cookie()
        req = await http.get(
            API_BBS_GET_COOKIE_TOKEN,
            params={"uid": uid, "stoken": cn_cfg["stoken"]},
            headers=header,
            use_cache=False,
        )
        data = await req.json()
        if data.get("retcode", -1) != RetCode.OK:
            await setting.clear_stoken()
            raise StokenError(t("account.stoken_fetch_fail"))
        log.info(t("account.stoken_ok"))


def get_mid() -> str | None:
    mid = re.search(
        r"(account_mid_v2|ltmid_v2|mid)=(.*?)(?:;|$)",
        str(config["cn"]["cookie"]),
    )
    return mid.group(2) if mid else None


def get_uid() -> str | None:
    uid: str | None = None
    uid_match = re.search(
        r"(account_id|ltuid|login_uid|ltuid_v2|account_id_v2)=(\d+)",
        config["cn"]["cookie"],
    )
    if uid_match is None:
        return uid
    uid = uid_match.group(2)
    return uid


async def get_cookie_token_by_stoken() -> str:
    cn_cfg = config["cn"]
    if cn_cfg["stoken"] == "" and cn_cfg["stuid"] == "":
        log.error(t("account.stoken_suid_empty"))
        await setting.clear_cookie()
        raise CookieError(t("account.cookie_invalid"))
    header = deepcopy(headers)
    header["cookie"] = get_stoken_cookie()
    response = await http.get(
        url=API_BBS_GET_COOKIE_TOKEN, headers=header, use_cache=False
    )
    data = await response.json()
    if data.get("retcode", -1) != RetCode.OK:
        log.error(t("account.stoken_fetch_fail"))
        await setting.clear_stoken()
        raise StokenError(t("account.stoken_error"))
    return cast(str, data["data"]["cookie_token"])


async def exchange_token_by_stoken(target: int) -> str:
    """Exchange SToken for LToken (target=2) or CookieToken (target=4) via Passport V2 API."""
    cn_cfg = config["cn"]
    stoken = str(cn_cfg.get("stoken", ""))
    mid = str(cn_cfg.get("mid", ""))
    if not stoken:
        raise StokenError(t("account.missing_stoken"))
    if not mid:
        log.error(t("account.mid_required"))
        raise CookieError(t("account.cookie_invalid"))

    body = json.dumps(
        {
            "dst_token_type": target,
            "src_token": {"token": stoken, "token_type": 1},
            "mid": mid,
        },
        separators=(",", ":"),
    )
    device = config.get("client", {}).get("device", {})
    req_headers: dict[str, str] = {
        "accept": "application/json",
        "content-type": "application/json",
        "DS": tools.get_ds_passport(body=body),
        "x-rpc-app_id": MIHOYOBBS_APP_ID,
        "x-rpc-client_type": MIHOYOBBS_CLIENT_TYPE,
        "x-rpc-app_version": MIHOYOBBS_VERSION,
        "x-rpc-game_biz": "bbs_cn",
        "x-rpc-sys_version": MIHOYOBBS_SYS_VERSION,
        "x-rpc-sdk_version": MIHOYOBBS_PASSPORT_VERSION,
        "x-rpc-account_version": MIHOYOBBS_PASSPORT_VERSION,
        "x-rpc-lifecycle_id": tools.get_lifecycle_id(),
        "x-rpc-device_id": str(device.get("id", "")),
        "x-rpc-device_name": str(device.get("name", "")),
        "x-rpc-device_model": str(device.get("model", "")),
        "User-Agent": MIHOYOBBS_APP_UA,
    }
    if device.get("fp"):
        req_headers["x-rpc-device_fp"] = str(device["fp"])

    response = await http.post(
        url=API_PASSPORT_EXCHANGE,
        headers=req_headers,
        data=body.encode("utf-8"),
    )
    data = await response.json()
    if data.get("retcode", -1) != RetCode.OK:
        retcode = data.get("retcode")
        message = data.get("message", "")
        log.error(t("account.exchange_fail", retcode=retcode, message=message))
        if retcode in (RetCode.UNAUTHORIZED, RetCode.STOKEN_EXPIRED_V2):
            await setting.clear_stoken()
            raise StokenError(t("account.stoken_invalid"))
        raise CookieError(t("account.exchange_fail", retcode=retcode, message=message))

    token_obj = (data.get("data") or {}).get("token") or {}
    value = token_obj.get("token")
    if not value:
        log.error(t("account.exchange_missing_token"))
        raise CookieError(t("account.exchange_missing_token"))
    return cast(str, value)


async def get_ltoken_by_stoken_v2() -> str:
    """Exchange SToken for LToken (dst_token_type=2)."""
    return await exchange_token_by_stoken(2)


async def get_cookie_token_by_stoken_v2() -> str:
    """Exchange SToken for CookieToken (dst_token_type=4)."""
    return await exchange_token_by_stoken(4)


async def build_account_cookie() -> str:
    """Build a complete BBS cookie, exchanging missing V2 tokens and syncing V1 aliases."""
    cn_cfg = config.get("cn", {})
    base = str(cn_cfg.get("cookie", ""))
    if not base or base == COOKIE_ERROR_SENTINEL:
        raise CookieError(t("account.missing_cookie"))

    fields = parse_cookie(base)
    stuid = str(cn_cfg.get("stuid", "")) or (get_uid() or "")
    mid = str(cn_cfg.get("mid", "")) or (get_mid() or "")
    changed = False

    if not fields.get("ltoken_v2") and not fields.get("ltoken"):
        try:
            ltoken = await get_ltoken_by_stoken_v2()
        except CookieError as e:
            log.warning(t("account.ltoken_fill_fail", error=e))
        else:
            fields["ltoken_v2"] = ltoken
            if stuid:
                fields["ltuid_v2"] = stuid
            if mid:
                fields["ltmid_v2"] = mid
            changed = True

    if not fields.get("cookie_token_v2") and not fields.get("cookie_token"):
        log.info(t("account.fetching_cookie_token"))
        try:
            cookie_token = await get_cookie_token_by_stoken_v2()
        except CookieError as e:
            log.warning(t("account.cookie_token_fill_fail", error=e))
        else:
            fields["cookie_token_v2"] = cookie_token
            if stuid:
                fields["account_id_v2"] = stuid
            if mid:
                fields["account_mid_v2"] = mid
            log.info(t("account.cookie_token_ok"))
            changed = True

    if changed:
        if stuid:
            fields.setdefault("ltuid_v2", stuid)
            fields.setdefault("account_id_v2", stuid)
        if mid:
            fields.setdefault("ltmid_v2", mid)
            fields.setdefault("account_mid_v2", mid)

    aliases_changed = sync_cookie_aliases(fields)
    formatted = format_cookie(fields)
    if changed or aliases_changed:
        config["cn"]["cookie"] = formatted
        await setting.save_config()

    return formatted


async def update_cookie_token() -> bool:
    """Refresh CookieToken in place using V2 Passport exchange when mid is available."""
    log.info(t("account.cookie_refresh_start"))
    cn_cfg = config["cn"]
    if str(cn_cfg.get("stoken", "")) == "":
        log.warning(t("account.no_stoken_cant_refresh"))
        return False

    current = str(cn_cfg.get("cookie", ""))
    fields = parse_cookie(current)
    use_v2 = require_mid() and bool(cn_cfg.get("mid"))

    if use_v2:
        new_token = await get_cookie_token_by_stoken_v2()
        fields["cookie_token_v2"] = new_token
        if cn_cfg.get("stuid"):
            fields.setdefault("account_id_v2", str(cn_cfg["stuid"]))
        if cn_cfg.get("mid"):
            fields.setdefault("account_mid_v2", str(cn_cfg["mid"]))
        sync_cookie_aliases(fields)
    else:
        new_token = await get_cookie_token_by_stoken()
        key = "cookie_token_v2" if "cookie_token_v2" in fields else "cookie_token"
        fields[key] = new_token
        sync_cookie_aliases(fields)

    cn_cfg["cookie"] = format_cookie(fields)
    log.info(t("account.cookie_token_refresh_ok"))
    await setting.save_config()
    return True


def require_mid() -> bool:
    """判断是否需要mid"""
    return str(config["cn"]["stoken"]).startswith("v2_")


def get_stoken_cookie() -> str:
    """获取带stoken的cookie"""
    cn_cfg = config["cn"]
    cookie = f"stuid={cn_cfg['stuid']};stoken={cn_cfg['stoken']}"
    if require_mid():
        if cn_cfg["mid"]:
            cookie += f";mid={cn_cfg['mid']}"
        else:
            log.error(t("account.mid_required"))
            raise CookieError(t("account.cookie_invalid"))
    return cookie


def require_cookie_token() -> bool:
    """判断是否需要 cookie_token"""
    return str(config["cn"]["stoken"]).startswith("v2_")


def require_stoken() -> bool:
    """判断是否需要 stoken"""
    return str(config["cn"]["stoken"]).startswith("v1_")
