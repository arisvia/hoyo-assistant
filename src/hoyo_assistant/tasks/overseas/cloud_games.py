"""Overseas server cloud game sign-in tasks."""

import functools

from ...core import log, setting, t
from ...core.constants import (
    API_CLOUD_GENSHIN_SIGN_OS,
    API_CLOUD_ZZZ_SIGN_OS,
    DEFAULT_OS_LANG,
    OS_CLOUD_APP_UA,
)
from ...core.models import CloudGameInfo, TaskReport
from ..base import BaseCloudGame

CLOUD_GAMES = [
    CloudGameInfo("genshin", API_CLOUD_GENSHIN_SIGN_OS, "hk4e_global"),
    CloudGameInfo("zzz", API_CLOUD_ZZZ_SIGN_OS, "nap_global"),
]


def _build_headers(token: str, game_biz: str, lang: str) -> dict[str, str]:
    """Build headers for OS cloud game API."""
    return {
        "Accept": "*/*",
        "x-rpc-combo_token": token,
        "Accept-Encoding": "gzip, deflate",
        "User-Agent": OS_CLOUD_APP_UA,
        "x-rpc-client_type": "3",
        "x-rpc-cg_game_biz": game_biz,
        "x-rpc-channel_id": "1",
        "x-rpc-language": lang,
    }


async def run_task() -> TaskReport:
    os_cfg = setting.get_account()
    cloud_cfg = os_cfg.get("cloud") or {}
    lang = os_cfg.get("lang", DEFAULT_OS_LANG)
    log.info(t("games.cloud.start"))
    ret_msg = ""
    had_error = False
    had_success = False
    for game in CLOUD_GAMES:
        token = cloud_cfg.get(game.name, "")
        if token:
            headers = _build_headers(token, game.biz, lang)
            game_task = BaseCloudGame(
                game=t(f"games.names.{game.name}"),
                url=game.api,
                coin_name=t(f"games.cloud.{game.name}_coin"),
                clear_cookie_func=functools.partial(
                    setting.clear_cloud_token, game.name
                ),
                headers=headers,
            )
            msg = await game_task.check_in()
            ret_msg += msg + "\n\n"
            if game_task.had_error:
                had_error = True
            elif msg:
                had_success = True

    return TaskReport(ret_msg, had_error=had_error, had_success=had_success)
