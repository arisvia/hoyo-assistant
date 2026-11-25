import asyncio
import random

from ...core import http, log, setting, t
from ...core.constants import (
    ACT_ID_OS_GENSHIN,
    ACT_ID_OS_HONKAI3RD,
    ACT_ID_OS_HONKAI_SR,
    ACT_ID_OS_TEARS_OF_THEMIS,
    ACT_ID_OS_ZZZ,
    API_OS_ACT,
    API_OS_ACT_HI3,
    API_OS_ACT_HSR,
    API_OS_ACT_LUNA,
    API_OS_ACT_ZZZ,
    API_OS_REFERER,
    DEFAULT_OS_LANG,
    DELAY_SIGN_RANGE,
    DESKTOP_BROWSER_UA,
    OS_ACT_ID_TO_SIGNGAME,
    RetCode,
)
from ...core.models import TaskReport

OS_GAMES: tuple[tuple[str, str, str, str], ...] = (
    ("genshin", API_OS_ACT, ACT_ID_OS_GENSHIN, "games.names.genshin"),
    ("honkai_sr", API_OS_ACT_HSR, ACT_ID_OS_HONKAI_SR, "games.names.honkai_sr"),
    ("honkai3rd", API_OS_ACT_HI3, ACT_ID_OS_HONKAI3RD, "games.names.honkai3rd"),
    (
        "tears_of_themis",
        API_OS_ACT_LUNA,
        ACT_ID_OS_TEARS_OF_THEMIS,
        "games.names.tears_of_themis",
    ),
    ("zzz", API_OS_ACT_ZZZ, ACT_ID_OS_ZZZ, "games.names.zzz"),
)


async def hoyo_checkin(
    event_base_url: str,
    act_id: str,
    game_name: str,
    signgame: str | None = None,
) -> TaskReport:
    """
    国际服游戏签到

    :param event_base_url: 基础Url
    :param act_id: 活动id
    :param game_name: 游戏名称
    :param signgame: 可选 x-rpc-signgame 请求头值
    :return: 签到结果
    """
    os_cfg = setting.get_account()
    os_lang = os_cfg.get("lang", DEFAULT_OS_LANG)
    base = event_base_url.rstrip("/")
    reward_url = f"{base}/home?lang={os_lang}&act_id={act_id}"
    info_url = f"{base}/info?lang={os_lang}&act_id={act_id}"
    sign_url = f"{base}/sign?lang={os_lang}"

    cookie_str = os_cfg.get("cookie", "")
    custom_ua = os_cfg.get("user_agent", "")

    headers: dict[str, str] = {
        "Accept": "application/json, text/plain, */*",
        "Origin": API_OS_REFERER.rstrip("/"),
        "Referer": API_OS_REFERER,
        "Accept-Encoding": "gzip, deflate, br",
        "User-Agent": custom_ua or DESKTOP_BROWSER_UA,
        "Cookie": cookie_str,
    }
    resolved_signgame = signgame or OS_ACT_ID_TO_SIGNGAME.get(act_id)
    if resolved_signgame:
        headers["x-rpc-signgame"] = resolved_signgame

    log.info(t("games.os.checkin_start", game=game_name))

    resp = await http.get(info_url, headers=headers, use_cache=False)
    info_list = await resp.json()

    info_retcode = info_list.get("retcode", RetCode.OK)
    info_data = info_list.get("data")
    if info_retcode != RetCode.OK or not isinstance(info_data, dict):
        reason = info_list.get("message", "Unknown error")
        ret_msg = t("games.os.checkin_fail", game=game_name, reason=reason)
        log.error(ret_msg)
        return TaskReport(ret_msg, had_error=True, had_success=False)

    today = info_data.get("today")
    total_sign_in_day = int(info_data.get("total_sign_day") or 0)
    already_signed_in = bool(info_data.get("is_sign"))
    first_bind = bool(info_data.get("first_bind"))

    if already_signed_in:
        ret_msg = t("games.os.checkin_already", game=game_name)
        log.info(ret_msg)
        return TaskReport(ret_msg, had_error=False, had_success=True)

    if first_bind:
        ret_msg = t("games.os.manual_checkin", game=game_name)
        log.warning(ret_msg)
        return TaskReport(ret_msg, had_error=False, had_success=True)

    resp_awards = await http.get(reward_url, headers=headers, use_cache=False)
    awards_data = await resp_awards.json()

    awards_payload = awards_data.get("data")
    awards = (
        awards_payload.get("awards", []) if isinstance(awards_payload, dict) else []
    )

    log.info(t("games.os.preparing", today=today))

    sleep_time = random.randint(*DELAY_SIGN_RANGE)
    log.debug(t("games.os.waiting", time=sleep_time))
    await asyncio.sleep(sleep_time)

    resp_sign = await http.post(
        sign_url, headers=headers, json={"act_id": act_id, "lang": os_lang}
    )
    response = await resp_sign.json()

    code = response.get("retcode", 99999)

    log.debug(t("games.os.return_code", code=code))

    if code == RetCode.ALREADY_SIGNED_IN:
        ret_msg = t("games.os.checkin_already", game=game_name)
        log.info(ret_msg)
        return TaskReport(ret_msg, had_error=False, had_success=True)
    if code != RetCode.OK:
        ret_msg = t(
            "games.os.checkin_fail",
            game=game_name,
            reason=response.get("message", "Unknown error"),
        )
        log.error(ret_msg)
        return TaskReport(ret_msg, had_error=True, had_success=False)

    days = total_sign_in_day + 1
    if isinstance(awards, list) and awards:
        reward_idx = min(total_sign_in_day, len(awards) - 1)
        reward = awards[reward_idx]
        reward_name = reward.get("name", t("games.cn.unknown_reward"))
        reward_cnt = reward.get("cnt", 0)
    else:
        reward_name = t("games.cn.unknown_reward")
        reward_cnt = 0

    log.info(
        t(
            "games.os.checkin_success",
            game=game_name,
            name=reward_name,
            count=reward_cnt,
        )
    )

    ret_msg = t(
        "games.os.sign_success_msg",
        game=game_name,
        days=days,
        name=reward_name,
        count=reward_cnt,
    )
    return TaskReport(ret_msg, had_error=False, had_success=True)


async def run_task() -> TaskReport:
    log.info(t("games.os.start"))
    os_conf = setting.get_account()
    enabled_games = set(os_conf.get("games") or [])
    ret_parts: list[str] = []
    had_error = False
    had_success = False

    for config_key, api_base, act_id, name_key in OS_GAMES:
        if config_key in enabled_games:
            if ret_parts:
                await asyncio.sleep(random.randint(*DELAY_SIGN_RANGE))
            part = await hoyo_checkin(api_base, act_id, t(name_key))
            if part:
                ret_parts.append(part)
            if getattr(part, "had_error", False):
                had_error = True
            if getattr(part, "had_success", bool(part)):
                had_success = True

    custom_games = os_conf.get("custom_games") or {}
    for game_key, spec in custom_games.items():
        if isinstance(spec, dict) and spec.get("enable", True) and spec.get("act_id"):
            if ret_parts:
                await asyncio.sleep(random.randint(*DELAY_SIGN_RANGE))
            api_base = str(spec.get("api_base") or API_OS_ACT_LUNA)
            display_name = str(spec.get("name") or game_key)
            signgame = str(spec.get("signgame") or "") or None
            part = await hoyo_checkin(
                api_base, str(spec["act_id"]), display_name, signgame=signgame
            )
            if part:
                ret_parts.append(part)
            if getattr(part, "had_error", False):
                had_error = True
            if getattr(part, "had_success", bool(part)):
                had_success = True

    return TaskReport(
        "\n".join(ret_parts),
        had_error=had_error,
        had_success=had_success,
    )
