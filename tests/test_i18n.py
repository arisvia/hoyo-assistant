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
