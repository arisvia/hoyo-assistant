"""Tests for hoyo_assistant.runner.executor."""

from __future__ import annotations

from copy import deepcopy
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hoyo_assistant.core import CookieError, StatusCode, StokenError, config, setting
from hoyo_assistant.core.models import AccountRunResult, TaskReport
from hoyo_assistant.runner import executor


@pytest.fixture
def cfg(mock_root_config):
    saved = deepcopy(dict(config))
    saved_path = (setting.config_path, setting._current_account)
    config.clear()
    config.update(deepcopy(mock_root_config))
    setting.config_path = None
    setting.set_current_account(None)
    yield config
    config.clear()
    config.update(saved)
    setting.config_path, setting._current_account = saved_path


class TestHelpers:
    def test_normalize_output_text(self):
        assert executor._normalize_output_text("") == ""
        assert executor._normalize_output_text("a\r\nb\n\n\nc   ") == "a\nb\n\nc"

    def test_resolve_account_label(self):
        assert (
            executor._resolve_account_label({"name": "大号", "region": "cn"}, 0)
            == "大号"
        )
        assert (
            executor._resolve_account_label({"name": "", "region": "os"}, 1) == "os#2"
        )

    def test_matches_filter(self):
        acct = {"name": "国服大号", "region": "cn"}
        assert executor._matches_filter(acct, 0, {"国服大号"}) is True
        assert executor._matches_filter(acct, 0, {"1"}) is True
        assert executor._matches_filter(acct, 0, {"cn#1"}) is True
        assert executor._matches_filter(acct, 0, {"2"}) is False


class TestHandleCnLogin:
    @pytest.mark.asyncio
    async def test_missing_empty_cookie_raises_cookie_error(self, mock_cn_account):
        mock_cn_account["cookie"] = ""
        with pytest.raises(CookieError):
            await executor.handle_cn_login(mock_cn_account)

    @pytest.mark.asyncio
    async def test_missing_creds_with_bbs_runs_login(self, mock_cn_account):
        mock_cn_account["bbs"]["enable"] = True
        mock_cn_account["cookie"] = "ltuid=1; ltoken=2"
        with (
            patch.object(executor.setting, "get_account", return_value=mock_cn_account),
            patch.object(executor.login, "login", new=AsyncMock()) as mock_login,
            patch.object(executor.tools, "tidy_cookie", return_value="tidied"),
            patch("hoyo_assistant.runner.executor.asyncio.sleep", new=AsyncMock()),
        ):
            await executor.handle_cn_login(mock_cn_account)
        mock_login.assert_awaited_once()
        assert mock_cn_account["cookie"] == "tidied"

    @pytest.mark.asyncio
    async def test_v2_creds_hydrate_cookie(self, mock_cn_account):
        mock_cn_account["cookie"] = "account_id_v2=1;stuid=1;stoken=v2_tok;mid=mid1;"
        with (
            patch.object(executor.setting, "get_account", return_value=mock_cn_account),
            patch.object(
                executor.login,
                "build_account_cookie",
                new=AsyncMock(return_value="built"),
            ) as mock_build,
        ):
            await executor.handle_cn_login(mock_cn_account)
        mock_build.assert_awaited_once()
        assert mock_cn_account["cookie"] == "built"


class TestRunAccount:
    @pytest.mark.asyncio
    async def test_cn_account_success(self, mock_cn_account):
        mock_cn_account["bbs"]["enable"] = True
        mock_cn_account["games"] = ["genshin"]
        mock_cn_account["cloud"]["genshin"] = "ctok"
        mock_cn_account["cookie"] = "ltoken=valid;stuid=1;stoken=v1_tok;mid=m;"

        fake_bbs = MagicMock()
        fake_bbs.run_task = AsyncMock(return_value="bbs ok")

        with (
            patch.object(executor, "http") as mock_http,
            patch.object(executor, "handle_cn_login", new=AsyncMock()),
            patch.object(executor.community, "Mihoyobbs", return_value=fake_bbs),
            patch.object(
                executor.chinese, "run_signin_task", new=AsyncMock(return_value="cn ok")
            ),
            patch.object(
                executor.chinese,
                "run_cloud_task",
                new=AsyncMock(return_value="cloud ok"),
            ),
        ):
            res = await executor.run_account(mock_cn_account, 0)

        assert res.status == StatusCode.SUCCESS.value
        assert res.region == "cn"
        assert "bbs ok" in res.message
        assert "cn ok" in res.message
        assert "cloud ok" in res.message
        assert setting._current_account is None
        mock_http.clear_cache.assert_called_once_with(include_public=False)
        mock_http.clear_cookies.assert_called_once()

    @pytest.mark.asyncio
    async def test_cn_partial_failure_keeps_other_results(self, mock_cn_account):
        mock_cn_account["bbs"]["enable"] = True
        mock_cn_account["games"] = ["genshin"]
        mock_cn_account["cookie"] = "ltoken=valid;stuid=1;stoken=v1_tok;mid=m;"

        fake_bbs = MagicMock()
        fake_bbs.run_task = AsyncMock(side_effect=StokenError("expired"))

        with (
            patch.object(executor, "http"),
            patch.object(executor, "handle_cn_login", new=AsyncMock()),
            patch.object(executor.community, "Mihoyobbs", return_value=fake_bbs),
            patch.object(
                executor.chinese, "run_signin_task", new=AsyncMock(return_value="cn ok")
            ),
        ):
            res = await executor.run_account(mock_cn_account, 0)

        assert res.status == StatusCode.PARTIAL_FAILURE.value
        assert "cn ok" in res.message

    @pytest.mark.asyncio
    async def test_os_account_success_and_missing_cookie(self, mock_os_account):
        mock_os_account["games"] = ["honkai_sr"]
        mock_os_account["cookie"] = ""
        with patch.object(executor, "http"):
            res_missing = await executor.run_account(mock_os_account, 1)
        assert res_missing.status == StatusCode.FAILURE.value

        mock_os_account["cookie"] = "ltoken_v2=abc"
        with (
            patch.object(executor, "http"),
            patch.object(
                executor.overseas,
                "run_signin_task",
                new=AsyncMock(return_value="os ok"),
            ),
        ):
            res_ok = await executor.run_account(mock_os_account, 1)
        assert res_ok.status == StatusCode.SUCCESS.value
        assert "os ok" in res_ok.message

    @pytest.mark.asyncio
    async def test_invalid_region_raises_and_unbinds(self):
        with (
            patch.object(executor, "http"),
            pytest.raises(ValueError),
        ):
            await executor.run_account({"region": "jp"}, 0)
        assert setting._current_account is None


class TestRunAccounts:
    @pytest.mark.asyncio
    async def test_disabled_root_config_returns_failure(self, cfg):
        config["enable"] = False
        with patch.object(setting, "load_config"):
            status, _, results = await executor.run_accounts("cfg.yaml")
        assert status == StatusCode.FAILURE.value
        assert results == []

    @pytest.mark.asyncio
    async def test_no_enabled_accounts_returns_failure(self, cfg):
        config["accounts"] = [{"region": "os", "enable": False}]
        with patch.object(setting, "load_config"):
            status, _, results = await executor.run_accounts("cfg.yaml")
        assert status == StatusCode.FAILURE.value
        assert results == []

    @pytest.mark.asyncio
    async def test_account_filter_runs_only_matching_accounts(self, cfg):
        mock_http = MagicMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)
        with (
            patch.object(setting, "load_config"),
            patch.object(executor, "http", mock_http),
            patch.object(
                executor,
                "run_account",
                new=AsyncMock(
                    return_value=AccountRunResult("OS-1", "os", 0, "os done", [])
                ),
            ) as mock_run,
            patch.object(executor, "dispatch_push", new=AsyncMock()) as mock_push,
            patch("hoyo_assistant.runner.executor.asyncio.sleep", new=AsyncMock()),
        ):
            status, summary, results = await executor.run_accounts(
                "cfg.yaml", account_filter=["OS-1"]
            )
        assert status == StatusCode.SUCCESS.value
        assert len(results) == 1
        mock_run.assert_awaited_once()
        mock_push.assert_awaited_once_with(results)
        assert "1" in summary

    @pytest.mark.asyncio
    async def test_mixed_cn_failure_and_os_success_returns_partial(self, cfg):
        mock_http = MagicMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)
        side_effects = [
            AccountRunResult("CN-1", "cn", StatusCode.FAILURE.value, "bad", None),
            AccountRunResult("OS-1", "os", StatusCode.SUCCESS.value, "good", []),
        ]
        with (
            patch.object(setting, "load_config"),
            patch.object(executor, "http", mock_http),
            patch.object(executor, "run_account", side_effect=side_effects),
            patch.object(executor, "dispatch_push", new=AsyncMock()),
            patch("hoyo_assistant.runner.executor.asyncio.sleep", new=AsyncMock()),
        ):
            status, _, results = await executor.run_accounts("cfg.yaml")
        assert status == StatusCode.PARTIAL_FAILURE.value
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_unmatched_filter_returns_failure(self, cfg):
        with patch.object(setting, "load_config"):
            status, _, results = await executor.run_accounts(
                "cfg.yaml", account_filter=["nonexistent"]
            )
        assert status == StatusCode.FAILURE.value
        assert results == []

    @pytest.mark.asyncio
    async def test_cn_login_cookie_error_caught_inside_run_account(
        self, mock_cn_account
    ):
        with (
            patch.object(executor, "http"),
            patch.object(
                executor, "handle_cn_login", side_effect=CookieError("bad cookie")
            ),
        ):
            res = await executor.run_account(mock_cn_account, 0)
        assert res.status == StatusCode.FAILURE.value
        assert "bad cookie" in res.message


class TestAutoQrFallback:
    @pytest.mark.asyncio
    async def test_non_tty_skips_auto_qr_immediately(self, mock_cn_account):
        with (
            patch.object(executor, "http"),
            patch.object(
                executor, "handle_cn_login", side_effect=CookieError("missing")
            ),
            patch.object(executor.qr_login, "qr_login_cn", new=AsyncMock()) as mock_qr,
        ):
            res = await executor.run_account(mock_cn_account, 0, allow_qr_login=False)
        assert res.status == StatusCode.FAILURE.value
        mock_qr.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_tty_auto_qr_recovers_failed_cn_login(self, mock_cn_account):
        mock_cn_account["bbs"]["enable"] = False
        mock_cn_account["games"] = ["genshin"]
        fake_res = executor.qr_login.QRLoginResult(
            uid="1001", device_id="dev", stoken="v2_s", mid="m1"
        )
        with (
            patch.object(executor, "http"),
            patch.object(
                executor,
                "handle_cn_login",
                new=AsyncMock(side_effect=[CookieError("expired"), None]),
            ) as mock_login,
            patch.object(
                executor.qr_login,
                "qr_login_cn",
                new=AsyncMock(return_value=fake_res),
            ) as mock_qr,
            patch.object(
                executor.qr_login,
                "upsert_cn_account",
                new=AsyncMock(return_value=(mock_cn_account, False)),
            ) as mock_upsert,
            patch.object(
                executor.chinese,
                "run_signin_task",
                new=AsyncMock(return_value="genshin ok"),
            ),
        ):
            res = await executor.run_account(mock_cn_account, 0, allow_qr_login=True)
        assert res.status == StatusCode.SUCCESS.value
        assert "genshin ok" in res.message
        assert mock_login.await_count == 2
        mock_qr.assert_awaited_once()
        mock_upsert.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_tty_auto_qr_timeout_skips_cleanly(self, mock_cn_account):
        with (
            patch.object(executor, "http"),
            patch.object(
                executor, "handle_cn_login", side_effect=StokenError("expired")
            ),
            patch.object(
                executor.qr_login,
                "qr_login_cn",
                new=AsyncMock(side_effect=TimeoutError("10s timeout")),
            ),
        ):
            res = await executor.run_account(mock_cn_account, 0, allow_qr_login=True)
        assert res.status == StatusCode.FAILURE.value

    @pytest.mark.asyncio
    async def test_tty_cloud_token_cleared_triggers_cloud_scope_retry(
        self, mock_cn_account
    ):
        mock_cn_account["bbs"]["enable"] = False
        mock_cn_account["games"] = []
        mock_cn_account["cloud"]["genshin"] = "old_cloud_tok"
        fake_res = executor.qr_login.QRLoginResult(
            uid="1001", device_id="dev", cloud_genshin_token="new_cloud_tok"
        )

        async def fake_cloud_task():
            if mock_cn_account["cloud"]["genshin"] == "old_cloud_tok":
                mock_cn_account["cloud"]["genshin"] = ""
                return "云·原神 token 失效"
            return "云·原神 签到成功"

        async def fake_upsert(result, target_account=None, scope="all"):
            mock_cn_account["cloud"]["genshin"] = result.cloud_genshin_token
            return mock_cn_account, False

        with (
            patch.object(executor, "http"),
            patch.object(executor, "handle_cn_login", new=AsyncMock()),
            patch.object(
                executor.chinese, "run_cloud_task", side_effect=fake_cloud_task
            ),
            patch.object(
                executor.qr_login,
                "qr_login_cn",
                new=AsyncMock(return_value=fake_res),
            ) as mock_qr,
            patch.object(
                executor.qr_login, "upsert_cn_account", side_effect=fake_upsert
            ),
        ):
            res = await executor.run_account(mock_cn_account, 0, allow_qr_login=True)
        assert res.status == StatusCode.SUCCESS.value
        assert "签到成功" in res.message
        assert mock_qr.call_args.kwargs["scope"] == "cloud"

    @pytest.mark.asyncio
    async def test_first_run_zero_accounts_tty_onboards_and_runs(self, cfg):
        config["accounts"] = []
        new_acct = {
            "name": "国服-999",
            "region": "cn",
            "enable": True,
            "cookie": "stuid=999;stoken=v2_s;mid=m1;",
            "bbs": {"enable": True, "forums": [2]},
            "games": ["genshin"],
        }
        mock_http = MagicMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)
        fake_res = executor.qr_login.QRLoginResult(
            uid="999", device_id="dev", stoken="v2_s", mid="m1"
        )

        async def fake_upsert(result, target_account=None, scope="all"):
            config["accounts"].append(new_acct)
            return new_acct, True

        with (
            patch.object(setting, "load_config"),
            patch.object(executor, "http", mock_http),
            patch.object(
                executor.qr_login,
                "qr_login_cn",
                new=AsyncMock(return_value=fake_res),
            ),
            patch.object(
                executor.qr_login, "upsert_cn_account", side_effect=fake_upsert
            ),
            patch.object(
                executor,
                "run_account",
                new=AsyncMock(
                    return_value=AccountRunResult("国服-999", "cn", 0, "ok", None)
                ),
            ) as mock_run_acct,
            patch.object(executor, "dispatch_push", new=AsyncMock()),
        ):
            status, _, results = await executor.run_accounts(
                "cfg.yaml", allow_qr_login=True
            )
        assert status == StatusCode.SUCCESS.value
        assert len(results) == 1
        mock_run_acct.assert_awaited_once_with(new_acct, 0, allow_qr_login=True)


class TestTaskErrorPropagationFixes:
    @pytest.mark.asyncio
    async def test_os_account_failed_signin_returns_failure_status(
        self, mock_os_account
    ):
        mock_os_account["games"] = ["genshin"]
        mock_os_account["cookie"] = "ltoken_v2=expired"
        with (
            patch.object(executor, "http"),
            patch.object(
                executor.overseas,
                "run_signin_task",
                new=AsyncMock(
                    return_value=TaskReport(
                        "Genshin failed", had_error=True, had_success=False
                    )
                ),
            ),
        ):
            res = await executor.run_account(mock_os_account, 0)
        assert res.status == StatusCode.FAILURE.value

    @pytest.mark.asyncio
    async def test_cn_account_failed_cloud_returns_failure_status(
        self, mock_cn_account
    ):
        mock_cn_account["bbs"]["enable"] = False
        mock_cn_account["games"] = []
        mock_cn_account["cloud"]["genshin"] = "bad_tok"
        with (
            patch.object(executor, "http"),
            patch.object(executor, "handle_cn_login", new=AsyncMock()),
            patch.object(
                executor.chinese,
                "run_cloud_task",
                new=AsyncMock(
                    return_value=TaskReport(
                        "cloud token invalid", had_error=True, had_success=False
                    )
                ),
            ),
        ):
            res = await executor.run_account(mock_cn_account, 0, allow_qr_login=False)
        assert res.status == StatusCode.FAILURE.value

    @pytest.mark.asyncio
    async def test_cn_signin_cookie_error_triggers_auto_qr_recovery(
        self, mock_cn_account
    ):
        mock_cn_account["bbs"]["enable"] = False
        mock_cn_account["games"] = ["genshin"]
        fake_res = executor.qr_login.QRLoginResult(
            uid="1001", device_id="dev", stoken="v2_s", mid="m1"
        )
        with (
            patch.object(executor, "http"),
            patch.object(executor, "handle_cn_login", new=AsyncMock()),
            patch.object(
                executor.chinese,
                "run_signin_task",
                new=AsyncMock(
                    side_effect=[
                        CookieError("expired"),
                        TaskReport("genshin ok", had_error=False, had_success=True),
                    ]
                ),
            ) as mock_signin,
            patch.object(
                executor.qr_login,
                "qr_login_cn",
                new=AsyncMock(return_value=fake_res),
            ) as mock_qr,
            patch.object(
                executor.qr_login,
                "upsert_cn_account",
                new=AsyncMock(return_value=(mock_cn_account, False)),
            ),
        ):
            res = await executor.run_account(mock_cn_account, 0, allow_qr_login=True)
        assert res.status == StatusCode.SUCCESS.value
        assert mock_signin.await_count == 2
        mock_qr.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_run_accounts_skips_redundant_reload_unless_forced(
        self, cfg, tmp_path
    ):
        cfg_file = tmp_path / "c.yaml"
        cfg_file.write_text("enable: false\naccounts: []\n", encoding="utf-8")
        setting.config_path = str(cfg_file)
        cfg["enable"] = False

        with patch.object(setting, "load_config") as mock_load:
            await executor.run_accounts(config_path=str(cfg_file))
            mock_load.assert_not_called()

            await executor.run_accounts(config_path=str(cfg_file), force_reload=True)
            mock_load.assert_called_once_with(str(cfg_file), use_env=True)

            await executor.run_accounts(config_path=str(tmp_path / "other.yaml"))
            assert mock_load.call_count == 2
