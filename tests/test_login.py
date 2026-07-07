"""Tests for hoyo_assistant.core.login module.

Functions like get_uid/get_mid/get_login_ticket read from the global
`config["account"]["cookie"]`, so tests mock that via `patch`.
"""

import pytest
from unittest.mock import patch

from hoyo_assistant.core.login import (
    get_login_ticket,
    get_mid,
    get_uid,
    get_stoken_cookie,
    require_mid,
    require_stoken,
    require_cookie_token,
)


def _patch_config(cookie: str = "", stoken: str = "", stuid: str = "123", mid: str = "abc"):
    """Patch the global config dict with the given values."""
    return patch(
        "hoyo_assistant.core.login.config",
        {"account": {"cookie": cookie, "stoken": stoken, "stuid": stuid, "mid": mid}},
    )


class TestGetLoginTicket:
    def test_found(self):
        with _patch_config("login_ticket=abc123; other=value"):
            assert get_login_ticket() == "abc123"

    def test_not_found(self):
        with _patch_config("other=value"):
            assert get_login_ticket() is None

    def test_empty(self):
        with _patch_config(""):
            assert get_login_ticket() is None


class TestGetMid:
    def test_from_account_mid_v2(self):
        with _patch_config("account_mid_v2=xyz789; other=value"):
            assert get_mid() == "xyz789"

    def test_from_ltmid_v2(self):
        with _patch_config("ltmid_v2=abc456; other=value"):
            assert get_mid() == "abc456"

    def test_from_mid(self):
        with _patch_config("mid=def123; other=value"):
            assert get_mid() == "def123"

    def test_not_found(self):
        with _patch_config("other=value"):
            assert get_mid() is None


class TestGetUid:
    def test_from_account_id(self):
        with _patch_config("account_id=123456; other=value"):
            assert get_uid() == "123456"

    def test_from_ltuid(self):
        with _patch_config("ltuid=789012; other=value"):
            assert get_uid() == "789012"

    def test_from_login_uid(self):
        with _patch_config("login_uid=345678; other=value"):
            assert get_uid() == "345678"

    def test_from_ltuid_v2(self):
        with _patch_config("ltuid_v2=901234; other=value"):
            assert get_uid() == "901234"

    def test_from_account_id_v2(self):
        with _patch_config("account_id_v2=567890; other=value"):
            assert get_uid() == "567890"

    def test_not_found(self):
        with _patch_config("other=value"):
            assert get_uid() is None


class TestRequireMid:
    def test_v1_stoken(self):
        with _patch_config(stoken="v1_xxx"):
            assert require_mid() is False

    def test_v2_stoken(self):
        with _patch_config(stoken="v2_xxx"):
            assert require_mid() is True

    def test_no_stoken(self):
        with _patch_config(stoken=""):
            assert require_mid() is False


class TestRequireStoken:
    def test_v1_stoken(self):
        with _patch_config(stoken="v1_xxx"):
            assert require_stoken() is True

    def test_v2_stoken(self):
        with _patch_config(stoken="v2_xxx"):
            assert require_stoken() is False

    def test_no_stoken(self):
        with _patch_config(stoken=""):
            assert require_stoken() is False


class TestRequireCookieToken:
    def test_v2_stoken(self):
        with _patch_config(stoken="v2_xxx"):
            assert require_cookie_token() is True

    def test_v1_stoken(self):
        with _patch_config(stoken="v1_xxx"):
            assert require_cookie_token() is False


class TestGetStokenCookie:
    def test_v1_stoken(self):
        with _patch_config(stoken="v1_xxx", stuid="123"):
            result = get_stoken_cookie()
            assert result == "stuid=123;stoken=v1_xxx"

    def test_v2_stoken_with_mid(self):
        with _patch_config(stoken="v2_xxx", stuid="123", mid="abc"):
            result = get_stoken_cookie()
            assert result == "stuid=123;stoken=v2_xxx;mid=abc"

    def test_v2_stoken_without_mid_raises(self):
        from hoyo_assistant.core.error import CookieError

        with _patch_config(stoken="v2_xxx", stuid="123", mid=""):
            with pytest.raises(CookieError):
                get_stoken_cookie()
