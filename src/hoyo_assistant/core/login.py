import json
from copy import deepcopy
from typing import cast

from . import CookieError, StokenError, http, log, setting, t, tools
from .constants import (
    API_BBS_GET_COOKIE_TOKEN,
    API_PASSPORT_EXCHANGE,
    COOKIE_MID_KEYS,
    COOKIE_UID_KEYS,
    COOKIE_V2_TO_V1_ALIASES,
    DEFAULT_HEADERS,
    MIHOYOBBS_APP_ID,
    MIHOYOBBS_APP_UA,
    MIHOYOBBS_CLIENT_TYPE,
    MIHOYOBBS_PASSPORT_VERSION,
    MIHOYOBBS_SYS_VERSION,
    MIHOYOBBS_VERSION,
    RetCode,
)
from .setting_schema import clean_cookie
from .tools import format_cookie, parse_cookie

headers = deepcopy(DEFAULT_HEADERS)
headers.pop("DS")
headers.pop("Origin")
headers.pop("Referer")

_UID_KEYS = COOKIE_UID_KEYS
_MID_KEYS = COOKIE_MID_KEYS
_STOKEN_KEYS = frozenset({"stoken", "stuid"})

# When V2 fields exist, mirror them onto the V1 alias keys (in-memory HTTP headers only)
_V2_TO_V1_ALIASES = COOKIE_V2_TO_V1_ALIASES


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


def _get_cookie_fields() -> dict[str, str]:
    """Parse the active account's cookie string into key/value fields."""
    return parse_cookie(str(setting.get_account().get("cookie", "")))


async def login() -> None:
    cn_cfg = setting.get_account()
    raw_cookie = str(cn_cfg.get("cookie", ""))
    if not raw_cookie.strip():
        await setting.clear_cookie()
        raise CookieError(t("account.missing_cookie"))

    stoken = get_stoken()
    if not stoken:
        raise StokenError(t("account.missing_stoken"))
    uid = get_uid()
    if uid is None:
        await setting.clear_cookie()
        raise CookieError(t("account.missing_uid"))

    fields = parse_cookie(raw_cookie)
    fields.setdefault("stuid", uid)
    if require_mid():
        extracted_mid = get_mid()
        if extracted_mid:
            fields.setdefault("mid", extracted_mid)
    cn_cfg["cookie"] = clean_cookie(format_cookie(fields), region="cn")
    log.info(t("account.login_ok"))
    log.info(t("account.saving_config"))
    await setting.save_config()

    # V2 stoken: fill missing ltoken_v2 / cookie_token_v2 via Passport V2 exchange
    if require_cookie_token() and get_mid():
        await build_account_cookie()

    # V1 stoken: verify / fetch cookie_token via legacy endpoint
    if require_stoken():
        log.info(t("account.fetching_stoken"))
        header = deepcopy(headers)
        header["cookie"] = get_stoken_cookie()
        req = await http.get(
            API_BBS_GET_COOKIE_TOKEN,
            params={"uid": uid, "stoken": stoken},
            headers=header,
            use_cache=False,
        )
        data = await req.json()
        if data.get("retcode", -1) != RetCode.OK:
            await setting.clear_stoken()
            raise StokenError(t("account.stoken_fetch_fail"))
        log.info(t("account.stoken_ok"))


def get_stoken() -> str:
    """Extract stoken from the active account's cookie string."""
    return _get_cookie_fields().get("stoken", "")


def get_mid() -> str | None:
    """Extract mid from the active account's cookie string."""
    fields = _get_cookie_fields()
    for key in _MID_KEYS:
        val = fields.get(key)
        if val:
            return val
    return None


def extract_uid_from_cookie(cookie: str) -> str | None:
    """Extract numeric UID from a raw cookie string."""
    fields = parse_cookie(cookie)
    for key in _UID_KEYS:
        val = fields.get(key)
        if val and val.isdigit():
            return val
    return None


def get_uid() -> str | None:
    """Extract numeric UID from the active account's cookie string."""
    return extract_uid_from_cookie(str(setting.get_account().get("cookie", "")))


def get_web_cookie() -> str:
    """Return active account cookie for Web/Luna requests.

    Strips high-privilege App stoken/stuid, backfills V2 id/mid pairs when
    available, and mirrors V2->V1 aliases in memory without modifying config.
    """
    raw = str(setting.get_account().get("cookie", ""))
    fields = parse_cookie(raw)
    if not fields:
        return raw
    web_fields = {k: v for k, v in fields.items() if k not in _STOKEN_KEYS}
    uid = get_uid()
    if uid:
        if web_fields.get("ltoken_v2"):
            web_fields.setdefault("ltuid_v2", uid)
        if web_fields.get("cookie_token_v2"):
            web_fields.setdefault("account_id_v2", uid)
    mid = get_mid()
    if mid:
        if web_fields.get("ltoken_v2"):
            web_fields.setdefault("ltmid_v2", mid)
        if web_fields.get("cookie_token_v2"):
            web_fields.setdefault("account_mid_v2", mid)
    sync_cookie_aliases(web_fields)
    return format_cookie(web_fields)


async def get_cookie_token_by_stoken() -> str:
    if not get_stoken() and not get_uid():
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
    cn_cfg = setting.get_account()
    stoken = get_stoken()
    mid = get_mid() or ""
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
    device = cn_cfg.get("device") or {}
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


async def build_account_cookie(*, save: bool = True) -> str:
    """Build a complete BBS cookie, exchanging missing V2 tokens and syncing V1 aliases."""
    cn_cfg = setting.get_account()
    base = str(cn_cfg.get("cookie", ""))
    if not base.strip():
        raise CookieError(t("account.missing_cookie"))

    fields = parse_cookie(base)
    stuid = get_uid() or ""
    mid = get_mid() or ""
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
            fields.setdefault("stuid", stuid)
            fields.setdefault("ltuid_v2", stuid)
            fields.setdefault("account_id_v2", stuid)
        if mid:
            fields.setdefault("mid", mid)
            fields.setdefault("ltmid_v2", mid)
            fields.setdefault("account_mid_v2", mid)

    formatted = clean_cookie(format_cookie(fields), region="cn")
    if changed:
        cn_cfg["cookie"] = formatted
        if save:
            await setting.save_config()

    return formatted


async def update_cookie_token() -> bool:
    """Refresh CookieToken in place using V2 Passport exchange when mid is available."""
    log.info(t("account.cookie_refresh_start"))
    cn_cfg = setting.get_account()
    stoken = get_stoken()
    if not stoken:
        log.warning(t("account.no_stoken_cant_refresh"))
        return False

    stuid = get_uid() or ""
    mid = get_mid() or ""
    current = str(cn_cfg.get("cookie", ""))
    fields = parse_cookie(current)
    use_v2 = require_mid() and bool(mid)

    if use_v2:
        new_token = await get_cookie_token_by_stoken_v2()
        fields["cookie_token_v2"] = new_token
        if stuid:
            fields.setdefault("account_id_v2", stuid)
        if mid:
            fields.setdefault("account_mid_v2", mid)
    else:
        new_token = await get_cookie_token_by_stoken()
        key = "cookie_token_v2" if "cookie_token_v2" in fields else "cookie_token"
        fields[key] = new_token

    cn_cfg["cookie"] = clean_cookie(format_cookie(fields), region="cn")
    log.info(t("account.cookie_token_refresh_ok"))
    await setting.save_config()
    return True


def require_mid() -> bool:
    """判断是否需要mid"""
    return get_stoken().startswith("v2_")


def get_stoken_cookie() -> str:
    """获取带stoken的cookie"""
    stoken = get_stoken()
    if not stoken:
        raise StokenError(t("account.missing_stoken"))
    uid = get_uid()
    if uid is None:
        raise CookieError(t("account.missing_uid"))
    cookie = f"stuid={uid};stoken={stoken}"
    if require_mid():
        mid = get_mid()
        if mid:
            cookie += f";mid={mid}"
        else:
            log.error(t("account.mid_required"))
            raise CookieError(t("account.cookie_invalid"))
    return cookie


def require_cookie_token() -> bool:
    """判断是否需要 cookie_token"""
    return get_stoken().startswith("v2_")


def require_stoken() -> bool:
    """判断是否需要 stoken"""
    return get_stoken().startswith("v1_")
