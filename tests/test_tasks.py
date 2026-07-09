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
from hoyo_assistant.tasks.overseas import cloud_games as os_cloud_games
from hoyo_assistant.tasks.web import activities

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
            assert checkin.headers["Cookie"] == mock_config["account"]["cookie"]
            assert checkin.headers["User-Agent"] == "TestUA"
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
    async def test_get_award_success(self, mock_config):
        resp = make_response(
            {
                "retcode": 0,
                "data": {"awards": [{"name": "Primogem", "cnt": 100}]},
            }
        )
        http = mock_http(get_return=resp)
        with (
            patch("hoyo_assistant.tasks.chinese.game_signin.config", mock_config),
            patch("hoyo_assistant.tasks.chinese.game_signin.http", http),
        ):
            checkin = GameCheckin("hk4e_cn", "genshin", "Genshin", "act_id", "Traveler")
            result = await checkin.get_award()
        assert result == [{"name": "Primogem", "cnt": 100}]

    @pytest.mark.asyncio
    async def test_get_award_failure(self, mock_config):
        resp = make_response({"retcode": -1})
        http = mock_http(get_return=resp)
        with (
            patch("hoyo_assistant.tasks.chinese.game_signin.config", mock_config),
            patch("hoyo_assistant.tasks.chinese.game_signin.http", http),
        ):
            checkin = GameCheckin("hk4e_cn", "genshin", "Genshin", "act_id", "Traveler")
            result = await checkin.get_award()
        assert result == []

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
        mock_config["games"]["cn"]["retries"] = 2
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
        mock_config["games"]["cn"]["retries"] = 2
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
        mock_config["games"]["cn"]["retries"] = 2
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
        mock_config["games"]["cn"]["genshin"]["black_list"] = ["uid123"]
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
        mock_config["games"]["cn"]["genshin"]["checkin"] = True
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
        mock_config["games"]["cn"]["genshin"]["checkin"] = True
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
        mock_config["games"]["cn"]["honkai2"]["checkin"] = True
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
        cfg["mihoyobbs"]["checkin_list"] = [2]
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
        mock_config["device"]["fp"] = "test_fp"
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
        mock_config["mihoyobbs"]["checkin_list"] = [2]
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
        mock_config["mihoyobbs"]["checkin_list"] = [2]
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
        bbs.bbs_config["checkin"] = True
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
        bbs.bbs_config["checkin"] = False
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
# Activities tests (tasks/web/activities.py)
# ---------------------------------------------------------------------------


class TestActivities:
    @pytest.mark.asyncio
    async def test_run_task_no_activities(self):
        config = {"web_activity": {"activities": []}}
        with patch("hoyo_assistant.tasks.web.activities.config", config):
            await activities.run_task()

    @pytest.mark.asyncio
    async def test_run_task_no_config(self):
        config = {}
        with patch("hoyo_assistant.tasks.web.activities.config", config):
            await activities.run_task()

    @pytest.mark.asyncio
    async def test_run_task_sync_func(self):
        sync_func = MagicMock()
        config = {"web_activity": {"activities": ["sync_func"]}}
        with (
            patch("hoyo_assistant.tasks.web.activities.config", config),
            patch.dict(activities.__dict__, {"sync_func": sync_func}),
        ):
            await activities.run_task()
        sync_func.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_task_async_func(self):
        async_func = AsyncMock()
        config = {"web_activity": {"activities": ["async_func"]}}
        with (
            patch("hoyo_assistant.tasks.web.activities.config", config),
            patch.dict(activities.__dict__, {"async_func": async_func}),
        ):
            await activities.run_task()
        async_func.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_run_task_not_found(self):
        config = {"web_activity": {"activities": ["nonexistent_func"]}}
        with patch("hoyo_assistant.tasks.web.activities.config", config):
            await activities.run_task()

    @pytest.mark.asyncio
    async def test_run_task_exception(self):
        def bad_func():
            raise ValueError("test error")

        config = {"web_activity": {"activities": ["bad_func"]}}
        with (
            patch("hoyo_assistant.tasks.web.activities.config", config),
            patch.dict(activities.__dict__, {"bad_func": bad_func}),
        ):
            await activities.run_task()


# ---------------------------------------------------------------------------
# CN CloudGames tests (tasks/chinese/cloud_games.py)
# ---------------------------------------------------------------------------


class TestCNCloudGames:
    @pytest.mark.asyncio
    async def test_clear_cookie(self, mock_config):
        mock_config["cloud_games"]["cn"]["genshin"]["token"] = "old_token"
        mock_setting = MagicMock()
        mock_setting.save_config = AsyncMock()
        with (
            patch("hoyo_assistant.tasks.chinese.cloud_games.config", mock_config),
            patch("hoyo_assistant.tasks.chinese.cloud_games.setting", mock_setting),
        ):
            await cn_cloud_games.clear_cookie("genshin")
        assert mock_config["cloud_games"]["cn"]["genshin"]["token"] == ""
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
        mock_config["cloud_games"]["cn"]["genshin"]["token"] = "test_token"
        mock_config["cloud_games"]["cn"]["zzz"]["token"] = "test_token2"
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
        mock_config["cloud_games"]["cn"]["genshin"]["token"] = "test_token"
        mock_config["cloud_games"]["cn"]["zzz"]["token"] = ""
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
        mock_config["cloud_games"]["os"]["genshin"]["token"] = "old_token"
        mock_setting = MagicMock()
        mock_setting.save_config = AsyncMock()
        with (
            patch("hoyo_assistant.tasks.overseas.cloud_games.config", mock_config),
            patch("hoyo_assistant.tasks.overseas.cloud_games.setting", mock_setting),
        ):
            await os_cloud_games.clear_cookie("genshin")
        assert mock_config["cloud_games"]["os"]["genshin"]["token"] == ""
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
        mock_config["cloud_games"]["os"]["genshin"]["token"] = "test_token"
        mock_config["cloud_games"]["os"]["zzz"]["token"] = "test_token2"
        mock_config["cloud_games"]["os"]["lang"] = "en-us"
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
        mock_config["cloud_games"]["os"]["genshin"]["token"] = "test_token"
        mock_config["cloud_games"]["os"]["zzz"]["token"] = ""
        with (
            patch.object(
                BaseCloudGame, "check_in", new=AsyncMock(return_value="result")
            ),
            patch("hoyo_assistant.tasks.overseas.cloud_games.config", mock_config),
        ):
            result = await os_cloud_games.run_task()
        assert "result" in result
