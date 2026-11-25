"""Tests for tasks/ modules."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hoyo_assistant.core import CookieError, StokenError
from hoyo_assistant.core.constants import DESKTOP_BROWSER_UA
from hoyo_assistant.tasks.base import BaseCloudGame
from hoyo_assistant.tasks.chinese import cloud_games as cn_cloud_games
from hoyo_assistant.tasks.chinese.game_signin import (
    ZZZ,
    CustomCNGameCheckin,
    GameCheckin,
    Genshin,
    Honkai2,
    Honkai3rd,
    Honkaisr,
    TearsOfThemis,
    checkin_game,
    run_task as cn_run_task,
)
from hoyo_assistant.tasks.community.miyoushe import Mihoyobbs, fetch_bbs_game_list
from hoyo_assistant.tasks.overseas import (
    cloud_games as os_cloud_games,
    game_signin as os_game_signin,
)


def make_response(json_data=None, text_data="", status=200):
    """Create a mock async HTTP response."""
    resp = AsyncMock()
    resp.json = AsyncMock(return_value=json_data if json_data is not None else {})
    resp.text = AsyncMock(return_value=text_data)
    resp.status = status
    return resp


def mock_http(
    get_return=None, get_side_effect=None, post_return=None, post_side_effect=None
):
    """Create a mock http object with async get/post."""
    http = MagicMock()
    http.get = AsyncMock()
    http.post = AsyncMock()
    if get_side_effect is not None:
        http.get.side_effect = get_side_effect
    elif get_return is not None:
        http.get.return_value = get_return
    if post_side_effect is not None:
        http.post.side_effect = post_side_effect
    elif post_return is not None:
        http.post.return_value = post_return
    return http


@pytest.fixture(autouse=True)
def _no_sleep():
    with patch("asyncio.sleep", new=AsyncMock()):
        yield


def _patch_cn(acct):
    return patch(
        "hoyo_assistant.tasks.chinese.game_signin.setting.get_account",
        return_value=acct,
    )


def _patch_bbs(acct):
    return patch(
        "hoyo_assistant.tasks.community.miyoushe.setting.get_account",
        return_value=acct,
    )


def _patch_cn_cloud(acct):
    return patch(
        "hoyo_assistant.tasks.chinese.cloud_games.setting.get_account",
        return_value=acct,
    )


def _patch_os_cloud(acct):
    return patch(
        "hoyo_assistant.tasks.overseas.cloud_games.setting.get_account",
        return_value=acct,
    )


def _patch_os_signin(acct):
    return patch(
        "hoyo_assistant.tasks.overseas.game_signin.setting.get_account",
        return_value=acct,
    )


# ---------------------------------------------------------------------------
# BaseCloudGame tests
# ---------------------------------------------------------------------------


class TestBaseCloudGame:
    def test_init(self):
        clear = MagicMock()
        headers = {"Cookie": "abc"}
        game = BaseCloudGame("genshin", "http://api", "coin", clear, headers)
        assert game.game == "genshin"
        assert game.url == "http://api"
        assert game.coin_name == "coin"
        assert game.clear_cookie_func is clear
        assert game.headers is headers

    @pytest.mark.asyncio
    async def test_check_in_success_with_free_time(self):
        resp = make_response(
            {
                "retcode": 0,
                "data": {
                    "free_time": {"free_time": "600", "send_freetime": "100"},
                    "play_card": {"short_msg": "active"},
                    "coin": {"coin_num": "50"},
                },
            }
        )
        clear = AsyncMock()
        http = mock_http(get_return=resp)
        with patch("hoyo_assistant.tasks.base.http", http):
            game = BaseCloudGame("genshin", "http://api", "coin", clear, {})
            result = await game.check_in()
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_check_in_limit_no_retry(self):
        resp = make_response(
            {
                "retcode": 0,
                "data": {
                    "free_time": {"free_time": "600", "send_freetime": "0"},
                    "play_card": {"short_msg": "active"},
                    "coin": {"coin_num": "50"},
                },
            }
        )
        http = mock_http(get_return=resp)
        with patch("hoyo_assistant.tasks.base.http", http):
            game = BaseCloudGame("genshin", "http://api", "coin", AsyncMock(), {})
            result = await game.check_in()
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_check_in_retry_success(self):
        first = make_response(
            {
                "retcode": 0,
                "data": {
                    "free_time": {"free_time": "300", "send_freetime": "0"},
                    "play_card": {"short_msg": "active"},
                    "coin": {"coin_num": "50"},
                },
            }
        )
        second = make_response(
            {
                "retcode": 0,
                "data": {
                    "free_time": {"free_time": "600", "send_freetime": "0"},
                    "play_card": {"short_msg": "active"},
                    "coin": {"coin_num": "50"},
                },
            }
        )
        http = mock_http(get_side_effect=[first, second])
        with patch("hoyo_assistant.tasks.base.http", http):
            game = BaseCloudGame("genshin", "http://api", "coin", AsyncMock(), {})
            result = await game.check_in(retry_on_limit=True)
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_check_in_retry_high_free_seconds(self):
        resp = make_response(
            {
                "retcode": 0,
                "data": {
                    "free_time": {"free_time": "700", "send_freetime": "0"},
                    "play_card": {"short_msg": "active"},
                    "coin": {"coin_num": "50"},
                },
            }
        )
        http = mock_http(get_return=resp)
        with patch("hoyo_assistant.tasks.base.http", http):
            game = BaseCloudGame("genshin", "http://api", "coin", AsyncMock(), {})
            result = await game.check_in(retry_on_limit=True)
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_check_in_token_invalid(self):
        resp = make_response({"retcode": -100})
        clear = AsyncMock()
        http = mock_http(get_return=resp)
        with patch("hoyo_assistant.tasks.base.http", http):
            game = BaseCloudGame("genshin", "http://api", "coin", clear, {})
            result = await game.check_in()
        clear.assert_awaited_once()
        assert game.had_error is True
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_check_in_error_retcode_and_exception(self):
        http = mock_http(get_return=make_response({"retcode": -1}, text_data="err"))
        with patch("hoyo_assistant.tasks.base.http", http):
            game = BaseCloudGame("genshin", "http://api", "coin", AsyncMock(), {})
            assert isinstance(await game.check_in(), str)
            assert game.had_error is True

        http_exc = mock_http()
        http_exc.get.side_effect = Exception("network error")
        with patch("hoyo_assistant.tasks.base.http", http_exc):
            game = BaseCloudGame("genshin", "http://api", "coin", AsyncMock(), {})
            assert isinstance(await game.check_in(), str)
            assert game.had_error is True


# ---------------------------------------------------------------------------
# CN GameCheckin tests
# ---------------------------------------------------------------------------


class TestGameCheckin:
    def test_init_and_set_headers(self, mock_cn_account):
        mock_cn_account["cookie"] = "account_id=123;stuid=123;stoken=v2_tok;"
        with _patch_cn(mock_cn_account):
            checkin = GameCheckin("hk4e_cn", "genshin", "Genshin", "act_id", "Traveler")
        assert checkin.game_id == "hk4e_cn"
        assert checkin.headers["Cookie"] == "account_id=123;"
        assert "stoken=" not in checkin.headers["Cookie"]
        assert "stuid=" not in checkin.headers["Cookie"]
        assert checkin.headers["x-rpc-device_id"] == "test-device-id"
        assert checkin.headers["User-Agent"].startswith("TestUA")
        assert "miHoYoBBS" in checkin.headers["User-Agent"]

    @pytest.mark.asyncio
    async def test_init_method_with_and_without_profiles(self, mock_cn_account):
        mock_account = MagicMock()
        mock_account.get_account_list = AsyncMock(
            return_value=[("Player", "uid123", "cn_gf01")]
        )
        resp = make_response(
            {"retcode": 0, "data": {"awards": [{"name": "item", "cnt": 1}]}}
        )
        http = mock_http(get_return=resp)
        with (
            _patch_cn(mock_cn_account),
            patch("hoyo_assistant.tasks.chinese.game_signin.http", http),
            patch("hoyo_assistant.tasks.chinese.game_signin.account", mock_account),
        ):
            checkin = GameCheckin("hk4e_cn", "genshin", "Genshin", "act_id", "Traveler")
            await checkin.init()
        assert checkin.profiles == [("Player", "uid123", "cn_gf01")]
        assert len(checkin.checkin_rewards) == 1

        mock_account.get_account_list = AsyncMock(return_value=[])
        with (
            _patch_cn(mock_cn_account),
            patch("hoyo_assistant.tasks.chinese.game_signin.account", mock_account),
        ):
            checkin = GameCheckin("hk4e_cn", "genshin", "Genshin", "act_id", "Traveler")
            await checkin.init()
        assert checkin.profiles == []

    @pytest.mark.asyncio
    async def test_get_checkin_rewards(self, mock_cn_account):
        fail_resp = make_response({"retcode": -1})
        success_resp = make_response(
            {"retcode": 0, "data": {"awards": [{"name": "item", "cnt": 1}]}}
        )
        http = mock_http(get_side_effect=[fail_resp, success_resp])
        with (
            _patch_cn(mock_cn_account),
            patch("hoyo_assistant.tasks.chinese.game_signin.http", http),
        ):
            checkin = GameCheckin("hk4e_cn", "genshin", "Genshin", "act_id", "Traveler")
            result = await checkin.get_checkin_rewards()
        assert result == [{"name": "item", "cnt": 1}]

    @pytest.mark.asyncio
    async def test_is_sign_paths(self, mock_cn_account):
        expired = make_response({"retcode": -100})
        success = make_response(
            {"retcode": 0, "data": {"is_sign": True, "total_sign_day": 2}}
        )
        http = mock_http(get_side_effect=[expired, success])
        mock_login = MagicMock()
        mock_login.get_web_cookie = MagicMock(return_value="cookie")
        mock_login.update_cookie_token = AsyncMock(return_value=True)
        with (
            _patch_cn(mock_cn_account),
            patch("hoyo_assistant.tasks.chinese.game_signin.http", http),
            patch("hoyo_assistant.tasks.chinese.game_signin.login", mock_login),
        ):
            checkin = GameCheckin("hk4e_cn", "genshin", "Genshin", "act_id", "Traveler")
            result = await checkin.is_sign("cn_gf01", "uid123")
        assert isinstance(result, dict)

        mock_login.update_cookie_token = AsyncMock(return_value=False)
        http_fail = mock_http(get_return=expired)
        with (
            _patch_cn(mock_cn_account),
            patch("hoyo_assistant.tasks.chinese.game_signin.http", http_fail),
            patch("hoyo_assistant.tasks.chinese.game_signin.login", mock_login),
            pytest.raises(CookieError),
        ):
            await checkin.is_sign("cn_gf01", "uid123")

    @pytest.mark.asyncio
    async def test_check_in_rate_limit_and_captcha(self, mock_cn_account):
        rate_resp = make_response({"retcode": 0}, status=429)
        success_resp = make_response({"retcode": 0, "data": {"success": 0}})
        http = mock_http(post_side_effect=[rate_resp, success_resp])
        with (
            _patch_cn(mock_cn_account),
            patch("hoyo_assistant.tasks.chinese.game_signin.RETRY_TIMES", 2),
            patch("hoyo_assistant.tasks.chinese.game_signin.http", http),
        ):
            checkin = GameCheckin("hk4e_cn", "genshin", "Genshin", "act_id", "Traveler")
            res = await checkin.check_in(("Player", "uid123", "cn_gf01"))
            assert res is success_resp

        captcha_resp = make_response(
            {
                "retcode": 0,
                "data": {"success": 1, "gt": "gt_val", "challenge": "ch_val"},
            }
        )
        http2 = mock_http(post_side_effect=[captcha_resp, success_resp])
        with (
            _patch_cn(mock_cn_account),
            patch("hoyo_assistant.tasks.chinese.game_signin.RETRY_TIMES", 2),
            patch("hoyo_assistant.tasks.chinese.game_signin.http", http2),
        ):
            checkin = GameCheckin("hk4e_cn", "genshin", "Genshin", "act_id", "Traveler")
            res2 = await checkin.check_in(("Player", "uid123", "cn_gf01"))
            assert res2 is success_resp
            assert http2.post.await_count == 2

    @pytest.mark.asyncio
    async def test_sign_account_variants(self, mock_cn_account):
        mock_cn_account["black_list"]["genshin"] = ["uid_blk"]
        with _patch_cn(mock_cn_account):
            checkin = GameCheckin("hk4e_cn", "genshin", "Genshin", "act_id", "Traveler")
            checkin.profiles = [("Blocked", "uid_blk", "cn_gf01")]
            checkin.is_sign = AsyncMock()
            await checkin.sign_account()
            checkin.is_sign.assert_not_awaited()

            checkin.profiles = [("Player", "uid123", "cn_gf01")]
            checkin.checkin_rewards = [{"name": "Day1", "cnt": 1}]
            checkin.is_sign = AsyncMock(
                return_value={
                    "is_sign": False,
                    "total_sign_day": 0,
                    "first_bind": False,
                }
            )
            checkin.check_in = AsyncMock(
                return_value=make_response({"retcode": 0, "data": {"success": 0}})
            )
            res = await checkin.sign_account()
            assert "Day1" in res

            checkin.checkin_rewards = []
            res_empty = await checkin.sign_account()
            assert "Player" in res_empty

    @pytest.mark.asyncio
    async def test_checkin_game_and_run_task(self, mock_cn_account):
        with _patch_cn(mock_cn_account):
            assert await checkin_game("genshin", Genshin, "Genshin") == ""
            assert await cn_run_task() == ""

        mock_cn_account["games"] = ["honkai2"]
        mock_instance = MagicMock()
        mock_instance.init = AsyncMock()
        mock_instance.sign_account = AsyncMock(return_value="done")
        with (
            _patch_cn(mock_cn_account),
            patch(
                "hoyo_assistant.tasks.chinese.game_signin.Honkai2",
                return_value=mock_instance,
            ),
        ):
            assert "done" in await cn_run_task()

    def test_subclasses_headers(self, mock_cn_account):
        with _patch_cn(mock_cn_account):
            assert Honkai2().game_id == "bh2_cn"
            assert Honkai3rd().headers["x-rpc-signgame"] == "bh3"
            assert TearsOfThemis().headers["x-rpc-signgame"] == "nxx"
            assert Genshin().headers["x-rpc-signgame"] == "hk4e"
            assert Honkaisr().headers["x-rpc-signgame"] == "hkrpg"
            assert ZZZ().headers["X-Rpc-Signgame"] == "zzz"


# ---------------------------------------------------------------------------
# Mihoyobbs tests
# ---------------------------------------------------------------------------


class TestMihoyobbs:
    def _make_bbs(self, mock_cn_account):
        mock_cn_account["bbs"]["forums"] = [2]
        mock_login = MagicMock()
        mock_login.get_stoken_cookie = MagicMock(return_value="test_stoken_cookie")
        mock_login.get_web_cookie = MagicMock(return_value="cookie")
        mock_login.update_cookie_token = AsyncMock(return_value=True)
        with (
            _patch_bbs(mock_cn_account),
            patch("hoyo_assistant.tasks.community.miyoushe.login", mock_login),
        ):
            return Mihoyobbs()

    def test_init_and_fp(self, mock_cn_account):
        mock_cn_account["cookie"] = "ltoken=l1;stuid=123;stoken=v2_s;"
        mock_cn_account["device"]["fp"] = "test_fp"
        bbs = self._make_bbs(mock_cn_account)
        assert bbs.headers.get("x-rpc-device_fp") == "test_fp"
        assert len(bbs.bbs_list) == 1

    def test_task_header_strips_stoken_and_stuid(self, mock_cn_account):
        mock_cn_account["bbs"]["forums"] = [2]
        mock_cn_account["cookie"] = "ltoken=l1;stuid=123;stoken=v1_tok;"
        with _patch_bbs(mock_cn_account):
            bbs = Mihoyobbs()
        assert bbs.headers["cookie"] == "stuid=123;stoken=v1_tok"
        assert "ltoken=l1;" in bbs.task_header["Cookie"]
        assert "stoken=" not in bbs.task_header["Cookie"]
        assert "stuid=" not in bbs.task_header["Cookie"]

    @pytest.mark.asyncio
    async def test_get_tasks_list_and_cookie_refresh(self, mock_cn_account):
        expired = make_response({"message": "err", "retcode": -100, "data": {}})
        success = make_response(
            {
                "message": "OK",
                "retcode": 0,
                "data": {
                    "can_get_points": 0,
                    "already_received_points": 10,
                    "total_points": 100,
                    "states": None,
                },
            }
        )
        http = mock_http(get_side_effect=[expired, success])
        mock_login = MagicMock()
        mock_login.get_stoken_cookie = MagicMock(return_value="cookie")
        mock_login.get_web_cookie = MagicMock(return_value="refreshed_web_cookie")
        mock_login.update_cookie_token = AsyncMock(return_value=True)
        mock_cn_account["bbs"]["forums"] = [2]
        with (
            _patch_bbs(mock_cn_account),
            patch("hoyo_assistant.tasks.community.miyoushe.login", mock_login),
            patch("hoyo_assistant.tasks.community.miyoushe.http", http),
        ):
            bbs = Mihoyobbs()
            await bbs.get_tasks_list()
        assert bbs.task_do["sign"] is True
        assert bbs.have_coins == 100
        assert bbs.task_header["Cookie"] == "refreshed_web_cookie"

    @pytest.mark.asyncio
    async def test_get_tasks_list_stoken_error(self, mock_cn_account):
        resp = make_response({"message": "err", "retcode": -100, "data": {}})
        http = mock_http(get_return=resp)
        mock_login = MagicMock()
        mock_login.get_stoken_cookie = MagicMock(return_value="cookie")
        mock_login.get_web_cookie = MagicMock(return_value="cookie")
        mock_login.update_cookie_token = AsyncMock(return_value=False)
        mock_cn_account["bbs"]["forums"] = [2]
        with (
            _patch_bbs(mock_cn_account),
            patch("hoyo_assistant.tasks.community.miyoushe.login", mock_login),
            patch("hoyo_assistant.tasks.community.miyoushe.http", http),
            patch(
                "hoyo_assistant.tasks.community.miyoushe.setting.clear_stoken",
                new=AsyncMock(),
            ) as mock_clear_stoken,
            patch(
                "hoyo_assistant.tasks.community.miyoushe.setting.clear_cookie",
                new=AsyncMock(),
            ) as mock_clear_cookie,
        ):
            bbs = Mihoyobbs()
            with pytest.raises(StokenError):
                await bbs.get_tasks_list()
        mock_clear_stoken.assert_awaited_once()
        mock_clear_cookie.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_get_tasks_list_transient_error_preserves_credentials(
        self, mock_cn_account
    ):
        resp = make_response({"message": "server err", "retcode": -500, "data": None})
        http = mock_http(get_return=resp)
        mock_login = MagicMock()
        mock_login.get_stoken_cookie = MagicMock(return_value="cookie")
        mock_login.get_web_cookie = MagicMock(return_value="cookie")
        mock_login.update_cookie_token = AsyncMock(return_value=False)
        mock_cn_account["bbs"]["forums"] = [2]
        with (
            _patch_bbs(mock_cn_account),
            patch("hoyo_assistant.tasks.community.miyoushe.login", mock_login),
            patch("hoyo_assistant.tasks.community.miyoushe.http", http),
            patch(
                "hoyo_assistant.tasks.community.miyoushe.setting.clear_stoken",
                new=AsyncMock(),
            ) as mock_clear_stoken,
            patch(
                "hoyo_assistant.tasks.community.miyoushe.setting.clear_cookie",
                new=AsyncMock(),
            ) as mock_clear_cookie,
        ):
            bbs = Mihoyobbs()
            with pytest.raises(RuntimeError):
                await bbs.get_tasks_list()
        mock_clear_stoken.assert_not_awaited()
        mock_clear_cookie.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_signing_paths(self, mock_cn_account):
        bbs = self._make_bbs(mock_cn_account)
        bbs.task_do["sign"] = False
        http = mock_http(post_return=make_response({"retcode": 0, "message": "OK"}))
        with patch("hoyo_assistant.tasks.community.miyoushe.http", http):
            await bbs.signing()
        http.post.assert_awaited_once()

        http_captcha = mock_http(
            post_return=make_response({"retcode": 1034, "message": "captcha"})
        )
        with patch("hoyo_assistant.tasks.community.miyoushe.http", http_captcha):
            await bbs.signing()
        http_captcha.post.assert_awaited_once()

        http_exp = mock_http(
            post_return=make_response({"retcode": -100, "message": "err"})
        )
        with (
            patch("hoyo_assistant.tasks.community.miyoushe.http", http_exp),
            patch(
                "hoyo_assistant.tasks.community.miyoushe.setting.clear_stoken",
                new=AsyncMock(),
            ) as mock_clear,
        ):
            with pytest.raises(StokenError):
                await bbs.signing()
        mock_clear.assert_awaited_once()


# ---------------------------------------------------------------------------
# CN & OS CloudGames tests
# ---------------------------------------------------------------------------


class TestCloudGames:
    def test_cn_build_headers(self):
        headers = cn_cloud_games._build_headers(
            "token",
            "hk4e_cn",
            "https://hostname.com",
            app_id="4",
            device_id="dev-1",
            device_fp="fp-1",
        )
        assert headers["x-rpc-combo_token"] == "token"
        assert headers["x-rpc-client_type"] == "4"
        assert headers["x-rpc-app_id"] == "4"
        assert headers["x-rpc-device_id"] == "dev-1"
        assert headers["x-rpc-device_fp"] == "fp-1"
        assert headers["Host"] == "hostname.com"
        plain_headers = cn_cloud_games._build_headers("token", "hk4e_cn", None)
        assert "Host" not in plain_headers
        assert "x-rpc-device_id" not in plain_headers

    @pytest.mark.asyncio
    async def test_cn_run_task_with_and_without_tokens(self, mock_cn_account):
        with _patch_cn_cloud(mock_cn_account):
            assert await cn_cloud_games.run_task() == ""

        mock_cn_account["cloud"]["genshin"] = "test_token"
        with (
            _patch_cn_cloud(mock_cn_account),
            patch.object(
                BaseCloudGame, "check_in", new=AsyncMock(return_value="cn cloud ok")
            ),
        ):
            assert "cn cloud ok" in await cn_cloud_games.run_task()

    def test_os_build_headers(self):
        headers = os_cloud_games._build_headers("token", "hk4e_global", "en-us")
        assert headers["x-rpc-combo_token"] == "token"
        assert headers["x-rpc-language"] == "en-us"

    @pytest.mark.asyncio
    async def test_os_run_task_with_and_without_tokens(self, mock_os_account):
        with _patch_os_cloud(mock_os_account):
            assert await os_cloud_games.run_task() == ""

        mock_os_account["cloud"]["zzz"] = "os_tok"
        with (
            _patch_os_cloud(mock_os_account),
            patch.object(
                BaseCloudGame, "check_in", new=AsyncMock(return_value="os cloud ok")
            ),
        ):
            assert "os cloud ok" in await os_cloud_games.run_task()


# ---------------------------------------------------------------------------
# OS GameSignin tests
# ---------------------------------------------------------------------------


class TestOSGameSignin:
    @pytest.mark.asyncio
    async def test_uses_desktop_ua_by_default_and_respects_custom_ua(
        self, mock_os_account
    ):
        mock_os_account["cookie"] = "ltoken_v2=xyz; ltuid_v2=123"
        info_resp = make_response({"data": {"is_sign": True, "first_bind": False}})
        mock_get = AsyncMock(return_value=info_resp)
        with (
            _patch_os_signin(mock_os_account),
            patch("hoyo_assistant.tasks.overseas.game_signin.http.get", mock_get),
        ):
            await os_game_signin.hoyo_checkin(
                os_game_signin.API_OS_ACT_HSR,
                os_game_signin.ACT_ID_OS_HONKAI_SR,
                "HSR",
            )
        assert mock_get.call_args.kwargs["headers"]["User-Agent"] == DESKTOP_BROWSER_UA

        mock_os_account["user_agent"] = "CustomOSAgent/1.0"
        with (
            _patch_os_signin(mock_os_account),
            patch("hoyo_assistant.tasks.overseas.game_signin.http.get", mock_get),
        ):
            await os_game_signin.hoyo_checkin(
                os_game_signin.API_OS_ACT_ZZZ,
                os_game_signin.ACT_ID_OS_ZZZ,
                "ZZZ",
            )
        assert mock_get.call_args.kwargs["headers"]["User-Agent"] == "CustomOSAgent/1.0"
        assert mock_get.call_args.kwargs["headers"]["x-rpc-signgame"] == "zzz"

    @pytest.mark.asyncio
    async def test_hoyo_checkin_success_and_day1_reward(self, mock_os_account):
        mock_os_account["cookie"] = "ltoken_v2=xyz; ltuid_v2=123"
        info_resp = make_response(
            {
                "retcode": 0,
                "data": {
                    "is_sign": False,
                    "first_bind": False,
                    "total_sign_day": 0,
                    "today": "2026-11-24",
                },
            }
        )
        award_resp = make_response(
            {
                "data": {
                    "awards": [
                        {"name": "Day1Item", "cnt": 3},
                        {"name": "Day30Item", "cnt": 999},
                    ]
                }
            }
        )
        sign_resp = make_response({"retcode": 0, "data": {"code": "ok"}})

        async def fake_get(url, **kwargs):
            return info_resp if "/info" in url else award_resp

        with (
            _patch_os_signin(mock_os_account),
            patch(
                "hoyo_assistant.tasks.overseas.game_signin.http.get",
                side_effect=fake_get,
            ),
            patch(
                "hoyo_assistant.tasks.overseas.game_signin.http.post",
                AsyncMock(return_value=sign_resp),
            ),
        ):
            res = await os_game_signin.hoyo_checkin(
                os_game_signin.API_OS_ACT, os_game_signin.ACT_ID_OS_GENSHIN, "Genshin"
            )
        assert "Day1Item" in res
        assert "Day30Item" not in res

    @pytest.mark.asyncio
    async def test_run_task_built_in_and_custom_games(self, mock_os_account):
        mock_os_account["cookie"] = "ltuid_v2=1; ltoken_v2=2"
        mock_os_account["games"] = ["genshin", "tears_of_themis"]
        mock_os_account["custom_games"] = {
            "planet": {
                "enable": True,
                "name": "Petit Planet",
                "act_id": "e20261204000001",
                "signgame": "planet",
            }
        }
        mock_checkin = AsyncMock(return_value="os ok")
        with (
            _patch_os_signin(mock_os_account),
            patch.object(os_game_signin, "hoyo_checkin", mock_checkin),
        ):
            res = await os_game_signin.run_task()
        assert "os ok" in res
        assert mock_checkin.await_count == 3


class TestNewGameSyncAndCustomCheckin:
    @pytest.mark.asyncio
    async def test_fetch_bbs_game_list_and_sync(self, mock_cn_account):
        resp = make_response(
            {
                "retcode": 0,
                "data": {
                    "list": [
                        {
                            "id": 10,
                            "name": "星布谷地",
                            "en_name": "planet",
                            "op_name": "hyg",
                        }
                    ]
                },
            }
        )
        http = mock_http(get_return=resp)
        with patch("hoyo_assistant.tasks.community.miyoushe.http", http):
            games = await fetch_bbs_game_list()
        assert games[10]["name"] == "星布谷地"

        mock_cn_account["bbs"]["forums"] = [2, 11]
        mock_cn_account["cookie"] = "stuid=123;stoken=v1_tok;"
        remote = {
            11: {
                "id": "11",
                "name": "新游戏社区",
                "en_name": "newgame",
                "op_name": "ng",
            }
        }
        with (
            _patch_bbs(mock_cn_account),
            patch(
                "hoyo_assistant.tasks.community.miyoushe.login.get_stoken_cookie",
                return_value="stuid=123;stoken=v1_tok",
            ),
            patch(
                "hoyo_assistant.tasks.community.miyoushe.fetch_bbs_game_list",
                new=AsyncMock(return_value=remote),
            ),
        ):
            bbs = Mihoyobbs()
            assert [f["id"] for f in bbs.bbs_list] == ["2"]
            await bbs.sync_unknown_forums()
            assert [f["id"] for f in bbs.bbs_list] == ["2", "11"]

    @pytest.mark.asyncio
    async def test_custom_cn_game_checkin_and_run_task(self, mock_cn_account):
        spec = {
            "enable": True,
            "name": "星布谷地",
            "game_biz": "hyg_cn",
            "act_id": "e20261204000001",
            "signgame": "planet",
            "api_base": "https://api-takumi.mihoyo.com/event/luna/hyg/",
            "origin": "https://act.mihoyo.com",
            "referer": "https://act.mihoyo.com/",
            "player_name": "旅居者",
            "black_list": ["10001"],
        }
        mock_cn_account["custom_games"] = {"planet": spec}
        with _patch_cn(mock_cn_account):
            game = CustomCNGameCheckin("planet", spec)
            assert game.headers["x-rpc-signgame"] == "planet"
            assert game._get_black_list() == ["10001"]

        fake_instance = MagicMock()
        fake_instance.init = AsyncMock()
        fake_instance.sign_account = AsyncMock(return_value="planet ok")
        with (
            _patch_cn(mock_cn_account),
            patch(
                "hoyo_assistant.tasks.chinese.game_signin.CustomCNGameCheckin",
                return_value=fake_instance,
            ) as mock_cls,
        ):
            res = await cn_run_task()
        assert "planet ok" in res
        mock_cls.assert_called_once_with("planet", spec)

    @pytest.mark.asyncio
    async def test_os_checkin_failure_sets_had_error_flag(self, mock_os_account):
        mock_os_account["cookie"] = "ltoken_v2=bad; ltuid_v2=1"
        err_resp = make_response({"retcode": -100, "message": "Not logged in"})
        with (
            _patch_os_signin(mock_os_account),
            patch(
                "hoyo_assistant.tasks.overseas.game_signin.http.get",
                new=AsyncMock(return_value=err_resp),
            ),
        ):
            res = await os_game_signin.hoyo_checkin(
                os_game_signin.API_OS_ACT, os_game_signin.ACT_ID_OS_GENSHIN, "Genshin"
            )
        assert res.had_error is True
        assert res.had_success is False

    @pytest.mark.asyncio
    async def test_cn_signin_non_captcha_failure_not_misclassified(
        self, mock_cn_account
    ):
        with _patch_cn(mock_cn_account):
            checkin = GameCheckin("hk4e_cn", "genshin", "Genshin", "act_id", "Traveler")
            checkin.profiles = [("Player", "uid123", "cn_gf01")]
            checkin.is_sign = AsyncMock(
                return_value={
                    "is_sign": False,
                    "total_sign_day": 0,
                    "first_bind": False,
                }
            )
            checkin.check_in = AsyncMock(
                return_value=make_response({"retcode": -500, "message": "busy"})
            )
            res = await checkin.sign_account()
        assert res.had_error is True
        assert res.had_captcha is False
        assert "验证码" not in res
        assert "Captcha" not in res

    @pytest.mark.asyncio
    async def test_mihoyobbs_skips_round2_when_all_forums_hit_captcha(
        self, mock_cn_account
    ):
        mock_cn_account["cookie"] = "ltoken=l1;stuid=123;stoken=v1_tok;"
        mock_cn_account["bbs"] = {"enable": True, "forums": [2, 5]}
        with _patch_bbs(mock_cn_account):
            bbs = Mihoyobbs()
        bbs.init = AsyncMock()
        bbs.today_get_coins = 30
        bbs.today_have_get_coins = 0
        bbs.have_coins = 100
        bbs.get_tasks_list = AsyncMock()
        http = mock_http(
            post_return=make_response({"retcode": 1034, "message": "captcha"})
        )
        with (
            patch("hoyo_assistant.tasks.community.miyoushe.http", http),
            patch(
                "hoyo_assistant.tasks.community.miyoushe.tools.get_ds2",
                return_value="ds",
            ),
        ):
            report = await bbs.run_task()
        assert report.had_captcha is True
        assert report.had_error is False
        assert http.post.await_count == 2
        bbs.get_tasks_list.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_mihoyobbs_runs_round2_when_partial_success(self, mock_cn_account):
        mock_cn_account["cookie"] = "ltoken=l1;stuid=123;stoken=v1_tok;"
        mock_cn_account["bbs"] = {"enable": True, "forums": [2, 5]}
        with _patch_bbs(mock_cn_account):
            bbs = Mihoyobbs()
        bbs.init = AsyncMock()
        bbs.today_get_coins = 30
        bbs.today_have_get_coins = 0
        bbs.have_coins = 100
        bbs.get_tasks_list = AsyncMock()
        http = mock_http(
            post_side_effect=[
                make_response({"retcode": 0, "message": "OK"}),
                make_response({"retcode": 1034, "message": "captcha"}),
                make_response({"retcode": 1034, "message": "captcha"}),
                make_response({"retcode": 1034, "message": "captcha"}),
            ]
        )
        with (
            patch("hoyo_assistant.tasks.community.miyoushe.http", http),
            patch(
                "hoyo_assistant.tasks.community.miyoushe.tools.get_ds2",
                return_value="ds",
            ),
        ):
            report = await bbs.run_task()
        assert report.had_captcha is True
        assert http.post.await_count == 4
        # Round 1 had partial success -> proceeded to round 2;
        # Round 2 hit all-captcha -> skipped trailing get_tasks_list().
        assert bbs.get_tasks_list.await_count == 1
