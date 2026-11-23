"""Tests for tasks/ modules."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hoyo_assistant.core import CookieError, StokenError
from hoyo_assistant.tasks.base import BaseCloudGame
from hoyo_assistant.tasks.chinese import cloud_games as cn_cloud_games
from hoyo_assistant.tasks.chinese.game_signin import (
    ZZZ,
    GameCheckin,
    Genshin,
    Honkai2,
    Honkai3rd,
    Honkaisr,
    TearsOfThemis,
    checkin_game,
    run_task as cn_run_task,
)
from hoyo_assistant.tasks.community.miyoushe import Mihoyobbs
from hoyo_assistant.tasks.overseas import (
    cloud_games as os_cloud_games,
    game_signin as os_game_signin,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
    """Patch asyncio.sleep to avoid slow tests."""
    with patch("asyncio.sleep", new=AsyncMock()):
        yield


# ---------------------------------------------------------------------------
# BaseCloudGame tests (tasks/base/__init__.py)
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
        clear = AsyncMock()
        http = mock_http(get_return=resp)
        with patch("hoyo_assistant.tasks.base.http", http):
            game = BaseCloudGame("genshin", "http://api", "coin", clear, {})
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
        clear = AsyncMock()
        http = mock_http(get_side_effect=[first, second])
        with patch("hoyo_assistant.tasks.base.http", http):
            game = BaseCloudGame("genshin", "http://api", "coin", clear, {})
            result = await game.check_in(retry_on_limit=True)
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_check_in_retry_fail(self):
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
                    "free_time": {"free_time": "300", "send_freetime": "0"},
                    "play_card": {"short_msg": "active"},
                    "coin": {"coin_num": "50"},
                },
            }
        )
        clear = AsyncMock()
        http = mock_http(get_side_effect=[first, second])
        with patch("hoyo_assistant.tasks.base.http", http):
            game = BaseCloudGame("genshin", "http://api", "coin", clear, {})
            result = await game.check_in(retry_on_limit=True)
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_check_in_retry_high_free_seconds(self):
        """retry_on_limit=True but free_seconds >= 600 → no retry, limit_fail."""
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
        clear = AsyncMock()
        http = mock_http(get_return=resp)
        with patch("hoyo_assistant.tasks.base.http", http):
            game = BaseCloudGame("genshin", "http://api", "coin", clear, {})
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
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_check_in_error_retcode(self):
        resp = make_response({"retcode": -1}, text_data="error msg")
        clear = AsyncMock()
        http = mock_http(get_return=resp)
        with patch("hoyo_assistant.tasks.base.http", http):
            game = BaseCloudGame("genshin", "http://api", "coin", clear, {})
            result = await game.check_in()
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_check_in_exception(self):
        clear = AsyncMock()
        http = mock_http()
        http.get.side_effect = Exception("network error")
        with patch("hoyo_assistant.tasks.base.http", http):
            game = BaseCloudGame("genshin", "http://api", "coin", clear, {})
            result = await game.check_in()
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# GameCheckin tests (tasks/chinese/game_signin.py)
# ---------------------------------------------------------------------------


class TestGameCheckin:
    def test_init(self, mock_config):
        with patch("hoyo_assistant.tasks.chinese.game_signin.config", mock_config):
            checkin = GameCheckin("hk4e_cn", "genshin", "Genshin", "act_id", "Traveler")
        assert checkin.game_id == "hk4e_cn"
        assert checkin.game_mid == "genshin"
        assert checkin.game_name == "Genshin"
        assert checkin.act_id == "act_id"
        assert checkin.player_name == "Traveler"
        assert "Cookie" in checkin.headers
        assert checkin.headers["x-rpc-device_id"] == "test-device-id"
        assert checkin.profiles == []

    def test_set_headers(self, mock_config):
        with patch("hoyo_assistant.tasks.chinese.game_signin.config", mock_config):
            checkin = GameCheckin("hk4e_cn", "genshin", "Genshin", "act_id", "Traveler")
            checkin.set_headers()
            assert checkin.headers["Cookie"] == mock_config["cn"]["cookie"]
            # UA comes from resolve_user_agent(client.user_agent): custom value
            # "TestUA" gets the miHoYoBBS/{version} suffix appended.
            assert checkin.headers["User-Agent"].startswith("TestUA")
            assert "miHoYoBBS" in checkin.headers["User-Agent"]
            assert "Referer" in checkin.headers

    @pytest.mark.asyncio
    async def test_init_method_with_profiles(self, mock_config):
        mock_account = MagicMock()
        mock_account.get_account_list = AsyncMock(
            return_value=[("Player", "uid123", "cn_gf01")]
        )
        resp = make_response(
            {
                "retcode": 0,
                "data": {"awards": [{"name": "item", "cnt": 1}]},
            }
        )
        http = mock_http(get_return=resp)
        with (
            patch("hoyo_assistant.tasks.chinese.game_signin.config", mock_config),
            patch("hoyo_assistant.tasks.chinese.game_signin.http", http),
            patch("hoyo_assistant.tasks.chinese.game_signin.account", mock_account),
        ):
            checkin = GameCheckin("hk4e_cn", "genshin", "Genshin", "act_id", "Traveler")
            await checkin.init()
        assert checkin.profiles == [("Player", "uid123", "cn_gf01")]
        assert len(checkin.checkin_rewards) > 0

    @pytest.mark.asyncio
    async def test_init_method_no_profiles(self, mock_config):
        mock_account = MagicMock()
        mock_account.get_account_list = AsyncMock(return_value=[])
        with (
            patch("hoyo_assistant.tasks.chinese.game_signin.config", mock_config),
            patch("hoyo_assistant.tasks.chinese.game_signin.account", mock_account),
        ):
            checkin = GameCheckin("hk4e_cn", "genshin", "Genshin", "act_id", "Traveler")
            await checkin.init()
        assert checkin.profiles == []
        assert checkin.checkin_rewards == []

    @pytest.mark.asyncio
    async def test_get_checkin_rewards_success(self, mock_config):
        resp = make_response(
            {
                "retcode": 0,
                "data": {"awards": [{"name": "item", "cnt": 1}]},
            }
        )
        http = mock_http(get_return=resp)
        with (
            patch("hoyo_assistant.tasks.chinese.game_signin.config", mock_config),
            patch("hoyo_assistant.tasks.chinese.game_signin.http", http),
        ):
            checkin = GameCheckin("hk4e_cn", "genshin", "Genshin", "act_id", "Traveler")
            result = await checkin.get_checkin_rewards()
        assert result == [{"name": "item", "cnt": 1}]

    @pytest.mark.asyncio
    async def test_get_checkin_rewards_retry_then_success(self, mock_config):
        fail_resp = make_response({"retcode": -1})
        success_resp = make_response(
            {
                "retcode": 0,
                "data": {"awards": [{"name": "item", "cnt": 1}]},
            }
        )
        http = mock_http(get_side_effect=[fail_resp, success_resp])
        with (
            patch("hoyo_assistant.tasks.chinese.game_signin.config", mock_config),
            patch("hoyo_assistant.tasks.chinese.game_signin.http", http),
        ):
            checkin = GameCheckin("hk4e_cn", "genshin", "Genshin", "act_id", "Traveler")
            result = await checkin.get_checkin_rewards()
        assert result == [{"name": "item", "cnt": 1}]

    @pytest.mark.asyncio
    async def test_get_checkin_rewards_all_fail(self, mock_config):
        fail_resp = make_response({"retcode": -1})
        http = mock_http(get_return=fail_resp)
        with (
            patch("hoyo_assistant.tasks.chinese.game_signin.config", mock_config),
            patch("hoyo_assistant.tasks.chinese.game_signin.http", http),
        ):
            checkin = GameCheckin("hk4e_cn", "genshin", "Genshin", "act_id", "Traveler")
            result = await checkin.get_checkin_rewards()
        assert result == []

    @pytest.mark.asyncio
    async def test_get_checkin_rewards_exception(self, mock_config):
        http = mock_http()
        http.get.side_effect = Exception("network error")
        with (
            patch("hoyo_assistant.tasks.chinese.game_signin.config", mock_config),
            patch("hoyo_assistant.tasks.chinese.game_signin.http", http),
        ):
            checkin = GameCheckin("hk4e_cn", "genshin", "Genshin", "act_id", "Traveler")
            result = await checkin.get_checkin_rewards()
        assert result == []

    @pytest.mark.asyncio
    async def test_is_sign_success(self, mock_config):
        resp = make_response(
            {
                "retcode": 0,
                "data": {"is_sign": False, "total_sign_day": 1},
            }
        )
        http = mock_http(get_return=resp)
        with (
            patch("hoyo_assistant.tasks.chinese.game_signin.config", mock_config),
            patch("hoyo_assistant.tasks.chinese.game_signin.http", http),
        ):
            checkin = GameCheckin("hk4e_cn", "genshin", "Genshin", "act_id", "Traveler")
            result = await checkin.is_sign("cn_gf01", "uid123")
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_is_sign_cookie_refresh(self, mock_config):
        expired = make_response({"retcode": -100})
        success = make_response(
            {
                "retcode": 0,
                "data": {"is_sign": True, "total_sign_day": 2},
            }
        )
        http = mock_http(get_side_effect=[expired, success])
        mock_login = MagicMock()
        mock_login.update_cookie_token = AsyncMock(return_value=True)
        with (
            patch("hoyo_assistant.tasks.chinese.game_signin.config", mock_config),
            patch("hoyo_assistant.tasks.chinese.game_signin.http", http),
            patch("hoyo_assistant.tasks.chinese.game_signin.login", mock_login),
        ):
            checkin = GameCheckin("hk4e_cn", "genshin", "Genshin", "act_id", "Traveler")
            result = await checkin.is_sign("cn_gf01", "uid123")
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_is_sign_cookie_invalid(self, mock_config):
        resp = make_response({"retcode": -100})
        http = mock_http(get_return=resp)
        mock_login = MagicMock()
        mock_login.update_cookie_token = AsyncMock(return_value=False)
        with (
            patch("hoyo_assistant.tasks.chinese.game_signin.config", mock_config),
            patch("hoyo_assistant.tasks.chinese.game_signin.http", http),
            patch("hoyo_assistant.tasks.chinese.game_signin.login", mock_login),
        ):
            checkin = GameCheckin("hk4e_cn", "genshin", "Genshin", "act_id", "Traveler")
            with pytest.raises(CookieError):
                await checkin.is_sign("cn_gf01", "uid123")

    @pytest.mark.asyncio
    async def test_check_in_success(self, mock_config):
        resp = make_response(
            {
                "retcode": 0,
                "data": {"success": 0},
            }
        )
        http = mock_http(post_return=resp)
        with (
            patch("hoyo_assistant.tasks.chinese.game_signin.config", mock_config),
            patch("hoyo_assistant.tasks.chinese.game_signin.http", http),
        ):
            checkin = GameCheckin("hk4e_cn", "genshin", "Genshin", "act_id", "Traveler")
            result = await checkin.check_in(("Player", "uid123", "cn_gf01"))
        assert result is not None

    @pytest.mark.asyncio
    async def test_check_in_rate_limit(self, mock_config):
        rate_resp = make_response({"retcode": 0}, status=429)
        success_resp = make_response({"retcode": 0, "data": {"success": 0}})
        http = mock_http(post_side_effect=[rate_resp, success_resp])
        mock_config["cn"]["retries"] = 2
        with (
            patch("hoyo_assistant.tasks.chinese.game_signin.config", mock_config),
            patch("hoyo_assistant.tasks.chinese.game_signin.http", http),
        ):
            checkin = GameCheckin("hk4e_cn", "genshin", "Genshin", "act_id", "Traveler")
            result = await checkin.check_in(("Player", "uid123", "cn_gf01"))
        assert result is not None

    @pytest.mark.asyncio
    async def test_check_in_captcha_dict(self, mock_config):
        captcha_resp = make_response(
            {
                "retcode": 0,
                "data": {"success": 1, "gt": "gt_val", "challenge": "ch_val"},
            }
        )
        success_resp = make_response({"retcode": 0, "data": {"success": 0}})
        http = mock_http(post_side_effect=[captcha_resp, success_resp])
        mock_captcha = MagicMock()
        mock_captcha.game_captcha = MagicMock(
            return_value={"validate": "val", "challenge": "new_chall"}
        )
        mock_config["cn"]["retries"] = 2
        with (
            patch("hoyo_assistant.tasks.chinese.game_signin.config", mock_config),
            patch("hoyo_assistant.tasks.chinese.game_signin.http", http),
            patch("hoyo_assistant.tasks.chinese.game_signin.captcha", mock_captcha),
        ):
            checkin = GameCheckin("hk4e_cn", "genshin", "Genshin", "act_id", "Traveler")
            result = await checkin.check_in(("Player", "uid123", "cn_gf01"))
        assert result is not None

    @pytest.mark.asyncio
    async def test_check_in_captcha_none(self, mock_config):
        captcha_resp = make_response(
            {
                "retcode": 0,
                "data": {"success": 1, "gt": "gt_val", "challenge": "ch_val"},
            }
        )
        success_resp = make_response({"retcode": 0, "data": {"success": 0}})
        http = mock_http(post_side_effect=[captcha_resp, success_resp])
        mock_captcha = MagicMock()
        mock_captcha.game_captcha = MagicMock(return_value=None)
        mock_config["cn"]["retries"] = 2
        with (
            patch("hoyo_assistant.tasks.chinese.game_signin.config", mock_config),
            patch("hoyo_assistant.tasks.chinese.game_signin.http", http),
            patch("hoyo_assistant.tasks.chinese.game_signin.captcha", mock_captcha),
        ):
            checkin = GameCheckin("hk4e_cn", "genshin", "Genshin", "act_id", "Traveler")
            result = await checkin.check_in(("Player", "uid123", "cn_gf01"))
        assert result is not None

    @pytest.mark.asyncio
    async def test_sign_account_no_profiles(self, mock_config):
        with patch("hoyo_assistant.tasks.chinese.game_signin.config", mock_config):
            checkin = GameCheckin("hk4e_cn", "genshin", "Genshin", "act_id", "Traveler")
            checkin.profiles = []
            result = await checkin.sign_account()
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_sign_account_blacklisted(self, mock_config):
        mock_config["cn"]["black_list"]["genshin"] = ["uid123"]
        with patch("hoyo_assistant.tasks.chinese.game_signin.config", mock_config):
            checkin = GameCheckin("hk4e_cn", "genshin", "Genshin", "act_id", "Traveler")
            checkin.profiles = [("Player", "uid123", "cn_gf01")]
            checkin.checkin_rewards = [{"name": "item", "cnt": 1}] * 5
            checkin.is_sign = AsyncMock()
            result = await checkin.sign_account()
        assert isinstance(result, str)
        checkin.is_sign.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_sign_account_already_signed(self, mock_config):
        with patch("hoyo_assistant.tasks.chinese.game_signin.config", mock_config):
            checkin = GameCheckin("hk4e_cn", "genshin", "Genshin", "act_id", "Traveler")
            checkin.profiles = [("Player", "uid123", "cn_gf01")]
            checkin.checkin_rewards = [{"name": "item", "cnt": 1}] * 5
            checkin.is_sign = AsyncMock(
                return_value={"is_sign": True, "total_sign_day": 2, "first_bind": False}
            )
            result = await checkin.sign_account()
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_sign_account_first_bind(self, mock_config):
        with patch("hoyo_assistant.tasks.chinese.game_signin.config", mock_config):
            checkin = GameCheckin("hk4e_cn", "genshin", "Genshin", "act_id", "Traveler")
            checkin.profiles = [("Player", "uid123", "cn_gf01")]
            checkin.checkin_rewards = [{"name": "item", "cnt": 1}] * 5
            checkin.is_sign = AsyncMock(
                return_value={"is_sign": False, "total_sign_day": 1, "first_bind": True}
            )
            result = await checkin.sign_account()
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_sign_account_success(self, mock_config):
        with patch("hoyo_assistant.tasks.chinese.game_signin.config", mock_config):
            checkin = GameCheckin("hk4e_cn", "genshin", "Genshin", "act_id", "Traveler")
            checkin.profiles = [("Player", "uid123", "cn_gf01")]
            checkin.checkin_rewards = [{"name": "item", "cnt": 1}] * 5
            checkin.is_sign = AsyncMock(
                return_value={
                    "is_sign": False,
                    "total_sign_day": 1,
                    "first_bind": False,
                }
            )
            resp = make_response({"retcode": 0, "data": {"success": 0}})
            checkin.check_in = AsyncMock(return_value=resp)
            result = await checkin.sign_account()
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_sign_account_already_signed_retcode(self, mock_config):
        with patch("hoyo_assistant.tasks.chinese.game_signin.config", mock_config):
            checkin = GameCheckin("hk4e_cn", "genshin", "Genshin", "act_id", "Traveler")
            checkin.profiles = [("Player", "uid123", "cn_gf01")]
            checkin.checkin_rewards = [{"name": "item", "cnt": 1}] * 5
            checkin.is_sign = AsyncMock(
                return_value={
                    "is_sign": False,
                    "total_sign_day": 1,
                    "first_bind": False,
                }
            )
            resp = make_response({"retcode": -5003, "data": {}})
            checkin.check_in = AsyncMock(return_value=resp)
            result = await checkin.sign_account()
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_sign_account_rate_limit(self, mock_config):
        with patch("hoyo_assistant.tasks.chinese.game_signin.config", mock_config):
            checkin = GameCheckin("hk4e_cn", "genshin", "Genshin", "act_id", "Traveler")
            checkin.profiles = [("Player", "uid123", "cn_gf01")]
            checkin.checkin_rewards = [{"name": "item", "cnt": 1}] * 5
            checkin.is_sign = AsyncMock(
                return_value={
                    "is_sign": False,
                    "total_sign_day": 1,
                    "first_bind": False,
                }
            )
            resp = make_response({}, status=429)
            checkin.check_in = AsyncMock(return_value=resp)
            result = await checkin.sign_account()
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_sign_account_captcha_fail(self, mock_config):
        with patch("hoyo_assistant.tasks.chinese.game_signin.config", mock_config):
            checkin = GameCheckin("hk4e_cn", "genshin", "Genshin", "act_id", "Traveler")
            checkin.profiles = [("Player", "uid123", "cn_gf01")]
            checkin.checkin_rewards = [{"name": "item", "cnt": 1}] * 5
            checkin.is_sign = AsyncMock(
                return_value={
                    "is_sign": False,
                    "total_sign_day": 1,
                    "first_bind": False,
                }
            )
            resp = make_response({"retcode": 0, "data": {"success": 1}})
            checkin.check_in = AsyncMock(return_value=resp)
            result = await checkin.sign_account()
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_sign_account_generic_fail(self, mock_config):
        with patch("hoyo_assistant.tasks.chinese.game_signin.config", mock_config):
            checkin = GameCheckin("hk4e_cn", "genshin", "Genshin", "act_id", "Traveler")
            checkin.profiles = [("Player", "uid123", "cn_gf01")]
            checkin.checkin_rewards = [{"name": "item", "cnt": 1}] * 5
            checkin.is_sign = AsyncMock(
                return_value={
                    "is_sign": False,
                    "total_sign_day": 1,
                    "first_bind": False,
                }
            )
            resp = make_response({"retcode": -1, "data": None})
            checkin.check_in = AsyncMock(return_value=resp)
            result = await checkin.sign_account()
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_sign_account_is_sign_not_dict(self, mock_config):
        with patch("hoyo_assistant.tasks.chinese.game_signin.config", mock_config):
            checkin = GameCheckin("hk4e_cn", "genshin", "Genshin", "act_id", "Traveler")
            checkin.profiles = [("Player", "uid123", "cn_gf01")]
            checkin.checkin_rewards = [{"name": "item", "cnt": 1}] * 5
            checkin.is_sign = AsyncMock(return_value="not_a_dict")
            result = await checkin.sign_account()
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_sign_account_check_in_none(self, mock_config):
        with patch("hoyo_assistant.tasks.chinese.game_signin.config", mock_config):
            checkin = GameCheckin("hk4e_cn", "genshin", "Genshin", "act_id", "Traveler")
            checkin.profiles = [("Player", "uid123", "cn_gf01")]
            checkin.checkin_rewards = [{"name": "item", "cnt": 1}] * 5
            checkin.is_sign = AsyncMock(
                return_value={
                    "is_sign": False,
                    "total_sign_day": 1,
                    "first_bind": False,
                }
            )
            checkin.check_in = AsyncMock(return_value=None)
            result = await checkin.sign_account()
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_checkin_game_disabled(self, mock_config):
        with patch("hoyo_assistant.tasks.chinese.game_signin.config", mock_config):
            result = await checkin_game("genshin", Genshin, "Genshin")
        assert result == ""

    @pytest.mark.asyncio
    async def test_checkin_game_enabled(self, mock_config):
        mock_config["cn"]["games"] = ["genshin"]
        mock_instance = MagicMock()
        mock_instance.init = AsyncMock()
        mock_instance.sign_account = AsyncMock(return_value="signed")
        mock_module = MagicMock(return_value=mock_instance)
        with patch("hoyo_assistant.tasks.chinese.game_signin.config", mock_config):
            result = await checkin_game("genshin", mock_module, "Genshin")
        assert "signed" in result
        mock_instance.init.assert_awaited_once()
        mock_instance.sign_account.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_checkin_game_no_print_name(self, mock_config):
        mock_config["cn"]["games"] = ["genshin"]
        mock_instance = MagicMock()
        mock_instance.init = AsyncMock()
        mock_instance.sign_account = AsyncMock(return_value="signed")
        mock_module = MagicMock(return_value=mock_instance)
        with patch("hoyo_assistant.tasks.chinese.game_signin.config", mock_config):
            result = await checkin_game("genshin", mock_module, "")
        assert "signed" in result

    @pytest.mark.asyncio
    async def test_run_task_all_disabled(self, mock_config):
        with patch("hoyo_assistant.tasks.chinese.game_signin.config", mock_config):
            result = await cn_run_task()
        assert result == ""

    @pytest.mark.asyncio
    async def test_run_task_one_enabled(self, mock_config):
        mock_config["cn"]["games"] = ["honkai2"]
        mock_instance = MagicMock()
        mock_instance.init = AsyncMock()
        mock_instance.sign_account = AsyncMock(return_value="done")
        with (
            patch(
                "hoyo_assistant.tasks.chinese.game_signin.Honkai2",
                return_value=mock_instance,
            ),
            patch("hoyo_assistant.tasks.chinese.game_signin.config", mock_config),
        ):
            result = await cn_run_task()
        assert "done" in result

    def test_subclass_honkai2(self, mock_config):
        with patch("hoyo_assistant.tasks.chinese.game_signin.config", mock_config):
            game = Honkai2()
        assert "Referer" in game.headers
        assert game.game_id == "bh2_cn"

    def test_subclass_honkai3rd(self, mock_config):
        with patch("hoyo_assistant.tasks.chinese.game_signin.config", mock_config):
            game = Honkai3rd()
        assert "Referer" in game.headers
        assert game.game_id == "bh3_cn"

    def test_subclass_tears_of_themis(self, mock_config):
        with patch("hoyo_assistant.tasks.chinese.game_signin.config", mock_config):
            game = TearsOfThemis()
        assert "Referer" in game.headers
        assert game.game_id == "nxx_cn"

    def test_subclass_genshin(self, mock_config):
        with patch("hoyo_assistant.tasks.chinese.game_signin.config", mock_config):
            game = Genshin()
        assert game.headers.get("x-rpc-signgame") == "hk4e"
        assert game.headers["Origin"] == "https://act.mihoyo.com"

    def test_subclass_honkaisr(self, mock_config):
        with patch("hoyo_assistant.tasks.chinese.game_signin.config", mock_config):
            game = Honkaisr()
        assert game.headers["Origin"] == "https://act.mihoyo.com"

    def test_subclass_zzz(self, mock_config):
        with patch("hoyo_assistant.tasks.chinese.game_signin.config", mock_config):
            game = ZZZ()
        assert game.headers.get("X-Rpc-Signgame") == "zzz"
        assert game.sign_api is not None


# ---------------------------------------------------------------------------
# Mihoyobbs tests (tasks/community/miyoushe.py)
# ---------------------------------------------------------------------------


class TestMihoyobbs:
    def _make_bbs(self, mock_config, **config_overrides):
        """Create a Mihoyobbs instance with patched dependencies."""
        cfg = mock_config
        cfg["cn"]["bbs"]["forums"] = [2]
        mock_login = MagicMock()
        mock_login.get_stoken_cookie = MagicMock(return_value="test_stoken_cookie")
        mock_login.update_cookie_token = AsyncMock(return_value=True)
        with (
            patch("hoyo_assistant.tasks.community.miyoushe.config", cfg),
            patch("hoyo_assistant.tasks.community.miyoushe.login", mock_login),
        ):
            return Mihoyobbs()

    def test_init(self, mock_config):
        bbs = self._make_bbs(mock_config)
        assert bbs.today_get_coins == 0
        assert bbs.have_coins == 0
        assert bbs.task_do["sign"] is False
        assert len(bbs.bbs_list) > 0
        assert "DS" in bbs.headers
        assert "cookie" in bbs.headers

    def test_init_with_fp(self, mock_config):
        mock_config["client"]["device"]["fp"] = "test_fp"
        bbs = self._make_bbs(mock_config)
        assert bbs.headers.get("x-rpc-device_fp") == "test_fp"

    @pytest.mark.asyncio
    async def test_get_tasks_list_already_done(self, mock_config):
        resp = make_response(
            {
                "message": "OK",
                "retcode": 0,
                "data": {
                    "can_get_points": 0,
                    "already_received_points": 10,
                    "total_points": 100,
                    "states": [],
                },
            }
        )
        http = mock_http(get_return=resp)
        bbs = self._make_bbs(mock_config)
        with patch("hoyo_assistant.tasks.community.miyoushe.http", http):
            await bbs.get_tasks_list()
        assert bbs.task_do["sign"] is True
        assert bbs.have_coins == 100

    @pytest.mark.asyncio
    async def test_get_tasks_list_mission_done(self, mock_config):
        resp = make_response(
            {
                "message": "OK",
                "retcode": 0,
                "data": {
                    "can_get_points": 20,
                    "already_received_points": 10,
                    "total_points": 100,
                    "states": [
                        {"mission_id": 58, "is_get_award": True},
                    ],
                },
            }
        )
        http = mock_http(get_return=resp)
        bbs = self._make_bbs(mock_config)
        with patch("hoyo_assistant.tasks.community.miyoushe.http", http):
            await bbs.get_tasks_list()
        assert bbs.task_do["sign"] is True

    @pytest.mark.asyncio
    async def test_get_tasks_list_mission_not_done(self, mock_config):
        resp = make_response(
            {
                "message": "OK",
                "retcode": 0,
                "data": {
                    "can_get_points": 20,
                    "already_received_points": 10,
                    "total_points": 100,
                    "states": [
                        {"mission_id": 58, "is_get_award": False},
                    ],
                },
            }
        )
        http = mock_http(get_return=resp)
        bbs = self._make_bbs(mock_config)
        with patch("hoyo_assistant.tasks.community.miyoushe.http", http):
            await bbs.get_tasks_list()
        assert bbs.task_do["sign"] is False

    @pytest.mark.asyncio
    async def test_get_tasks_list_cookie_refresh(self, mock_config):
        expired = make_response({"message": "err", "retcode": -100, "data": {}})
        success = make_response(
            {
                "message": "OK",
                "retcode": 0,
                "data": {
                    "can_get_points": 0,
                    "already_received_points": 10,
                    "total_points": 100,
                    "states": [],
                },
            }
        )
        http = mock_http(get_side_effect=[expired, success])
        mock_login = MagicMock()
        mock_login.get_stoken_cookie = MagicMock(return_value="cookie")
        mock_login.update_cookie_token = AsyncMock(return_value=True)
        mock_setting = MagicMock()
        mock_setting.clear_cookie = AsyncMock()
        mock_config["cn"]["bbs"]["forums"] = [2]
        with (
            patch("hoyo_assistant.tasks.community.miyoushe.config", mock_config),
            patch("hoyo_assistant.tasks.community.miyoushe.login", mock_login),
            patch("hoyo_assistant.tasks.community.miyoushe.http", http),
            patch("hoyo_assistant.tasks.community.miyoushe.setting", mock_setting),
        ):
            bbs = Mihoyobbs()
            await bbs.get_tasks_list()
        assert bbs.task_do["sign"] is True

    @pytest.mark.asyncio
    async def test_get_tasks_list_stoken_error(self, mock_config):
        resp = make_response({"message": "err", "retcode": -100, "data": {}})
        http = mock_http(get_return=resp)
        mock_login = MagicMock()
        mock_login.get_stoken_cookie = MagicMock(return_value="cookie")
        mock_login.update_cookie_token = AsyncMock(return_value=False)
        mock_setting = MagicMock()
        mock_setting.clear_cookie = AsyncMock()
        mock_config["cn"]["bbs"]["forums"] = [2]
        with (
            patch("hoyo_assistant.tasks.community.miyoushe.config", mock_config),
            patch("hoyo_assistant.tasks.community.miyoushe.login", mock_login),
            patch("hoyo_assistant.tasks.community.miyoushe.http", http),
            patch("hoyo_assistant.tasks.community.miyoushe.setting", mock_setting),
        ):
            bbs = Mihoyobbs()
            with pytest.raises(StokenError):
                await bbs.get_tasks_list()

    @pytest.mark.asyncio
    async def test_signing_already_done(self, mock_config):
        bbs = self._make_bbs(mock_config)
        bbs.task_do["sign"] = True
        await bbs.signing()

    @pytest.mark.asyncio
    async def test_signing_success(self, mock_config):
        resp = make_response({"retcode": 0, "message": "OK"})
        http = mock_http(post_return=resp)
        bbs = self._make_bbs(mock_config)
        bbs.task_do["sign"] = False
        with patch("hoyo_assistant.tasks.community.miyoushe.http", http):
            await bbs.signing()
        http.post.assert_awaited()

    @pytest.mark.asyncio
    async def test_signing_captcha(self, mock_config):
        captcha_resp = make_response({"retcode": 1034, "message": "err"})
        success_resp = make_response({"retcode": 0, "message": "OK"})
        http = mock_http(post_side_effect=[captcha_resp, success_resp])
        bbs = self._make_bbs(mock_config)
        bbs.task_do["sign"] = False
        bbs.get_pass_challenge = AsyncMock(return_value="challenge_str")
        with patch("hoyo_assistant.tasks.community.miyoushe.http", http):
            await bbs.signing()
        bbs.get_pass_challenge.assert_awaited()

    @pytest.mark.asyncio
    async def test_signing_captcha_none(self, mock_config):
        captcha_resp = make_response({"retcode": 1034, "message": "err"})
        success_resp = make_response({"retcode": 0, "message": "OK"})
        http = mock_http(post_side_effect=[captcha_resp, success_resp])
        bbs = self._make_bbs(mock_config)
        bbs.task_do["sign"] = False
        bbs.get_pass_challenge = AsyncMock(return_value=None)
        with patch("hoyo_assistant.tasks.community.miyoushe.http", http):
            await bbs.signing()

    @pytest.mark.asyncio
    async def test_signing_cookie_expired(self, mock_config):
        resp = make_response({"retcode": -100, "message": "err"})
        http = mock_http(post_return=resp)
        mock_setting = MagicMock()
        mock_setting.clear_stoken = AsyncMock()
        bbs = self._make_bbs(mock_config)
        bbs.task_do["sign"] = False
        with (
            patch("hoyo_assistant.tasks.community.miyoushe.http", http),
            patch("hoyo_assistant.tasks.community.miyoushe.setting", mock_setting),
        ):
            with pytest.raises(StokenError):
                await bbs.signing()
        mock_setting.clear_stoken.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_signing_unknown_error(self, mock_config):
        unknown_resp = make_response({"retcode": 999, "message": "unknown"})
        success_resp = make_response({"retcode": 0, "message": "OK"})
        http = mock_http(post_side_effect=[unknown_resp, success_resp])
        bbs = self._make_bbs(mock_config)
        bbs.task_do["sign"] = False
        with patch("hoyo_assistant.tasks.community.miyoushe.http", http):
            await bbs.signing()

    @pytest.mark.asyncio
    async def test_run_task_already_done(self, mock_config):
        bbs = self._make_bbs(mock_config)
        bbs.get_tasks_list = AsyncMock()
        bbs.task_do["sign"] = True
        bbs.today_have_get_coins = 10
        bbs.have_coins = 100
        result = await bbs.run_task()
        assert "米游社" in result

    @pytest.mark.asyncio
    async def test_run_task_with_signing(self, mock_config):
        bbs = self._make_bbs(mock_config)
        bbs.get_tasks_list = AsyncMock()
        bbs.task_do["sign"] = False
        bbs.today_get_coins = 20
        bbs.today_have_get_coins = 10
        bbs.have_coins = 100
        bbs.bbs_config["enable"] = True
        bbs.signing = AsyncMock()
        result = await bbs.run_task()
        assert "米游社" in result
        bbs.signing.assert_awaited()

    @pytest.mark.asyncio
    async def test_run_task_checkin_disabled(self, mock_config):
        bbs = self._make_bbs(mock_config)
        bbs.get_tasks_list = AsyncMock()
        bbs.task_do["sign"] = False
        bbs.today_get_coins = 20
        bbs.today_have_get_coins = 10
        bbs.have_coins = 100
        bbs.bbs_config["enable"] = False
        bbs.signing = AsyncMock()
        result = await bbs.run_task()
        assert "米游社" in result
        bbs.signing.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_get_pass_challenge_success(self, mock_config):
        captcha_resp = make_response(
            {
                "retcode": 0,
                "data": {"gt": "gt_val", "challenge": "ch_val"},
            }
        )
        verify_resp = make_response(
            {
                "retcode": 0,
                "data": {"challenge": "verified_chall"},
            }
        )
        http = mock_http(get_return=captcha_resp)
        http.post = AsyncMock(return_value=verify_resp)
        mock_captcha = MagicMock()
        mock_captcha.bbs_captcha = MagicMock(
            return_value={"validate": "val", "challenge": "new_chall"}
        )
        bbs = self._make_bbs(mock_config)
        with (
            patch("hoyo_assistant.tasks.community.miyoushe.http", http),
            patch("hoyo_assistant.tasks.community.miyoushe.captcha", mock_captcha),
        ):
            result = await bbs.get_pass_challenge()
        assert result == "verified_chall"

    @pytest.mark.asyncio
    async def test_get_pass_challenge_retcode_fail(self, mock_config):
        captcha_resp = make_response({"retcode": -1, "data": {}})
        http = mock_http(get_return=captcha_resp)
        bbs = self._make_bbs(mock_config)
        with patch("hoyo_assistant.tasks.community.miyoushe.http", http):
            result = await bbs.get_pass_challenge()
        assert result is None

    @pytest.mark.asyncio
    async def test_get_pass_challenge_captcha_none(self, mock_config):
        captcha_resp = make_response(
            {
                "retcode": 0,
                "data": {"gt": "gt_val", "challenge": "ch_val"},
            }
        )
        http = mock_http(get_return=captcha_resp)
        mock_captcha = MagicMock()
        mock_captcha.bbs_captcha = MagicMock(return_value=None)
        bbs = self._make_bbs(mock_config)
        with (
            patch("hoyo_assistant.tasks.community.miyoushe.http", http),
            patch("hoyo_assistant.tasks.community.miyoushe.captcha", mock_captcha),
        ):
            result = await bbs.get_pass_challenge()
        assert result is None


# ---------------------------------------------------------------------------
# CN CloudGames tests (tasks/chinese/cloud_games.py)
# ---------------------------------------------------------------------------


class TestCNCloudGames:
    @pytest.mark.asyncio
    async def test_clear_cookie(self, mock_config):
        mock_config["cn"]["cloud"]["genshin"] = "old_token"
        mock_setting = MagicMock()
        mock_setting.save_config = AsyncMock()
        with (
            patch("hoyo_assistant.tasks.chinese.cloud_games.config", mock_config),
            patch("hoyo_assistant.tasks.chinese.cloud_games.setting", mock_setting),
        ):
            await cn_cloud_games.clear_cookie("genshin")
        assert mock_config["cn"]["cloud"]["genshin"] == ""
        mock_setting.save_config.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_clear_cookie_no_config(self):
        config = {}
        mock_setting = MagicMock()
        mock_setting.save_config = AsyncMock()
        with (
            patch("hoyo_assistant.tasks.chinese.cloud_games.config", config),
            patch("hoyo_assistant.tasks.chinese.cloud_games.setting", mock_setting),
        ):
            await cn_cloud_games.clear_cookie("genshin")
        mock_setting.save_config.assert_not_awaited()

    def test_build_headers_with_hostname(self):
        headers = cn_cloud_games._build_headers("token", "hk4e_cn", "hostname.com")
        assert headers["x-rpc-combo_token"] == "token"
        assert headers["x-rpc-cg_game_biz"] == "hk4e_cn"
        assert headers["Host"] == "hostname.com"

    def test_build_headers_without_hostname(self):
        headers = cn_cloud_games._build_headers("token", "hk4e_cn", None)
        assert headers["x-rpc-combo_token"] == "token"
        assert "Host" not in headers

    @pytest.mark.asyncio
    async def test_run_task_with_token(self, mock_config):
        mock_config["cn"]["cloud"]["genshin"] = "test_token"
        mock_config["cn"]["cloud"]["zzz"] = "test_token2"
        with (
            patch.object(
                BaseCloudGame, "check_in", new=AsyncMock(return_value="result")
            ),
            patch("hoyo_assistant.tasks.chinese.cloud_games.config", mock_config),
        ):
            result = await cn_cloud_games.run_task()
        assert "result" in result

    @pytest.mark.asyncio
    async def test_run_task_without_token(self, mock_config):
        with patch("hoyo_assistant.tasks.chinese.cloud_games.config", mock_config):
            result = await cn_cloud_games.run_task()
        assert result == ""

    @pytest.mark.asyncio
    async def test_run_task_partial_token(self, mock_config):
        mock_config["cn"]["cloud"]["genshin"] = "test_token"
        mock_config["cn"]["cloud"]["zzz"] = ""
        with (
            patch.object(
                BaseCloudGame, "check_in", new=AsyncMock(return_value="result")
            ),
            patch("hoyo_assistant.tasks.chinese.cloud_games.config", mock_config),
        ):
            result = await cn_cloud_games.run_task()
        assert "result" in result


# ---------------------------------------------------------------------------
# OS CloudGames tests (tasks/overseas/cloud_games.py)
# ---------------------------------------------------------------------------


class TestOSCloudGames:
    @pytest.mark.asyncio
    async def test_clear_cookie(self, mock_config):
        mock_config["os"]["cloud"]["genshin"] = "old_token"
        mock_setting = MagicMock()
        mock_setting.save_config = AsyncMock()
        with (
            patch("hoyo_assistant.tasks.overseas.cloud_games.config", mock_config),
            patch("hoyo_assistant.tasks.overseas.cloud_games.setting", mock_setting),
        ):
            await os_cloud_games.clear_cookie("genshin")
        assert mock_config["os"]["cloud"]["genshin"] == ""
        mock_setting.save_config.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_clear_cookie_no_config(self):
        config = {}
        mock_setting = MagicMock()
        mock_setting.save_config = AsyncMock()
        with (
            patch("hoyo_assistant.tasks.overseas.cloud_games.config", config),
            patch("hoyo_assistant.tasks.overseas.cloud_games.setting", mock_setting),
        ):
            await os_cloud_games.clear_cookie("genshin")
        mock_setting.save_config.assert_not_awaited()

    def test_build_headers(self):
        headers = os_cloud_games._build_headers("token", "hk4e_global", "en-us")
        assert headers["x-rpc-combo_token"] == "token"
        assert headers["x-rpc-cg_game_biz"] == "hk4e_global"
        assert headers["x-rpc-language"] == "en-us"

    @pytest.mark.asyncio
    async def test_run_task_with_token(self, mock_config):
        mock_config["os"]["cloud"]["genshin"] = "test_token"
        mock_config["os"]["cloud"]["zzz"] = "test_token2"
        mock_config["os"]["lang"] = "en-us"
        with (
            patch.object(
                BaseCloudGame, "check_in", new=AsyncMock(return_value="result")
            ),
            patch("hoyo_assistant.tasks.overseas.cloud_games.config", mock_config),
        ):
            result = await os_cloud_games.run_task()
        assert "result" in result

    @pytest.mark.asyncio
    async def test_run_task_without_token(self, mock_config):
        with patch("hoyo_assistant.tasks.overseas.cloud_games.config", mock_config):
            result = await os_cloud_games.run_task()
        assert result == ""

    @pytest.mark.asyncio
    async def test_run_task_partial_token(self, mock_config):
        mock_config["os"]["cloud"]["genshin"] = "test_token"
        mock_config["os"]["cloud"]["zzz"] = ""
        with (
            patch.object(
                BaseCloudGame, "check_in", new=AsyncMock(return_value="result")
            ),
            patch("hoyo_assistant.tasks.overseas.cloud_games.config", mock_config),
        ):
            result = await os_cloud_games.run_task()
        assert "result" in result


# ---------------------------------------------------------------------------
# OS GameSignin tests (tasks/overseas/game_signin.py)
# ---------------------------------------------------------------------------


class TestOSGameSignin:
    @pytest.fixture
    def os_config(self):
        return {
            "os": {
                "cookie": "ltoken=xyz; ltuid=123",
                "lang": "en-us",
                "games": ["genshin"],
                "custom_games": {},
            }
        }

    @pytest.mark.asyncio
    async def test_hoyo_checkin_already_signed(self, os_config):
        info_resp = make_response({"data": {"is_sign": True, "first_bind": False}})
        with (
            patch("hoyo_assistant.tasks.overseas.game_signin.config", os_config),
            patch(
                "hoyo_assistant.tasks.overseas.game_signin.http.get",
                AsyncMock(return_value=info_resp),
            ),
        ):
            res = await os_game_signin.hoyo_checkin(
                "https://act.hoyolab.com", "act_123", "Genshin"
            )
        assert "Genshin" in res

    @pytest.mark.asyncio
    async def test_hoyo_checkin_first_bind(self, os_config):
        info_resp = make_response({"data": {"is_sign": False, "first_bind": True}})
        with (
            patch("hoyo_assistant.tasks.overseas.game_signin.config", os_config),
            patch(
                "hoyo_assistant.tasks.overseas.game_signin.http.get",
                AsyncMock(return_value=info_resp),
            ),
        ):
            res = await os_game_signin.hoyo_checkin(
                "https://act.hoyolab.com", "act_123", "Genshin"
            )
        assert "Genshin" in res

    @pytest.mark.asyncio
    async def test_hoyo_checkin_success(self, os_config):
        info_resp = make_response(
            {
                "data": {
                    "is_sign": False,
                    "first_bind": False,
                    "total_sign_day": 1,
                    "today": "2026-08-18",
                }
            }
        )
        award_resp = make_response(
            {"data": {"awards": [{"name": "Primogems", "cnt": 60}]}}
        )
        sign_resp = make_response({"retcode": 0, "data": {"code": "ok"}})

        async def fake_get(url, **kwargs):
            if "/info" in url:
                return info_resp
            return award_resp

        with (
            patch("hoyo_assistant.tasks.overseas.game_signin.config", os_config),
            patch(
                "hoyo_assistant.tasks.overseas.game_signin.http.get",
                side_effect=fake_get,
            ),
            patch(
                "hoyo_assistant.tasks.overseas.game_signin.http.post",
                AsyncMock(return_value=sign_resp),
            ),
            patch("asyncio.sleep", AsyncMock()),
        ):
            res = await os_game_signin.hoyo_checkin(
                "https://act.hoyolab.com", "act_123", "Genshin"
            )
        assert "Genshin" in res

    @pytest.mark.asyncio
    async def test_hoyo_checkin_retcode_already_signed(self, os_config):
        info_resp = make_response(
            {
                "data": {
                    "is_sign": False,
                    "first_bind": False,
                    "total_sign_day": 1,
                    "today": "2026-08-18",
                }
            }
        )
        award_resp = make_response(
            {"data": {"awards": [{"name": "Primogems", "cnt": 60}]}}
        )
        sign_resp = make_response({"retcode": -5003, "message": "already signed"})

        async def fake_get(url, **kwargs):
            if "/info" in url:
                return info_resp
            return award_resp

        with (
            patch("hoyo_assistant.tasks.overseas.game_signin.config", os_config),
            patch(
                "hoyo_assistant.tasks.overseas.game_signin.http.get",
                side_effect=fake_get,
            ),
            patch(
                "hoyo_assistant.tasks.overseas.game_signin.http.post",
                AsyncMock(return_value=sign_resp),
            ),
            patch("asyncio.sleep", AsyncMock()),
        ):
            res = await os_game_signin.hoyo_checkin(
                "https://act.hoyolab.com", "act_123", "Genshin"
            )
        assert "Genshin" in res

    @pytest.mark.asyncio
    async def test_hoyo_checkin_error(self, os_config):
        info_resp = make_response(
            {
                "data": {
                    "is_sign": False,
                    "first_bind": False,
                    "total_sign_day": 1,
                    "today": "2026-08-18",
                }
            }
        )
        award_resp = make_response(
            {"data": {"awards": [{"name": "Primogems", "cnt": 60}]}}
        )
        sign_resp = make_response({"retcode": 10001, "message": "token error"})

        async def fake_get(url, **kwargs):
            if "/info" in url:
                return info_resp
            return award_resp

        with (
            patch("hoyo_assistant.tasks.overseas.game_signin.config", os_config),
            patch(
                "hoyo_assistant.tasks.overseas.game_signin.http.get",
                side_effect=fake_get,
            ),
            patch(
                "hoyo_assistant.tasks.overseas.game_signin.http.post",
                AsyncMock(return_value=sign_resp),
            ),
            patch("asyncio.sleep", AsyncMock()),
        ):
            res = await os_game_signin.hoyo_checkin(
                "https://act.hoyolab.com", "act_123", "Genshin"
            )
        assert "token error" in res

    @pytest.mark.asyncio
    async def test_hoyo_checkin_zzz_header(self, os_config):
        info_resp = make_response({"data": {"is_sign": True, "first_bind": False}})
        mock_get = AsyncMock(return_value=info_resp)
        with (
            patch("hoyo_assistant.tasks.overseas.game_signin.config", os_config),
            patch("hoyo_assistant.tasks.overseas.game_signin.http.get", mock_get),
        ):
            await os_game_signin.hoyo_checkin(
                "https://act.hoyolab.com", os_game_signin.ACT_ID_OS_ZZZ, "ZZZ"
            )
        headers = mock_get.call_args.kwargs["headers"]
        assert headers.get("x-rpc-signgame") == "zzz"

    @pytest.mark.asyncio
    async def test_run_task(self, os_config):
        os_config["os"]["games"] = [
            "genshin",
            "honkai_sr",
            "honkai3rd",
            "tears_of_themis",
            "zzz",
        ]

        mock_checkin = AsyncMock(return_value="checked")
        with (
            patch("hoyo_assistant.tasks.overseas.game_signin.config", os_config),
            patch.object(os_game_signin, "hoyo_checkin", mock_checkin),
        ):
            res = await os_game_signin.run_task()
        assert "checked" in res
        # Verify Tears of Themis uses Luna OS endpoint (not Genshin's /event/sol)
        tot_call = next(
            c
            for c in mock_checkin.call_args_list
            if c.args[1] == os_game_signin.ACT_ID_OS_TEARS_OF_THEMIS
        )
        assert tot_call.args[0] == os_game_signin.API_OS_ACT_LUNA

    @pytest.mark.asyncio
    async def test_hoyo_checkin_invalid_cookie_response(self, os_config):
        info_resp = make_response(
            {"retcode": -100, "message": "Not logged in", "data": None}
        )
        with (
            patch("hoyo_assistant.tasks.overseas.game_signin.config", os_config),
            patch(
                "hoyo_assistant.tasks.overseas.game_signin.http.get",
                AsyncMock(return_value=info_resp),
            ),
        ):
            res = await os_game_signin.hoyo_checkin(
                os_game_signin.API_OS_ACT, os_game_signin.ACT_ID_OS_GENSHIN, "Genshin"
            )
        assert "Not logged in" in res

    @pytest.mark.asyncio
    async def test_hoyo_checkin_day1_picks_first_reward(self, os_config):
        info_resp = make_response(
            {
                "retcode": 0,
                "data": {
                    "is_sign": False,
                    "first_bind": False,
                    "total_sign_day": 0,
                    "today": "2026-11-01",
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
            patch("hoyo_assistant.tasks.overseas.game_signin.config", os_config),
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


class TestAPIRegressionFixes:
    def test_cn_game_ds_and_subclass_headers_preserved(self, mock_config):
        mock_config["cn"]["cookie"] = "account_id=123; cookie_token=old"
        with patch("hoyo_assistant.tasks.chinese.game_signin.config", mock_config):
            genshin = Genshin()
            assert genshin.headers["DS"] != ""
            assert genshin.headers["x-rpc-signgame"] == "hk4e"
            assert genshin.headers["Origin"] == "https://act.mihoyo.com"
            # Re-calling set_headers() (as on cookie refresh) must keep subclass headers
            genshin.set_headers()
            assert genshin.headers["x-rpc-signgame"] == "hk4e"
            assert genshin.headers["Origin"] == "https://act.mihoyo.com"

            hsr = Honkaisr()
            assert hsr.headers["x-rpc-signgame"] == "hkrpg"

            tot = TearsOfThemis()
            assert "&act_id=" in tot.headers["Referer"]
            assert tot.headers["x-rpc-signgame"] == "nxx"

    @pytest.mark.asyncio
    async def test_cn_zzz_uses_zzz_endpoints(self, mock_config):
        from hoyo_assistant.core.constants import (
            API_ZZZ_GAME_CHECKIN_REWARDS,
            API_ZZZ_GAME_IS_SIGN,
        )

        rewards_resp = make_response({"retcode": 0, "data": {"awards": []}})
        is_sign_resp = make_response(
            {"retcode": 0, "data": {"is_sign": True, "total_sign_day": 1}}
        )
        http = mock_http(get_side_effect=[rewards_resp, is_sign_resp])
        with (
            patch("hoyo_assistant.tasks.chinese.game_signin.config", mock_config),
            patch("hoyo_assistant.tasks.chinese.game_signin.http", http),
        ):
            zzz = ZZZ()
            await zzz.get_checkin_rewards()
            await zzz.is_sign("prod_gf_cn", "10001")
        assert http.get.call_args_list[0].args[0] == API_ZZZ_GAME_CHECKIN_REWARDS
        assert http.get.call_args_list[1].kwargs["url"] == API_ZZZ_GAME_IS_SIGN

    @pytest.mark.asyncio
    async def test_cn_day1_and_empty_rewards_safe(self, mock_config):
        with patch("hoyo_assistant.tasks.chinese.game_signin.config", mock_config):
            checkin = GameCheckin("hk4e_cn", "genshin", "Genshin", "act_id", "Traveler")
            checkin.profiles = [("Player", "uid123", "cn_gf01")]
            checkin.checkin_rewards = [
                {"name": "Day1", "cnt": 1},
                {"name": "Day2", "cnt": 2},
            ]
            checkin.is_sign = AsyncMock(
                return_value={
                    "is_sign": False,
                    "total_sign_day": 1,
                    "first_bind": False,
                }
            )
            checkin.check_in = AsyncMock(
                return_value=make_response({"retcode": 0, "data": {"success": 0}})
            )
            res = await checkin.sign_account()
            assert "Day2" in res

            # Empty rewards should not raise IndexError
            checkin.checkin_rewards = []
            res_empty = await checkin.sign_account()
            assert "Player" in res_empty

    def test_cn_cloud_games_hostnames_have_no_scheme(self):
        for game in cn_cloud_games.CLOUD_GAMES:
            assert game.hostname is not None
            assert "://" not in game.hostname
        headers = cn_cloud_games._build_headers(
            "tok", "hk4e_cn", "https://api-cloudgame.mihoyo.com"
        )
        assert headers["Host"] == "api-cloudgame.mihoyo.com"

    @pytest.mark.asyncio
    async def test_cloud_game_bypasses_cache_and_updates_free_time(self):
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
                    "free_time": {"free_time": "315", "send_freetime": "0"},
                    "play_card": {"short_msg": "active"},
                    "coin": {"coin_num": "50"},
                },
            }
        )
        http = mock_http(get_side_effect=[first, second])
        with patch("hoyo_assistant.tasks.base.http", http):
            game = BaseCloudGame("genshin", "http://api", "coin", AsyncMock(), {})
            result = await game.check_in(retry_on_limit=True)
        for call in http.get.call_args_list:
            assert call.kwargs.get("use_cache") is False
        assert "15" in result
        assert "5" in result  # 315 mins = 5 hours 15 mins

    @pytest.mark.asyncio
    async def test_miyoushe_null_states_does_not_crash(self, mock_config):
        mock_config["cn"]["stuid"] = "123"
        mock_config["cn"]["stoken"] = "v1_tok"
        resp = make_response(
            {
                "retcode": 0,
                "message": "OK",
                "data": {
                    "can_get_points": 50,
                    "already_received_points": 0,
                    "total_points": 100,
                    "states": None,
                },
            }
        )
        http = mock_http(get_return=resp)
        with (
            patch("hoyo_assistant.tasks.community.miyoushe.config", mock_config),
            patch("hoyo_assistant.tasks.community.miyoushe.http", http),
            patch(
                "hoyo_assistant.tasks.community.miyoushe.login.get_stoken_cookie",
                return_value="stuid=123;stoken=v1_tok",
            ),
        ):
            bbs = Mihoyobbs()
            await bbs.get_tasks_list()
        assert bbs.today_get_coins == 50


class TestNewGameSyncAndCustomCheckin:
    @pytest.mark.asyncio
    async def test_fetch_bbs_game_list_success(self):
        from hoyo_assistant.tasks.community.miyoushe import fetch_bbs_game_list

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
                        },
                        {
                            "id": 9,
                            "name": "崩坏：因缘精灵",
                            "en_name": "hna",
                            "op_name": "abc",
                        },
                    ]
                },
            }
        )
        http = mock_http(get_return=resp)
        with patch("hoyo_assistant.tasks.community.miyoushe.http", http):
            games = await fetch_bbs_game_list()
        assert games[10]["name"] == "星布谷地"
        assert games[10]["op_name"] == "hyg"
        assert games[9]["en_name"] == "hna"

    @pytest.mark.asyncio
    async def test_fetch_bbs_game_list_error_returns_empty(self):
        from hoyo_assistant.tasks.community.miyoushe import fetch_bbs_game_list

        http = mock_http(get_side_effect=RuntimeError("offline"))
        with patch("hoyo_assistant.tasks.community.miyoushe.http", http):
            assert await fetch_bbs_game_list() == {}

    @pytest.mark.asyncio
    async def test_miyoushe_sync_unknown_forums(self, mock_config):
        mock_config["cn"]["bbs"]["forums"] = [2, 11, 999]
        mock_config["cn"]["stuid"] = "123"
        mock_config["cn"]["stoken"] = "v1_tok"
        remote = {
            11: {
                "id": "11",
                "name": "新游戏社区",
                "en_name": "newgame",
                "op_name": "ng",
            }
        }
        with (
            patch("hoyo_assistant.tasks.community.miyoushe.config", mock_config),
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
            assert bbs.bbs_list[1]["name"] == "新游戏社区"

    @pytest.mark.asyncio
    async def test_custom_cn_game_checkin_headers_apis_and_blacklist(self, mock_config):
        from hoyo_assistant.tasks.chinese.game_signin import CustomCNGameCheckin

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
        mock_config["cn"]["custom_games"] = {"planet": spec}
        with patch("hoyo_assistant.tasks.chinese.game_signin.config", mock_config):
            game = CustomCNGameCheckin("planet", spec)
            assert game.game_id == "hyg_cn"
            assert game.act_id == "e20261204000001"
            assert game.headers["x-rpc-signgame"] == "planet"
            assert game.headers["Origin"] == "https://act.mihoyo.com"
            assert game.headers["Referer"] == "https://act.mihoyo.com/"
            assert (
                game.rewards_api
                == "https://api-takumi.mihoyo.com/event/luna/hyg/home?lang=zh-cn"
            )
            assert (
                game.is_sign_api
                == "https://api-takumi.mihoyo.com/event/luna/hyg/info?lang=zh-cn"
            )
            assert game.sign_api == "https://api-takumi.mihoyo.com/event/luna/hyg/sign"
            assert game._get_black_list() == ["10001"]

    @pytest.mark.asyncio
    async def test_cn_run_task_executes_custom_games(self, mock_config):
        from hoyo_assistant.tasks.chinese import game_signin as cn_mod

        mock_config["cn"]["custom_games"] = {
            "planet": {
                "enable": True,
                "name": "星布谷地",
                "game_biz": "hyg_cn",
                "act_id": "e20261204000001",
            },
            "disabled_game": {
                "enable": False,
                "name": "Ignored",
                "game_biz": "abc_cn",
                "act_id": "e0",
            },
        }
        fake_instance = MagicMock()
        fake_instance.init = AsyncMock()
        fake_instance.sign_account = AsyncMock(return_value="planet ok")
        with (
            patch("hoyo_assistant.tasks.chinese.game_signin.config", mock_config),
            patch(
                "hoyo_assistant.tasks.chinese.game_signin.asyncio.sleep",
                new=AsyncMock(),
            ),
            patch(
                "hoyo_assistant.tasks.chinese.game_signin.CustomCNGameCheckin",
                return_value=fake_instance,
            ) as mock_cls,
        ):
            res = await cn_mod.run_task()
        assert "planet ok" in res
        mock_cls.assert_called_once_with(
            "planet", mock_config["cn"]["custom_games"]["planet"]
        )

    @pytest.mark.asyncio
    async def test_os_run_task_executes_custom_games_with_signgame(self, mock_config):
        from hoyo_assistant.tasks.overseas import game_signin as os_mod

        mock_config["os"]["cookie"] = "ltuid_v2=1; ltoken_v2=2"
        mock_config["os"]["custom_games"] = {
            "planet": {
                "enable": True,
                "name": "Petit Planet",
                "act_id": "e20261204000001",
                "signgame": "planet",
            }
        }
        with (
            patch("hoyo_assistant.tasks.overseas.game_signin.config", mock_config),
            patch(
                "hoyo_assistant.tasks.overseas.game_signin.hoyo_checkin",
                new=AsyncMock(return_value="os planet ok"),
            ) as mock_checkin,
        ):
            res = await os_mod.run_task()
        assert "os planet ok" in res
        mock_checkin.assert_awaited_once_with(
            os_mod.API_OS_ACT_LUNA,
            "e20261204000001",
            "Petit Planet",
            signgame="planet",
        )
