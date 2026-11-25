"""Tests for hoyo_assistant.core.login module."""

from unittest.mock import patch

import pytest

from hoyo_assistant.core.error import CookieError, StokenError
from hoyo_assistant.core.login import (
    get_mid,
    get_stoken,
    get_stoken_cookie,
    get_uid,
    get_web_cookie,
    require_cookie_token,
    require_mid,
    require_stoken,
)


def _patch_account(cookie: str = "", stoken: str = "", stuid: str = "", mid: str = ""):
    """Patch setting.get_account to return a CN account dict with a single cookie."""
    extra: list[str] = []
    if stuid:
        extra.append(f"stuid={stuid}")
    if stoken:
        extra.append(f"stoken={stoken}")
    if mid:
        extra.append(f"mid={mid}")
    if extra:
        parts = ([cookie.rstrip(";")] if cookie.strip() else []) + extra
        combined = ";".join(parts) + ";"
    else:
        combined = cookie
    acct = {
        "region": "cn",
        "cookie": combined,
    }
    return patch("hoyo_assistant.core.login.setting.get_account", return_value=acct)


class TestGetMid:
    def test_from_account_mid_v2(self):
        with _patch_account("account_mid_v2=xyz789; other=value"):
            assert get_mid() == "xyz789"

    def test_from_ltmid_v2(self):
        with _patch_account("ltmid_v2=abc456; other=value"):
            assert get_mid() == "abc456"

    def test_from_mid(self):
        with _patch_account("mid=def123; other=value"):
            assert get_mid() == "def123"

    def test_not_found(self):
        with _patch_account("other=value"):
            assert get_mid() is None


class TestGetUid:
    def test_from_account_id(self):
        with _patch_account("account_id=123456; other=value"):
            assert get_uid() == "123456"

    def test_from_ltuid(self):
        with _patch_account("ltuid=789012; other=value"):
            assert get_uid() == "789012"

    def test_from_login_uid(self):
        with _patch_account("login_uid=345678; other=value"):
            assert get_uid() == "345678"

    def test_from_ltuid_v2(self):
        with _patch_account("ltuid_v2=901234; other=value"):
            assert get_uid() == "901234"

    def test_from_account_id_v2(self):
        with _patch_account("account_id_v2=567890; other=value"):
            assert get_uid() == "567890"

    def test_stuid_takes_priority_and_non_numeric_ignored(self):
        with _patch_account("stuid=111; account_id_v2=222"):
            assert get_uid() == "111"
        with _patch_account("stuid=not_num; ltuid_v2=999"):
            assert get_uid() == "999"

    def test_not_found(self):
        with _patch_account("other=value"):
            assert get_uid() is None


class TestGetStokenAndWebCookie:
    def test_get_stoken(self):
        with _patch_account(stoken="v2_secret"):
            assert get_stoken() == "v2_secret"
        with _patch_account("ltoken=abc"):
            assert get_stoken() == ""

    def test_get_web_cookie_strips_stoken_and_mirrors_v1_in_memory(self):
        full = "ltoken_v2=L2; cookie_token_v2=C2; stuid=123; stoken=v2_secret; mid=m1;"
        with _patch_account(full):
            web = get_web_cookie()
        assert "ltoken_v2=L2;" in web
        assert "cookie_token_v2=C2;" in web
        assert "ltoken=L2;" in web
        assert "cookie_token=C2;" in web
        assert "ltuid_v2=123;" in web
        assert "ltuid=123;" in web
        assert "account_id_v2=123;" in web
        assert "account_id=123;" in web
        assert "ltmid_v2=m1;" in web
        assert "account_mid_v2=m1;" in web
        assert "mid=m1;" in web
        assert "stoken=" not in web
        assert "stuid=" not in web

    def test_get_web_cookie_raw_fallback(self):
        with _patch_account("unparseable_raw_token"):
            assert get_web_cookie() == "unparseable_raw_token"


class TestRequireMid:
    def test_v1_stoken(self):
        with _patch_account(stoken="v1_xxx"):
            assert require_mid() is False

    def test_v2_stoken(self):
        with _patch_account(stoken="v2_xxx"):
            assert require_mid() is True

    def test_no_stoken(self):
        with _patch_account(stoken=""):
            assert require_mid() is False


class TestRequireStoken:
    def test_v1_stoken(self):
        with _patch_account(stoken="v1_xxx"):
            assert require_stoken() is True

    def test_v2_stoken(self):
        with _patch_account(stoken="v2_xxx"):
            assert require_stoken() is False

    def test_no_stoken(self):
        with _patch_account(stoken=""):
            assert require_stoken() is False


class TestRequireCookieToken:
    def test_v2_stoken(self):
        with _patch_account(stoken="v2_xxx"):
            assert require_cookie_token() is True

    def test_v1_stoken(self):
        with _patch_account(stoken="v1_xxx"):
            assert require_cookie_token() is False


class TestGetStokenCookie:
    def test_v1_stoken(self):
        with _patch_account(stoken="v1_xxx", stuid="123"):
            result = get_stoken_cookie()
            assert result == "stuid=123;stoken=v1_xxx"

    def test_v2_stoken_with_mid(self):
        with _patch_account(stoken="v2_xxx", stuid="123", mid="abc"):
            result = get_stoken_cookie()
            assert result == "stuid=123;stoken=v2_xxx;mid=abc"

    def test_v2_stoken_without_mid_raises(self):
        with _patch_account(stoken="v2_xxx", stuid="123", mid=""):
            with pytest.raises(CookieError):
                get_stoken_cookie()

    def test_missing_stoken_or_uid_raises(self):
        with _patch_account(cookie="account_id=123"):
            with pytest.raises(StokenError):
                get_stoken_cookie()
        with _patch_account(cookie="stoken=v1_xxx"):
            with pytest.raises(CookieError):
                get_stoken_cookie()
