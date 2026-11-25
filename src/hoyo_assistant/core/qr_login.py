"""Terminal QR-code login for China mainland (MiYoUShe & Cloud Genshin) accounts."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import parse_qs, urlparse

import segno

from . import http, log, login, setting, t, tools
from .constants import (
    API_HK4E_COMBO_LOGIN,
    API_PASSPORT_GET_TOKEN_BY_GAME_TOKEN,
    API_QR_FETCH,
    API_QR_QUERY,
    DESKTOP_BROWSER_UA,
    HK4E_CN_APP_ID,
    HK4E_CN_APP_KEY,
    HK4E_CN_CHANNEL_ID,
    MIHOYOBBS_APP_ID,
    MIHOYOBBS_APP_UA,
    MIHOYOBBS_CLIENT_TYPE,
    MIHOYOBBS_VERSION,
    QR_LOGIN_DEFAULT_TIMEOUT,
    QR_LOGIN_POLL_INTERVAL,
    RetCode,
)
from .setting_schema import (
    BBSConfig,
    CNAccountConfig,
    CNGameId,
    DeviceConfig,
    clean_cookie,
)
from .tools import format_cookie

QRScope = Literal["all", "bbs", "cloud"]

DEFAULT_NEW_CN_BBS_FORUMS: tuple[int, ...] = (2, 5)
DEFAULT_NEW_CN_GAMES: tuple[CNGameId, ...] = ("genshin", "honkai_sr", "zzz")


def should_use_ansi_qr() -> bool:
    """Determine whether QR terminal rendering should emit ANSI color sequences."""
    return tools.use_rich_output(require_stdin=True, check_ci=True)


def default_qr_printer(message: str) -> None:
    """Print QR or status text safely without Rich markup corruption."""
    if "\x1b[" in message:
        from rich.console import Console
        from rich.text import Text

        Console(no_color=False, force_terminal=True).print(
            Text.from_ansi(message), soft_wrap=True
        )
    else:
        print(message)


@dataclass
class QRLoginResult:
    """Credentials obtained from a confirmed MiYoUShe App QR scan."""

    uid: str
    device_id: str
    stoken: str = ""
    mid: str = ""
    cloud_genshin_token: str = ""


def is_interactive_terminal() -> bool:
    """Return True only when attached to a live TTY outside CI environments."""
    return tools.is_tty(require_stdin=True, check_ci=True)


def render_qr_terminal(url: str, *, use_ansi: bool = True, border: int = 2) -> str:
    """Render a URL as a compact Unicode half-block QR code for terminal display."""
    qr = segno.make(url, error="l")
    matrix = [[bool(cell) for cell in row] for row in qr.matrix]
    width = len(matrix[0]) if matrix else 0

    pad_row = [False] * (width + border * 2)
    padded: list[list[bool]] = [list(pad_row) for _ in range(border)]
    for row in matrix:
        padded.append(([False] * border) + row + ([False] * border))
    for _ in range(border):
        padded.append(list(pad_row))

    if len(padded) % 2 == 1:
        padded.append(list(pad_row))

    lines: list[str] = []
    for y in range(0, len(padded), 2):
        top_row = padded[y]
        bottom_row = padded[y + 1]
        chars: list[str] = []
        for top_dark, bottom_dark in zip(top_row, bottom_row, strict=True):
            if not use_ansi:
                # Invert polarity for plain dark terminals without ANSI colors
                top_dark = not top_dark
                bottom_dark = not bottom_dark

            if top_dark and bottom_dark:
                chars.append("█")
            elif top_dark and not bottom_dark:
                chars.append("▀")
            elif not top_dark and bottom_dark:
                chars.append("▄")
            else:
                chars.append(" ")
        line = "".join(chars)
        if use_ansi:
            lines.append(f"\x1b[47;30m{line}\x1b[0m")
        else:
            lines.append(line)

    return "\n".join(lines)


async def fetch_qr_code(device_id: str) -> tuple[str, str]:
    """Fetch a MiYoUShe QR login URL and ticket."""
    resp = await http.post(
        API_QR_FETCH,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": DESKTOP_BROWSER_UA,
        },
        json={"app_id": HK4E_CN_APP_ID, "device": device_id},
    )
    payload = await resp.json()
    if payload.get("retcode") != RetCode.OK:
        msg = payload.get("message", "")
        raise RuntimeError(f"QR fetch failed (retcode={payload.get('retcode')}): {msg}")

    url = str((payload.get("data") or {}).get("url", "")).strip()
    if not url:
        raise RuntimeError("QR fetch response missing url")

    parsed = urlparse(url)
    tickets = parse_qs(parsed.query).get("ticket", [])
    ticket = tickets[0].strip() if tickets else ""
    if not ticket:
        raise RuntimeError("QR URL missing ticket parameter")
    return url, ticket


async def poll_qr_status(
    device_id: str,
    ticket: str,
    *,
    timeout: int = QR_LOGIN_DEFAULT_TIMEOUT,
    poll_interval: float = QR_LOGIN_POLL_INTERVAL,
    on_status: Callable[[str], None] | None = None,
) -> tuple[str, str]:
    """Poll QR scan status until confirmed, returning `(uid, game_token)`."""
    deadline = time.monotonic() + max(timeout, 1)
    last_stat: str | None = None

    while True:
        resp = await http.post(
            API_QR_QUERY,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": DESKTOP_BROWSER_UA,
            },
            json={
                "app_id": HK4E_CN_APP_ID,
                "device": device_id,
                "ticket": ticket,
            },
        )
        payload = await resp.json()
        retcode = payload.get("retcode", -1)
        if retcode == RetCode.QR_EXPIRED:
            raise TimeoutError(t("qr.expired"))
        if retcode != RetCode.OK:
            msg = payload.get("message", "")
            raise RuntimeError(f"QR query failed (retcode={retcode}): {msg}")

        data = payload.get("data") or {}
        stat = str(data.get("stat", ""))
        if stat and stat != last_stat:
            last_stat = stat
            if on_status is not None:
                on_status(stat)

        if stat == "Confirmed":
            raw = (data.get("payload") or {}).get("raw", "")
            if not raw:
                raise RuntimeError("Confirmed QR payload missing raw data")
            parsed = json.loads(raw)
            uid = str(parsed.get("uid", "")).strip()
            game_token = str(parsed.get("token", "")).strip()
            if not uid or not game_token:
                raise RuntimeError("Confirmed QR payload missing uid or token")
            return uid, game_token

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(t("qr.timeout", timeout=timeout))

        await asyncio.sleep(min(poll_interval, remaining))


async def exchange_stoken_by_game_token(
    uid: str,
    game_token: str,
    device: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """Exchange `(uid, game_token)` for MiYoUShe App `(stoken, mid)`."""
    device_id = str((device or {}).get("id", ""))
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "x-rpc-app_id": MIHOYOBBS_APP_ID,
        "x-rpc-client_type": MIHOYOBBS_CLIENT_TYPE,
        "x-rpc-app_version": MIHOYOBBS_VERSION,
        "x-rpc-device_id": device_id,
        "User-Agent": MIHOYOBBS_APP_UA,
    }
    resp = await http.post(
        API_PASSPORT_GET_TOKEN_BY_GAME_TOKEN,
        headers=headers,
        json={"account_id": int(uid), "game_token": game_token},
    )
    payload = await resp.json()
    if payload.get("retcode") != RetCode.OK:
        msg = payload.get("message", "")
        raise RuntimeError(
            f"getTokenByGameToken failed (retcode={payload.get('retcode')}): {msg}"
        )

    data = payload.get("data") or {}
    stoken = str((data.get("token") or {}).get("token", "")).strip()
    mid = str((data.get("user_info") or {}).get("mid", "")).strip()
    if not stoken or not mid:
        raise RuntimeError("getTokenByGameToken response missing stoken or mid")
    return stoken, mid


def compute_cloud_genshin_combo_token(open_id: str, combo_token: str) -> str:
    """Compute signed Cloud Genshin `x-rpc-combo_token` header value."""
    sign_src = (
        f"app_id={HK4E_CN_APP_ID}&channel_id={HK4E_CN_CHANNEL_ID}"
        f"&combo_token={combo_token}&open_id={open_id}"
    )
    si = hmac.new(
        HK4E_CN_APP_KEY.encode("utf-8"),
        sign_src.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return (
        f"ai={HK4E_CN_APP_ID};ci={HK4E_CN_CHANNEL_ID};"
        f"oi={open_id};ct={combo_token};si={si};bi=hk4e_cn"
    )


async def exchange_cloud_genshin_token(
    uid: str, game_token: str, device_id: str
) -> str:
    """Exchange `(uid, game_token)` for signed Cloud Genshin `x-rpc-combo_token`."""
    data_str = json.dumps(
        {"uid": str(uid), "guest": False, "token": game_token},
        separators=(",", ":"),
    )
    raw_sign = (
        f"app_id={HK4E_CN_APP_ID}&channel_id={HK4E_CN_CHANNEL_ID}"
        f"&data={data_str}&device={device_id}"
    )
    sign = hmac.new(
        HK4E_CN_APP_KEY.encode("utf-8"),
        raw_sign.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    resp = await http.post(
        API_HK4E_COMBO_LOGIN,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": DESKTOP_BROWSER_UA,
        },
        json={
            "app_id": int(HK4E_CN_APP_ID),
            "channel_id": int(HK4E_CN_CHANNEL_ID),
            "data": data_str,
            "device": device_id,
            "sign": sign,
        },
    )
    payload = await resp.json()
    if payload.get("retcode") != RetCode.OK:
        msg = payload.get("message", "")
        raise RuntimeError(
            f"Cloud Genshin combo login failed (retcode={payload.get('retcode')}): {msg}"
        )

    data = payload.get("data") or {}
    open_id = str(data.get("open_id", "")).strip()
    combo_token = str(data.get("combo_token", "")).strip()
    if not open_id or not combo_token:
        raise RuntimeError("Combo login response missing open_id or combo_token")
    return compute_cloud_genshin_combo_token(open_id, combo_token)


async def qr_login_cn(
    *,
    scope: QRScope = "all",
    timeout: int = QR_LOGIN_DEFAULT_TIMEOUT,
    device: dict[str, Any] | None = None,
    printer: Callable[[str], None] | None = None,
    use_ansi: bool | None = None,
) -> QRLoginResult:
    """Display terminal QR code, wait for MiYoUShe App confirmation, and exchange tokens."""
    emit = printer or default_qr_printer
    resolved_timeout = max(int(timeout), 1)
    resolved_ansi = should_use_ansi_qr() if use_ansi is None else use_ansi
    device_id = str((device or {}).get("id", "")).strip() or str(uuid.uuid4())

    url, ticket = await fetch_qr_code(device_id)
    emit(t("qr.prompt", timeout=resolved_timeout))
    emit(render_qr_terminal(url, use_ansi=resolved_ansi))

    def _on_status(stat: str) -> None:
        if stat == "Scanned":
            emit(t("qr.scanned"))

    uid, game_token = await poll_qr_status(
        device_id,
        ticket,
        timeout=resolved_timeout,
        on_status=_on_status,
    )

    stoken = ""
    mid = ""
    cloud_genshin_token = ""

    if scope in ("all", "bbs"):
        stoken, mid = await exchange_stoken_by_game_token(
            uid, game_token, {"id": device_id}
        )

    if scope in ("all", "cloud"):
        try:
            cloud_genshin_token = await exchange_cloud_genshin_token(
                uid, game_token, device_id
            )
        except Exception as e:
            if scope == "cloud":
                raise
            log.warning(t("qr.cloud_exchange_warn", error=e))

    return QRLoginResult(
        uid=uid,
        device_id=device_id,
        stoken=stoken,
        mid=mid,
        cloud_genshin_token=cloud_genshin_token,
    )


def _find_cn_account_by_uid(accounts: list[Any], uid: str) -> dict[str, Any] | None:
    """Return existing `region: cn` account whose cookie UID matches `uid`."""
    for acct in accounts:
        if not isinstance(acct, dict) or acct.get("region") != "cn":
            continue
        existing_uid = login.extract_uid_from_cookie(str(acct.get("cookie", "")))
        if existing_uid == uid:
            return acct
    return None


async def upsert_cn_account(
    result: QRLoginResult,
    *,
    target_account: dict[str, Any] | None = None,
    scope: QRScope = "all",
    name: str | None = None,
    hydrate_cookie: bool = True,
) -> tuple[dict[str, Any], bool]:
    """Overwrite matched UID CN account or create a new one, then persist config."""
    raw_accounts = setting.config.get("accounts")
    if not isinstance(raw_accounts, list):
        raw_accounts = []
        setting.config["accounts"] = raw_accounts
    accounts: list[Any] = raw_accounts

    created_new = False
    account: dict[str, Any] | None = target_account
    if account is None:
        account = _find_cn_account_by_uid(accounts, result.uid)

    if account is None:
        default_name = (name or "").strip() or f"国服-{result.uid}"
        model = CNAccountConfig(
            name=default_name,
            region="cn",
            device=DeviceConfig(id=result.device_id),
            bbs=BBSConfig(enable=True, forums=list(DEFAULT_NEW_CN_BBS_FORUMS)),
            games=list(DEFAULT_NEW_CN_GAMES),
        )
        account = model.model_dump()
        accounts.append(account)
        created_new = True
    elif name and name.strip():
        account["name"] = name.strip()

    device = account.get("device")
    if not isinstance(device, dict):
        device = DeviceConfig().model_dump()
        account["device"] = device
    if not device.get("id") or result.cloud_genshin_token:
        device["id"] = result.device_id

    if scope in ("all", "bbs") and result.stoken:
        cookie_fields: dict[str, str] = {
            "stuid": result.uid,
            "stoken": result.stoken,
        }
        if result.mid:
            cookie_fields["mid"] = result.mid
        account["cookie"] = clean_cookie(format_cookie(cookie_fields), region="cn")

        if hydrate_cookie and result.mid:
            prev_account = setting._current_account
            setting.set_current_account(account)
            try:
                account["cookie"] = await login.build_account_cookie(save=False)
            finally:
                setting.set_current_account(prev_account)

    if scope in ("all", "cloud") and result.cloud_genshin_token:
        cloud = account.get("cloud")
        if not isinstance(cloud, dict):
            cloud = {"genshin": "", "zzz": ""}
            account["cloud"] = cloud
        cloud["genshin"] = result.cloud_genshin_token

    await setting.save_config()
    return account, created_new
