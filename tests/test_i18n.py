import json
import pathlib
import re

from hoyo_assistant.core.i18n import I18n


def test_i18n_translation(monkeypatch):
    I18n()
    # Test setting language via env because it detects it at initialization
    monkeypatch.setenv("HOYO_ASSISTANT_LANGUAGE", "zh_CN")
    translator_zh = I18n()
    zh_val = translator_zh.t("cli.task.server_help_title")
    assert isinstance(zh_val, str)

    monkeypatch.setenv("HOYO_ASSISTANT_LANGUAGE", "en_US")
    translator_en = I18n()
    en_val = translator_en.t("cli.task.server_help_title")
    assert isinstance(en_val, str)


def test_i18n_interpolation():
    translator = I18n()
    # Test formatting with variables if key has them
    msg = translator.t("cli.task.single_fail", error="TestError")
    assert "TestError" in msg


def test_i18n_default():
    translator = I18n()
    # If key doesn't exist, it returns the key itself. It doesn't have a default parameter in signature.
    assert translator.t("non_existing_key") == "non_existing_key"


def _flatten_locale(data: dict, prefix: str = "") -> dict[str, str]:
    out: dict[str, str] = {}
    for key, val in data.items():
        full = f"{prefix}.{key}" if prefix else key
        if isinstance(val, dict):
            out.update(_flatten_locale(val, full))
        else:
            out[full] = str(val)
    return out


def test_i18n_locales_parity_and_placeholders():
    locales_dir = (
        pathlib.Path(__file__).resolve().parents[1]
        / "src"
        / "hoyo_assistant"
        / "locales"
    )
    en = _flatten_locale(
        json.loads((locales_dir / "en_US.json").read_text(encoding="utf-8"))
    )
    zh = _flatten_locale(
        json.loads((locales_dir / "zh_CN.json").read_text(encoding="utf-8"))
    )
    assert set(en) == set(zh), (
        f"Locale key mismatch: en-zh={set(en) - set(zh)}, zh-en={set(zh) - set(en)}"
    )
    for key in sorted(en):
        en_placeholders = set(re.findall(r"\{([a-zA-Z0-9_]+)(?::[^}]*)?\}", en[key]))
        zh_placeholders = set(re.findall(r"\{([a-zA-Z0-9_]+)(?::[^}]*)?\}", zh[key]))
        assert en_placeholders == zh_placeholders, (
            f"Placeholder mismatch for '{key}': en={en_placeholders} vs zh={zh_placeholders}"
        )


def test_i18n_all_source_keys_exist():
    src_dir = pathlib.Path(__file__).resolve().parents[1] / "src" / "hoyo_assistant"
    en = _flatten_locale(
        json.loads((src_dir / "locales" / "en_US.json").read_text(encoding="utf-8"))
    )
    missing: list[str] = []
    for py_file in src_dir.rglob("*.py"):
        text = py_file.read_text(encoding="utf-8")
        for match in re.finditer(r"""\bt\(\s*["']([a-zA-Z0-9_.]+)["']""", text):
            key = match.group(1)
            if key not in en:
                missing.append(f"{key} ({py_file.name})")
    assert not missing, f"Missing locale keys used in src/: {missing}"


def test_i18n_no_unused_locale_keys():
    src_dir = pathlib.Path(__file__).resolve().parents[1] / "src" / "hoyo_assistant"
    en = _flatten_locale(
        json.loads((src_dir / "locales" / "en_US.json").read_text(encoding="utf-8"))
    )
    all_src = "\n".join(
        py_file.read_text(encoding="utf-8") for py_file in src_dir.rglob("*.py")
    )
    dynamic_prefixes = ("games.names.", "games.titles.")
    dynamic_suffixes = ("_coin",)
    unused = [
        key
        for key in sorted(en)
        if key not in all_src
        and not key.startswith(dynamic_prefixes)
        and not (key.startswith("games.cloud.") and key.endswith(dynamic_suffixes))
    ]
    assert not unused, f"Unused locale keys in en_US.json: {unused}"
