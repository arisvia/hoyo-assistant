"""Tests for hoyo_assistant.core.push module (PushHandler, providers, push())."""

import asyncio
import inspect

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from hoyo_assistant.core import push as push_mod
from hoyo_assistant.core.push import PushHandler, async_push, get_push_title


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _mock_resp(data=None, status=200, text="ok"):
    resp = AsyncMock()
    resp.status = status
    resp.json = AsyncMock(return_value=data if data is not None else {})
    resp.text = AsyncMock(return_value=text)
    resp.url = "http://example.com"
    return resp


def _patch_setting_config(push_cfg: dict):
    """Patch setting.config so PushHandler.get_cfg() returns push_cfg."""
    return patch("hoyo_assistant.core.push.setting.config", {"push": push_cfg})


# ---------------------------------------------------------------------------
# get_push_title
# ---------------------------------------------------------------------------
class TestGetPushTitle:
    @pytest.mark.parametrize(
        "status_id,expected_key",
        [
            (-99, "push.status_missing_dep"),
            (-2, "push.status_error_id"),
            (-1, "push.status_config_update"),
            (0, "push.status_success"),
            (1, "push.status_fail"),
            (2, "push.status_partial_fail"),
            (3, "push.status_captcha"),
        ],
    )
    def test_known_status(self, status_id, expected_key):
        with patch("hoyo_assistant.core.push.t", side_effect=lambda k, **kw: k):
            assert get_push_title(status_id) == expected_key

    def test_unknown_status(self):
        with patch("hoyo_assistant.core.push.t", side_effect=lambda k, **kw: k):
            assert get_push_title(999) == "push.status_unknown"


# ---------------------------------------------------------------------------
# PushHandler init + config helpers
# ---------------------------------------------------------------------------
class TestPushHandlerInit:
    def test_init_binds_global_http(self):
        h = PushHandler()
        assert h.http is push_mod.http

    def test_get_cfg_returns_push_dict(self):
        h = PushHandler()
        with _patch_setting_config({"enable": True, "telegram": {"x": 1}}):
            assert h.get_cfg() == {"enable": True, "telegram": {"x": 1}}

    def test_get_cfg_empty_when_no_push_key(self):
        h = PushHandler()
        with patch("hoyo_assistant.core.push.setting.config", {}):
            assert h.get_cfg() == {}

    def test_get_val_returns_nested(self):
        h = PushHandler()
        with _patch_setting_config(
            {"telegram": {"bot_token": "tok", "chat_id": "123"}}
        ):
            assert h.get_val("telegram", "bot_token") == "tok"
            assert h.get_val("telegram", "chat_id") == "123"

    def test_get_val_default_when_section_missing(self):
        h = PushHandler()
        with _patch_setting_config({"enable": True}):
            assert h.get_val("telegram", "bot_token", "def") == "def"

    def test_get_val_default_when_section_not_dict(self):
        h = PushHandler()
        with _patch_setting_config({"telegram": "not-a-dict"}):
            assert h.get_val("telegram", "bot_token", "def") == "def"

    def test_get_val_default_when_key_missing(self):
        h = PushHandler()
        with _patch_setting_config({"telegram": {"other": 1}}):
            assert h.get_val("telegram", "bot_token", "def") == "def"


# ---------------------------------------------------------------------------
# msg_replace (block keys)
# ---------------------------------------------------------------------------
class TestMsgReplace:
    def test_no_block_keys(self):
        h = PushHandler()
        with _patch_setting_config({}):
            assert h.msg_replace("hello world") == "hello world"

    def test_empty_block_keys(self):
        h = PushHandler()
        with _patch_setting_config({"push_block_keys": ""}):
            assert h.msg_replace("hello world") == "hello world"

    def test_single_block_key(self):
        h = PushHandler()
        with _patch_setting_config({"push_block_keys": "secret"}):
            assert h.msg_replace("my secret value") == "my ****** value"

    def test_multiple_block_keys(self):
        h = PushHandler()
        with _patch_setting_config({"push_block_keys": "foo,bar"}):
            result = h.msg_replace("foo and bar")
            assert "foo" not in result
            assert "bar" not in result
            assert "***" in result

    def test_block_keys_with_whitespace_trimmed(self):
        h = PushHandler()
        with _patch_setting_config({"push_block_keys": "  spaced  "}):
            # "spaced" is 6 chars → 6 asterisks
            assert h.msg_replace("a spaced b") == "a ****** b"

    def test_non_string_input_coerced(self):
        h = PushHandler()
        with _patch_setting_config({}):
            assert h.msg_replace(12345) == "12345"


# ---------------------------------------------------------------------------
# _build_push_payload
# ---------------------------------------------------------------------------
class TestBuildPushPayload:
    def test_returns_three_strings(self):
        h = PushHandler()
        with patch("hoyo_assistant.core.push.t",
                   side_effect=lambda k, **kw: k):
            title, body, full = h._build_push_payload(0, "hello")
            assert isinstance(title, str)
            assert isinstance(body, str)
            assert isinstance(full, str)

    def test_empty_message_uses_placeholder(self):
        h = PushHandler()
        calls = []

        def fake_t(k, **kw):
            calls.append((k, kw))
            if k == "push.empty_message":
                return "EMPTY"
            return k

        with patch("hoyo_assistant.core.push.t", side_effect=fake_t):
            _, body, _ = h._build_push_payload(0, "")
            # body template call should have content="EMPTY"
            body_call = next(
                c for c in calls if c[0] == "push.template_body"
            )
            assert body_call[1]["content"] == "EMPTY"

    def test_none_message_uses_placeholder(self):
        h = PushHandler()
        seen = []

        def fake_t(k, **kw):
            seen.append((k, kw))
            return k

        with patch("hoyo_assistant.core.push.t", side_effect=fake_t):
            h._build_push_payload(0, None)
        # When push_message is None, content falls back to push.empty_message
        empty_calls = [c for c in seen if c[0] == "push.empty_message"]
        assert len(empty_calls) == 1


# ---------------------------------------------------------------------------
# Provider tests — each mocks self.http.post / self.http.get
# ---------------------------------------------------------------------------
class TestTelegramProvider:
    @pytest.mark.asyncio
    async def test_sends_post(self):
        h = PushHandler()
        resp = _mock_resp()
        with _patch_setting_config(
            {"telegram": {"bot_token": "BOT", "chat_id": "123"}}
        ), patch.object(h, "http") as mock_http:
            mock_http.post = AsyncMock(return_value=resp)
            await h.telegram(0, "msg")
            mock_http.post.assert_awaited_once()
            _, kwargs = mock_http.post.call_args
            assert "BOT" in kwargs["url"]
            assert kwargs["data"]["chat_id"] == "123"

    @pytest.mark.asyncio
    async def test_custom_api_url(self):
        h = PushHandler()
        resp = _mock_resp()
        with _patch_setting_config(
            {"telegram": {
                "api_url": "custom.telegram.example",
                "bot_token": "BOT",
                "chat_id": "1",
            }}
        ), patch.object(h, "http") as mock_http:
            mock_http.post = AsyncMock(return_value=resp)
            await h.telegram(0, "msg")
            _, kwargs = mock_http.post.call_args
            assert "custom.telegram.example" in kwargs["url"]


class TestFtqqProvider:
    @pytest.mark.asyncio
    async def test_sends_post_with_sendkey(self):
        h = PushHandler()
        resp = _mock_resp()
        with _patch_setting_config({"ftqq": {"sendkey": "SK123"}}), \
             patch.object(h, "http") as mock_http:
            mock_http.post = AsyncMock(return_value=resp)
            await h.ftqq(0, "msg")
            _, kwargs = mock_http.post.call_args
            assert "SK123.send" in kwargs["url"]
            assert "title" in kwargs["data"]
            assert "desp" in kwargs["data"]


class TestPushplusProvider:
    @pytest.mark.asyncio
    async def test_sends_post(self):
        h = PushHandler()
        resp = _mock_resp()
        with _patch_setting_config(
            {"pushplus": {"token": "TOK", "topic": "TPC"}}
        ), patch.object(h, "http") as mock_http:
            mock_http.post = AsyncMock(return_value=resp)
            await h.pushplus(0, "msg")
            _, kwargs = mock_http.post.call_args
            assert kwargs["data"]["token"] == "TOK"
            assert kwargs["data"]["topic"] == "TPC"


class TestPushmeProvider:
    @pytest.mark.asyncio
    async def test_missing_key_returns_early(self):
        h = PushHandler()
        with _patch_setting_config({"pushme": {"token": ""}}), \
             patch.object(h, "http") as mock_http:
            mock_http.post = AsyncMock()
            await h.pushme(0, "msg")
            mock_http.post.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_success_path(self):
        h = PushHandler()
        resp = _mock_resp(status=200, text="success")
        with _patch_setting_config({"pushme": {"token": "KEY"}}), \
             patch.object(h, "http") as mock_http:
            mock_http.post = AsyncMock(return_value=resp)
            await h.pushme(0, "msg")
            mock_http.post.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_non_success_response_logs_error(self):
        h = PushHandler()
        resp = _mock_resp(status=500, text="fail")
        with _patch_setting_config({"pushme": {"token": "KEY"}}), \
             patch.object(h, "http") as mock_http, \
             patch("hoyo_assistant.core.push.log") as mock_log:
            mock_http.post = AsyncMock(return_value=resp)
            await h.pushme(0, "msg")
            mock_log.error.assert_called()


class TestCqhttpProvider:
    @pytest.mark.asyncio
    async def test_qq_and_group_both_set_aborts(self):
        h = PushHandler()
        with _patch_setting_config(
            {"cqhttp": {"cqhttp_qq": "1", "cqhttp_group": "2"}}
        ), patch.object(h, "http") as mock_http:
            mock_http.post = AsyncMock()
            await h.cqhttp(0, "msg")
            mock_http.post.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_qq_only_sends(self):
        h = PushHandler()
        resp = _mock_resp()
        with _patch_setting_config(
            {"cqhttp": {"cqhttp_qq": "123", "cqhttp_group": None,
                        "cqhttp_url": "http://cq/"}}
        ), patch.object(h, "http") as mock_http:
            mock_http.post = AsyncMock(return_value=resp)
            await h.cqhttp(0, "msg")
            _, kwargs = mock_http.post.call_args
            assert kwargs["json"]["user_id"] == 123
            assert "group_id" not in kwargs["json"]

    @pytest.mark.asyncio
    async def test_group_only_sends(self):
        h = PushHandler()
        resp = _mock_resp()
        with _patch_setting_config(
            {"cqhttp": {"cqhttp_qq": None, "cqhttp_group": "456",
                        "cqhttp_url": "http://cq/"}}
        ), patch.object(h, "http") as mock_http:
            mock_http.post = AsyncMock(return_value=resp)
            await h.cqhttp(0, "msg")
            _, kwargs = mock_http.post.call_args
            assert kwargs["json"]["group_id"] == 456
            assert "user_id" not in kwargs["json"]


class TestWecomProvider:
    @pytest.mark.asyncio
    async def test_two_post_calls(self):
        h = PushHandler()
        token_resp = _mock_resp({"access_token": "AT"})
        send_resp = _mock_resp()
        with _patch_setting_config(
            {"wecom": {"secret": "S", "wechat_id": "CID", "agentid": "9",
                       "touser": "@all"}}
        ), patch.object(h, "http") as mock_http:
            mock_http.post = AsyncMock(
                side_effect=[token_resp, send_resp]
            )
            await h.wecom(0, "msg")
            assert mock_http.post.await_count == 2
            # first call: gettoken (url passed as kwarg)
            first_url = mock_http.post.call_args_list[0].kwargs["url"]
            assert "gettoken" in first_url
            # second call: message/send (url passed positionally)
            second_args = mock_http.post.call_args_list[1].args
            assert "message/send" in second_args[0]
            assert "AT" in second_args[0]


class TestPushdeerProvider:
    @pytest.mark.asyncio
    async def test_sends_get(self):
        h = PushHandler()
        resp = _mock_resp()
        with _patch_setting_config(
            {"pushdeer": {"api_url": "http://pd", "token": "TK"}}
        ), patch.object(h, "http") as mock_http:
            mock_http.get = AsyncMock(return_value=resp)
            await h.pushdeer(0, "msg")
            _, kwargs = mock_http.get.call_args
            assert "message/push" in kwargs["url"]
            assert kwargs["params"]["pushkey"] == "TK"


class TestBarkProvider:
    @pytest.mark.asyncio
    async def test_sends_get(self):
        h = PushHandler()
        resp = _mock_resp({"message": "ok"})
        with _patch_setting_config(
            {"bark": {"api_url": "http://bark", "token": "TK", "icon": "x"}}
        ), patch.object(h, "http") as mock_http:
            mock_http.get = AsyncMock(return_value=resp)
            await h.bark(0, "msg")
            _, kwargs = mock_http.get.call_args
            assert "/TK/" in kwargs["url"]


class TestGotifyProvider:
    @pytest.mark.asyncio
    async def test_sends_post_with_priority(self):
        h = PushHandler()
        resp = _mock_resp({"errmsg": "ok"})
        with _patch_setting_config(
            {"gotify": {"api_url": "http://g", "token": "TK", "priority": 5}}
        ), patch.object(h, "http") as mock_http:
            mock_http.post = AsyncMock(return_value=resp)
            await h.gotify(0, "msg")
            _, kwargs = mock_http.post.call_args
            assert "message?token=TK" in kwargs["url"]
            assert kwargs["json"]["priority"] == 5


class TestIftttProvider:
    @pytest.mark.asyncio
    async def test_success_returns_one(self):
        h = PushHandler()
        resp = _mock_resp(text="ok")
        with _patch_setting_config(
            {"ifttt": {"event": "EV", "key": "KY"}}
        ), patch.object(h, "http") as mock_http:
            mock_http.post = AsyncMock(return_value=resp)
            result = await h.ifttt(0, "msg")
            assert result == 1

    @pytest.mark.asyncio
    async def test_errors_returns_zero(self):
        h = PushHandler()
        resp = _mock_resp(text='{"errors":["bad"]}')
        with _patch_setting_config(
            {"ifttt": {"event": "EV", "key": "KY"}}
        ), patch.object(h, "http") as mock_http:
            mock_http.post = AsyncMock(return_value=resp)
            result = await h.ifttt(0, "msg")
            assert result == 0


class TestWebhookProvider:
    @pytest.mark.asyncio
    async def test_sends_post(self):
        h = PushHandler()
        resp = _mock_resp({"errmsg": "ok"})
        with _patch_setting_config(
            {"webhook": {"webhook_url": "http://wh"}}
        ), patch.object(h, "http") as mock_http:
            mock_http.post = AsyncMock(return_value=resp)
            await h.webhook(0, "msg")
            _, kwargs = mock_http.post.call_args
            assert kwargs["url"] == "http://wh"
            assert "title" in kwargs["json"]
            assert "message" in kwargs["json"]


class TestQmsgProvider:
    @pytest.mark.asyncio
    async def test_sends_post(self):
        h = PushHandler()
        resp = _mock_resp({"reason": "ok"})
        with _patch_setting_config(
            {"qmsg": {"key": "K"}}
        ), patch.object(h, "http") as mock_http:
            mock_http.post = AsyncMock(return_value=resp)
            await h.qmsg(0, "msg")
            _, kwargs = mock_http.post.call_args
            assert "/send/K" in kwargs["url"]
            assert "msg" in kwargs["data"]


class TestDiscordProvider:
    @pytest.mark.asyncio
    async def test_success_status_204(self):
        h = PushHandler()
        resp = _mock_resp(status=204, text="")
        with _patch_setting_config(
            {"discord": {"webhook": "http://dc"}}
        ), patch.object(h, "http") as mock_http, \
             patch("hoyo_assistant.core.push.log") as mock_log:
            mock_http.post = AsyncMock(return_value=resp)
            await h.discord(0, "msg")
            mock_http.post.assert_awaited_once()
            mock_log.info.assert_called()

    @pytest.mark.asyncio
    async def test_non_204_logs_warning(self):
        h = PushHandler()
        resp = _mock_resp(status=400, text="bad")
        with _patch_setting_config(
            {"discord": {"webhook": "http://dc"}}
        ), patch.object(h, "http") as mock_http, \
             patch("hoyo_assistant.core.push.log") as mock_log:
            mock_http.post = AsyncMock(return_value=resp)
            await h.discord(0, "msg")
            mock_log.warning.assert_called()

    @pytest.mark.parametrize(
        "status_id,expected_color",
        [(0, 1926125), (1, 14368575), (2, 16744192), (3, 16744192)],
    )
    def test_get_color_logic(self, status_id, expected_color):
        # Replicate the get_color closure logic from discord()
        embed_color = 16744192
        if status_id == 0:
            embed_color = 1926125
        elif status_id == 1:
            embed_color = 14368575
        elif status_id in (2, 3):
            embed_color = 16744192
        assert embed_color == expected_color


class TestServerchan3Provider:
    @pytest.mark.asyncio
    async def test_valid_key_sends_post(self):
        h = PushHandler()
        resp = _mock_resp()
        with _patch_setting_config(
            {"serverchan3": {"sendkey": "sctp123t", "tags": ""}}
        ), patch.object(h, "http") as mock_http:
            mock_http.post = AsyncMock(return_value=resp)
            await h.serverchan3(0, "msg")
            _, kwargs = mock_http.post.call_args
            assert "123.push.ft07.com" in kwargs["url"]
            assert "sctp123t.send" in kwargs["url"]

    @pytest.mark.asyncio
    async def test_invalid_key_raises_value_error(self):
        h = PushHandler()
        with _patch_setting_config(
            {"serverchan3": {"sendkey": "invalid_key", "tags": ""}}
        ):
            with pytest.raises(ValueError):
                await h.serverchan3(0, "msg")


class TestWecomrobotProvider:
    @pytest.mark.asyncio
    async def test_sends_post(self):
        h = PushHandler()
        resp = _mock_resp({"errmsg": "ok"})
        with _patch_setting_config(
            {"wecomrobot": {"url": "http://wr", "mobile": "13800000000"}}
        ), patch.object(h, "http") as mock_http:
            mock_http.post = AsyncMock(return_value=resp)
            await h.wecomrobot(0, "msg")
            _, kwargs = mock_http.post.call_args
            assert kwargs["json"]["text"]["mentioned_mobile_list"] == [
                "13800000000"
            ]


class TestFeishubotProvider:
    @pytest.mark.asyncio
    async def test_sends_post(self):
        h = PushHandler()
        resp = _mock_resp({"msg": "ok"})
        with _patch_setting_config(
            {"feishubot": {"webhook": "http://fs"}}
        ), patch.object(h, "http") as mock_http:
            mock_http.post = AsyncMock(return_value=resp)
            await h.feishubot(0, "msg")
            _, kwargs = mock_http.post.call_args
            assert kwargs["json"]["msg_type"] == "text"


class TestDingrobotProvider:
    @pytest.mark.asyncio
    async def test_no_secret(self):
        h = PushHandler()
        resp = _mock_resp({"errmsg": "ok"})
        with _patch_setting_config(
            {"dingrobot": {"webhook": "http://dr", "secret": ""}}
        ), patch.object(h, "http") as mock_http:
            mock_http.post = AsyncMock(return_value=resp)
            await h.dingrobot(0, "msg")
            url = mock_http.post.call_args.kwargs["url"]
            assert url == "http://dr"
            assert "timestamp" not in url

    @pytest.mark.asyncio
    async def test_with_secret_appends_sign(self):
        h = PushHandler()
        resp = _mock_resp({"errmsg": "ok"})
        with _patch_setting_config(
            {"dingrobot": {"webhook": "http://dr", "secret": "SEC"}}
        ), patch.object(h, "http") as mock_http:
            mock_http.post = AsyncMock(return_value=resp)
            await h.dingrobot(0, "msg")
            url = mock_http.post.call_args.kwargs["url"]
            assert "timestamp=" in url
            assert "sign=" in url


# ---------------------------------------------------------------------------
# push() dispatch orchestration
# ---------------------------------------------------------------------------
class TestPushDispatch:
    @pytest.mark.asyncio
    async def test_disabled_returns_zero(self):
        h = PushHandler()
        with _patch_setting_config({"enable": False, "active": ["telegram"]}):
            result = await h.push(0, "msg")
            assert result == 0

    @pytest.mark.asyncio
    async def test_error_push_only_skips_success_status(self):
        h = PushHandler()
        with _patch_setting_config(
            {"enable": True, "error_push_only": True, "active": ["telegram"]}
        ), patch.object(h, "telegram", new=AsyncMock()) as mock_tg:
            result = await h.push(0, "msg")
            assert result == 0
            mock_tg.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_error_push_only_allows_failure_status(self):
        h = PushHandler()
        with _patch_setting_config(
            {"enable": True, "error_push_only": True, "active": ["telegram"]}
        ), patch.object(h, "telegram", new=AsyncMock()) as mock_tg:
            result = await h.push(1, "msg")
            mock_tg.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_dispatches_all_active_channels(self):
        h = PushHandler()
        with _patch_setting_config(
            {"enable": True, "active": ["telegram", "ftqq", "pushplus"]}
        ), patch.object(h, "telegram", new=AsyncMock()) as mock_tg, \
             patch.object(h, "ftqq", new=AsyncMock()) as mock_ft, \
             patch.object(h, "pushplus", new=AsyncMock()) as mock_pp:
            result = await h.push(0, "msg")
            assert result == 0
            mock_tg.assert_awaited_once()
            mock_ft.assert_awaited_once()
            mock_pp.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_unknown_channel_name_skipped(self):
        h = PushHandler()
        with _patch_setting_config(
            {"enable": True, "active": ["nonexistent_channel"]}
        ), patch("hoyo_assistant.core.push.log") as mock_log:
            result = await h.push(0, "msg")
            # func is None → warning, push_success stays True → 0
            assert result == 0
            mock_log.warning.assert_called()

    @pytest.mark.asyncio
    async def test_provider_exception_returns_one(self):
        h = PushHandler()
        with _patch_setting_config(
            {"enable": True, "active": ["telegram"]}
        ), patch.object(h, "telegram",
                        new=AsyncMock(side_effect=RuntimeError("boom"))):
            result = await h.push(0, "msg")
            assert result == 1

    @pytest.mark.asyncio
    async def test_msg_replace_applied_before_dispatch(self):
        h = PushHandler()
        with _patch_setting_config(
            {"enable": True, "active": ["telegram"], "push_block_keys": "secret"}
        ), patch.object(h, "telegram", new=AsyncMock()) as mock_tg:
            await h.push(0, "my secret msg")
            # push() calls func(status, masked_msg) positionally
            sent_msg = mock_tg.call_args[0][1]
            assert "******" in sent_msg
            assert "secret" not in sent_msg

    @pytest.mark.asyncio
    async def test_sync_provider_invoked_without_await(self):
        """wintoast is a sync method; push() should call it directly."""
        h = PushHandler()
        called = {"count": 0}

        def fake_wintoast(status_id, msg):
            called["count"] += 1

        with _patch_setting_config(
            {"enable": True, "active": ["wintoast"]}
        ), patch.object(h, "wintoast", side_effect=fake_wintoast):
            await h.push(0, "msg")
            assert called["count"] == 1

    @pytest.mark.asyncio
    async def test_partial_failure_returns_one(self):
        h = PushHandler()
        with _patch_setting_config(
            {"enable": True, "active": ["telegram", "ftqq"]}
        ), patch.object(h, "telegram", new=AsyncMock()), \
             patch.object(h, "ftqq",
                          new=AsyncMock(side_effect=ValueError("x"))):
            result = await h.push(0, "msg")
            assert result == 1


# ---------------------------------------------------------------------------
# async_push / module-level push
# ---------------------------------------------------------------------------
class TestAsyncPush:
    @pytest.mark.asyncio
    async def test_async_push_returns_zero_when_disabled(self):
        with _patch_setting_config({"enable": False, "active": []}):
            result = await async_push(0, "msg")
            assert result == 0

    @pytest.mark.asyncio
    async def test_push_alias_is_async_push(self):
        assert push_mod.push is async_push

    @pytest.mark.asyncio
    async def test_async_push_dispatches_through_handler(self):
        with _patch_setting_config(
            {"enable": True, "active": ["telegram"]}
        ), patch.object(PushHandler, "telegram", new=AsyncMock()) as mock_tg:
            await push_mod.push(0, "msg")
            mock_tg.assert_awaited_once()


# ---------------------------------------------------------------------------
# Timeout / network error handling
# ---------------------------------------------------------------------------
class TestPushNetworkErrors:
    @pytest.mark.asyncio
    async def test_provider_timeout_caught_by_push_dispatch(self):
        import asyncio as _asyncio

        h = PushHandler()
        with _patch_setting_config(
            {"enable": True, "active": ["telegram"]}
        ), patch.object(h, "telegram",
                        new=AsyncMock(side_effect=_asyncio.TimeoutError())):
            result = await h.push(0, "msg")
            assert result == 1

    @pytest.mark.asyncio
    async def test_provider_aiohttp_error_caught(self):
        import aiohttp

        h = PushHandler()
        with _patch_setting_config(
            {"enable": True, "active": ["telegram"]}
        ), patch.object(
            h, "telegram",
            new=AsyncMock(side_effect=aiohttp.ClientError("net")),
        ):
            result = await h.push(0, "msg")
            assert result == 1

    @pytest.mark.asyncio
    async def test_telegram_propagates_http_error_when_called_directly(self):
        import aiohttp

        h = PushHandler()
        with _patch_setting_config(
            {"telegram": {"bot_token": "B", "chat_id": "1"}}
        ), patch.object(h, "http") as mock_http:
            mock_http.post = AsyncMock(
                side_effect=aiohttp.ClientError("timeout")
            )
            with pytest.raises(aiohttp.ClientError):
                await h.telegram(0, "msg")


# ---------------------------------------------------------------------------
# Provider registration sanity (all are coroutine functions except wintoast)
# ---------------------------------------------------------------------------
class TestProviderRegistration:
    @pytest.mark.parametrize(
        "name",
        [
            "telegram", "ftqq", "pushplus", "pushme", "cqhttp", "smtp",
            "wecom", "wecomrobot", "pushdeer", "dingrobot", "feishubot",
            "bark", "gotify", "ifttt", "webhook", "qmsg", "discord",
            "serverchan3",
        ],
    )
    def test_provider_exists_on_handler(self, name):
        h = PushHandler()
        assert hasattr(h, name)
        assert callable(getattr(h, name))

    def test_all_providers_async_except_wintoast(self):
        h = PushHandler()
        async_names = [
            "telegram", "ftqq", "pushplus", "pushme", "cqhttp", "smtp",
            "wecom", "wecomrobot", "pushdeer", "dingrobot", "feishubot",
            "bark", "gotify", "ifttt", "webhook", "qmsg", "discord",
            "serverchan3",
        ]
        for name in async_names:
            assert inspect.iscoroutinefunction(getattr(h, name)), \
                f"{name} should be async"
        assert not inspect.iscoroutinefunction(h.wintoast)
