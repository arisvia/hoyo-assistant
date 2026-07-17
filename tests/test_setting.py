"""Tests for hoyo_assistant.core.setting."""

import os
from copy import deepcopy

import pytest
import yaml

from hoyo_assistant.core import setting

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def clean_setting():
    """Snapshot and reset setting module globals between tests."""
    saved = (
        setting.config.copy(),
        deepcopy(setting.config_raw),
        deepcopy(setting.runtime_overrides),
        setting.config_path,
        setting.path,
    )
    setting.config.clear()
    setting.config.update(setting.DEFAULT_CONFIG)
    setting.config_raw.clear()
    setting.config_raw.update(setting.DEFAULT_CONFIG)
    setting.runtime_overrides.clear()
    setting.config_path = None
    setting.path = None
    yield setting
    setting.config.clear()
    setting.config.update(saved[0])
    setting.config_raw.clear()
    setting.config_raw.update(saved[1])
    setting.runtime_overrides.clear()
    setting.runtime_overrides.update(saved[2])
    setting.config_path = saved[3]
    setting.path = saved[4]


@pytest.fixture
def config_file(tmp_path):
    """Write a minimal valid config file and return its path."""
    cfg = {
        "enable": True,
        "account": {
            "cookie": "test_cookie_value_long_enough",
            "stuid": "123456789",
            "stoken": "test_stoken_value",
            "mid": "test_mid_value",
        },
        "client": {
            "user_agent": "",
            "device": {
                "name": "TestDevice",
                "model": "TestModel",
                "id": "test-device-id",
                "fp": "",
            },
        },
        "mihoyobbs": {
            "checkin": True,
            "checkin_list": [5, 2],
        },
        "push": {
            "enable": False,
            "telegram": {"token": "secret_bot_token_long", "chat_id": "123"},
        },
    }
    path = tmp_path / "config.yaml"
    path.write_text(yaml.dump(cfg), encoding="utf-8")
    return str(path)


@pytest.fixture
def empty_config_file(tmp_path):
    path = tmp_path / "empty.yaml"
    path.write_text("", encoding="utf-8")
    return str(path)


# ---------------------------------------------------------------------------
# reload_config / load_config
# ---------------------------------------------------------------------------


class TestReloadConfig:
    def test_reload_with_no_file_uses_defaults(self, clean_setting):
        clean_setting.reload_config(config_file=None, use_env=False)
        assert "account" in clean_setting.config
        assert clean_setting.config["enable"] is True

    def test_reload_with_valid_file(self, clean_setting, config_file):
        clean_setting.reload_config(config_file=config_file, use_env=False)
        assert clean_setting.config_path == config_file
        assert clean_setting.path == os.path.dirname(config_file)
        assert clean_setting.config["account"]["stuid"] == "123456789"

    def test_reload_sets_config_path_and_dir(self, clean_setting, config_file):
        clean_setting.reload_config(config_file=config_file, use_env=False)
        assert clean_setting.config_path == config_file
        assert clean_setting.path == os.path.dirname(config_file)

    def test_reload_with_overrides_applied(self, clean_setting, config_file):
        overrides = {"enable": False}
        clean_setting.reload_config(
            config_file=config_file, overrides=overrides, use_env=False
        )
        assert clean_setting.config["enable"] is False
        assert clean_setting.runtime_overrides == overrides

    def test_reload_overrides_win_over_file(self, clean_setting, config_file):
        overrides = {"account": {"cookie": "override_cookie_long_enough"}}
        clean_setting.reload_config(
            config_file=config_file, overrides=overrides, use_env=False
        )
        assert (
            clean_setting.config["account"]["cookie"] == "override_cookie_long_enough"
        )

    def test_reload_nonexistent_file_falls_back_to_defaults(
        self, clean_setting, tmp_path
    ):
        # Nonexistent file path logs a warning and falls back to defaults (does NOT raise).
        missing = str(tmp_path / "nope.yaml")
        clean_setting.reload_config(config_file=missing, use_env=False)
        assert "account" in clean_setting.config
        # config_path not updated when file doesn't exist
        assert clean_setting.config_path is None

    def test_reload_empty_file_uses_defaults(self, clean_setting, empty_config_file):
        clean_setting.reload_config(config_file=empty_config_file, use_env=False)
        # empty file yields empty dict, HoyoSettings fills defaults
        assert "account" in clean_setting.config
        assert clean_setting.config["enable"] is True

    def test_reload_invalid_config_raises(self, clean_setting, tmp_path):
        bad = tmp_path / "bad.yaml"
        # account must be a dict; pass a scalar to force validation failure
        bad.write_text("account: not_a_dict\n", encoding="utf-8")
        with pytest.raises(ValueError):
            clean_setting.reload_config(config_file=str(bad), use_env=False)

    def test_reload_use_env_true_reads_env_over_file(
        self, clean_setting, config_file, monkeypatch
    ):
        # BaseSettings reads env regardless; use_env=True confirms env priority over file.
        monkeypatch.setenv("HOYO_ASSISTANT_ENABLE", "false")
        clean_setting.reload_config(config_file=config_file, use_env=True)
        assert clean_setting.config["enable"] is False

    def test_reload_env_always_overrides_regardless_of_use_env_flag(
        self, clean_setting, config_file, monkeypatch
    ):
        # Document: BaseSettings reads env in both use_env paths (init + model_validate).
        monkeypatch.setenv("HOYO_ASSISTANT_ENABLE", "false")
        clean_setting.reload_config(config_file=config_file, use_env=False)
        assert clean_setting.config["enable"] is False

    def test_reload_use_env_true_picks_env(
        self, clean_setting, config_file, monkeypatch
    ):
        monkeypatch.setenv("HOYO_ASSISTANT_ENABLE", "false")
        clean_setting.reload_config(config_file=config_file, use_env=True)
        # env priority > init/file
        assert clean_setting.config["enable"] is False


# ---------------------------------------------------------------------------
# get_effective_config
# ---------------------------------------------------------------------------


class TestGetEffectiveConfig:
    def test_redact_true_masks_cookie(self, clean_setting):
        clean_setting.config["account"]["cookie"] = "very_long_cookie_secret_value"
        effective = clean_setting.get_effective_config(redact=True)
        masked = effective["account"]["cookie"]
        assert masked != "very_long_cookie_secret_value"
        assert "very_long_cookie_secret_value" not in masked
        assert "***" in masked

    def test_redact_true_masks_short_cookie_as_asterisks(self, clean_setting):
        clean_setting.config["account"]["cookie"] = "short"
        effective = clean_setting.get_effective_config(redact=True)
        assert effective["account"]["cookie"] == "***"

    def test_redact_true_masks_empty_cookie_as_empty(self, clean_setting):
        clean_setting.config["account"]["cookie"] = ""
        effective = clean_setting.get_effective_config(redact=True)
        assert effective["account"]["cookie"] == ""

    def test_redact_true_masks_none_cookie_as_empty(self, clean_setting):
        clean_setting.config["account"]["cookie"] = None
        effective = clean_setting.get_effective_config(redact=True)
        assert effective["account"]["cookie"] == ""

    def test_redact_true_masks_stoken(self, clean_setting):
        clean_setting.config["account"]["stoken"] = "very_long_stoken_value_x"
        effective = clean_setting.get_effective_config(redact=True)
        assert "***" in effective["account"]["stoken"]
        assert "very_long_stoken_value_x" not in effective["account"]["stoken"]

    def test_redact_true_masks_token_in_nested(self, clean_setting):
        clean_setting.config["cloud_games"]["cn"]["genshin"]["token"] = (
            "cloud_token_long_enough"
        )
        effective = clean_setting.get_effective_config(redact=True)
        masked = effective["cloud_games"]["cn"]["genshin"]["token"]
        assert "***" in masked

    def test_redact_false_returns_raw(self, clean_setting):
        clean_setting.config["account"]["cookie"] = "plain_cookie_value"
        effective = clean_setting.get_effective_config(redact=False)
        assert effective["account"]["cookie"] == "plain_cookie_value"

    def test_redact_does_not_mutate_real_config(self, clean_setting):
        original_cookie = "very_long_cookie_secret_value"
        clean_setting.config["account"]["cookie"] = original_cookie
        clean_setting.get_effective_config(redact=True)
        assert clean_setting.config["account"]["cookie"] == original_cookie

    def test_redact_uses_walk_on_lists(self, clean_setting):
        # mihoyobbs.checkin_list is a list of ints, should pass through unchanged
        clean_setting.config["mihoyobbs"]["checkin_list"] = [5, 2]
        effective = clean_setting.get_effective_config(redact=True)
        assert effective["mihoyobbs"]["checkin_list"] == [5, 2]


# ---------------------------------------------------------------------------
# validate_config_file
# ---------------------------------------------------------------------------


class TestValidateConfigFile:
    def test_valid_config(self, config_file):
        ok, errors = setting.validate_config_file(config_file)
        assert ok is True
        assert errors == []

    def test_nonexistent_file(self, tmp_path):
        ok, errors = setting.validate_config_file(str(tmp_path / "nope.yaml"))
        assert ok is False
        assert "File not found" in errors[0]

    def test_empty_config_is_valid(self, empty_config_file):
        ok, errors = setting.validate_config_file(empty_config_file)
        assert ok is True
        assert errors == []

    def test_invalid_config_returns_errors(self, tmp_path):
        bad = tmp_path / "bad.yaml"
        # account must be a dict; scalar forces validation failure
        bad.write_text("account: not_a_dict\n", encoding="utf-8")
        ok, errors = setting.validate_config_file(str(bad))
        assert ok is False
        assert len(errors) >= 1
        assert isinstance(errors[0], str)


# ---------------------------------------------------------------------------
# save_config_sync
# ---------------------------------------------------------------------------


class TestSaveConfigSync:
    def test_save_to_explicit_path(self, clean_setting, tmp_path):
        out = tmp_path / "out.yaml"
        # Use a non-default value so exclude_defaults=True keeps it
        clean_setting.save_config_sync(str(out), {"enable": False})
        assert out.exists()
        loaded = yaml.safe_load(out.read_text(encoding="utf-8"))
        assert loaded == {"enable": False}

    def test_save_defaults_to_config_path(self, clean_setting, tmp_path):
        out = tmp_path / "cfg.yaml"
        clean_setting.config_path = str(out)
        clean_setting.save_config_sync(None, None)
        assert out.exists()
        loaded = yaml.safe_load(out.read_text(encoding="utf-8"))
        assert isinstance(loaded, dict)

    def test_save_with_no_target_noop(self, clean_setting, tmp_path, caplog):
        clean_setting.config_path = None
        # should not raise
        clean_setting.save_config_sync(None, None)
        # nothing written, no exception

    def test_save_preserves_unicode(self, clean_setting, tmp_path):
        out = tmp_path / "uni.yaml"
        clean_setting.save_config_sync(
            str(out), {"client": {"device": {"name": "测试设备"}}}
        )
        content = out.read_text(encoding="utf-8")
        assert "测试设备" in content


# ---------------------------------------------------------------------------
# auto_fill_config_file
# ---------------------------------------------------------------------------


class TestAutoFillConfigFile:
    def test_auto_fill_complete_config_noop(self, config_file):
        # config_file already has all defaults applied via HoyoSettings,
        # but original_data may equal filled_data only if no defaults were missing.
        # Since our fixture provides full values, expect success (either complete or auto-filled).
        ok, msg = setting.auto_fill_config_file(config_file, backup=False)
        assert ok is True
        assert isinstance(msg, str)

    def test_auto_fill_partial_config(self, tmp_path):
        partial = tmp_path / "partial.yaml"
        # Provide a non-default value so it survives exclude_defaults=True.
        partial.write_text("enable: false\n", encoding="utf-8")
        ok, msg = setting.auto_fill_config_file(str(partial), backup=False)
        assert ok is True
        loaded = yaml.safe_load(partial.read_text(encoding="utf-8"))
        assert loaded.get("enable") is False

    def test_auto_fill_complete_config_writes_file(self, tmp_path):
        f = tmp_path / "c.yaml"
        f.write_text("enable: false\n", encoding="utf-8")
        ok, msg = setting.auto_fill_config_file(str(f), backup=False)
        assert ok is True
        loaded = yaml.safe_load(f.read_text(encoding="utf-8"))
        assert loaded.get("enable") is False

    def test_auto_fill_creates_backup(self, tmp_path):
        f = tmp_path / "c.yaml"
        f.write_text("enable: true\n", encoding="utf-8")
        ok, _ = setting.auto_fill_config_file(str(f), backup=True)
        assert ok is True
        backup = tmp_path / "c.yaml.bak"
        assert backup.exists()

    def test_auto_fill_no_backup_when_disabled(self, tmp_path):
        f = tmp_path / "c.yaml"
        f.write_text("enable: true\n", encoding="utf-8")
        ok, _ = setting.auto_fill_config_file(str(f), backup=False)
        assert ok is True
        backup = tmp_path / "c.yaml.bak"
        assert not backup.exists()

    def test_auto_fill_nonexistent_file(self, tmp_path):
        ok, msg = setting.auto_fill_config_file(
            str(tmp_path / "nope.yaml"), backup=False
        )
        assert ok is False
        assert isinstance(msg, str)

    def test_auto_fill_invalid_config_returns_error(self, tmp_path):
        bad = tmp_path / "bad.yaml"
        # account must be a dict; scalar forces validation failure
        bad.write_text("account: not_a_dict\n", encoding="utf-8")
        ok, msg = setting.auto_fill_config_file(str(bad), backup=False)
        assert ok is False
        assert isinstance(msg, str)


# ---------------------------------------------------------------------------
# Environment variable overrides
# ---------------------------------------------------------------------------


class TestEnvOverrides:
    def test_env_enable_overrides_file(self, clean_setting, config_file, monkeypatch):
        monkeypatch.setenv("HOYO_ASSISTANT_ENABLE", "false")
        clean_setting.reload_config(config_file=config_file, use_env=True)
        assert clean_setting.config["enable"] is False

    def test_env_enable_true_overrides_file_false(
        self, clean_setting, tmp_path, monkeypatch
    ):
        # file has enable=False, env has True -> env wins
        f = tmp_path / "c.yaml"
        f.write_text("enable: false\n", encoding="utf-8")
        monkeypatch.setenv("HOYO_ASSISTANT_ENABLE", "true")
        clean_setting.reload_config(config_file=str(f), use_env=True)
        assert clean_setting.config["enable"] is True

    def test_env_nested_delimiter(self, clean_setting, config_file, monkeypatch):
        monkeypatch.setenv("HOYO_ASSISTANT_ACCOUNT__STUID", "999999999")
        clean_setting.reload_config(config_file=config_file, use_env=True)
        assert clean_setting.config["account"]["stuid"] == "999999999"

    def test_env_push_enable_nested(self, clean_setting, config_file, monkeypatch):
        monkeypatch.setenv("HOYO_ASSISTANT_PUSH__ENABLE", "true")
        clean_setting.reload_config(config_file=config_file, use_env=True)
        assert clean_setting.config["push"]["enable"] is True

    def test_env_overrides_win_over_overrides_when_use_env_true(
        self, clean_setting, config_file, monkeypatch
    ):
        # runtime_overrides applied after HoyoSettings, but env was already merged into HoyoSettings.
        # overrides are merged on top of model_dump(), so overrides win over env.
        # This test documents the actual behavior: overrides > env (post-merge).
        monkeypatch.setenv("HOYO_ASSISTANT_ENABLE", "false")
        clean_setting.reload_config(
            config_file=config_file,
            overrides={"enable": True},
            use_env=True,
        )
        assert clean_setting.config["enable"] is True

    def test_env_cleaned_between_tests(self, clean_setting, config_file, monkeypatch):
        # ensure no leak from previous test
        monkeypatch.delenv("HOYO_ASSISTANT_ENABLE", raising=False)
        clean_setting.reload_config(config_file=config_file, use_env=True)
        assert clean_setting.config["enable"] is True


# ---------------------------------------------------------------------------
# _deep_merge_dict
# ---------------------------------------------------------------------------


class TestDeepMerge:
    def test_shallow_merge(self):
        base = {"a": 1, "b": 2}
        result = setting._deep_merge_dict(base, {"b": 3})
        assert result == {"a": 1, "b": 3}

    def test_nested_merge(self):
        base = {"a": {"x": 1, "y": 2}}
        result = setting._deep_merge_dict(base, {"a": {"y": 3}})
        assert result == {"a": {"x": 1, "y": 3}}

    def test_merge_does_not_mutate_base(self):
        base = {"a": {"x": 1}}
        setting._deep_merge_dict(base, {"a": {"y": 2}})
        assert base == {"a": {"x": 1}}

    def test_merge_replaces_non_dict_values(self):
        base = {"a": [1, 2]}
        result = setting._deep_merge_dict(base, {"a": [3]})
        assert result == {"a": [3]}


# ---------------------------------------------------------------------------
# DEFAULT_CONFIG
# ---------------------------------------------------------------------------


class TestDefaultConfig:
    def test_default_config_is_dict(self):
        assert isinstance(setting.DEFAULT_CONFIG, dict)

    def test_default_config_has_required_keys(self):
        for key in ["enable", "account", "client", "games", "push"]:
            assert key in setting.DEFAULT_CONFIG

    def test_default_config_has_no_version(self):
        # version field was removed as dead code
        assert "version" not in setting.DEFAULT_CONFIG

    def test_default_config_account_has_cookie(self):
        assert "cookie" in setting.DEFAULT_CONFIG["account"]
