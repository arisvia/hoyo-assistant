import asyncio
import random
from typing import Any, cast

from ...core import CookieError, account, captcha, config, http, log, login, t, tools
from ...core.constants import (
    ACT_ID_CN_GENSHIN,
    ACT_ID_CN_HONKAI2,
    ACT_ID_CN_HONKAI3RD,
    ACT_ID_CN_HONKAI_SR,
    ACT_ID_CN_TEARS_OF_THEMIS,
    ACT_ID_CN_ZZZ,
    API_CN_GAME_CHECKIN_REWARDS,
    API_CN_GAME_IS_SIGN,
    API_CN_GAME_SIGN,
    API_ZZZ_GAME_CHECKIN_REWARDS,
    API_ZZZ_GAME_IS_SIGN,
    API_ZZZ_GAME_SIGN,
    CN_GAME_LANG,
    DELAY_CAPTCHA_RETRY_RANGE,
    DELAY_RATE_LIMIT_SECONDS,
    DELAY_REWARD_RETRY_SECONDS,
    DELAY_SIGN_RANGE,
    MIHOYOBBS_ACCEPT_LANGUAGE,
    MIHOYOBBS_CLIENT_TYPE_WEB,
    MIHOYOBBS_VERSION,
    MIHOYOBBS_X_REQUESTED_WITH,
    ORIGIN_MIHOYO_ACT,
    ORIGIN_MIHOYO_WEBSTATIC,
    REF_BH2_SIGN,
    REF_BH3_SIGN,
    REF_GENSHIN_SIGN,
    REF_NXX_SIGN,
    RetCode,
)


class GameCheckin:
    def __init__(
        self,
        game_id: str,
        game_mid: str,
        game_name: str,
        act_id: str,
        player_name: str = "Player",
    ) -> None:
        self.game_id = game_id
        self.game_mid = game_mid
        self.game_name = game_name
        self.act_id = act_id
        self.player_name = player_name
        self.rewards_api = API_CN_GAME_CHECKIN_REWARDS
        self.is_sign_api = API_CN_GAME_IS_SIGN
        self.sign_api = API_CN_GAME_SIGN
        self.headers: dict[str, str] = {}
        self.profiles: list[Any] = []
        self.checkin_rewards: list[Any] = []
        self.set_headers()

    async def init(self) -> None:
        self.profiles = await account.get_account_list(self.game_id, self.headers)
        if len(self.profiles) != 0:
            self.checkin_rewards = await self.get_checkin_rewards()

    def _apply_game_headers(self) -> None:
        """Apply game-specific headers. Subclasses override this so cookie refreshes preserve them."""

    def set_headers(self) -> None:
        cookie = config["cn"]["cookie"]
        device_cfg = config["client"]["device"]
        device_id = device_cfg.get("id") or (
            tools.get_device_id(cookie) if cookie else ""
        )
        self.headers = {
            "Accept": "application/json, text/plain, */*",
            "DS": tools.get_ds(web=True),
            "Origin": ORIGIN_MIHOYO_WEBSTATIC,
            "x-rpc-app_version": MIHOYOBBS_VERSION,
            "User-Agent": tools.resolve_user_agent(config["client"]["user_agent"]),
            "x-rpc-client_type": MIHOYOBBS_CLIENT_TYPE_WEB,
            "Referer": f"{REF_GENSHIN_SIGN}?act_id={self.act_id}",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": MIHOYOBBS_ACCEPT_LANGUAGE,
            "X-Requested-With": MIHOYOBBS_X_REQUESTED_WITH,
            "Cookie": cookie,
            "x-rpc-device_id": device_id,
        }
        if device_cfg.get("fp"):
            self.headers["x-rpc-device_fp"] = device_cfg["fp"]
        self._apply_game_headers()

    def _format_reward(self, index: int) -> str:
        """Safely format reward at 0-based index without raising IndexError."""
        if 0 <= index < len(self.checkin_rewards):
            return tools.get_item(self.checkin_rewards[index])
        return t("games.cn.unknown_reward")

    def _get_black_list(self) -> list[str]:
        """Return configured blacklist UIDs for this game (top-level + custom game)."""
        cn_cfg = config["cn"]
        black_list: list[str] = list(
            (cn_cfg.get("black_list") or {}).get(self.game_mid) or []
        )
        custom_cfg = (cn_cfg.get("custom_games") or {}).get(self.game_mid)
        if isinstance(custom_cfg, dict):
            for uid in custom_cfg.get("black_list") or []:
                if uid not in black_list:
                    black_list.append(uid)
        return black_list

    async def get_checkin_rewards(self) -> list[Any]:
        log.info(t("games.cn.getting_rewards", name=self.game_name))
        max_retry = 3
        for i in range(max_retry):
            try:
                response = await http.get(
                    self.rewards_api,
                    params={"act_id": self.act_id},
                    headers=self.headers,
                    use_cache=(i == 0),
                )
                data = await response.json()
                if data["retcode"] == RetCode.OK:
                    return cast(list[Any], data["data"]["awards"])
                log.warning(t("games.cn.getting_rewards_retry", retry=i + 1))
            except Exception as e:
                log.warning(t("games.cn.getting_rewards_error", error=e, retry=i + 1))
            await asyncio.sleep(DELAY_REWARD_RETRY_SECONDS)
        log.warning(t("games.cn.getting_rewards_fail"))
        return []

    async def is_sign(self, region: str, uid: str, update: bool = False) -> Any:
        req = await http.get(
            url=self.is_sign_api,
            params={"act_id": self.act_id, "region": region, "uid": uid},
            headers=self.headers,
            use_cache=False,
        )
        data = await req.json()
        if data["retcode"] != RetCode.OK:
            if not update and await login.update_cookie_token():
                self.set_headers()
                return await self.is_sign(region, uid, True)
            log.warning(t("games.cn.getting_info_fail"))
            log.debug(f"Response: {data}")
            raise CookieError(t("account.cookie_invalid"))
        return data["data"]

    async def check_in(self, profile: list[Any]) -> Any:
        header = self.headers.copy()
        retries = config["cn"].get("retries", 3)
        result = None
        for i in range(1, retries + 1):
            if i > 1:
                log.info(t("games.cn.captcha", retry=i, max=retries))
            header["DS"] = tools.get_ds(web=True)
            result = await http.post(
                url=self.sign_api,
                headers=header,
                json={"act_id": self.act_id, "region": profile[2], "uid": profile[1]},
            )
            if result.status == 429:
                await asyncio.sleep(DELAY_RATE_LIMIT_SECONDS)
                log.warning(t("games.cn.rate_limit"))
                continue
            data = await result.json()
            if (
                data["retcode"] == RetCode.OK
                and data["data"]["success"] == 1
                and i < retries
            ):
                captcha_result = captcha.game_captcha(
                    data["data"]["gt"], data["data"]["challenge"]
                )
                if captcha_result is not None:
                    challenge = data["data"]["challenge"]
                    if isinstance(captcha_result, dict):
                        validate = captcha_result["validate"]
                        challenge = captcha_result["challenge"]
                    else:
                        validate = captcha_result  # type: ignore[unreachable]
                    header.update(
                        {
                            "x-rpc-challenge": challenge,
                            "x-rpc-validate": validate,
                            "x-rpc-seccode": f"{validate}|jordan",
                        }
                    )
                await asyncio.sleep(random.randint(*DELAY_CAPTCHA_RETRY_RANGE))
            else:
                break
        return result

    async def sign_account(self) -> str:
        return_data = f"{self.game_name}: "
        if not self.profiles:
            log.warning(t("games.cn.no_account", name=self.game_name))
            return_data += t("games.cn.no_account_msg", name=self.game_name)
            return return_data
        black_list = self._get_black_list()
        for profile in self.profiles:
            if profile[1] in black_list:
                log.info(t("games.cn.blacklisted", uid=profile[1]))
                continue
            log.info(t("games.cn.checkin_start", name=profile[0]))
            await asyncio.sleep(random.randint(*DELAY_SIGN_RANGE))
            is_data = await self.is_sign(region=profile[2], uid=profile[1])
            if not isinstance(is_data, dict):
                log.warning(t("games.cn.getting_info_fail"))
                return_data += t("games.cn.sign_fail_account", uid=profile[0])
                continue
            if is_data.get("first_bind", False):
                log.warning(
                    t("games.cn.first_bind", name=self.player_name, uid=profile[0])
                )
                continue
            total_days = int(is_data.get("total_sign_day", 0))
            if is_data["is_sign"]:
                signed_days = total_days
                reward_item = self._format_reward(max(signed_days - 1, 0))
                log.info(
                    t(
                        "games.cn.checkin_already",
                        name=self.player_name,
                        uid=profile[0],
                        reward=reward_item,
                    )
                )
            else:
                await asyncio.sleep(random.randint(*DELAY_SIGN_RANGE))
                req = await self.check_in(profile)
                if req is None:
                    log.warning(
                        t(
                            "games.cn.checkin_fail",
                            name=self.player_name,
                            uid=profile[0],
                            reason="Unknown",
                        )
                    )
                    return_data += t("games.cn.sign_fail_account", uid=profile[0])
                    continue
                if req.status != 429:
                    data = await req.json()
                    payload = data.get("data") if isinstance(data, dict) else None
                    payload_success = (
                        payload.get("success") if isinstance(payload, dict) else None
                    )
                    if data.get("retcode") == RetCode.OK and payload_success == 0:
                        signed_days = total_days + 1
                        reward_item = self._format_reward(max(signed_days - 1, 0))
                        log.info(
                            t(
                                "games.cn.checkin_success",
                                name=self.player_name,
                                uid=profile[0],
                                reward=reward_item,
                            )
                        )
                    elif data.get("retcode") == RetCode.ALREADY_SIGNED_IN:
                        signed_days = total_days
                        reward_item = self._format_reward(max(signed_days - 1, 0))
                        log.info(
                            t(
                                "games.cn.checkin_already",
                                name=self.player_name,
                                uid=profile[0],
                                reward=reward_item,
                            )
                        )
                    else:
                        s = t("games.cn.sign_fail_msg")
                        if (
                            payload not in (None, "")
                            and isinstance(payload, dict)
                            and payload.get("success", -1)
                        ):
                            s += (
                                f"{t('games.cn.captcha_trigger')}\njson info: "
                                + await req.text()
                            )
                        log.warning(s)
                        return_data += t("games.cn.sign_fail_captcha", uid=profile[0])
                        continue
                else:
                    return_data += t("games.cn.sign_fail_account", uid=profile[0])
                    continue

            reward_item_final = self._format_reward(max(signed_days - 1, 0))
            return_data += t(
                "games.cn.sign_success_msg",
                uid=profile[0],
                days=signed_days,
                reward=reward_item_final,
            )
        return return_data


class Honkai2(GameCheckin):
    def __init__(self) -> None:
        super().__init__(
            "bh2_cn",
            "honkai2",
            t("games.names.honkai2"),
            ACT_ID_CN_HONKAI2,
            t("games.titles.honkai2"),
        )

    def _apply_game_headers(self) -> None:
        self.headers["Referer"] = (
            f"{REF_BH2_SIGN}?bbs_auth_required"
            f"=true&act_id={ACT_ID_CN_HONKAI2}&bbs_presentation_style=fullscreen"
            "&utm_source=bbs&utm_medium=mys&utm_campaign=icon"
        )


class Honkai3rd(GameCheckin):
    def __init__(self) -> None:
        super().__init__(
            "bh3_cn",
            "honkai3rd",
            t("games.names.honkai3rd"),
            ACT_ID_CN_HONKAI3RD,
            t("games.titles.honkai3rd"),
        )

    def _apply_game_headers(self) -> None:
        self.headers["Referer"] = (
            f"{REF_BH3_SIGN}?bbs_auth_required"
            f"=true&act_id={ACT_ID_CN_HONKAI3RD}&bbs_presentation_style=fullscreen"
            "&utm_source=bbs&utm_medium=mys&utm_campaign=icon"
        )
        self.headers["x-rpc-signgame"] = "bh3"


class TearsOfThemis(GameCheckin):
    def __init__(self) -> None:
        super().__init__(
            "nxx_cn",
            "tears_of_themis",
            t("games.names.tears_of_themis"),
            ACT_ID_CN_TEARS_OF_THEMIS,
            t("games.titles.tears_of_themis"),
        )

    def _apply_game_headers(self) -> None:
        self.headers["Referer"] = (
            f"{REF_NXX_SIGN}?bbs_auth_required=true&bbs_presentation_style=fullscreen&act_id={ACT_ID_CN_TEARS_OF_THEMIS}"
        )
        self.headers["x-rpc-signgame"] = "nxx"


class Genshin(GameCheckin):
    def __init__(self) -> None:
        super().__init__(
            "hk4e_cn",
            "genshin",
            t("games.names.genshin"),
            ACT_ID_CN_GENSHIN,
            t("games.titles.genshin"),
        )

    def _apply_game_headers(self) -> None:
        self.headers["Origin"] = ORIGIN_MIHOYO_ACT
        self.headers["x-rpc-signgame"] = "hk4e"


class Honkaisr(GameCheckin):
    def __init__(self) -> None:
        super().__init__(
            "hkrpg_cn",
            "honkai_sr",
            t("games.names.honkai_sr"),
            ACT_ID_CN_HONKAI_SR,
            t("games.titles.honkai_sr"),
        )

    def _apply_game_headers(self) -> None:
        self.headers["Origin"] = ORIGIN_MIHOYO_ACT
        self.headers["x-rpc-signgame"] = "hkrpg"


class ZZZ(GameCheckin):
    def __init__(self) -> None:
        super().__init__(
            "nap_cn", "zzz", t("games.names.zzz"), ACT_ID_CN_ZZZ, t("games.titles.zzz")
        )
        self.rewards_api = API_ZZZ_GAME_CHECKIN_REWARDS
        self.is_sign_api = API_ZZZ_GAME_IS_SIGN
        self.sign_api = API_ZZZ_GAME_SIGN

    def _apply_game_headers(self) -> None:
        self.headers["Origin"] = ORIGIN_MIHOYO_ACT
        self.headers["X-Rpc-Signgame"] = "zzz"


class CustomCNGameCheckin(GameCheckin):
    """Configurable CN game check-in for newly launched titles (e.g., Petit Planet / HNA)."""

    def __init__(self, game_mid: str, spec: dict[str, Any]) -> None:
        self._origin = str(spec.get("origin") or ORIGIN_MIHOYO_ACT)
        self._referer = str(spec.get("referer") or "")
        self._signgame = str(spec.get("signgame") or "")
        super().__init__(
            game_id=str(spec["game_biz"]),
            game_mid=game_mid,
            game_name=str(spec.get("name") or game_mid),
            act_id=str(spec["act_id"]),
            player_name=str(spec.get("player_name") or t("games.titles.honkai2")),
        )
        api_base = str(spec.get("api_base") or "").rstrip("/")
        if api_base:
            self.rewards_api = f"{api_base}/home?lang={CN_GAME_LANG}"
            self.is_sign_api = f"{api_base}/info?lang={CN_GAME_LANG}"
            self.sign_api = f"{api_base}/sign"

    def _apply_game_headers(self) -> None:
        if self._origin:
            self.headers["Origin"] = self._origin
        if self._referer:
            self.headers["Referer"] = self._referer
        if self._signgame:
            self.headers["x-rpc-signgame"] = self._signgame


async def checkin_game(
    game_name: str, game_module: type, game_print_name: str = ""
) -> str:
    enabled_games = config["cn"].get("games") or []
    if game_name in enabled_games:
        await asyncio.sleep(random.randint(*DELAY_SIGN_RANGE))
        if game_print_name == "":
            game_print_name = game_name
        log.info(t("games.cn.checkin_start", name=game_print_name))
        instance = game_module()
        await instance.init()
        return f"\n\n{await instance.sign_account()}"
    return ""


async def run_task() -> str:
    games = [
        ("honkai2", Honkai2, "games.names.honkai2"),
        ("honkai3rd", Honkai3rd, "games.names.honkai3rd"),
        ("tears_of_themis", TearsOfThemis, "games.names.tears_of_themis"),
        ("genshin", Genshin, "games.names.genshin"),
        ("honkai_sr", Honkaisr, "games.names.honkai_sr"),
        ("zzz", ZZZ, "games.names.zzz"),
    ]
    return_data = ""
    for game_name, game_module, name_key in games:
        return_data += await checkin_game(game_name, game_module, t(name_key))

    custom_games = config["cn"].get("custom_games") or {}
    for game_mid, spec in custom_games.items():
        if (
            isinstance(spec, dict)
            and spec.get("enable", True)
            and spec.get("game_biz")
            and spec.get("act_id")
        ):
            await asyncio.sleep(random.randint(*DELAY_SIGN_RANGE))
            display_name = str(spec.get("name") or game_mid)
            log.info(t("games.cn.checkin_start", name=display_name))
            instance = CustomCNGameCheckin(game_mid, spec)
            await instance.init()
            return_data += f"\n\n{await instance.sign_account()}"
    return return_data
