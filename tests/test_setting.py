"""Tests for hoyo_assistant.core.setting and setting_schema (unified v3 schema)."""

import sys
from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from hoyo_assistant.core import setting
from hoyo_assistant.core.setting_schema import HoyoConfig, HoyoSettings, clean_cookie


@pytest.fixture
def clean_setting():
    """Snapshot and reset setting module globals between tests."""
    saved = (
        setting.config.copy(),
        deepcopy(setting.runtime_overrides),
        setting.config_path,
        setting._current_account,
    )
    setting.config.clear()
    setting.config.update(deepcopy(setting.DEFAULT_CONFIG))
    setting.runtime_overrides.clear()
    setting.config_path = None
    setting.set_current_account(None)
    yield setting
    setting.config.clear()
    setting.config.update(saved[0])
    setting.runtime_overrides.clear()
    setting.runtime_overrides.update(saved[1])
    setting.config_path = saved[2]
    setting.set_current_account(saved[3])


@pytest.fixture
def config_file(tmp_path):
    """Write a minimal valid unified v3 config file and return its path."""
    cfg = {
        "enable": True,
        "push": {
            "enable": False,
            "merge": True,
            "default": ["tg_main"],
            "targets": {
                "tg_main": {
                    "type": "telegram",
                    "bot_token": "secret_bot_token_long",
                    "chat_id": "123",
                }
            },
        },
        "accounts": [
            {
                "name": "CN-1",
                "region": "cn",
                "cookie": (
                    "ltoken_v2=test_cookie_value_long_enough;"
                    "stuid=123456789;"
                    "stoken=v2_test_stoken_value;"
                    "mid=test_mid_value;"
                ),
                "device": {
                    "name": "TestDevice",
                    "model": "TestModel",
                    "id": "test-device-id",
                    "fp": "",
                },
                "bbs": {"enable": True, "forums": [5, 2]},
                "games": ["genshin", "zzz"],
            },
            {
                "name": "OS-1",
                "region": "os",
                "push": False,
                "cookie": "os_cookie_value_long_enough",
                "games": ["honkai_sr"],
            },
        ],
    }
    path = tmp_path / "config.yaml"
    path.write_text(yaml.dump(cfg), encoding="utf-8")
    return str(path)


@pytest.fixture
def empty_config_file(tmp_path):
    path = tmp_path / "empty.yaml"
    path.write_text("", encoding="utf-8")
    return str(path)


class TestReloadConfig:
    def test_reload_with_no_file_uses_defaults(self, clean_setting, monkeypatch):
        monkeypatch.setattr(clean_setting, "_find_default_config_file", lambda: None)
        clean_setting.reload_config(config_file=None, use_env=False)
        assert set(clean_setting.config) == {"enable", "push", "accounts"}
        assert clean_setting.config["enable"] is True
        assert clean_setting.config["accounts"] == []

    def test_reload_with_valid_file(self, clean_setting, config_file):
        clean_setting.reload_config(config_file=config_file, use_env=False)
        assert clean_setting.config_path == config_file
        assert len(clean_setting.config["accounts"]) == 2
        cn_acct, os_acct = clean_setting.config["accounts"]
        assert cn_acct["region"] == "cn"
        assert "123456789" in cn_acct["cookie"]
        assert "stuid" not in cn_acct
        assert cn_acct["games"] == ["genshin", "zzz"]
        assert os_acct["region"] == "os"
        assert os_acct["push"] == []
        assert os_acct["games"] == ["honkai_sr"]

    def test_reload_with_overrides_applied(self, clean_setting, config_file):
        overrides = {"enable": False}
        clean_setting.reload_config(
            config_file=config_file, overrides=overrides, use_env=False
        )
        assert clean_setting.config["enable"] is False
        assert clean_setting.runtime_overrides == overrides

    def test_reload_nonexistent_file_falls_back_to_defaults(
        self, clean_setting, tmp_path
    ):
        missing = str(tmp_path / "nope.yaml")
        clean_setting.reload_config(config_file=missing, use_env=False)
        assert clean_setting.config["accounts"] == []
        assert clean_setting.config_path is None

    def test_reload_empty_file_uses_defaults(self, clean_setting, empty_config_file):
        clean_setting.reload_config(config_file=empty_config_file, use_env=False)
        assert clean_setting.config["enable"] is True

    def test_reload_invalid_config_raises(self, clean_setting, tmp_path):
        bad = tmp_path / "bad.yaml"
        bad.write_text("accounts: not_a_list\n", encoding="utf-8")
        with pytest.raises(ValueError):
            clean_setting.reload_config(config_file=str(bad), use_env=False)

    def test_reload_clears_bound_account(self, clean_setting, config_file):
        clean_setting.set_current_account({"region": "cn"})
        clean_setting.reload_config(config_file=config_file, use_env=False)
        assert clean_setting._current_account is None


class TestAccountBindingAndClearHelpers:
    def test_get_account_returns_bound_account(self, clean_setting):
        acct = {"region": "cn", "cookie": "abc"}
        clean_setting.set_current_account(acct)
        assert clean_setting.get_account() is acct

    def test_get_account_falls_back_to_sole_account(self, clean_setting):
        acct = {"region": "os", "cookie": "os_cookie"}
        clean_setting.config["accounts"] = [acct]
        assert clean_setting.get_account() is acct

    def test_get_account_raises_when_unbound_with_multiple_or_zero(self, clean_setting):
        clean_setting.config["accounts"] = []
        with pytest.raises(RuntimeError):
            clean_setting.get_account()
        clean_setting.config["accounts"] = [{"region": "cn"}, {"region": "os"}]
        with pytest.raises(RuntimeError):
            clean_setting.get_account()

    @pytest.mark.asyncio
    async def test_clear_cookie_stoken_and_cloud_token_mutate_bound_account(
        self, clean_setting, config_file
    ):
        clean_setting.reload_config(config_file=config_file, use_env=False)
        cn_acct = clean_setting.config["accounts"][0]
        cn_acct["cookie"] = (
            "ltoken_v2=keep_lt;stuid=123456789;stoken=v2_secret_tok;mid=m1;"
        )
        cn_acct["cloud"]["genshin"] = "cloud_tok"
        clean_setting.set_current_account(cn_acct)

        await clean_setting.clear_stoken()
        assert "stoken=" not in cn_acct["cookie"]
        assert "ltoken_v2=keep_lt" in cn_acct["cookie"]
        assert "stuid=123456789" in cn_acct["cookie"]
        assert "mid=m1" in cn_acct["cookie"]

        await clean_setting.clear_cookie()
        assert cn_acct["cookie"] == ""

        await clean_setting.clear_cloud_token("genshin")
        assert cn_acct["cloud"]["genshin"] == ""

        loaded = yaml.safe_load(Path(config_file).read_text(encoding="utf-8"))
        assert len(loaded["accounts"]) == 2
        assert loaded["accounts"][0]["region"] == "cn"
        assert loaded["accounts"][1]["region"] == "os"
        assert loaded["accounts"][1]["push"] == []
        assert loaded["push"]["targets"]["tg_main"]["type"] == "telegram"


class TestGetEffectiveConfig:
    def test_redact_masks_account_secrets_and_push_targets(
        self, clean_setting, config_file
    ):
        clean_setting.reload_config(config_file=config_file, use_env=False)
        clean_setting.config["accounts"][0]["cloud"]["genshin"] = (
            "cloud_token_long_enough"
        )
        effective = clean_setting.get_effective_config(redact=True)
        cn_acct = effective["accounts"][0]
        assert "***" in cn_acct["cookie"]
        assert "test_cookie_value_long_enough" not in cn_acct["cookie"]
        assert "v2_test_stoken_value" not in cn_acct["cookie"]
        assert "***" in cn_acct["cloud"]["genshin"]
        assert "***" in effective["push"]["targets"]["tg_main"]["bot_token"]

    def test_redact_false_returns_raw(self, clean_setting, config_file):
        clean_setting.reload_config(config_file=config_file, use_env=False)
        effective = clean_setting.get_effective_config(redact=False)
        assert "test_cookie_value_long_enough" in effective["accounts"][0]["cookie"]

    def test_redact_does_not_mutate_real_config(self, clean_setting, config_file):
        clean_setting.reload_config(config_file=config_file, use_env=False)
        clean_setting.get_effective_config(redact=True)
        assert (
            "test_cookie_value_long_enough"
            in clean_setting.config["accounts"][0]["cookie"]
        )


class TestValidateConfigFileAndSchema:
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

    def test_rejects_typo_in_push_target_field(self, tmp_path):
        bad = tmp_path / "bad_push.yaml"
        bad.write_text(
            "push:\n  targets:\n    tg:\n      type: telegram\n      bot_toke: 'abc'\n",
            encoding="utf-8",
        )
        ok, errors = setting.validate_config_file(str(bad))
        assert ok is False
        assert "bot_toke" in errors[0]

    def test_rejects_undefined_push_target_in_default(self, tmp_path):
        bad = tmp_path / "bad_default.yaml"
        bad.write_text("push:\n  default: [missing_target]\n", encoding="utf-8")
        ok, errors = setting.validate_config_file(str(bad))
        assert ok is False
        assert "missing_target" in errors[0]

    def test_rejects_undefined_push_target_in_account(self, tmp_path):
        bad = tmp_path / "bad_acct_push.yaml"
        bad.write_text(
            "accounts:\n  - name: A\n    region: os\n    push: missing_target\n",
            encoding="utf-8",
        )
        ok, errors = setting.validate_config_file(str(bad))
        assert ok is False
        assert "missing_target" in errors[0]

    def test_rejects_cn_only_field_on_os_account(self, tmp_path):
        bad = tmp_path / "bad_os_field.yaml"
        bad.write_text(
            "accounts:\n  - region: os\n    bbs:\n      enable: true\n",
            encoding="utf-8",
        )
        ok, errors = setting.validate_config_file(str(bad))
        assert ok is False
        assert "bbs" in errors[0]

    @pytest.mark.parametrize("legacy_key", ["stoken", "stuid", "mid", "retries"])
    def test_rejects_removed_legacy_cn_fields(self, tmp_path, legacy_key):
        bad = tmp_path / f"legacy_{legacy_key}.yaml"
        bad.write_text(
            f"accounts:\n  - region: cn\n    {legacy_key}: 'val'\n",
            encoding="utf-8",
        )
        ok, errors = setting.validate_config_file(str(bad))
        assert ok is False
        assert legacy_key in errors[0]

    def test_rejects_os_only_field_on_cn_account(self, tmp_path):
        bad = tmp_path / "bad_cn_field.yaml"
        bad.write_text(
            "accounts:\n  - region: cn\n    lang: en-us\n",
            encoding="utf-8",
        )
        ok, errors = setting.validate_config_file(str(bad))
        assert ok is False
        assert "lang" in errors[0]

    def test_rejects_ghost_os_honkai2_game(self, tmp_path):
        bad = tmp_path / "bad_os.yaml"
        bad.write_text(
            "accounts:\n  - region: os\n    games: [honkai2]\n",
            encoding="utf-8",
        )
        ok, errors = setting.validate_config_file(str(bad))
        assert ok is False
        assert "honkai2" in errors[0]

    def test_rejects_legacy_v2_top_level_keys(self, tmp_path):
        for key in ("cn", "os", "client"):
            bad = tmp_path / f"v2_{key}.yaml"
            bad.write_text(f"{key}:\n  cookie: abc\n", encoding="utf-8")
            ok, errors = setting.validate_config_file(str(bad))
            assert ok is False
            assert key in errors[0]

    def test_push_target_shorthand_infers_provider_type(self):
        cfg = HoyoConfig.model_validate(
            {
                "push": {
                    "default": ["telegram"],
                    "targets": {
                        "telegram": {"bot_token": "tok", "chat_id": "1"},
                    },
                }
            }
        )
        assert cfg.push.targets["telegram"].type == "telegram"


class TestFindDefaultConfigFile:
    def test_discovers_cwd_yaml_and_yml(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys, "frozen", False, raising=False)
        monkeypatch.chdir(tmp_path)
        yml = tmp_path / "config.yml"
        yml.write_text("enable: true\n", encoding="utf-8")
        assert setting._find_default_config_file() == str(tmp_path / "config.yml")

        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text("enable: true\n", encoding="utf-8")
        assert setting._find_default_config_file() == str(tmp_path / "config.yaml")

    def test_frozen_exe_prioritizes_sibling_then_falls_back_to_cwd(
        self, tmp_path, monkeypatch
    ):
        bin_dir = tmp_path / "bin"
        work_dir = tmp_path / "work"
        bin_dir.mkdir()
        work_dir.mkdir()
        exe_path = bin_dir / "hoyo-assistant.exe"
        exe_path.write_text("", encoding="utf-8")

        cwd_cfg = work_dir / "config.yaml"
        cwd_cfg.write_text("enable: true\n", encoding="utf-8")

        monkeypatch.chdir(work_dir)
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "executable", str(exe_path))

        # No sibling config yet -> falls back to cwd/config.yaml
        assert setting._find_default_config_file() == str(cwd_cfg)

        # Sibling config.yaml takes priority over cwd/config.yaml
        sibling_cfg = bin_dir / "config.yaml"
        sibling_cfg.write_text("enable: true\n", encoding="utf-8")
        assert setting._find_default_config_file() == str(sibling_cfg)

    def test_deduplicates_game_lists(self):
        s = HoyoSettings.model_validate(
            {
                "accounts": [
                    {"region": "cn", "games": ["genshin", "zzz", "genshin"]},
                    {"region": "os", "games": ["zzz", "zzz"]},
                ]
            }
        )
        assert s.accounts[0].games == ["genshin", "zzz"]
        assert s.accounts[1].games == ["zzz"]


class TestSaveConfigSync:
    def test_save_to_explicit_path_preserves_discriminators(
        self, clean_setting, tmp_path
    ):
        out = tmp_path / "out.yaml"
        clean_setting.save_config_sync(
            str(out),
            {
                "enable": False,
                "push": {
                    "targets": {"tg_main": {"type": "telegram", "bot_token": "t"}}
                },
                "accounts": [
                    {"region": "cn", "cookie": "c", "push": False},
                    {"region": "os", "cookie": "o"},
                ],
            },
        )
        assert out.exists()
        loaded = yaml.safe_load(out.read_text(encoding="utf-8"))
        assert loaded["enable"] is False
        assert loaded["push"]["targets"]["tg_main"]["type"] == "telegram"
        assert loaded["accounts"][0]["region"] == "cn"
        assert loaded["accounts"][0]["push"] == []
        assert loaded["accounts"][1]["region"] == "os"
        assert "push" not in loaded["accounts"][1]

    def test_save_with_no_target_noop(self, clean_setting):
        clean_setting.config_path = None
        clean_setting.save_config_sync(None, None)

    def test_save_default_only_config_not_empty_yaml(self, clean_setting, tmp_path):
        out = tmp_path / "minimal.yaml"
        clean_setting.save_config_sync(str(out), {"enable": True, "accounts": []})
        loaded = yaml.safe_load(out.read_text(encoding="utf-8"))
        assert loaded == {"enable": True, "accounts": []}


class TestZeroTemplateInit:
    def test_get_default_config_path_normal_and_frozen(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys, "frozen", False, raising=False)
        monkeypatch.chdir(tmp_path)
        assert setting.get_default_config_path() == str(tmp_path / "config.yaml")

        exe_dir = tmp_path / "dist"
        exe_dir.mkdir()
        exe_path = exe_dir / "hoyo-assistant.exe"
        exe_path.write_text("", encoding="utf-8")
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "executable", str(exe_path))
        assert setting.get_default_config_path() == str(exe_dir / "config.yaml")

    def test_ensure_config_initialized_creates_minimal_and_is_idempotent(
        self, clean_setting, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(sys, "frozen", False, raising=False)
        monkeypatch.setattr(clean_setting, "_find_default_config_file", lambda: None)
        monkeypatch.chdir(tmp_path)

        target_path, created = clean_setting.ensure_config_initialized()
        assert created is True
        assert target_path == str(tmp_path / "config.yaml")
        loaded = yaml.safe_load(Path(target_path).read_text(encoding="utf-8"))
        assert loaded == {"enable": True, "accounts": []}
        assert clean_setting.config_path == target_path

        target_path_2, created_2 = clean_setting.ensure_config_initialized(target_path)
        assert created_2 is False
        assert target_path_2 == target_path

    def test_save_preserves_unicode(self, clean_setting, tmp_path):
        out = tmp_path / "uni.yaml"
        clean_setting.save_config_sync(
            str(out),
            {
                "accounts": [
                    {"region": "cn", "device": {"name": "测试设备"}},
                ]
            },
        )
        content = out.read_text(encoding="utf-8")
        assert "测试设备" in content


class TestAutoFillConfigFile:
    def test_auto_fill_does_not_leak_env_secrets(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOYO_ASSISTANT_PUSH__ENABLE", "true")
        f = tmp_path / "clean.yaml"
        f.write_text("enable: false\n", encoding="utf-8")
        ok, _ = setting.auto_fill_config_file(str(f), backup=False)
        assert ok is True
        loaded = yaml.safe_load(f.read_text(encoding="utf-8"))
        assert "push" not in loaded

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

    def test_auto_fill_invalid_config_returns_error(self, tmp_path):
        bad = tmp_path / "bad.yaml"
        bad.write_text("accounts: not_a_list\n", encoding="utf-8")
        ok, _ = setting.auto_fill_config_file(str(bad), backup=False)
        assert ok is False


class TestEnvOverrides:
    def test_env_enable_and_push_merge_override_file(
        self, clean_setting, config_file, monkeypatch
    ):
        monkeypatch.setenv("HOYO_ASSISTANT_ENABLE", "false")
        monkeypatch.setenv("HOYO_ASSISTANT_PUSH__ENABLE", "true")
        monkeypatch.setenv("HOYO_ASSISTANT_PUSH__MERGE", "false")
        clean_setting.reload_config(config_file=config_file, use_env=True)
        assert clean_setting.config["enable"] is False
        assert clean_setting.config["push"]["enable"] is True
        assert clean_setting.config["push"]["merge"] is False

    def test_reload_use_env_false_ignores_env(
        self, clean_setting, config_file, monkeypatch
    ):
        monkeypatch.setenv("HOYO_ASSISTANT_ENABLE", "false")
        clean_setting.reload_config(config_file=config_file, use_env=False)
        assert clean_setting.config["enable"] is True


class TestDefaultConfig:
    def test_default_config_has_v3_keys(self):
        assert set(setting.DEFAULT_CONFIG) == {"enable", "push", "accounts"}
        for legacy in ("cn", "os", "client", "account", "mihoyobbs", "games"):
            assert legacy not in setting.DEFAULT_CONFIG


class TestCookieCleaningAndYamlFormat:
    def test_clean_cookie_cn_prunes_noise_and_redundant_v1(self):
        raw = (
            "_ga=GA1.2.3; _MHYUUID=uuid1; DEVICEFP=fp1; bbs_theme=dark; "
            "login_ticket=legacy_tkt; ltoken=L2; ltoken_v2=L2; "
            "ltuid=123; ltuid_v2=123; cookie_token=C2; cookie_token_v2=C2; "
            "account_id=123; account_id_v2=123; mid=m1; stoken=v2_s; stuid=123;"
        )
        cleaned = clean_cookie(raw, region="cn")
        for noise in ("_ga=", "_MHYUUID=", "DEVICEFP=", "bbs_theme=", "login_ticket="):
            assert noise not in cleaned
        for redundant_v1 in (
            "ltoken=L2",
            "ltuid=123",
            "cookie_token=C2",
            "account_id=123",
        ):
            assert f";{redundant_v1};" not in f";{cleaned}"
        for expected in (
            "ltoken_v2=L2;",
            "ltuid_v2=123;",
            "cookie_token_v2=C2;",
            "account_id_v2=123;",
            "stuid=123;",
            "stoken=v2_s;",
            "mid=m1;",
        ):
            assert expected in cleaned

    def test_clean_cookie_cn_preserves_v1_when_no_v2(self):
        raw = "_ga=1; ltoken=L1; ltuid=123; cookie_token=C1; stuid=123; stoken=v1_s;"
        cleaned = clean_cookie(raw, region="cn")
        assert cleaned == "ltoken=L1;ltuid=123;cookie_token=C1;stuid=123;stoken=v1_s;"

    def test_clean_cookie_os_prunes_noise_and_cn_only_keys(self):
        raw = (
            "_ga=1; mi18nLang=zh-cn; HYV_LOGIN_PLATFORM_OPTIONAL_AGREEMENT=x; "
            "stuid=999; stoken=v2_cn; mid=m_cn; "
            "ltoken=L2; ltoken_v2=L2; ltuid_v2=999; ltmid_v2=m_os;"
        )
        cleaned = clean_cookie(raw, region="os")
        assert cleaned == "ltoken_v2=L2;ltuid_v2=999;ltmid_v2=m_os;"

    def test_clean_cookie_safety_fallback_on_non_standard_strings(self):
        assert clean_cookie("opaque_token_without_eq", region="cn") == (
            "opaque_token_without_eq"
        )
        assert clean_cookie("custom_k=custom_v", region="os") == "custom_k=custom_v;"

    def test_dump_yaml_and_format_idempotency(self, tmp_path):
        cfg_file = tmp_path / "config.yaml"
        long_ua = "Mozilla/5.0 " + ("X" * 120)
        long_cookie = (
            "_ga=noise; ltoken_v2=" + ("A" * 100) + "; stuid=1; stoken=v2_tok; mid=m1;"
        )
        raw_yaml = (
            "accounts:\n"
            f"- cookie: {long_cookie}\n"
            f"  user_agent: {long_ua}\n"
            "  region: cn\n"
            "  name: CN-1\n"
            "  games:\n"
            "  - genshin\n"
        )
        cfg_file.write_text(raw_yaml, encoding="utf-8")

        ok, msg = setting.auto_fill_config_file(str(cfg_file), backup=True)
        assert ok is True
        assert (tmp_path / "config.yaml.bak").read_text(encoding="utf-8") == raw_yaml

        formatted_text = cfg_file.read_text(encoding="utf-8")
        lines = formatted_text.splitlines()
        assert "  - name: CN-1" in lines
        assert formatted_text.index("name: CN-1") < formatted_text.index("region: cn")
        assert formatted_text.index("region: cn") < formatted_text.index("cookie:")
        assert any(line.strip() == f"user_agent: {long_ua}" for line in lines)
        assert "_ga=" not in formatted_text

        # Second format run is idempotent and reports already complete
        ok2, msg2 = setting.auto_fill_config_file(str(cfg_file), backup=False)
        assert ok2 is True
        assert "完整" in msg2 or "complete" in msg2.lower()


class TestStrictEnvAndRedactionFixes:
    def test_load_config_use_env_still_rejects_unknown_yaml_keys(
        self, clean_setting, tmp_path
    ):
        bad = tmp_path / "typo.yaml"
        bad.write_text("enabel: true\ncn:\n  cookie: abc\n", encoding="utf-8")
        with pytest.raises(ValueError):
            clean_setting.reload_config(config_file=str(bad), use_env=True)

    def test_save_config_does_not_persist_env_overrides(
        self, clean_setting, config_file, monkeypatch
    ):
        monkeypatch.setenv("HOYO_ASSISTANT_PUSH__ENABLE", "true")
        monkeypatch.setenv("HOYO_ASSISTANT_ENABLE", "false")
        clean_setting.reload_config(config_file=config_file, use_env=True)
        assert clean_setting.config["push"]["enable"] is True
        assert clean_setting.config["enable"] is False

        clean_setting.config["accounts"][0]["cloud"]["genshin"] = "updated_cloud_tok"
        clean_setting.save_config_sync()

        saved_yaml = yaml.safe_load(Path(config_file).read_text(encoding="utf-8"))
        assert saved_yaml["accounts"][0]["cloud"]["genshin"] == "updated_cloud_tok"
        assert saved_yaml.get("push", {}).get("enable", False) is False
        assert saved_yaml.get("enable", True) is True
        assert clean_setting.config["push"]["enable"] is True

    def test_redact_masks_wecomrobot_and_webhook_urls(self, clean_setting, tmp_path):
        cfg_file = tmp_path / "push_url.yaml"
        cfg_file.write_text(
            yaml.dump(
                {
                    "push": {
                        "targets": {
                            "wr": {
                                "type": "wecomrobot",
                                "url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=secret-robot-key",
                            },
                            "wh": {
                                "type": "webhook",
                                "url": "https://hooks.example.com/trigger/super-secret-path",
                            },
                            "pm": {
                                "type": "pushme",
                                "token": "pm_secret_token",
                                "url": "https://push.i-i.me/",
                            },
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        clean_setting.reload_config(config_file=str(cfg_file), use_env=False)
        effective = clean_setting.get_effective_config(redact=True)
        targets = effective["push"]["targets"]
        assert "secret-robot-key" not in targets["wr"]["url"]
        assert "***" in targets["wr"]["url"]
        assert "super-secret-path" not in targets["wh"]["url"]
        assert "***" in targets["wh"]["url"]
        assert targets["pm"]["url"] == "https://push.i-i.me/"

    def test_collect_config_warnings_flags_incomplete_targets_and_duplicates(self):
        from hoyo_assistant.core.setting_schema import collect_config_warnings

        cfg = HoyoConfig.model_validate(
            {
                "push": {
                    "enable": True,
                    "default": ["tg_empty"],
                    "targets": {"tg_empty": {"type": "telegram"}},
                },
                "accounts": [
                    {
                        "name": "Dup",
                        "region": "cn",
                        "custom_games": {"newg": {"enable": True, "name": "NewG"}},
                    },
                    {"name": "Dup", "region": "os"},
                ],
            }
        )
        warnings = collect_config_warnings(cfg)
        joined = "\n".join(warnings)
        assert "Duplicate account name" in joined
        assert "custom_games.newg" in joined
        assert "tg_empty" in joined

    @pytest.mark.parametrize(
        "legacy_key", ["cn", "os", "client", "mihoyobbs", "account", "games"]
    )
    def test_legacy_v2_keys_rejected_with_clear_error(self, legacy_key):
        with pytest.raises(ValueError, match="Legacy v2"):
            HoyoConfig.model_validate({legacy_key: {}})

    def test_wintoast_target_forbids_legacy_enable_field(self):
        cfg = HoyoConfig.model_validate(
            {"push": {"targets": {"win": {"type": "wintoast"}}}}
        )
        assert cfg.push.targets["win"].type == "wintoast"
        with pytest.raises(ValueError):
            HoyoConfig.model_validate(
                {"push": {"targets": {"win": {"type": "wintoast", "enable": True}}}}
            )
