"""Tests for hoyo_assistant.core.setting (pure v2 schema)."""

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
    setting.config.update(deepcopy(setting.DEFAULT_CONFIG))
    setting.config_raw.clear()
    setting.config_raw.update(deepcopy(setting.DEFAULT_CONFIG))
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
    """Write a minimal valid v2 config file and return its path."""
    cfg = {
        "enable": True,
        "cn": {
            "cookie": "test_cookie_value_long_enough",
            "stuid": "123456789",
            "stoken": "test_stoken_value",
            "mid": "test_mid_value",
            "bbs": {"enable": True, "forums": [5, 2]},
            "games": ["genshin", "zzz"],
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
        "push": {
            "enable": False,
            "channels": {
                "telegram": {"bot_token": "secret_bot_token_long", "chat_id": "123"}
            },
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
        assert "cn" in clean_setting.config
        assert "os" in clean_setting.config
        assert clean_setting.config["enable"] is True

    def test_reload_with_valid_file(self, clean_setting, config_file):
        clean_setting.reload_config(config_file=config_file, use_env=False)
        assert clean_setting.config_path == config_file
        assert clean_setting.path == os.path.dirname(config_file)
        assert clean_setting.config["cn"]["stuid"] == "123456789"
        assert clean_setting.config["cn"]["games"] == ["genshin", "zzz"]

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
        overrides = {"cn": {"cookie": "override_cookie_long_enough"}}
        clean_setting.reload_config(
            config_file=config_file, overrides=overrides, use_env=False
        )
        assert clean_setting.config["cn"]["cookie"] == "override_cookie_long_enough"

    def test_reload_nonexistent_file_falls_back_to_defaults(
        self, clean_setting, tmp_path
    ):
        missing = str(tmp_path / "nope.yaml")
        clean_setting.reload_config(config_file=missing, use_env=False)
        assert "cn" in clean_setting.config
        assert clean_setting.config_path is None

    def test_reload_empty_file_uses_defaults(self, clean_setting, empty_config_file):
        clean_setting.reload_config(config_file=empty_config_file, use_env=False)
        assert "cn" in clean_setting.config
        assert clean_setting.config["enable"] is True

    def test_reload_invalid_config_raises(self, clean_setting, tmp_path):
        bad = tmp_path / "bad.yaml"
        bad.write_text("cn: not_a_dict\n", encoding="utf-8")
        with pytest.raises(ValueError):
            clean_setting.reload_config(config_file=str(bad), use_env=False)

    def test_reload_use_env_true_reads_env_over_file(
        self, clean_setting, config_file, monkeypatch
    ):
        monkeypatch.setenv("HOYO_ASSISTANT_ENABLE", "false")
        clean_setting.reload_config(config_file=config_file, use_env=True)
        assert clean_setting.config["enable"] is False

    def test_reload_use_env_false_ignores_env(
        self, clean_setting, config_file, monkeypatch
    ):
        monkeypatch.setenv("HOYO_ASSISTANT_ENABLE", "false")
        clean_setting.reload_config(config_file=config_file, use_env=False)
        assert clean_setting.config["enable"] is True


# ---------------------------------------------------------------------------
# get_effective_config
# ---------------------------------------------------------------------------


class TestGetEffectiveConfig:
    def test_redact_true_masks_cookie(self, clean_setting):
        clean_setting.config["cn"]["cookie"] = "very_long_cookie_secret_value"
        effective = clean_setting.get_effective_config(redact=True)
        masked = effective["cn"]["cookie"]
        assert masked != "very_long_cookie_secret_value"
        assert "very_long_cookie_secret_value" not in masked
        assert "***" in masked

    def test_redact_true_masks_short_cookie_as_asterisks(self, clean_setting):
        clean_setting.config["cn"]["cookie"] = "short"
        effective = clean_setting.get_effective_config(redact=True)
        assert effective["cn"]["cookie"] == "***"

    def test_redact_true_masks_empty_cookie_as_empty(self, clean_setting):
        clean_setting.config["cn"]["cookie"] = ""
        effective = clean_setting.get_effective_config(redact=True)
        assert effective["cn"]["cookie"] == ""

    def test_redact_true_masks_none_cookie_as_empty(self, clean_setting):
        clean_setting.config["cn"]["cookie"] = None
        effective = clean_setting.get_effective_config(redact=True)
        assert effective["cn"]["cookie"] == ""

    def test_redact_true_masks_stoken(self, clean_setting):
        clean_setting.config["cn"]["stoken"] = "very_long_stoken_value_x"
        effective = clean_setting.get_effective_config(redact=True)
        assert "***" in effective["cn"]["stoken"]
        assert "very_long_stoken_value_x" not in effective["cn"]["stoken"]

    def test_redact_true_masks_cloud_token(self, clean_setting):
        clean_setting.config["cn"]["cloud"]["genshin"] = "cloud_token_long_enough"
        effective = clean_setting.get_effective_config(redact=True)
        masked = effective["cn"]["cloud"]["genshin"]
        assert "***" in masked
        assert "cloud_token_long_enough" not in masked

    def test_redact_true_masks_push_webhook_and_bot_token(self, clean_setting):
        clean_setting.config["push"]["channels"]["telegram"] = {
            "bot_token": "123456:ABCDEF_SECRET",
            "chat_id": "999",
        }
        clean_setting.config["push"]["channels"]["discord"] = {
            "webhook": "https://discord.com/api/webhooks/1234/secret_token"
        }
        effective = clean_setting.get_effective_config(redact=True)
        assert "***" in effective["push"]["channels"]["telegram"]["bot_token"]
        assert "***" in effective["push"]["channels"]["discord"]["webhook"]

    def test_redact_false_returns_raw(self, clean_setting):
        clean_setting.config["cn"]["cookie"] = "plain_cookie_value"
        effective = clean_setting.get_effective_config(redact=False)
        assert effective["cn"]["cookie"] == "plain_cookie_value"

    def test_redact_does_not_mutate_real_config(self, clean_setting):
        original_cookie = "very_long_cookie_secret_value"
        clean_setting.config["cn"]["cookie"] = original_cookie
        clean_setting.get_effective_config(redact=True)
        assert clean_setting.config["cn"]["cookie"] == original_cookie

    def test_redact_uses_walk_on_lists(self, clean_setting):
        clean_setting.config["cn"]["bbs"]["forums"] = [5, 2]
        effective = clean_setting.get_effective_config(redact=True)
        assert effective["cn"]["bbs"]["forums"] == [5, 2]


# ---------------------------------------------------------------------------
# validate_config_file & strict v2 schema validation
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
        bad.write_text("cn: not_a_dict\n", encoding="utf-8")
        ok, errors = setting.validate_config_file(str(bad))
        assert ok is False
        assert len(errors) >= 1
        assert isinstance(errors[0], str)

    def test_rejects_typo_in_push_channel_field(self, tmp_path):
        bad = tmp_path / "bad_push.yaml"
        bad.write_text(
            "push:\n  channels:\n    telegram:\n      bot_toke: 'abc'\n",
            encoding="utf-8",
        )
        ok, errors = setting.validate_config_file(str(bad))
        assert ok is False
        assert "bot_toke" in errors[0]

    def test_rejects_ghost_os_honkai2_game(self, tmp_path):
        bad = tmp_path / "bad_os.yaml"
        bad.write_text("os:\n  games: [honkai2]\n", encoding="utf-8")
        ok, errors = setting.validate_config_file(str(bad))
        assert ok is False
        assert "honkai2" in errors[0]

    def test_rejects_unknown_cn_game_id(self, tmp_path):
        bad = tmp_path / "bad_cn.yaml"
        bad.write_text("cn:\n  games: [genshn]\n", encoding="utf-8")
        ok, errors = setting.validate_config_file(str(bad))
        assert ok is False
        assert "genshn" in errors[0]

    def test_rejects_legacy_v1_top_level_keys(self, tmp_path):
        bad = tmp_path / "v1.yaml"
        bad.write_text("account:\n  cookie: abc\n", encoding="utf-8")
        ok, errors = setting.validate_config_file(str(bad))
        assert ok is False
        assert "account" in errors[0]

    def test_repo_config_template_is_valid(self):
        from pathlib import Path

        template_path = (
            Path(__file__).resolve().parents[1] / "config" / "config.yaml.template"
        )
        ok, errors = setting.validate_config_file(str(template_path))
        assert ok is True, f"config.yaml.template failed validation: {errors}"

    def test_deduplicates_game_lists(self):
        from hoyo_assistant.core.setting_schema import HoyoSettings

        s = HoyoSettings.model_validate(
            {
                "cn": {"games": ["genshin", "zzz", "genshin"]},
                "os": {"games": ["zzz", "zzz"]},
            }
        )
        assert s.cn.games == ["genshin", "zzz"]
        assert s.os.games == ["zzz"]


# ---------------------------------------------------------------------------
# save_config_sync
# ---------------------------------------------------------------------------


class TestSaveConfigSync:
    def test_save_to_explicit_path(self, clean_setting, tmp_path):
        out = tmp_path / "out.yaml"
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

    def test_save_with_no_target_noop(self, clean_setting):
        clean_setting.config_path = None
        clean_setting.save_config_sync(None, None)

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
        ok, msg = setting.auto_fill_config_file(config_file, backup=False)
        assert ok is True
        assert isinstance(msg, str)

    def test_auto_fill_does_not_leak_env_secrets(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOYO_ASSISTANT_CN__COOKIE", "super_secret_env_cookie")
        f = tmp_path / "clean.yaml"
        f.write_text("enable: false\n", encoding="utf-8")
        ok, _ = setting.auto_fill_config_file(str(f), backup=False)
        assert ok is True
        assert "super_secret_env_cookie" not in f.read_text(encoding="utf-8")

    def test_auto_fill_creates_backup(self, tmp_path):
        f = tmp_path / "c.yaml"
        f.write_text("enable: true\n", encoding="utf-8")
        ok, _ = setting.auto_fill_config_file(str(f), backup=True)
        assert ok is True
        assert (tmp_path / "c.yaml.bak").exists()

    def test_auto_fill_no_backup_when_disabled(self, tmp_path):
        f = tmp_path / "c.yaml"
        f.write_text("enable: true\n", encoding="utf-8")
        ok, _ = setting.auto_fill_config_file(str(f), backup=False)
        assert ok is True
        assert not (tmp_path / "c.yaml.bak").exists()

    def test_auto_fill_nonexistent_file(self, tmp_path):
        ok, msg = setting.auto_fill_config_file(
            str(tmp_path / "nope.yaml"), backup=False
        )
        assert ok is False
        assert isinstance(msg, str)

    def test_auto_fill_invalid_config_returns_error(self, tmp_path):
        bad = tmp_path / "bad.yaml"
        bad.write_text("cn: not_a_dict\n", encoding="utf-8")
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
        f = tmp_path / "c.yaml"
        f.write_text("enable: false\n", encoding="utf-8")
        monkeypatch.setenv("HOYO_ASSISTANT_ENABLE", "true")
        clean_setting.reload_config(config_file=str(f), use_env=True)
        assert clean_setting.config["enable"] is True

    def test_env_nested_delimiter(self, clean_setting, config_file, monkeypatch):
        monkeypatch.setenv("HOYO_ASSISTANT_CN__STUID", "999999999")
        clean_setting.reload_config(config_file=config_file, use_env=True)
        assert clean_setting.config["cn"]["stuid"] == "999999999"

    def test_env_push_enable_nested(self, clean_setting, config_file, monkeypatch):
        monkeypatch.setenv("HOYO_ASSISTANT_PUSH__ENABLE", "true")
        clean_setting.reload_config(config_file=config_file, use_env=True)
        assert clean_setting.config["push"]["enable"] is True

    def test_overrides_win_over_env(self, clean_setting, config_file, monkeypatch):
        monkeypatch.setenv("HOYO_ASSISTANT_ENABLE", "false")
        clean_setting.reload_config(
            config_file=config_file,
            overrides={"enable": True},
            use_env=True,
        )
        assert clean_setting.config["enable"] is True

    def test_env_cleaned_between_tests(self, clean_setting, config_file, monkeypatch):
        monkeypatch.delenv("HOYO_ASSISTANT_ENABLE", raising=False)
        clean_setting.reload_config(config_file=config_file, use_env=True)
        assert clean_setting.config["enable"] is True


# ---------------------------------------------------------------------------
# _deep_merge_dict
# ---------------------------------------------------------------------------


class TestDeepMerge:
    def test_shallow_merge(self):
        base = {"a": 1, "b": 2}
        assert setting._deep_merge_dict(base, {"b": 3}) == {"a": 1, "b": 3}

    def test_nested_merge(self):
        base = {"a": {"x": 1, "y": 2}}
        assert setting._deep_merge_dict(base, {"a": {"y": 3}}) == {
            "a": {"x": 1, "y": 3}
        }

    def test_merge_does_not_mutate_base(self):
        base = {"a": {"x": 1}}
        setting._deep_merge_dict(base, {"a": {"y": 2}})
        assert base == {"a": {"x": 1}}

    def test_merge_replaces_non_dict_values(self):
        base = {"a": [1, 2]}
        assert setting._deep_merge_dict(base, {"a": [3]}) == {"a": [3]}


# ---------------------------------------------------------------------------
# DEFAULT_CONFIG
# ---------------------------------------------------------------------------


class TestDefaultConfig:
    def test_default_config_is_dict(self):
        assert isinstance(setting.DEFAULT_CONFIG, dict)

    def test_default_config_has_v2_keys(self):
        assert set(setting.DEFAULT_CONFIG) == {"enable", "cn", "os", "client", "push"}

    def test_default_config_has_no_legacy_keys(self):
        for legacy in (
            "version",
            "account",
            "mihoyobbs",
            "games",
            "cloud_games",
            "web_activity",
        ):
            assert legacy not in setting.DEFAULT_CONFIG

    def test_default_config_cn_has_cookie(self):
        assert "cookie" in setting.DEFAULT_CONFIG["cn"]
