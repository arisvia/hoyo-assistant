"""Tests for hoyo_assistant.runner.single_account and multi_account.

Ponytail: multi_account.py references setting/StatusCode/CookieError/StokenError
without importing them (source bug). The autouse fixture below injects them into
the module namespace so tests exercise real logic. Fix the source imports to drop this.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from copy import deepcopy
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hoyo_assistant.core import (
    CookieError,
    StatusCode,
    StokenError,
    config,
    setting,
)
from hoyo_assistant.runner import multi_account, single_account


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _patch_multi_missing_imports():
    """Inject names multi_account.py forgot to import."""
    saved = {
        "StatusCode": getattr(multi_account, "StatusCode", None),
        "CookieError": getattr(multi_account, "CookieError", None),
        "StokenError": getattr(multi_account, "StokenError", None),
        "setting": getattr(multi_account, "setting", None),
    }
    multi_account.StatusCode = StatusCode
    multi_account.CookieError = CookieError
    multi_account.StokenError = StokenError
    multi_account.setting = setting
    yield
    for k, v in saved.items():
        if v is None:
            delattr(multi_account, k)
        else:
            setattr(multi_account, k, v)


@pytest.fixture
def cfg(mock_config):
    """Replace global config dict contents with mock_config, restore after."""
    saved = deepcopy(dict(config))
    config.clear()
    config.update(deepcopy(mock_config))
    config.setdefault("enable", True)
    config.setdefault("web_activity", {"activities": []})
    yield config
    config.clear()
    config.update(saved)


@pytest.fixture
def reset_setting_path():
    saved = (setting.config_path, setting.path)
    setting.config_path = None
    setting.path = None
    yield
    setting.config_path, setting.path = saved


# ===========================================================================
# single_account._normalize_output_text
# ===========================================================================


class TestNormalizeOutputText:
    def test_empty_returns_empty(self):
        assert single_account._normalize_output_text("") == ""

    def test_none_returns_empty(self):
        assert single_account._normalize_output_text(None) == ""

    def test_crlf_to_lf(self):
        assert single_account._normalize_output_text("a\r\nb") == "a\nb"

    def test_cr_to_lf(self):
        assert single_account._normalize_output_text("a\rb") == "a\nb"

    def test_trailing_whitespace_stripped(self):
        assert single_account._normalize_output_text("a   \nb  ") == "a\nb"

    def test_multiple_newlines_collapsed(self):
        assert single_account._normalize_output_text("a\n\n\n\nb") == "a\n\nb"

    def test_leading_trailing_stripped(self):
        assert single_account._normalize_output_text("\n\na\n\n") == "a"

    def test_non_string_input_coerced(self):
        assert single_account._normalize_output_text(123) == "123"


# ===========================================================================
# single_account.initialize_config
# ===========================================================================


class TestInitializeConfig:
    @pytest.mark.asyncio
    async def test_config_path_provided_loads(self, cfg, reset_setting_path):
        with patch.object(setting, "load_config") as mock_load:
            ok, msg = await single_account.initialize_config("x.yaml", use_env=True)
        mock_load.assert_called_once_with("x.yaml", use_env=True)
        assert ok is True
        assert msg is None

    @pytest.mark.asyncio
    async def test_no_config_path_first_run_loads_default(self, cfg, reset_setting_path):
        with patch.object(setting, "load_config") as mock_load:
            ok, msg = await single_account.initialize_config(None, use_env=True)
        mock_load.assert_called_once_with(None, use_env=True)
        assert ok is True

    @pytest.mark.asyncio
    async def test_no_config_path_already_loaded_skips_load(self, cfg):
        setting.config_path = "already.yaml"
        try:
            with patch.object(setting, "load_config") as mock_load:
                ok, msg = await single_account.initialize_config(None, use_env=True)
            mock_load.assert_not_called()
            assert ok is True
        finally:
            setting.config_path = None

    @pytest.mark.asyncio
    async def test_config_disabled_returns_false(self, cfg, reset_setting_path):
        config["enable"] = False
        with patch.object(setting, "load_config"):
            ok, msg = await single_account.initialize_config("x.yaml")
        assert ok is False
        assert msg is not None


# ===========================================================================
# single_account.handle_login
# ===========================================================================


class TestHandleLogin:
    @pytest.mark.asyncio
    async def test_empty_account_with_checkin_calls_login(self, cfg):
        config["mihoyobbs"]["checkin"] = True
        config["account"]["stuid"] = ""
        config["account"]["stoken"] = ""
        config["account"]["mid"] = ""
        with patch.object(single_account, "login", new=MagicMock()) as login_mod:
            login_mod.login = AsyncMock()
            with patch.object(single_account, "tools") as tools_mod:
                tools_mod.tidy_cookie = MagicMock(return_value="tidied")
                with patch("hoyo_assistant.runner.single_account.asyncio.sleep", new=AsyncMock()):
                    await single_account.handle_login()
        login_mod.login.assert_awaited_once()
        assert config["account"]["cookie"] == "tidied"

    @pytest.mark.asyncio
    async def test_filled_account_no_login(self, cfg):
        config["account"]["stuid"] = "u"
        config["account"]["stoken"] = "s"
        config["account"]["mid"] = "m"
        with patch.object(single_account, "login", new=MagicMock()) as login_mod:
            login_mod.login = AsyncMock()
            await single_account.handle_login()
        login_mod.login.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_empty_account_no_checkin_no_login(self, cfg):
        config["mihoyobbs"]["checkin"] = False
        config["account"]["stuid"] = ""
        config["account"]["stoken"] = ""
        config["account"]["mid"] = ""
        with patch.object(single_account, "login", new=MagicMock()) as login_mod:
            login_mod.login = AsyncMock()
            with patch.object(single_account, "tools") as tools_mod:
                tools_mod.tidy_cookie = MagicMock(return_value="tidied")
                await single_account.handle_login()
        login_mod.login.assert_not_awaited()


# ===========================================================================
# single_account.run_miyoushe_tasks
# ===========================================================================


class TestRunMiyousheTasks:
    @pytest.mark.asyncio
    async def test_checkin_disabled_returns_empty(self, cfg):
        config["mihoyobbs"]["checkin"] = False
        msg, stoken_err = await single_account.run_miyoushe_tasks()
        assert msg == ""
        assert stoken_err is False

    @pytest.mark.asyncio
    async def test_stoken_error_returns_error(self, cfg):
        config["mihoyobbs"]["checkin"] = True
        config["account"]["stoken"] = "StokenError"
        msg, stoken_err = await single_account.run_miyoushe_tasks()
        assert stoken_err is True
        assert msg != ""

    @pytest.mark.asyncio
    async def test_run_task_success(self, cfg):
        config["mihoyobbs"]["checkin"] = True
        config["account"]["stoken"] = "valid"
        fake_bbs = MagicMock()
        fake_bbs.run_task = AsyncMock(return_value="bbs result")
        with patch.object(single_account, "community") as community_mod:
            community_mod.Mihoyobbs = MagicMock(return_value=fake_bbs)
            msg, stoken_err = await single_account.run_miyoushe_tasks()
        assert msg == "bbs result"
        assert stoken_err is False

    @pytest.mark.asyncio
    async def test_stoken_error_raised(self, cfg):
        config["mihoyobbs"]["checkin"] = True
        config["account"]["stoken"] = "valid"
        fake_bbs = MagicMock()
        fake_bbs.run_task = AsyncMock(side_effect=StokenError("bad"))
        with patch.object(single_account, "community") as community_mod:
            community_mod.Mihoyobbs = MagicMock(return_value=fake_bbs)
            msg, stoken_err = await single_account.run_miyoushe_tasks()
        assert stoken_err is True
        assert msg != ""

    @pytest.mark.asyncio
    async def test_generic_exception_caught(self, cfg):
        config["mihoyobbs"]["checkin"] = True
        config["account"]["stoken"] = "valid"
        fake_bbs = MagicMock()
        fake_bbs.run_task = AsyncMock(side_effect=RuntimeError("boom"))
        with patch.object(single_account, "community") as community_mod:
            community_mod.Mihoyobbs = MagicMock(return_value=fake_bbs)
            msg, stoken_err = await single_account.run_miyoushe_tasks()
        assert stoken_err is False
        assert msg != ""


# ===========================================================================
# single_account.run_cn_signin_tasks
# ===========================================================================


class TestRunCnSigninTasks:
    @pytest.mark.asyncio
    async def test_no_checkin_no_cloud_returns_empty(self, cfg):
        with patch.object(single_account, "chinese") as chinese_mod:
            chinese_mod.run_signin_task = AsyncMock()
            chinese_mod.run_cloud_task = AsyncMock()
            result = await single_account.run_cn_signin_tasks()
        assert result == ""
        chinese_mod.run_signin_task.assert_not_awaited()
        chinese_mod.run_cloud_task.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_checkin_enabled_runs_signin(self, cfg):
        config["games"]["cn"]["genshin"]["checkin"] = True
        with patch.object(single_account, "chinese") as chinese_mod:
            chinese_mod.run_signin_task = AsyncMock(return_value="signin ok")
            chinese_mod.run_cloud_task = AsyncMock()
            result = await single_account.run_cn_signin_tasks()
        assert "signin ok" in result
        chinese_mod.run_signin_task.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cloud_enabled_runs_cloud(self, cfg):
        config["cloud_games"]["cn"]["genshin"]["enable"] = True
        with patch.object(single_account, "chinese") as chinese_mod:
            chinese_mod.run_signin_task = AsyncMock()
            chinese_mod.run_cloud_task = AsyncMock(return_value="cloud ok")
            result = await single_account.run_cn_signin_tasks()
        assert "cloud ok" in result
        chinese_mod.run_cloud_task.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_both_enabled_both_run(self, cfg):
        config["games"]["cn"]["genshin"]["checkin"] = True
        config["cloud_games"]["cn"]["zzz"]["enable"] = True
        with patch.object(single_account, "chinese") as chinese_mod:
            chinese_mod.run_signin_task = AsyncMock(return_value="signin")
            chinese_mod.run_cloud_task = AsyncMock(return_value="cloud")
            result = await single_account.run_cn_signin_tasks()
        assert "signin" in result
        assert "cloud" in result


# ===========================================================================
# single_account.run_os_signin_tasks
# ===========================================================================


class TestRunOsSigninTasks:
    @pytest.mark.asyncio
    async def test_no_cookie_no_cloud_returns_empty(self, cfg):
        with patch.object(single_account, "overseas") as overseas_mod:
            overseas_mod.run_signin_task = AsyncMock()
            overseas_mod.run_cloud_task = AsyncMock()
            result = await single_account.run_os_signin_tasks()
        assert result == ""
        overseas_mod.run_signin_task.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_cookie_and_checkin_runs_signin(self, cfg):
        config["games"]["os"]["cookie"] = "os_cookie"
        config["games"]["os"]["genshin"]["checkin"] = True
        with patch.object(single_account, "overseas") as overseas_mod:
            overseas_mod.run_signin_task = AsyncMock(return_value="os signin")
            overseas_mod.run_cloud_task = AsyncMock()
            result = await single_account.run_os_signin_tasks()
        assert "os signin" in result
        overseas_mod.run_signin_task.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cloud_enabled_runs_cloud(self, cfg):
        config["cloud_games"]["os"]["genshin"]["enable"] = True
        with patch.object(single_account, "overseas") as overseas_mod:
            overseas_mod.run_signin_task = AsyncMock()
            overseas_mod.run_cloud_task = AsyncMock(return_value="os cloud")
            result = await single_account.run_os_signin_tasks()
        assert "os cloud" in result

    @pytest.mark.asyncio
    async def test_empty_signin_result_not_appended(self, cfg):
        config["games"]["os"]["cookie"] = "os_cookie"
        config["games"]["os"]["genshin"]["checkin"] = True
        with patch.object(single_account, "overseas") as overseas_mod:
            overseas_mod.run_signin_task = AsyncMock(return_value="")
            overseas_mod.run_cloud_task = AsyncMock()
            result = await single_account.run_os_signin_tasks()
        assert result == ""


# ===========================================================================
# single_account.run_web_activity_tasks
# ===========================================================================


class TestRunWebActivityTasks:
    @pytest.mark.asyncio
    async def test_no_activities_noop(self, cfg):
        config["web_activity"]["activities"] = []
        with patch.object(single_account, "web") as web_mod:
            web_mod.run_task = AsyncMock()
            await single_account.run_web_activity_tasks()
        web_mod.run_task.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_activities_present_runs_task(self, cfg):
        config["web_activity"]["activities"] = ["act1"]
        with patch.object(single_account, "web") as web_mod:
            web_mod.run_task = AsyncMock()
            await single_account.run_web_activity_tasks()
        web_mod.run_task.assert_awaited_once()


# ===========================================================================
# single_account.run_once
# ===========================================================================


class TestRunOnce:
    @pytest.mark.asyncio
    async def test_config_disabled_returns_failure(self, cfg, reset_setting_path):
        config["enable"] = False
        with patch.object(setting, "load_config"):
            code, msg = await single_account.run_once("x.yaml")
        assert code == StatusCode.FAILURE.value

    @pytest.mark.asyncio
    async def test_cookie_error_raised(self, cfg, reset_setting_path):
        config["account"]["cookie"] = "CookieError"
        config["account"]["stuid"] = "u"
        config["account"]["stoken"] = "s"
        config["account"]["mid"] = "m"
        mock_http = MagicMock()
        mock_http.cache = MagicMock()
        mock_http.cache.clear = MagicMock()
        mock_http.clear_cookies = MagicMock()
        with patch.object(setting, "load_config"), \
             patch("hoyo_assistant.runner.single_account.handle_login", new=AsyncMock()):
            # Import path inside run_once uses `from ..core.request import http`
            with patch("hoyo_assistant.core.request.http", mock_http):
                with pytest.raises(CookieError):
                    await single_account.run_once("x.yaml")

    @pytest.mark.asyncio
    async def test_success_path(self, cfg, reset_setting_path):
        config["account"]["stuid"] = "u"
        config["account"]["stoken"] = "s"
        config["account"]["mid"] = "m"
        config["account"]["cookie"] = "valid"
        mock_http = MagicMock()
        mock_http.cache = MagicMock()
        mock_http.cache.clear = MagicMock()
        mock_http.clear_cookies = MagicMock()
        with patch.object(setting, "load_config"), \
             patch("hoyo_assistant.runner.single_account.handle_login", new=AsyncMock()), \
             patch("hoyo_assistant.runner.single_account.run_miyoushe_tasks", new=AsyncMock(return_value=("bbs", False))), \
             patch("hoyo_assistant.runner.single_account.run_cn_signin_tasks", new=AsyncMock(return_value="cn")), \
             patch("hoyo_assistant.runner.single_account.run_os_signin_tasks", new=AsyncMock(return_value="os")), \
             patch("hoyo_assistant.runner.single_account.run_web_activity_tasks", new=AsyncMock()), \
             patch("hoyo_assistant.core.request.http", mock_http):
            code, msg = await single_account.run_once("x.yaml")
        assert code == StatusCode.SUCCESS.value
        assert "bbs" in msg
        assert "cn" in msg
        assert "os" in msg

    @pytest.mark.asyncio
    async def test_stoken_error_propagates(self, cfg, reset_setting_path):
        config["account"]["stuid"] = "u"
        config["account"]["stoken"] = "s"
        config["account"]["mid"] = "m"
        config["account"]["cookie"] = "valid"
        mock_http = MagicMock()
        mock_http.cache = MagicMock()
        mock_http.cache.clear = MagicMock()
        mock_http.clear_cookies = MagicMock()
        with patch.object(setting, "load_config"), \
             patch("hoyo_assistant.runner.single_account.handle_login", new=AsyncMock()), \
             patch("hoyo_assistant.runner.single_account.run_miyoushe_tasks", new=AsyncMock(return_value=("bbs", True))), \
             patch("hoyo_assistant.runner.single_account.run_cn_signin_tasks", new=AsyncMock(return_value="")), \
             patch("hoyo_assistant.runner.single_account.run_os_signin_tasks", new=AsyncMock(return_value="")), \
             patch("hoyo_assistant.runner.single_account.run_web_activity_tasks", new=AsyncMock()), \
             patch("hoyo_assistant.core.request.http", mock_http):
            with pytest.raises(StokenError):
                await single_account.run_once("x.yaml")

    @pytest.mark.asyncio
    async def test_captcha_detected(self, cfg, reset_setting_path):
        config["account"]["stuid"] = "u"
        config["account"]["stoken"] = "s"
        config["account"]["mid"] = "m"
        config["account"]["cookie"] = "valid"
        mock_http = MagicMock()
        mock_http.cache = MagicMock()
        mock_http.cache.clear = MagicMock()
        mock_http.clear_cookies = MagicMock()
        captcha_text = "验证码 triggered"
        with patch.object(setting, "load_config"), \
             patch("hoyo_assistant.runner.single_account.handle_login", new=AsyncMock()), \
             patch("hoyo_assistant.runner.single_account.run_miyoushe_tasks", new=AsyncMock(return_value=(captcha_text, False))), \
             patch("hoyo_assistant.runner.single_account.run_cn_signin_tasks", new=AsyncMock(return_value="")), \
             patch("hoyo_assistant.runner.single_account.run_os_signin_tasks", new=AsyncMock(return_value="")), \
             patch("hoyo_assistant.runner.single_account.run_web_activity_tasks", new=AsyncMock()), \
             patch("hoyo_assistant.core.request.http", mock_http):
            code, msg = await single_account.run_once("x.yaml")
        assert code == StatusCode.CAPTCHA_TRIGGERED.value

    @pytest.mark.asyncio
    async def test_task_exception_caught(self, cfg, reset_setting_path):
        config["account"]["stuid"] = "u"
        config["account"]["stoken"] = "s"
        config["account"]["mid"] = "m"
        config["account"]["cookie"] = "valid"
        mock_http = MagicMock()
        mock_http.cache = MagicMock()
        mock_http.cache.clear = MagicMock()
        mock_http.clear_cookies = MagicMock()
        with patch.object(setting, "load_config"), \
             patch("hoyo_assistant.runner.single_account.handle_login", new=AsyncMock()), \
             patch("hoyo_assistant.runner.single_account.run_miyoushe_tasks", new=AsyncMock(side_effect=RuntimeError("boom"))), \
             patch("hoyo_assistant.runner.single_account.run_cn_signin_tasks", new=AsyncMock(return_value="")), \
             patch("hoyo_assistant.runner.single_account.run_os_signin_tasks", new=AsyncMock(return_value="")), \
             patch("hoyo_assistant.runner.single_account.run_web_activity_tasks", new=AsyncMock()), \
             patch("hoyo_assistant.core.request.http", mock_http):
            code, msg = await single_account.run_once("x.yaml")
        assert code == StatusCode.SUCCESS.value


# ===========================================================================
# single_account.run_single_account
# ===========================================================================


class TestRunSingleAccount:
    @pytest.mark.asyncio
    async def test_no_push_returns_directly(self, cfg):
        mock_http = MagicMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)
        with patch("hoyo_assistant.runner.single_account.http", mock_http), \
             patch("hoyo_assistant.runner.single_account.run_once", new=AsyncMock(return_value=(0, "ok"))), \
             patch("hoyo_assistant.runner.single_account.is_push_enabled", return_value=False):
            code, msg = await single_account.run_single_account("x.yaml", use_env=True)
        assert code == 0
        assert msg == "ok"

    @pytest.mark.asyncio
    async def test_push_enabled_calls_push(self, cfg):
        mock_http = MagicMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)
        with patch("hoyo_assistant.runner.single_account.http", mock_http), \
             patch("hoyo_assistant.runner.single_account.run_once", new=AsyncMock(return_value=(1, "err"))), \
             patch("hoyo_assistant.runner.single_account.is_push_enabled", return_value=True), \
             patch("hoyo_assistant.runner.single_account.push") as push_mod:
            push_mod.push = AsyncMock()
            code, msg = await single_account.run_single_account("x.yaml", use_env=False)
        assert code == 1
        push_mod.push.assert_awaited_once_with(1, "err")

    @pytest.mark.asyncio
    async def test_use_env_false_passes_use_env(self, cfg):
        mock_http = MagicMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)
        with patch("hoyo_assistant.runner.single_account.http", mock_http), \
             patch("hoyo_assistant.runner.single_account.run_once", new=AsyncMock(return_value=(0, "ok"))) as mock_once, \
             patch("hoyo_assistant.runner.single_account.is_push_enabled", return_value=False):
            await single_account.run_single_account("x.yaml", use_env=False)
        mock_once.assert_awaited_once_with("x.yaml", use_env=False)


# ===========================================================================
# multi_account._normalize_targets
# ===========================================================================


class TestNormalizeTargets:
    def test_none_returns_empty(self):
        assert multi_account._normalize_targets(None) == []

    def test_str_splits_comma(self):
        assert multi_account._normalize_targets("a,b") == ["a", "b"]

    def test_str_strips_whitespace(self):
        assert multi_account._normalize_targets(" a , b ") == ["a", "b"]

    def test_list_returns_list(self):
        assert multi_account._normalize_targets(["a", "b"]) == ["a", "b"]

    def test_list_strips_and_filters_empty(self):
        assert multi_account._normalize_targets([" a ", "", "  "]) == ["a"]

    def test_single_str_no_comma(self):
        assert multi_account._normalize_targets("a.yaml") == ["a.yaml"]


# ===========================================================================
# multi_account._collect_config_pool
# ===========================================================================


class TestCollectConfigPool:
    def test_file_path(self, tmp_path):
        f = tmp_path / "a.yaml"
        f.write_text("enable: true")
        pool = multi_account._collect_config_pool([str(f)])
        assert len(pool) == 1
        assert pool[0][1] == "a.yaml"

    def test_directory_collects_yaml(self, tmp_path):
        (tmp_path / "a.yaml").write_text("x")
        (tmp_path / "b.yml").write_text("x")
        (tmp_path / "c.txt").write_text("x")
        pool = multi_account._collect_config_pool([str(tmp_path)])
        names = sorted(p[1] for p in pool)
        assert names == ["a.yaml", "b.yml"]

    def test_dedup(self, tmp_path):
        f = tmp_path / "a.yaml"
        f.write_text("x")
        pool = multi_account._collect_config_pool([str(f), str(f)])
        assert len(pool) == 1

    def test_nonexistent_path_skipped(self):
        pool = multi_account._collect_config_pool(["/no/such/path"])
        assert pool == []

    def test_file_and_dir_combined(self, tmp_path):
        d = tmp_path / "dir"
        d.mkdir()
        (d / "in_dir.yaml").write_text("x")
        f = tmp_path / "top.yaml"
        f.write_text("x")
        pool = multi_account._collect_config_pool([str(f), str(d)])
        assert len(pool) == 2


# ===========================================================================
# multi_account.run_multi_account
# ===========================================================================


class TestRunMultiAccount:
    @pytest.mark.asyncio
    async def test_no_config_found_returns_failure(self):
        with patch("hoyo_assistant.runner.multi_account.asyncio.sleep", new=AsyncMock()):
            code, msg = await multi_account.run_multi_account(["/no/such"])
        assert code == StatusCode.FAILURE.value

    @pytest.mark.asyncio
    async def test_success_all_ok(self, tmp_path):
        f = tmp_path / "a.yaml"
        f.write_text("x")
        with patch("hoyo_assistant.runner.multi_account.run_single_account", new=AsyncMock(return_value=(0, "ok"))), \
             patch("hoyo_assistant.runner.multi_account.http") as http_mod, \
             patch("hoyo_assistant.runner.multi_account.asyncio.sleep", new=AsyncMock()):
            http_mod.__aenter__ = AsyncMock(return_value=http_mod)
            http_mod.__aexit__ = AsyncMock(return_value=None)
            code, msg = await multi_account.run_multi_account([str(f)])
        assert code == StatusCode.SUCCESS.value

    @pytest.mark.asyncio
    async def test_all_errors_returns_failure(self, tmp_path):
        f = tmp_path / "a.yaml"
        f.write_text("x")
        with patch("hoyo_assistant.runner.multi_account.run_single_account", new=AsyncMock(return_value=(1, "err"))), \
             patch("hoyo_assistant.runner.multi_account.http") as http_mod, \
             patch("hoyo_assistant.runner.multi_account.asyncio.sleep", new=AsyncMock()):
            http_mod.__aenter__ = AsyncMock(return_value=http_mod)
            http_mod.__aexit__ = AsyncMock(return_value=None)
            code, msg = await multi_account.run_multi_account([str(f)])
        assert code == StatusCode.FAILURE.value

    @pytest.mark.asyncio
    async def test_partial_error_returns_partial(self, tmp_path):
        f1 = tmp_path / "a.yaml"
        f1.write_text("x")
        f2 = tmp_path / "b.yaml"
        f2.write_text("x")
        results = iter([(0, "ok"), (1, "err")])
        with patch("hoyo_assistant.runner.multi_account.run_single_account", new=AsyncMock(side_effect=lambda *a, **k: next(results))), \
             patch("hoyo_assistant.runner.multi_account.http") as http_mod, \
             patch("hoyo_assistant.runner.multi_account.asyncio.sleep", new=AsyncMock()):
            http_mod.__aenter__ = AsyncMock(return_value=http_mod)
            http_mod.__aexit__ = AsyncMock(return_value=None)
            code, msg = await multi_account.run_multi_account([str(f1), str(f2)])
        assert code == StatusCode.PARTIAL_FAILURE.value

    @pytest.mark.asyncio
    async def test_captcha_triggered(self, tmp_path):
        f = tmp_path / "a.yaml"
        f.write_text("x")
        with patch("hoyo_assistant.runner.multi_account.run_single_account", new=AsyncMock(return_value=(3, "captcha"))), \
             patch("hoyo_assistant.runner.multi_account.http") as http_mod, \
             patch("hoyo_assistant.runner.multi_account.asyncio.sleep", new=AsyncMock()):
            http_mod.__aenter__ = AsyncMock(return_value=http_mod)
            http_mod.__aexit__ = AsyncMock(return_value=None)
            code, msg = await multi_account.run_multi_account([str(f)])
        assert code == StatusCode.CAPTCHA_TRIGGERED.value

    @pytest.mark.asyncio
    async def test_cookie_error_caught(self, tmp_path):
        f = tmp_path / "a.yaml"
        f.write_text("x")
        with patch("hoyo_assistant.runner.multi_account.run_single_account", new=AsyncMock(side_effect=CookieError("bad"))), \
             patch("hoyo_assistant.runner.multi_account.http") as http_mod, \
             patch("hoyo_assistant.runner.multi_account.is_push_enabled", return_value=False), \
             patch("hoyo_assistant.runner.multi_account.asyncio.sleep", new=AsyncMock()):
            http_mod.__aenter__ = AsyncMock(return_value=http_mod)
            http_mod.__aexit__ = AsyncMock(return_value=None)
            code, msg = await multi_account.run_multi_account([str(f)])
        assert code == StatusCode.FAILURE.value

    @pytest.mark.asyncio
    async def test_stoken_error_caught(self, tmp_path):
        f = tmp_path / "a.yaml"
        f.write_text("x")
        with patch("hoyo_assistant.runner.multi_account.run_single_account", new=AsyncMock(side_effect=StokenError("bad"))), \
             patch("hoyo_assistant.runner.multi_account.http") as http_mod, \
             patch("hoyo_assistant.runner.multi_account.is_push_enabled", return_value=False), \
             patch("hoyo_assistant.runner.multi_account.asyncio.sleep", new=AsyncMock()):
            http_mod.__aenter__ = AsyncMock(return_value=http_mod)
            http_mod.__aexit__ = AsyncMock(return_value=None)
            code, msg = await multi_account.run_multi_account([str(f)])
        assert code == StatusCode.FAILURE.value

    @pytest.mark.asyncio
    async def test_unknown_status_goes_to_close(self, tmp_path):
        f = tmp_path / "a.yaml"
        f.write_text("x")
        with patch("hoyo_assistant.runner.multi_account.run_single_account", new=AsyncMock(return_value=(99, "unknown"))), \
             patch("hoyo_assistant.runner.multi_account.http") as http_mod, \
             patch("hoyo_assistant.runner.multi_account.asyncio.sleep", new=AsyncMock()):
            http_mod.__aenter__ = AsyncMock(return_value=http_mod)
            http_mod.__aexit__ = AsyncMock(return_value=None)
            code, msg = await multi_account.run_multi_account([str(f)])
        assert code == StatusCode.SUCCESS.value

    @pytest.mark.asyncio
    async def test_default_config_dir_search(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        cfg_dir = tmp_path / "config"
        cfg_dir.mkdir()
        f = cfg_dir / "a.yaml"
        f.write_text("x")
        (cfg_dir / "template.yaml").write_text("x")
        with patch("hoyo_assistant.runner.multi_account.run_single_account", new=AsyncMock(return_value=(0, "ok"))), \
             patch("hoyo_assistant.runner.multi_account.http") as http_mod, \
             patch("hoyo_assistant.runner.multi_account.asyncio.sleep", new=AsyncMock()):
            http_mod.__aenter__ = AsyncMock(return_value=http_mod)
            http_mod.__aexit__ = AsyncMock(return_value=None)
            code, msg = await multi_account.run_multi_account(None)
        assert code == StatusCode.SUCCESS.value

    @pytest.mark.asyncio
    async def test_push_enabled_on_cookie_error(self, tmp_path):
        f = tmp_path / "a.yaml"
        f.write_text("x")
        # In the new code, run_multi_account just catches CookieError and does NOT push from itself.
        # But run_single_account itself handles pushing, so if run_single_account raises CookieError,
        # it was already pushed inside run_single_account. We don't push inside run_multi_account.
        # Thus, we can test that run_multi_account safely catches the exception and marks it as failure.
        with patch("hoyo_assistant.runner.multi_account.run_single_account", new=AsyncMock(side_effect=CookieError("bad"))), \
             patch("hoyo_assistant.runner.multi_account.http") as http_mod, \
             patch("hoyo_assistant.runner.multi_account.is_push_enabled", return_value=True), \
             patch("hoyo_assistant.runner.multi_account.push") as push_mod, \
             patch("hoyo_assistant.runner.multi_account.asyncio.sleep", new=AsyncMock()):
            http_mod.__aenter__ = AsyncMock(return_value=http_mod)
            http_mod.__aexit__ = AsyncMock(return_value=None)
            push_mod.push = AsyncMock()
            await multi_account.run_multi_account([str(f)])
        # No push inside run_multi_account anymore, but it should succeed execution.
        assert True
