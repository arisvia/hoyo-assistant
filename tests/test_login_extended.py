"""Extended tests for hoyo_assistant.core.login async/network functions.

Complements tests/test_login.py (which covers the sync regex helpers:
get_uid/get_mid/require_*/get_stoken_cookie).
"""

from unittest.mock import AsyncMock, patch

import pytest

from hoyo_assistant.core import login as login_mod
from hoyo_assistant.core.error import CookieError, StokenError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _cfg(cookie="", stoken="", stuid="", mid="", login_ticket=""):
    return {
        "cn": {
            "cookie": cookie,
            "stoken": stoken,
            "stuid": stuid,
            "mid": mid,
            "login_ticket": login_ticket,
        }
    }


def _mock_resp(data, status=200):
    """Build an AsyncMock response whose .json() returns data."""
    resp = AsyncMock()
    resp.status = status
    resp.json = AsyncMock(return_value=data)
    resp.text = AsyncMock(return_value=str(data))
    return resp


def _patch_config(cfg_dict):
    return patch("hoyo_assistant.core.login.config", cfg_dict)


def _patch_setting():
    """Patch setting module functions used by login (all async no-ops)."""
    return patch.multiple(
        "hoyo_assistant.core.login.setting",
        clear_cookie=AsyncMock(),
        clear_stoken=AsyncMock(),
        save_config=AsyncMock(),
    )


# ---------------------------------------------------------------------------
# get_cookie_token_by_stoken
# ---------------------------------------------------------------------------
class TestGetCookieTokenByStoken:
    @pytest.mark.asyncio
    async def test_empty_stoken_and_stuid_raises(self):
        cfg = _cfg(stoken="", stuid="")
        with (
            _patch_config(cfg),
            patch(
                "hoyo_assistant.core.login.setting.clear_cookie", new=AsyncMock()
            ) as mock_clear,
        ):
            with pytest.raises(CookieError):
                await login_mod.get_cookie_token_by_stoken()
            mock_clear.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_success_v1(self):
        cfg = _cfg(stoken="v1_abc", stuid="123")
        resp = _mock_resp({"retcode": 0, "data": {"cookie_token": "ct_value"}})
        with (
            _patch_config(cfg),
            patch("hoyo_assistant.core.login.http.get", return_value=resp) as mock_get,
        ):
            result = await login_mod.get_cookie_token_by_stoken()
            assert result == "ct_value"
            mock_get.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_retcode_nonzero_raises_stoken_error(self):
        cfg = _cfg(stoken="v1_abc", stuid="123")
        resp = _mock_resp({"retcode": -100, "data": None})
        with (
            _patch_config(cfg),
            patch("hoyo_assistant.core.login.http.get", return_value=resp),
            patch(
                "hoyo_assistant.core.login.setting.clear_stoken", new=AsyncMock()
            ) as mock_clear,
        ):
            with pytest.raises(StokenError):
                await login_mod.get_cookie_token_by_stoken()
            mock_clear.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_v2_stoken_includes_mid_in_cookie_header(self):
        cfg = _cfg(stoken="v2_abc", stuid="123", mid="mid_val")
        resp = _mock_resp({"retcode": 0, "data": {"cookie_token": "ct_v2"}})
        with (
            _patch_config(cfg),
            patch("hoyo_assistant.core.login.http.get", return_value=resp) as mock_get,
        ):
            await login_mod.get_cookie_token_by_stoken()
            # headers kwarg should contain mid for v2 stoken
            _, kwargs = mock_get.call_args
            sent_cookie = kwargs["headers"]["cookie"]
            assert "stuid=123" in sent_cookie
            assert "stoken=v2_abc" in sent_cookie
            assert "mid=mid_val" in sent_cookie


# ---------------------------------------------------------------------------
# update_cookie_token
# ---------------------------------------------------------------------------
class TestUpdateCookieToken:
    @pytest.mark.asyncio
    async def test_no_stoken_returns_false(self):
        cfg = _cfg(stoken="", cookie="cookie_token=old;")
        with _patch_config(cfg):
            result = await login_mod.update_cookie_token()
            assert result is False

    @pytest.mark.asyncio
    async def test_refresh_existing_cookie_token(self):
        cfg = _cfg(
            stoken="v1_abc",
            stuid="123",
            cookie="cookie_token=OLD; account_id=123",
        )
        resp = _mock_resp({"retcode": 0, "data": {"cookie_token": "NEW"}})
        with (
            _patch_config(cfg),
            patch("hoyo_assistant.core.login.http.get", return_value=resp),
            patch(
                "hoyo_assistant.core.login.setting.save_config", new=AsyncMock()
            ) as mock_save,
            patch(
                "hoyo_assistant.core.login.get_cookie_token_by_stoken",
                new=AsyncMock(return_value="NEW"),
            ),
        ):
            result = await login_mod.update_cookie_token()
            assert result is True
            assert "NEW" in login_mod.config["cn"]["cookie"]
            assert "OLD" not in login_mod.config["cn"]["cookie"]
            mock_save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_append_cookie_token_when_missing_v1(self):
        cfg = _cfg(
            stoken="v1_abc",
            stuid="123",
            cookie="account_id=123",  # no cookie_token
        )
        resp = _mock_resp({"retcode": 0, "data": {"cookie_token": "appended_ct"}})
        with (
            _patch_config(cfg),
            patch("hoyo_assistant.core.login.http.get", return_value=resp),
            patch(
                "hoyo_assistant.core.login.setting.save_config", new=AsyncMock()
            ) as mock_save,
        ):
            result = await login_mod.update_cookie_token()
            assert result is True
            assert "cookie_token=appended_ct" in login_mod.config["cn"]["cookie"]
            mock_save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_refresh_v2_uses_passport_exchange_and_syncs_aliases(self):
        cfg = _cfg(
            stoken="v2_abc",
            stuid="123",
            mid="mid_1",
            cookie="account_id_v2=123; account_mid_v2=mid_1; cookie_token=OLD",
        )
        cfg["client"] = {
            "device": {"id": "dev1", "name": "Phone", "model": "M1", "fp": "fp1"}
        }
        resp = _mock_resp({"retcode": 0, "data": {"token": {"token": "NEW_V2"}}})
        with (
            _patch_config(cfg),
            patch(
                "hoyo_assistant.core.login.http.post", return_value=resp
            ) as mock_post,
            patch(
                "hoyo_assistant.core.login.setting.save_config", new=AsyncMock()
            ) as mock_save,
        ):
            result = await login_mod.update_cookie_token()
            assert result is True
            cookie = login_mod.config["cn"]["cookie"]
            assert "cookie_token_v2=NEW_V2" in cookie
            assert "cookie_token=NEW_V2" in cookie
            assert "OLD" not in cookie
            mock_post.assert_awaited_once()
            _, kwargs = mock_post.call_args
            assert kwargs["headers"]["x-rpc-device_fp"] == "fp1"
            mock_save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_v2_exchange_retcode_expired_clears_stoken(self):
        cfg = _cfg(stoken="v2_abc", stuid="123", mid="mid_1", cookie="account_id=123")
        resp = _mock_resp({"retcode": -100, "message": "expired", "data": None})
        with (
            _patch_config(cfg),
            patch("hoyo_assistant.core.login.http.post", return_value=resp),
            patch(
                "hoyo_assistant.core.login.setting.clear_stoken", new=AsyncMock()
            ) as mock_clear,
            patch("hoyo_assistant.core.login.setting.save_config", new=AsyncMock()),
        ):
            with pytest.raises(StokenError):
                await login_mod.update_cookie_token()
            mock_clear.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_v2_exchange_missing_token_raises_cookie_error(self):
        cfg = _cfg(stoken="v2_abc", stuid="123", mid="mid_1", cookie="account_id=123")
        resp = _mock_resp({"retcode": 0, "data": {"token": {}}})
        with (
            _patch_config(cfg),
            patch("hoyo_assistant.core.login.http.post", return_value=resp),
            pytest.raises(CookieError),
        ):
            await login_mod.exchange_token_by_stoken(4)

    @pytest.mark.asyncio
    async def test_v2_exchange_other_retcode_raises_cookie_error(self):
        cfg = _cfg(stoken="v2_abc", stuid="123", mid="mid_1", cookie="account_id=123")
        resp = _mock_resp({"retcode": -500, "message": "server busy", "data": None})
        with (
            _patch_config(cfg),
            patch("hoyo_assistant.core.login.http.post", return_value=resp),
            pytest.raises(CookieError),
        ):
            await login_mod.exchange_token_by_stoken(2)


# ---------------------------------------------------------------------------
# Cookie parse / format / alias sync / build_account_cookie
# ---------------------------------------------------------------------------
class TestCookieHelpers:
    def test_parse_format_and_sync_aliases(self):
        raw = "ltoken_v2=L2; ltuid_v2=100; cookie_token_v2=C2; ltoken=OLD; badpart;"
        fields = login_mod.parse_cookie(raw)
        assert "badpart" not in fields
        changed = login_mod.sync_cookie_aliases(fields)
        assert changed is True
        assert fields["ltoken"] == "L2"
        assert fields["ltuid"] == "100"
        assert fields["cookie_token"] == "C2"
        formatted = login_mod.format_cookie(fields)
        assert "ltoken=L2;" in formatted
        assert "cookie_token_v2=C2;" in formatted
        assert login_mod.format_cookie({}) == ""

    @pytest.mark.asyncio
    async def test_build_account_cookie_fills_missing_v2_tokens(self):
        cfg = _cfg(
            cookie="account_id_v2=123; account_mid_v2=mid1",
            stoken="v2_abc",
            stuid="123",
            mid="mid1",
        )
        lt_resp = _mock_resp({"retcode": 0, "data": {"token": {"token": "LT_V2"}}})
        ct_resp = _mock_resp({"retcode": 0, "data": {"token": {"token": "CT_V2"}}})
        with (
            _patch_config(cfg),
            patch(
                "hoyo_assistant.core.login.http.post",
                side_effect=[lt_resp, ct_resp],
            ) as mock_post,
            patch(
                "hoyo_assistant.core.login.setting.save_config", new=AsyncMock()
            ) as mock_save,
        ):
            result = await login_mod.build_account_cookie()
            assert "ltoken_v2=LT_V2" in result
            assert "ltoken=LT_V2" in result
            assert "cookie_token_v2=CT_V2" in result
            assert "cookie_token=CT_V2" in result
            assert mock_post.await_count == 2
            mock_save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_build_account_cookie_empty_raises(self):
        cfg = _cfg(cookie="", stoken="v2_abc", stuid="123", mid="mid1")
        with _patch_config(cfg), pytest.raises(CookieError):
            await login_mod.build_account_cookie()


# ---------------------------------------------------------------------------
# login() orchestration
# ---------------------------------------------------------------------------
class TestLoginOrchestration:
    @pytest.mark.asyncio
    async def test_missing_cookie_raises(self):
        cfg = _cfg(cookie="")
        with (
            _patch_config(cfg),
            patch(
                "hoyo_assistant.core.login.setting.clear_cookie", new=AsyncMock()
            ) as mock_clear,
        ):
            with pytest.raises(CookieError):
                await login_mod.login()
            mock_clear.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_missing_stoken_raises(self):
        cfg = _cfg(cookie="account_id=123", stoken="")
        with _patch_config(cfg), pytest.raises(StokenError):
            await login_mod.login()

    @pytest.mark.asyncio
    async def test_missing_uid_raises(self):
        cfg = _cfg(cookie="some=value", stoken="v2_abc")
        with (
            _patch_config(cfg),
            patch(
                "hoyo_assistant.core.login.setting.clear_cookie", new=AsyncMock()
            ) as mock_clear,
        ):
            with pytest.raises(CookieError):
                await login_mod.login()
            mock_clear.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_v2_full_flow_success(self):
        """v2 stoken: extracts stuid + mid and exchanges missing ltoken_v2/cookie_token_v2 via Passport V2."""
        cfg = _cfg(
            cookie="account_id_v2=123; account_mid_v2=mid1",
            stoken="v2_abc",
            stuid="",
            mid="",
        )
        lt_resp = _mock_resp({"retcode": 0, "data": {"token": {"token": "lt_v2"}}})
        ct_resp = _mock_resp({"retcode": 0, "data": {"token": {"token": "ct_v2"}}})
        with (
            _patch_config(cfg),
            patch(
                "hoyo_assistant.core.login.http.post",
                side_effect=[lt_resp, ct_resp],
            ) as mock_post,
            patch(
                "hoyo_assistant.core.login.setting.save_config", new=AsyncMock()
            ) as mock_save,
        ):
            await login_mod.login()
            assert login_mod.config["cn"]["stuid"] == "123"
            assert login_mod.config["cn"]["mid"] == "mid1"
            assert "cookie_token_v2=ct_v2" in login_mod.config["cn"]["cookie"]
            assert "cookie_token=ct_v2" in login_mod.config["cn"]["cookie"]
            assert "ltoken_v2=lt_v2" in login_mod.config["cn"]["cookie"]
            mock_save.assert_awaited()
            assert mock_post.await_count == 2

    @pytest.mark.asyncio
    async def test_v2_cookie_token_fetch_failure_clears_stoken(self):
        cfg = _cfg(
            cookie="account_id_v2=123; account_mid_v2=mid1",
            stoken="v2_abc",
        )
        ct_resp = _mock_resp({"retcode": -100, "message": "expired", "data": None})
        with (
            _patch_config(cfg),
            patch("hoyo_assistant.core.login.http.post", return_value=ct_resp),
            patch(
                "hoyo_assistant.core.login.setting.clear_stoken", new=AsyncMock()
            ) as mock_clear,
            patch("hoyo_assistant.core.login.setting.save_config", new=AsyncMock()),
        ):
            with pytest.raises(StokenError):
                await login_mod.login()
            mock_clear.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_v1_flow_with_stoken_fetch_and_refresh(self):
        """v1 stoken verifies via legacy API_BBS_GET_COOKIE_TOKEN."""
        cfg = _cfg(
            cookie="account_id=123; login_ticket=ticket1",
            stoken="v1_abc",
        )
        stoken_resp = _mock_resp({"retcode": 0, "data": {}})
        with (
            _patch_config(cfg),
            patch(
                "hoyo_assistant.core.login.http.get", return_value=stoken_resp
            ) as mock_get,
            patch("hoyo_assistant.core.login.setting.save_config", new=AsyncMock()),
        ):
            await login_mod.login()
            assert mock_get.await_count == 1

    @pytest.mark.asyncio
    async def test_v1_stoken_fetch_failure_clears_stoken(self):
        cfg = _cfg(
            cookie="account_id=123; login_ticket=ticket1",
            stoken="v1_abc",
        )
        stoken_resp = _mock_resp({"retcode": -100, "data": None})
        with (
            _patch_config(cfg),
            patch("hoyo_assistant.core.login.http.get", return_value=stoken_resp),
            patch(
                "hoyo_assistant.core.login.setting.clear_stoken", new=AsyncMock()
            ) as mock_clear,
            patch("hoyo_assistant.core.login.setting.save_config", new=AsyncMock()),
        ):
            with pytest.raises(StokenError):
                await login_mod.login()
            mock_clear.assert_awaited_once()


# ---------------------------------------------------------------------------
# v2_stoken-related helpers (extended edge cases)
# ---------------------------------------------------------------------------
class TestV2StokenEdgeCases:
    def test_require_cookie_token_v2(self):
        with _patch_config(_cfg(stoken="v2_xyz")):
            assert login_mod.require_cookie_token() is True

    def test_require_mid_v2(self):
        with _patch_config(_cfg(stoken="v2_xyz")):
            assert login_mod.require_mid() is True

    def test_get_stoken_cookie_v2_missing_mid_raises(self):
        from hoyo_assistant.core.error import CookieError as CE

        cfg = _cfg(stoken="v2_abc", stuid="123", mid="")
        with _patch_config(cfg), pytest.raises(CE):
            login_mod.get_stoken_cookie()

    def test_get_stoken_cookie_v1_no_mid_appended(self):
        cfg = _cfg(stoken="v1_abc", stuid="456", mid="ignored")
        with _patch_config(cfg):
            # v1 → mid never appended even if present
            assert login_mod.get_stoken_cookie() == "stuid=456;stoken=v1_abc"


# ---------------------------------------------------------------------------
# Network error handling
# ---------------------------------------------------------------------------
class TestNetworkErrors:
    @pytest.mark.asyncio
    async def test_exchange_token_http_error_propagates(self):
        import aiohttp

        cfg = _cfg(stoken="v2_abc", stuid="123", mid="mid_1")
        with (
            _patch_config(cfg),
            patch(
                "hoyo_assistant.core.login.http.post",
                side_effect=aiohttp.ClientError("network down"),
            ),
            pytest.raises(aiohttp.ClientError),
        ):
            await login_mod.exchange_token_by_stoken(4)

    @pytest.mark.asyncio
    async def test_update_cookie_token_get_cookie_token_by_stoken_error(self):
        """When refresh path's get_cookie_token_by_stoken raises StokenError,
        update_cookie_token should propagate it."""
        cfg = _cfg(
            stoken="v1_abc",
            stuid="123",
            cookie="cookie_token=OLD;",
        )
        with (
            _patch_config(cfg),
            patch(
                "hoyo_assistant.core.login.get_cookie_token_by_stoken",
                new=AsyncMock(side_effect=StokenError("fail")),
            ),
            pytest.raises(StokenError),
        ):
            await login_mod.update_cookie_token()
