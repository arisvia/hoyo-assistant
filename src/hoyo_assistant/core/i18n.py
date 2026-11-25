import json
import locale
import os
import sys
from typing import Any, cast

from .constants import EnvVar
from .loghelper import log


class I18n:
    def __init__(self) -> None:
        self._locales: dict[str, dict[str, Any]] = {}
        self._current_lang = "zh_CN"
        default_dir = os.path.join(
            os.path.dirname(os.path.dirname(str(os.path.abspath(__file__)))), "locales"
        )
        meipass = getattr(sys, "_MEIPASS", None)
        if getattr(sys, "frozen", False) and meipass:
            bundled_dir = os.path.join(str(meipass), "hoyo_assistant", "locales")
            self._locales_dir = (
                bundled_dir if os.path.exists(bundled_dir) else default_dir
            )
        else:
            self._locales_dir = default_dir
        self._load_locales()
        self._detect_language()

    def _normalize_lang(self, lang_code: str) -> str | None:
        cleaned = lang_code.strip().split(".")[0].replace("-", "_")
        if not cleaned:
            return None
        if cleaned in self._locales:
            return cleaned
        lowered = cleaned.lower()
        for existing in self._locales:
            if existing.lower() == lowered:
                return existing
        if lowered.startswith("zh") or "chinese" in lowered:
            return "zh_CN" if "zh_CN" in self._locales else None
        if lowered.startswith("en") or "english" in lowered:
            return "en_US" if "en_US" in self._locales else None
        return None

    def _detect_language(self) -> None:
        """Detect system language or use ENVIRONMENT variable."""
        env_lang = os.getenv(EnvVar.LANGUAGE)
        if env_lang:
            normalized = self._normalize_lang(env_lang)
            if normalized:
                self._current_lang = normalized
                log.debug(f"Language set from env: {self._current_lang}")
                return
            log.warning(
                f"Unsupported {EnvVar.LANGUAGE}={env_lang!r}; fallback to {self._current_lang}"
            )
            return

        try:
            sys_lang_code = locale.getlocale()[0]
            if not sys_lang_code:
                lang_env = os.getenv(EnvVar.LANG_FALLBACK, "")
                sys_lang_code = (
                    lang_env.split(".")[0].replace("-", "_") if lang_env else None
                )
            if sys_lang_code:
                normalized_sys = self._normalize_lang(sys_lang_code)
                self._current_lang = normalized_sys or (
                    "en_US" if "en_US" in self._locales else self._current_lang
                )
                log.debug(
                    f"Detected system language: {sys_lang_code}, using: {self._current_lang}"
                )
        except Exception as e:
            log.warning(f"Failed to detect system language: {e}. Fallback to zh_CN.")
            self._current_lang = "zh_CN"

    def _load_locales(self) -> None:
        """Load all JSON files from locales directory."""
        if not os.path.exists(self._locales_dir):
            log.warning(f"Locales directory not found: {self._locales_dir}")
            return

        for filename in os.listdir(self._locales_dir):
            if filename.endswith(".json"):
                lang_code = filename[:-5]  # remove .json
                try:
                    with open(
                        os.path.join(self._locales_dir, filename), encoding="utf-8"
                    ) as f:
                        # json.load 返回 Any，显式 cast 为 dict[str, Any] 以满足类型检查
                        self._locales[lang_code] = cast(dict[str, Any], json.load(f))
                    log.debug(f"Loaded locale: {lang_code}")
                except Exception as e:
                    log.error(f"Failed to load locale {filename}: {e}")

    def t(self, key: str, **kwargs: Any) -> str:
        """
        Translate key (e.g. 'cli.task.single_start').
        Supports nested keys and format arguments.
        """
        keys = key.split(".")
        # value can be nested dict or string; use Any to avoid incompatible-assignment when
        # traversing nested keys
        value: Any = self._locales.get(self._current_lang, {})

        # Traverse
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                value = None
                break

        if value is None:
            return key

        if isinstance(value, str):
            if not kwargs:
                return value
            try:
                return value.format(**kwargs)
            except Exception as e:
                log.warning(
                    f"Failed to format string '{value}' with args {kwargs}: {e}"
                )
                return value

        return str(value)


# Singleton instance
i18n = I18n()

# Helper export
t = i18n.t
