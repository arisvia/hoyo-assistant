import asyncio
import json
import random
from typing import Any, cast

from ...core import StokenError, captcha, config, http, log, login, setting, t, tools
from ...core.constants import (
    API_BBS_CAPTCHA_VERIFY,
    API_BBS_GAME_LIST,
    API_BBS_GET_CAPTCHA,
    API_BBS_SIGN,
    API_BBS_TASKS_LIST,
    BBS_API_HOST,
    DELAY_BBS_RANGE,
    MIHOYOBBS_ACCEPT_LANGUAGE,
    MIHOYOBBS_APP_UA,
    MIHOYOBBS_CHANNEL,
    MIHOYOBBS_CLIENT_TYPE,
    MIHOYOBBS_POST_TYPES,
    MIHOYOBBS_SYS_VERSION,
    MIHOYOBBS_VERIFY_KEY,
    MIHOYOBBS_VERSION,
    MIHOYOBBS_X_REQUESTED_WITH,
    ORIGIN_MIHOYO_WEBSTATIC,
    REFERER_MIHOYO_APP,
    RetCode,
)


async def wait() -> None:
    await asyncio.sleep(random.randint(*DELAY_BBS_RANGE))


async def fetch_bbs_game_list() -> dict[int, dict[str, str]]:
    """Fetch the live MiYoUShe community game list for syncing newly added forums."""
    try:
        req = await http.get(url=API_BBS_GAME_LIST, use_cache=True)
        data = await req.json()
        if data.get("retcode") != RetCode.OK:
            return {}
        items = (data.get("data") or {}).get("list") or []
        result: dict[int, dict[str, str]] = {}
        for item in items:
            raw_id = item.get("id")
            name = item.get("name")
            if raw_id is not None and name:
                gid = int(raw_id)
                result[gid] = {
                    "id": str(gid),
                    "name": str(name),
                    "en_name": str(item.get("en_name", "")),
                    "op_name": str(item.get("op_name", "")),
                }
        return result
    except Exception as e:
        log.debug(f"Failed to fetch live MiYoUShe game list: {e}")
        return {}


class Mihoyobbs:
    def __init__(self) -> None:
        self.today_get_coins = 0
        self.today_have_get_coins = 0
        self.have_coins = 0
        cn_cfg = config["cn"]
        self.bbs_config = cn_cfg["bbs"]
        self._unknown_forum_ids: list[int] = []
        tmp_list: list[dict[str, Any]] = []
        for i in self.bbs_config["forums"]:
            val = MIHOYOBBS_POST_TYPES.get(i)
            if val is not None:
                tmp_list.append(cast(dict[str, Any], val))
            else:
                self._unknown_forum_ids.append(int(i))
        self.bbs_list: list[dict[str, Any]] = tmp_list
        cookie = cn_cfg.get("cookie", "")
        device_cfg = config["client"]["device"]
        device_id = device_cfg.get("id") or (
            tools.get_device_id(cookie) if cookie else ""
        )
        self.headers = {
            "DS": tools.get_ds(web=False),
            "cookie": login.get_stoken_cookie(),
            "x-rpc-client_type": MIHOYOBBS_CLIENT_TYPE,
            "x-rpc-app_version": MIHOYOBBS_VERSION,
            "x-rpc-sys_version": MIHOYOBBS_SYS_VERSION,
            "x-rpc-channel": MIHOYOBBS_CHANNEL,
            "x-rpc-device_id": device_id,
            "x-rpc-device_name": device_cfg["name"],
            "x-rpc-device_model": device_cfg["model"],
            "x-rpc-h265_supported": "1",
            "Referer": REFERER_MIHOYO_APP,
            "x-rpc-verify_key": MIHOYOBBS_VERIFY_KEY,
            "x-rpc-csm_source": "discussion",
            "Content-Type": "application/json; charset=UTF-8",
            "Host": BBS_API_HOST,
            "Connection": "Keep-Alive",
            "Accept-Encoding": "gzip",
            "User-Agent": MIHOYOBBS_APP_UA,
        }
        self.task_header = {
            "Accept": "application/json, text/plain, */*",
            "Origin": ORIGIN_MIHOYO_WEBSTATIC,
            "User-Agent": tools.resolve_user_agent(config["client"]["user_agent"]),
            "Referer": ORIGIN_MIHOYO_WEBSTATIC,
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": MIHOYOBBS_ACCEPT_LANGUAGE,
            "X-Requested-With": MIHOYOBBS_X_REQUESTED_WITH,
            "Cookie": cookie,
        }
        if device_cfg.get("fp"):
            self.headers["x-rpc-device_fp"] = device_cfg["fp"]
        self.task_do = {
            "sign": False,
        }

    async def sync_unknown_forums(self) -> None:
        """Resolve forum IDs not in the built-in table via the live MiYoUShe game list."""
        if not self._unknown_forum_ids:
            return
        remote_games = await fetch_bbs_game_list()
        if not remote_games:
            return
        for gid in self._unknown_forum_ids:
            forum = remote_games.get(gid)
            if forum is not None:
                self.bbs_list.append(forum)
                log.info(t("mihoyobbs.forum_synced", forum=forum["name"], gid=gid))
        self._unknown_forum_ids.clear()

    async def init(self) -> None:
        await self.sync_unknown_forums()
        await self.get_tasks_list()

    async def get_pass_challenge(self) -> str | None:
        header = self.headers.copy()
        header["DS"] = tools.get_ds(web=False)
        req = await http.get(url=API_BBS_GET_CAPTCHA, headers=header, use_cache=False)
        data = await req.json()
        if data["retcode"] != RetCode.OK:
            return None
        captcha_result = captcha.bbs_captcha(
            data["data"]["gt"], data["data"]["challenge"]
        )
        if captcha_result is not None:
            challenge = data["data"]["challenge"]
            if isinstance(captcha_result, dict):
                validate = captcha_result["validate"]
                challenge = captcha_result["challenge"]
            else:
                validate = captcha_result  # type: ignore[unreachable]
            header["DS"] = tools.get_ds(web=False)
            check_req = await http.post(
                url=API_BBS_CAPTCHA_VERIFY,
                headers=header,
                json={
                    "geetest_challenge": challenge,
                    "geetest_seccode": validate + "|jordan",
                    "geetest_validate": validate,
                },
            )
            check = await check_req.json()
            if check["retcode"] == RetCode.OK:
                return cast(str, check["data"]["challenge"])
        return None

    async def get_tasks_list(self, update: bool = False) -> None:
        log.info(t("mihoyobbs.get_tasks"))
        req = await http.get(
            url=API_BBS_TASKS_LIST,
            params={"point_sn": "myb"},
            headers=self.task_header,
            use_cache=False,
        )
        data = await req.json()
        message = str(data.get("message") or "")
        if "err" in message or data["retcode"] == RetCode.UNAUTHORIZED:
            if not update and await login.update_cookie_token():
                self.task_header["Cookie"] = config["cn"]["cookie"]
                return await self.get_tasks_list(True)
            log.error(t("mihoyobbs.get_tasks_fail"))
            await setting.clear_cookie()
            raise StokenError(t("account.stoken_error"))
        self.today_get_coins = data["data"]["can_get_points"]
        self.today_have_get_coins = data["data"]["already_received_points"]
        self.have_coins = data["data"]["total_points"]

        # 58 represents check-in
        tasks = {
            58: {"attr": "sign", "done": "is_get_award"},
        }
        missions = data["data"].get("states") or []
        if self.today_get_coins == 0:
            self.task_do["sign"] = True
        else:
            for task in tasks:
                mission_state = next(
                    (x for x in missions if x["mission_id"] == task), None
                )
                if mission_state is None:
                    continue
                do = tasks[task]
                if mission_state[do["done"]]:
                    self.task_do[do["attr"]] = True

        if data["data"]["can_get_points"] != 0:
            if len(missions) == 0:
                log.info(t("mihoyobbs.coins_today", coins=self.today_get_coins))
            else:
                new_day = missions[0]["mission_id"] >= 62
                if new_day:
                    log.info(t("mihoyobbs.coins_new_day", coins=self.today_get_coins))
                else:
                    log.info(t("mihoyobbs.coins_remain", coins=self.today_get_coins))

    async def signing(self) -> None:
        if self.task_do["sign"]:
            log.info(t("mihoyobbs.task_done"))
            return
        log.info(t("mihoyobbs.signing"))
        header = self.headers.copy()
        for forum in self.bbs_list:
            challenge = None
            for _retry_count in range(2):
                post_data = json.dumps({"gids": forum["id"]}).replace(" ", "")
                header["DS"] = tools.get_ds2("", post_data)
                req = await http.post(url=API_BBS_SIGN, data=post_data, headers=header)
                log.debug(await req.text())
                data = await req.json()
                message = str(data.get("message") or "")
                if data["retcode"] == RetCode.CAPTCHA_TRIGGERED:
                    log.warning(t("mihoyobbs.sign_captcha"))
                    challenge = await self.get_pass_challenge()
                    if challenge is not None:
                        header["x-rpc-challenge"] = challenge
                elif "err" not in message and data["retcode"] == RetCode.OK:
                    log.info(
                        t(
                            "mihoyobbs.sign_success",
                            forum=forum["name"],
                            message=message or "OK",
                        )
                    )
                    await wait()
                    break
                elif data["retcode"] == RetCode.UNAUTHORIZED:
                    log.error(t("mihoyobbs.sign_cookie_expired"))
                    await setting.clear_stoken()
                    raise StokenError(t("account.stoken_error"))
                else:
                    log.error(t("mihoyobbs.sign_unknown_error", error=await req.text()))
            if challenge is not None:
                header.pop("x-rpc-challenge")

    async def run_task(self) -> str:
        await self.init()
        return_data = "米游社: "
        if self.task_do["sign"]:
            summary = t(
                "mihoyobbs.summary_done",
                got=self.today_have_get_coins,
                total=self.have_coins,
            )
            log.info(summary)
            return return_data + summary

        i = 0
        while self.today_get_coins != 0 and i < 2:
            if i > 0:
                await wait()
            if self.bbs_config["enable"]:
                await self.signing()
            await self.get_tasks_list()
            i += 1

        summary = t(
            "mihoyobbs.summary_remain",
            got=self.today_have_get_coins,
            can_get=self.today_get_coins,
            total=self.have_coins,
        )
        log.info(summary)
        await wait()
        return return_data + summary
