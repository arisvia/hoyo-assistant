"""Tests for hoyo_assistant.core.push module (named targets & per-target routing)."""

from unittest.mock import AsyncMock, patch

import pytest

from hoyo_assistant.core import StatusCode, push as push_mod
from hoyo_assistant.core.models import AccountRunResult
from hoyo_assistant.core.push import (
    PushHandler,
    async_push,
    dispatch_push,
    get_push_title,
)


def _mock_resp(data=None, status=200, text="ok"):
    resp = AsyncMock()
    resp.status = status
    resp.json = AsyncMock(return_value=data if data is not None else {})
    resp.text = AsyncMock(return_value=text)
    resp.url = "http://example.com"
    return resp


def _patch_setting_config(push_cfg: dict):
    return patch("hoyo_assistant.core.push.setting.config", {"push": push_cfg})


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


class TestPushHandlerInit:
    def test_init_binds_global_http(self):
        h = PushHandler()
        assert h.http is push_mod.http

    def test_get_targets_returns_dict(self):
        h = PushHandler()
        with _patch_setting_config(
            {"enable": True, "targets": {"tg_main": {"type": "telegram"}}}
        ):
            assert h.get_targets() == {"tg_main": {"type": "telegram"}}

    def test_get_targets_empty_when_missing(self):
        h = PushHandler()
        with patch("hoyo_assistant.core.push.setting.config", {}):
            assert h.get_targets() == {}


class TestMsgReplace:
    def test_no_block_keys(self):
        h = PushHandler()
        with _patch_setting_config({}):
            assert h.msg_replace("hello world") == "hello world"

    def test_single_and_multiple_block_keys(self):
        h = PushHandler()
        with _patch_setting_config({"block_keys": ["secret", "token"]}):
            assert h.msg_replace("my secret token") == "my ****** *****"

    def test_string_block_keys_trimmed(self):
        h = PushHandler()
        with _patch_setting_config({"block_keys": "  spaced  "}):
            assert h.msg_replace("a spaced b") == "a ****** b"


class TestProviders:
    @pytest.mark.asyncio
    async def test_telegram(self):
        h = PushHandler()
        with patch.object(h, "http") as mock_http:
            mock_http.post = AsyncMock(return_value=_mock_resp())
            await h.telegram(
                0,
                "msg",
                {"api_url": "custom.tg", "bot_token": "BOT", "chat_id": "123"},
            )
            _, kwargs = mock_http.post.call_args
            assert "custom.tg/botBOT/sendMessage" in kwargs["url"]
            assert kwargs["data"]["chat_id"] == "123"

    @pytest.mark.asyncio
    async def test_ftqq(self):
        h = PushHandler()
        with patch.object(h, "http") as mock_http:
            mock_http.post = AsyncMock(return_value=_mock_resp())
            await h.ftqq(0, "msg", {"sendkey": "SK123"})
            assert "SK123.send" in mock_http.post.call_args.kwargs["url"]

    @pytest.mark.asyncio
    async def test_pushplus(self):
        h = PushHandler()
        with patch.object(h, "http") as mock_http:
            mock_http.post = AsyncMock(return_value=_mock_resp())
            await h.pushplus(0, "msg", {"token": "TOK", "topic": "TPC"})
            assert mock_http.post.call_args.kwargs["data"]["token"] == "TOK"

    @pytest.mark.asyncio
    async def test_pushme_success_and_missing_key(self):
        h = PushHandler()
        with patch.object(h, "http") as mock_http:
            mock_http.post = AsyncMock()
            await h.pushme(0, "msg", {"token": ""})
            mock_http.post.assert_not_awaited()

            mock_http.post = AsyncMock(
                return_value=_mock_resp(status=200, text="success")
            )
            await h.pushme(0, "msg", {"token": "KEY"})
            mock_http.post.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cqhttp(self):
        h = PushHandler()
        with patch.object(h, "http") as mock_http:
            mock_http.post = AsyncMock()
            await h.cqhttp(0, "msg", {"qq": "1", "group": "2"})
            mock_http.post.assert_not_awaited()

            mock_http.post = AsyncMock(return_value=_mock_resp())
            await h.cqhttp(0, "msg", {"qq": "123", "group": None, "url": "http://cq/"})
            assert mock_http.post.call_args.kwargs["json"]["user_id"] == 123

    @pytest.mark.asyncio
    async def test_wecom(self):
        h = PushHandler()
        token_resp = _mock_resp({"access_token": "AT"})
        send_resp = _mock_resp()
        with patch.object(h, "http") as mock_http:
            mock_http.post = AsyncMock(side_effect=[token_resp, send_resp])
            await h.wecom(
                0,
                "msg",
                {"secret": "S", "wechat_id": "CID", "agentid": "9", "touser": "@all"},
            )
            assert mock_http.post.await_count == 2

    @pytest.mark.asyncio
    async def test_wecomrobot(self):
        h = PushHandler()
        with patch.object(h, "http") as mock_http:
            mock_http.post = AsyncMock(return_value=_mock_resp({"errmsg": "ok"}))
            await h.wecomrobot(0, "msg", {"url": "http://wr", "mobile": ["138"]})
            assert mock_http.post.call_args.kwargs["json"]["text"][
                "mentioned_mobile_list"
            ] == ["138"]

    @pytest.mark.asyncio
    async def test_pushdeer_and_bark_and_gotify(self):
        h = PushHandler()
        with patch.object(h, "http") as mock_http:
            mock_http.get = AsyncMock(return_value=_mock_resp({"message": "ok"}))
            mock_http.post = AsyncMock(return_value=_mock_resp({"errmsg": "ok"}))
            await h.pushdeer(0, "msg", {"api_url": "http://pd", "token": "TK"})
            assert mock_http.get.call_args.kwargs["params"]["pushkey"] == "TK"

            await h.bark(
                0, "msg", {"api_url": "http://bark", "token": "TK", "icon": "x"}
            )
            assert "/TK/" in mock_http.get.call_args.kwargs["url"]

            await h.gotify(
                0, "msg", {"api_url": "http://g", "token": "TK", "priority": 5}
            )
            assert mock_http.post.call_args.kwargs["json"]["priority"] == 5

    @pytest.mark.asyncio
    async def test_ifttt(self):
        h = PushHandler()
        with patch.object(h, "http") as mock_http:
            mock_http.post = AsyncMock(return_value=_mock_resp(text="ok"))
            assert await h.ifttt(0, "msg", {"event": "EV", "key": "KY"}) == 1
            mock_http.post = AsyncMock(
                return_value=_mock_resp(text='{"errors":["bad"]}')
            )
            assert await h.ifttt(0, "msg", {"event": "EV", "key": "KY"}) == 0

    @pytest.mark.asyncio
    async def test_webhook_and_qmsg_and_discord(self):
        h = PushHandler()
        with patch.object(h, "http") as mock_http:
            mock_http.post = AsyncMock(return_value=_mock_resp({"errmsg": "ok"}))
            await h.webhook(0, "msg", {"url": "http://wh"})
            assert mock_http.post.call_args.kwargs["url"] == "http://wh"

            await h.qmsg(0, "msg", {"key": "K"})
            assert "/send/K" in mock_http.post.call_args.kwargs["url"]

            mock_http.post = AsyncMock(return_value=_mock_resp(status=204))
            await h.discord(0, "msg", {"webhook": "http://dc"})
            mock_http.post.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_dingrobot_and_feishubot(self):
        h = PushHandler()
        with patch.object(h, "http") as mock_http:
            mock_http.post = AsyncMock(return_value=_mock_resp({"errmsg": "ok"}))
            await h.dingrobot(0, "msg", {"webhook": "http://dr", "secret": "SEC"})
            assert "sign=" in mock_http.post.call_args.kwargs["url"]

            await h.feishubot(0, "msg", {"webhook": "http://fs", "secret": "SEC"})
            assert "sign" in mock_http.post.call_args.kwargs["json"]

    @pytest.mark.asyncio
    async def test_serverchan3_wxpusher_ntfy(self):
        h = PushHandler()
        with patch.object(h, "http") as mock_http:
            mock_http.post = AsyncMock(return_value=_mock_resp({"msg": "ok"}))
            await h.serverchan3(0, "msg", {"sendkey": "sctp123t", "tags": ""})
            assert "123.push.ft07.com" in mock_http.post.call_args.kwargs["url"]

            await h.wxpusher(
                0,
                "msg",
                {"app_token": "AT", "uids": ["U1"], "topic_ids": [101]},
            )
            assert mock_http.post.call_args.kwargs["json"]["appToken"] == "AT"

            await h.ntfy(
                0,
                "msg",
                {
                    "api_url": "https://ntfy.example.com/",
                    "topic": "hoyo",
                    "token": "tk",
                    "priority": "high",
                },
            )
            assert (
                mock_http.post.call_args.kwargs["url"]
                == "https://ntfy.example.com/hoyo"
            )


class TestNamedTargetRoutingAndAggregation:
    @pytest.mark.asyncio
    async def test_dispatch_results_merges_shared_target_and_isolates_override(self):
        h = PushHandler()
        cfg = {
            "enable": True,
            "error_only": False,
            "merge": True,
            "default": ["tg_main"],
            "targets": {
                "tg_main": {"type": "telegram", "bot_token": "MAIN", "chat_id": "1"},
                "tg_friend": {
                    "type": "telegram",
                    "bot_token": "FRIEND",
                    "chat_id": "2",
                },
            },
        }
        results = [
            AccountRunResult("国服-1", "cn", StatusCode.SUCCESS.value, "ok1", None),
            AccountRunResult(
                "国服-2", "cn", StatusCode.FAILURE.value, "bad2", ["tg_friend"]
            ),
            AccountRunResult("国际服", "os", StatusCode.SUCCESS.value, "ok3", None),
            AccountRunResult("静默号", "os", StatusCode.SUCCESS.value, "ok4", []),
        ]
        sent: list[tuple[str, int, str]] = []

        async def fake_send(target_name, status, message):
            sent.append((target_name, status, message))
            return True

        with (
            _patch_setting_config(cfg),
            patch("hoyo_assistant.core.push.is_push_enabled", return_value=True),
            patch.object(h, "send_to_target", side_effect=fake_send),
        ):
            rc = await h.dispatch_results(results)

        assert rc == 0
        assert len(sent) == 2
        assert sent[0][0] == "tg_main"
        assert sent[0][1] == StatusCode.SUCCESS.value
        assert "【国服-1】\nok1" in sent[0][2]
        assert "【国际服】\nok3" in sent[0][2]
        assert "国服-2" not in sent[0][2]
        assert "静默号" not in sent[0][2]

        assert sent[1][0] == "tg_friend"
        assert sent[1][1] == StatusCode.FAILURE.value
        assert sent[1][2] == "【国服-2】\nbad2"

    @pytest.mark.asyncio
    async def test_error_only_evaluates_independently_per_target(self):
        h = PushHandler()
        cfg = {
            "enable": True,
            "error_only": True,
            "merge": True,
            "default": ["tg_main"],
            "targets": {
                "tg_main": {"type": "telegram", "bot_token": "MAIN", "chat_id": "1"},
                "tg_friend": {
                    "type": "telegram",
                    "bot_token": "FRIEND",
                    "chat_id": "2",
                },
            },
        }
        results = [
            AccountRunResult("国服-1", "cn", StatusCode.SUCCESS.value, "ok1", None),
            AccountRunResult(
                "国服-2", "cn", StatusCode.FAILURE.value, "bad2", ["tg_friend"]
            ),
        ]
        sent: list[str] = []

        async def fake_send(target_name, status, message):
            sent.append(target_name)
            return True

        with (
            _patch_setting_config(cfg),
            patch("hoyo_assistant.core.push.is_push_enabled", return_value=True),
            patch.object(h, "send_to_target", side_effect=fake_send),
        ):
            await h.dispatch_results(results)

        assert sent == ["tg_friend"]

    @pytest.mark.asyncio
    async def test_merge_false_sends_per_account(self):
        h = PushHandler()
        cfg = {
            "enable": True,
            "error_only": False,
            "merge": False,
            "default": ["tg_main"],
            "targets": {
                "tg_main": {"type": "telegram", "bot_token": "MAIN", "chat_id": "1"},
            },
        }
        results = [
            AccountRunResult("A", "cn", StatusCode.SUCCESS.value, "m1", None),
            AccountRunResult("B", "os", StatusCode.SUCCESS.value, "m2", None),
        ]
        sent: list[str] = []

        async def fake_send(target_name, status, message):
            sent.append(message)
            return True

        with (
            _patch_setting_config(cfg),
            patch("hoyo_assistant.core.push.is_push_enabled", return_value=True),
            patch.object(h, "send_to_target", side_effect=fake_send),
        ):
            await h.dispatch_results(results)

        assert sent == ["【A】\nm1", "【B】\nm2"]

    @pytest.mark.asyncio
    async def test_disabled_returns_zero_without_sending(self):
        h = PushHandler()
        with (
            _patch_setting_config(
                {
                    "enable": False,
                    "default": ["tg_main"],
                    "targets": {"tg_main": {"type": "telegram"}},
                }
            ),
            patch("hoyo_assistant.core.push.is_push_enabled", return_value=False),
            patch.object(h, "send_to_target", new=AsyncMock()) as mock_send,
        ):
            assert await h.push(0, "msg") == 0
            assert (
                await dispatch_push([AccountRunResult("A", "cn", 0, "ok", None)]) == 0
            )
            mock_send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_send_to_target_handles_unknown_target_and_provider_error(self):
        h = PushHandler()
        with _patch_setting_config({"targets": {"bad": {"type": "telegram"}}}):
            assert await h.send_to_target("missing", 0, "m") is False
            with patch.object(
                h, "telegram", new=AsyncMock(side_effect=RuntimeError("boom"))
            ):
                assert await h.send_to_target("bad", 0, "m") is False

    @pytest.mark.asyncio
    async def test_async_push_uses_default_targets(self):
        cfg = {
            "enable": True,
            "default": ["tg_main"],
            "targets": {
                "tg_main": {"type": "telegram", "bot_token": "B", "chat_id": "1"}
            },
        }
        with (
            _patch_setting_config(cfg),
            patch("hoyo_assistant.core.push.is_push_enabled", return_value=True),
            patch.object(
                PushHandler, "send_to_target", new=AsyncMock(return_value=True)
            ) as mock_send,
        ):
            rc = await async_push(0, "hello")
        assert rc == 0
        mock_send.assert_awaited_once_with("tg_main", 0, "hello")


class TestPushProviderFixes:
    @pytest.mark.asyncio
    async def test_telegram_accepts_full_scheme_api_url(self):
        h = PushHandler()
        with patch.object(h, "http") as mock_http:
            mock_http.post = AsyncMock(return_value=_mock_resp({"ok": True}))
            await h.telegram(
                0,
                "msg",
                {
                    "api_url": "https://tg-proxy.example.com/",
                    "bot_token": "BOT",
                    "chat_id": "123",
                },
            )
            assert (
                mock_http.post.call_args.kwargs["url"]
                == "https://tg-proxy.example.com/botBOT/sendMessage"
            )

    @pytest.mark.asyncio
    async def test_dingrobot_without_query_uses_question_mark(self):
        h = PushHandler()
        with patch.object(h, "http") as mock_http:
            mock_http.post = AsyncMock(return_value=_mock_resp({"errcode": 0}))
            await h.dingrobot(
                0,
                "msg",
                {"webhook": "https://oapi.dingtalk.com/robot/send", "secret": "SEC"},
            )
            url = mock_http.post.call_args.kwargs["url"]
            assert "?timestamp=" in url

    @pytest.mark.asyncio
    async def test_webhook_handles_204_empty_json_and_400_failure(self):
        h = PushHandler()
        resp_204 = AsyncMock()
        resp_204.status = 204
        resp_204.json = AsyncMock(side_effect=ValueError("no body"))
        resp_204.text = AsyncMock(return_value="")

        resp_500 = _mock_resp(status=500, text="Internal Server Error")
        with (
            _patch_setting_config(
                {"targets": {"wh": {"type": "webhook", "url": "http://wh"}}}
            ),
            patch.object(h, "http") as mock_http,
        ):
            mock_http.post = AsyncMock(return_value=resp_204)
            assert await h.send_to_target("wh", 0, "msg") is True

            mock_http.post = AsyncMock(return_value=resp_500)
            assert await h.send_to_target("wh", 0, "msg") is False

    def test_wintoast_missing_dependency_returns_false(self):
        h = PushHandler()
        with patch("builtins.__import__", side_effect=ImportError("no win11toast")):
            assert h.wintoast(0, "msg", {}) is False
