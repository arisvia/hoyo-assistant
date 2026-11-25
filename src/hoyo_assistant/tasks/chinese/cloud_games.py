"""CN server cloud game sign-in tasks."""

import functools
from urllib.parse import urlparse

from ...core import log, setting, t
from ...core.constants import (
    API_CLOUD_GENSHIN,
    API_CLOUD_GENSHIN_SIGN,
    API_CLOUD_ZZZ,
    API_CLOUD_ZZZ_SIGN,
    DESKTOP_BROWSER_UA,
    HK4E_CN_APP_ID,
    NAP_CN_APP_ID,
    REFERER_MIHOYO_APP,
)
from ...core.models import CloudGameInfo, TaskReport
from ..base import BaseCloudGame

CLOUD_GAMES = [
    CloudGameInfo(
        "genshin",
        API_CLOUD_GENSHIN_SIGN,
        "hk4e_cn",
        urlparse(API_CLOUD_GENSHIN).netloc,
    ),
    CloudGameInfo(
        "zzz",
        API_CLOUD_ZZZ_SIGN,
        "nap_cn",
        urlparse(API_CLOUD_ZZZ).netloc,
    ),
]

_CLOUD_GAME_APP_IDS: dict[str, str] = {
    "genshin": HK4E_CN_APP_ID,
    "zzz": NAP_CN_APP_ID,
}


def _build_headers(
    token: str,
    game_biz: str,
    hostname: str | None,
    *,
    app_id: str = "",
    device_id: str = "",
    device_fp: str = "",
) -> dict[str, str]:
    """Build headers for CN cloud game API."""
    headers: dict[str, str] = {
        "Accept": "*/*",
        "Referer": REFERER_MIHOYO_APP,
        "x-rpc-combo_token": token,
        "x-rpc-cg_game_biz": game_biz,
        "x-rpc-client_type": "4",
        "Accept-Encoding": "gzip, deflate",
        "User-Agent": DESKTOP_BROWSER_UA,
    }
    if app_id:
        headers["x-rpc-app_id"] = app_id
    if device_id:
        headers["x-rpc-device_id"] = device_id
    if device_fp:
        headers["x-rpc-device_fp"] = device_fp
    if hostname:
        parsed = urlparse(hostname)
        headers["Host"] = parsed.netloc or hostname
    return headers


async def run_task() -> TaskReport:
    acct = setting.get_account()
    cloud_cfg = acct.get("cloud") or {}
    device = acct.get("device") or {}
    device_id = str(device.get("id", "")).strip()
    device_fp = str(device.get("fp", "")).strip()

    log.info(t("games.cloud.start"))
    ret_msg = ""
    had_error = False
    had_success = False
    for game in CLOUD_GAMES:
        token = cloud_cfg.get(game.name, "")
        if token:
            headers = _build_headers(
                token,
                game.biz,
                game.hostname,
                app_id=_CLOUD_GAME_APP_IDS.get(game.name, ""),
                device_id=device_id,
                device_fp=device_fp,
            )
            game_task = BaseCloudGame(
                game=t(f"games.names.{game.name}"),
                url=game.api,
                coin_name=t(f"games.cloud.{game.name}_coin"),
                clear_cookie_func=functools.partial(
                    setting.clear_cloud_token, game.name
                ),
                headers=headers,
            )
            msg = await game_task.check_in(retry_on_limit=True)
            ret_msg += msg + "\n\n"
            if game_task.had_error:
                had_error = True
            elif msg:
                had_success = True

    return TaskReport(ret_msg, had_error=had_error, had_success=had_success)
