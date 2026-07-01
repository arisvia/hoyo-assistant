import asyncio
import json
import random
from typing import Any, cast

from ...core import StokenError, captcha, config, http, log, login, setting, t, tools
from ...core.constants import (
    API_BBS_CAPTCHA_VERIFY,
    API_BBS_GET_CAPTCHA,
    API_BBS_SIGN,
    API_BBS_TASKS_LIST,
    MIHOYOBBS_CLIENT_TYPE,
    MIHOYOBBS_POST_TYPES,
    MIHOYOBBS_VERIFY_KEY,
    MIHOYOBBS_VERSION,
)


async def wait() -> None:
    await asyncio.sleep(random.randint(3, 8))


class Mihoyobbs:
    def __init__(self) -> None:
        self.today_get_coins = 0
        self.today_have_get_coins = 0
        self.have_coins = 0
        self.bbs_config = config["mihoyobbs"]
        tmp_list: list[dict[str, Any]] = []
        for i in self.bbs_config["checkin_list"]:
            val = MIHOYOBBS_POST_TYPES.get(i)
            if val is not None:
                tmp_list.append(cast(dict[str, Any], val))
        self.bbs_list: list[dict[str, Any]] = tmp_list
        self.headers = {
            "DS": tools.get_ds(web=False),
            "cookie": login.get_stoken_cookie(),
            "x-rpc-client_type": MIHOYOBBS_CLIENT_TYPE,
            "x-rpc-app_version": MIHOYOBBS_VERSION,
            "x-rpc-sys_version": "12",
            "x-rpc-channel": "miyousheluodi",
            "x-rpc-device_id": config["device"]["id"],
            "x-rpc-device_name": config["device"]["name"],
            "x-rpc-device_model": config["device"]["model"],
            "x-rpc-h265_supported": "1",
            "Referer": "https://app.mihoyo.com",
            "x-rpc-verify_key": MIHOYOBBS_VERIFY_KEY,
            "x-rpc-csm_source": "discussion",
            "Content-Type": "application/json; charset=UTF-8",
            "Host": "bbs-api.miyoushe.com",
            "Connection": "Keep-Alive",
            "Accept-Encoding": "gzip",
            "User-Agent": "okhttp/4.9.3",
        }
        self.task_header = {
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://webstatic.mihoyo.com",
            "User-Agent": "Mozilla/5.0 (Linux; Android 12; Unspecified Device) AppleWebKit/537.36 (KHTML, like Gecko) "
            f"Version/4.0 Chrome/103.0.5060.129 Mobile Safari/537.36 miHoYoBBS/{MIHOYOBBS_VERSION}",
            "Referer": "https://webstatic.mihoyo.com",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "zh-CN,en-US;q=0.8",
            "X-Requested-With": "com.mihoyo.hyperion",
            "Cookie": config.get("account", {}).get("cookie", ""),
        }
        if config["device"]["fp"] != "":
            self.headers["x-rpc-device_fp"] = config["device"]["fp"]
        self.task_do = {
            "sign": False,
        }

    async def init(self) -> None:
        await self.get_tasks_list()

    async def get_pass_challenge(self) -> str | None:
        req = await http.get(url=API_BBS_GET_CAPTCHA, headers=self.headers)
        data = await req.json()
        if data["retcode"] != 0:
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
            check_req = await http.post(
                url=API_BBS_CAPTCHA_VERIFY,
                headers=self.headers,
                json={
                    "geetest_challenge": challenge,
                    "geetest_seccode": validate + "|jordan",
                    "geetest_validate": validate,
                },
            )
            check = await check_req.json()
            if check["retcode"] == 0:
                return cast(str, check["data"]["challenge"])
        return None

    # 获取任务列表，用来判断做了哪些任务
    async def get_tasks_list(self, update: bool = False) -> None:
        log.info(t("mihoyobbs.get_tasks"))
        req = await http.get(
            url=API_BBS_TASKS_LIST,
            params={"point_sn": "myb"},
            headers=self.task_header,
            use_cache=False,
        )
        data = await req.json()
        if "err" in data["message"] or data["retcode"] == -100:
            if not update and await login.update_cookie_token():
                self.task_header["Cookie"] = config["account"]["cookie"]
                return await self.get_tasks_list(True)
            else:
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
        if self.today_get_coins == 0:
            self.task_do["sign"] = True
        else:
            missions = data["data"]["states"]
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
            if len(data["data"]["states"]) == 0:
                log.info(t("mihoyobbs.coins_today", coins=self.today_get_coins))
            else:
                new_day = data["data"]["states"][0]["mission_id"] >= 62
                if new_day:
                    log.info(t("mihoyobbs.coins_new_day", coins=self.today_get_coins))
                else:
                    log.info(t("mihoyobbs.coins_remain", coins=self.today_get_coins))

    # 进行签到操作
    async def signing(self) -> None:
        if self.task_do["sign"]:
            log.info(t("mihoyobbs.task_done"))
            return
        log.info(t("mihoyobbs.signing"))
        header = self.headers.copy()
        for forum in self.bbs_list:
            challenge = None
            for _retry_count in range(2):
                post_data = json.dumps({"gids": forum["id"]})
                post_data = post_data.replace(" ", "")
                header["DS"] = tools.get_ds2("", post_data)
                req = await http.post(url=API_BBS_SIGN, data=post_data, headers=header)
                log.debug(await req.text())
                data = await req.json()
                if data["retcode"] == 1034:
                    log.warning(t("mihoyobbs.sign_captcha"))
                    challenge = await self.get_pass_challenge()
                    if challenge is not None:
                        header["x-rpc-challenge"] = challenge
                elif "err" not in data["message"] and data["retcode"] == 0:
                    log.info(
                        t(
                            "mihoyobbs.sign_success",
                            forum=forum["name"],
                            message=data.get("message", "OK"),
                        )
                    )
                    await wait()
                    break
                elif data["retcode"] == -100:
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
            return_data += t(
                "mihoyobbs.summary_done",
                got=self.today_have_get_coins,
                total=self.have_coins,
            )
            log.info(
                t(
                    "mihoyobbs.summary_done",
                    got=self.today_have_get_coins,
                    total=self.have_coins,
                )
            )
            return return_data

        i = 0
        while self.today_get_coins != 0 and i < 2:
            if i > 0:
                await wait()
            if self.bbs_config["checkin"]:
                await self.signing()
            await self.get_tasks_list()
            i += 1

        return_data += t(
            "mihoyobbs.summary_remain",
            got=self.today_have_get_coins,
            can_get=self.today_get_coins,
            total=self.have_coins,
        )
        log.info(
            t(
                "mihoyobbs.summary_remain",
                got=self.today_have_get_coins,
                can_get=self.today_get_coins,
                total=self.have_coins,
            )
        )
        await wait()
        return return_data
