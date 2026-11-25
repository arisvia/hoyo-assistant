"""Tests for hoyo_assistant.core.qr_login."""

from __future__ import annotations

import hashlib
import hmac
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hoyo_assistant.core import qr_login, setting
from hoyo_assistant.core.constants import (
    HK4E_CN_APP_ID,
    HK4E_CN_APP_KEY,
    HK4E_CN_CHANNEL_ID,
)


def _make_resp(data: dict) -> MagicMock:
    resp = MagicMock()
    resp.json = AsyncMock(return_value=data)
    return resp


class TestTerminalDetectionAndRendering:
    def test_is_interactive_terminal(self, monkeypatch):
        for var in ("CI", "GITHUB_ACTIONS", "GITLAB_CI", "JENKINS_URL", "BUILDKITE"):
            monkeypatch.delenv(var, raising=False)

        fake_in = MagicMock()
        fake_out = MagicMock()
        fake_in.isatty.return_value = True
        fake_out.isatty.return_value = True

        with patch("sys.stdin", fake_in), patch("sys.stdout", fake_out):
            assert qr_login.is_interactive_terminal() is True

            monkeypatch.setenv("CI", "true")
            assert qr_login.is_interactive_terminal() is False
            monkeypatch.delenv("CI")

            fake_in.isatty.return_value = False
            assert qr_login.is_interactive_terminal() is False

    @pytest.mark.parametrize("use_ansi", [True, False])
    def test_render_qr_terminal(self, use_ansi):
        rendered = qr_login.render_qr_terminal(
            "https://user.mihoyo.com/qr_code_in_game.html?app_id=4&ticket=abc123",
            use_ansi=use_ansi,
        )
        lines = rendered.splitlines()
        assert len(lines) >= 10
        assert any(ch in rendered for ch in ("▀", "▄", "█", " "))
        if use_ansi:
            assert "\x1b[47;30m" in rendered
            assert "\x1b[0m" in rendered
        else:
            assert "\x1b[" not in rendered


class TestQRProtocolFlows:
    @pytest.mark.asyncio
    async def test_fetch_qr_code_parses_ticket(self):
        mock_http = MagicMock()
        mock_http.post = AsyncMock(
            return_value=_make_resp(
                {
                    "retcode": 0,
                    "data": {
                        "url": "https://user.mihoyo.com/qr_code_in_game.html?app_id=4&ticket=tkt_999"
                    },
                }
            )
        )
        with patch.object(qr_login, "http", mock_http):
            url, ticket = await qr_login.fetch_qr_code("dev-uuid")
        assert "ticket=tkt_999" in url
        assert ticket == "tkt_999"

    @pytest.mark.asyncio
    async def test_fetch_qr_code_error_raises(self):
        mock_http = MagicMock()
        mock_http.post = AsyncMock(
            return_value=_make_resp({"retcode": -1, "message": "bad device"})
        )
        with (
            patch.object(qr_login, "http", mock_http),
            pytest.raises(RuntimeError, match="QR fetch failed"),
        ):
            await qr_login.fetch_qr_code("dev-uuid")

    @pytest.mark.asyncio
    async def test_poll_qr_status_transitions_to_confirmed(self):
        states = []
        mock_http = MagicMock()
        mock_http.post = AsyncMock(
            side_effect=[
                _make_resp({"retcode": 0, "data": {"stat": "Init"}}),
                _make_resp({"retcode": 0, "data": {"stat": "Scanned"}}),
                _make_resp(
                    {
                        "retcode": 0,
                        "data": {
                            "stat": "Confirmed",
                            "payload": {
                                "raw": json.dumps(
                                    {"uid": "388098055", "token": "gtok_1"}
                                )
                            },
                        },
                    }
                ),
            ]
        )
        with (
            patch.object(qr_login, "http", mock_http),
            patch("hoyo_assistant.core.qr_login.asyncio.sleep", new=AsyncMock()),
        ):
            uid, game_token = await qr_login.poll_qr_status(
                "dev-1", "tkt", timeout=30, poll_interval=0.1, on_status=states.append
            )
        assert uid == "388098055"
        assert game_token == "gtok_1"
        assert states == ["Init", "Scanned", "Confirmed"]

    @pytest.mark.asyncio
    async def test_poll_qr_status_expired_raises_timeout(self):
        mock_http = MagicMock()
        mock_http.post = AsyncMock(
            return_value=_make_resp({"retcode": -106, "message": "expired"})
        )
        with (
            patch.object(qr_login, "http", mock_http),
            pytest.raises(TimeoutError),
        ):
            await qr_login.poll_qr_status("dev-1", "tkt", timeout=10)

    @pytest.mark.asyncio
    async def test_poll_qr_status_deadline_timeout(self):
        mock_http = MagicMock()
        mock_http.post = AsyncMock(
            return_value=_make_resp({"retcode": 0, "data": {"stat": "Init"}})
        )
        with (
            patch.object(qr_login, "http", mock_http),
            patch(
                "hoyo_assistant.core.qr_login.time.monotonic",
                side_effect=[0.0, 11.0],
            ),
            pytest.raises(TimeoutError),
        ):
            await qr_login.poll_qr_status("dev-1", "tkt", timeout=10)

    @pytest.mark.asyncio
    async def test_exchange_stoken_by_game_token(self):
        mock_http = MagicMock()
        mock_http.post = AsyncMock(
            return_value=_make_resp(
                {
                    "retcode": 0,
                    "data": {
                        "token": {"token": "v2_stoken_abc"},
                        "user_info": {"mid": "mid_xyz"},
                    },
                }
            )
        )
        with patch.object(qr_login, "http", mock_http):
            stoken, mid = await qr_login.exchange_stoken_by_game_token(
                "12345", "gtok", {"id": "dev-9"}
            )
        assert stoken == "v2_stoken_abc"
        assert mid == "mid_xyz"
        call_kwargs = mock_http.post.call_args.kwargs
        assert call_kwargs["headers"]["x-rpc-app_id"] == "bll8iq97cem8"
        assert call_kwargs["json"] == {"account_id": 12345, "game_token": "gtok"}

    @pytest.mark.asyncio
    async def test_exchange_cloud_genshin_token_and_hmac(self):
        mock_http = MagicMock()
        mock_http.post = AsyncMock(
            return_value=_make_resp(
                {
                    "retcode": 0,
                    "data": {"open_id": "oid_1", "combo_token": "ctok_2"},
                }
            )
        )
        with patch.object(qr_login, "http", mock_http):
            combo = await qr_login.exchange_cloud_genshin_token(
                "82226658", "gtok_cloud", "dev-uuid-1"
            )

        body = mock_http.post.call_args.kwargs["json"]
        raw_req_sign = (
            f"app_id={HK4E_CN_APP_ID}&channel_id={HK4E_CN_CHANNEL_ID}"
            f"&data={body['data']}&device=dev-uuid-1"
        )
        expected_req_sign = hmac.new(
            HK4E_CN_APP_KEY.encode(), raw_req_sign.encode(), hashlib.sha256
        ).hexdigest()
        assert body["sign"] == expected_req_sign

        si_src = (
            f"app_id={HK4E_CN_APP_ID}&channel_id={HK4E_CN_CHANNEL_ID}"
            "&combo_token=ctok_2&open_id=oid_1"
        )
        expected_si = hmac.new(
            HK4E_CN_APP_KEY.encode(), si_src.encode(), hashlib.sha256
        ).hexdigest()
        assert combo == f"ai=4;ci=1;oi=oid_1;ct=ctok_2;si={expected_si};bi=hk4e_cn"

    @pytest.mark.asyncio
    async def test_qr_login_cn_scopes_and_cloud_warning_fallback(self):
        printed: list[str] = []
        with (
            patch.object(
                qr_login,
                "fetch_qr_code",
                new=AsyncMock(
                    return_value=(
                        "https://user.mihoyo.com/qr_code_in_game.html?ticket=t1",
                        "t1",
                    )
                ),
            ),
            patch.object(
                qr_login,
                "poll_qr_status",
                new=AsyncMock(return_value=("555", "gt1")),
            ),
            patch.object(
                qr_login,
                "exchange_stoken_by_game_token",
                new=AsyncMock(return_value=("v2_s", "mid555")),
            ) as mock_bbs,
            patch.object(
                qr_login,
                "exchange_cloud_genshin_token",
                new=AsyncMock(side_effect=RuntimeError("cloud down")),
            ) as mock_cloud,
        ):
            res_all = await qr_login.qr_login_cn(
                scope="all", timeout=60, printer=printed.append
            )
        assert res_all.uid == "555"
        assert res_all.stoken == "v2_s"
        assert res_all.cloud_genshin_token == ""
        mock_bbs.assert_awaited_once()
        mock_cloud.assert_awaited_once()
        assert any("▀" in line or "█" in line for line in printed)


class TestUpsertCnAccountDeduplication:
    @pytest.fixture
    def clean_state(self, tmp_path):
        saved = (
            setting.config.copy(),
            setting.config_path,
            setting._current_account,
        )
        cfg_file = tmp_path / "config.yaml"
        setting.config_path = str(cfg_file)
        setting.config.clear()
        setting.config.update(
            {"enable": True, "push": {"enable": False}, "accounts": []}
        )
        setting.set_current_account(None)
        yield cfg_file
        setting.config.clear()
        setting.config.update(saved[0])
        setting.config_path = saved[1]
        setting.set_current_account(saved[2])

    @pytest.mark.asyncio
    async def test_overwrites_same_uid_without_creating_duplicate(self, clean_state):
        existing = {
            "name": "我的主号",
            "region": "cn",
            "enable": True,
            "cookie": "ltoken_v2=old_lt;stuid=82226658;stoken=v2_old;mid=old_m;",
            "device": {"id": "old-dev"},
            "bbs": {"enable": True, "forums": [2, 6]},
            "games": ["genshin", "zzz"],
            "cloud": {"genshin": "old_cloud", "zzz": "keep_zzz"},
        }
        other = {
            "name": "国际服",
            "region": "os",
            "cookie": "ltuid_v2=999;ltoken_v2=os;",
        }
        setting.config["accounts"] = [existing, other]

        res = qr_login.QRLoginResult(
            uid="82226658",
            device_id="new-dev",
            stoken="v2_new_stoken",
            mid="new_mid",
            cloud_genshin_token="new_cloud_tok",
        )
        with patch.object(
            qr_login.login,
            "build_account_cookie",
            new=AsyncMock(
                return_value=(
                    "ltoken_v2=fresh_lt;cookie_token_v2=fresh_ct;"
                    "stuid=82226658;stoken=v2_new_stoken;mid=new_mid;"
                )
            ),
        ):
            acct, created = await qr_login.upsert_cn_account(res, scope="all")

        assert created is False
        assert acct is existing
        assert len(setting.config["accounts"]) == 2
        assert existing["name"] == "我的主号"
        assert existing["bbs"]["forums"] == [2, 6]
        assert existing["games"] == ["genshin", "zzz"]
        assert "stoken=v2_new_stoken;" in existing["cookie"]
        assert "ltoken_v2=fresh_lt;" in existing["cookie"]
        assert existing["cloud"]["genshin"] == "new_cloud_tok"
        assert existing["cloud"]["zzz"] == "keep_zzz"
        assert clean_state.exists()

    @pytest.mark.asyncio
    async def test_appends_new_account_with_defaults_when_uid_new(self, clean_state):
        res = qr_login.QRLoginResult(
            uid="123456",
            device_id="dev-new",
            stoken="v2_s",
            mid="m_new",
            cloud_genshin_token="cloud_new",
        )
        with patch.object(
            qr_login.login,
            "build_account_cookie",
            new=AsyncMock(return_value="stuid=123456;stoken=v2_s;mid=m_new;"),
        ):
            acct, created = await qr_login.upsert_cn_account(res, scope="all")

        assert created is True
        assert len(setting.config["accounts"]) == 1
        assert acct["name"] == "国服-123456"
        assert acct["region"] == "cn"
        assert acct["bbs"] == {"enable": True, "forums": [2, 5]}
        assert acct["games"] == ["genshin", "honkai_sr", "zzz"]
        assert acct["cloud"]["genshin"] == "cloud_new"
        assert acct["device"]["id"] == "dev-new"
