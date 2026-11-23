"""CN server cloud game sign-in tasks."""

import functools
from urllib.parse import urlparse

from ...core import config, log, setting, t
from ...core.constants import (
    API_CLOUD_GENSHIN,
    API_CLOUD_GENSHIN_SIGN,
    API_CLOUD_ZZZ,
    API_CLOUD_ZZZ_SIGN,
    DESKTOP_BROWSER_UA,
    REFERER_MIHOYO_APP,
)
from ...core.models import CloudGameInfo
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


async def clear_cookie(code: str) -> None:
    if "cn" in config and "cloud" in config["cn"]:
        config["cn"]["cloud"][code] = ""
        await setting.save_config()


def _build_headers(token: str, game_biz: str, hostname: str | None) -> dict[str, str]:
    """Build headers for CN cloud game API."""
    headers: dict[str, str] = {
        "Accept": "*/*",
        "Referer": REFERER_MIHOYO_APP,
        "x-rpc-combo_token": token,
        "x-rpc-cg_game_biz": game_biz,
        "Accept-Encoding": "gzip, deflate",
        "User-Agent": DESKTOP_BROWSER_UA,
    }
    if hostname:
        parsed = urlparse(hostname)
        headers["Host"] = parsed.netloc or hostname
    return headers


async def run_task() -> str:
    cloud_cfg = config["cn"]["cloud"]
    log.info(t("games.cloud.start"))
    ret_msg = ""
    for game in CLOUD_GAMES:
        token = cloud_cfg.get(game.name, "")
        if token:
            headers = _build_headers(token, game.biz, game.hostname)
            game_task = BaseCloudGame(
                game=t(f"games.names.{game.name}"),
                url=game.api,
                coin_name=t(f"games.cloud.{game.name}_coin"),
                clear_cookie_func=functools.partial(clear_cookie, game.name),
                headers=headers,
            )
            ret_msg += await game_task.check_in(retry_on_limit=True) + "\n\n"

    return ret_msg
