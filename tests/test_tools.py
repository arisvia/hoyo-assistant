"""Tests for hoyo_assistant.core.tools module."""

import pytest

from hoyo_assistant.core.tools import (
    md5,
    random_text,
    timestamp,
    get_ds,
    get_ds2,
    get_device_id,
    get_item,
    get_next_day_timestamp,
    time_conversion,
    tidy_cookie,
    get_useragent,
)


class TestMd5:
    def test_md5_basic(self):
        assert md5("hello") == "5d41402abc4b2a76b9719d911017c592"

    def test_md5_empty(self):
        assert md5("") == "d41d8cd98f00b204e9800998ecf8427e"

    def test_md5_chinese(self):
        result = md5("你好")
        assert isinstance(result, str)
        assert len(result) == 32


class TestRandomText:
    def test_random_text_length(self):
        text = random_text(10)
        assert len(text) == 10

    def test_random_text_empty(self):
        text = random_text(0)
        assert text == ""

    def test_random_text_alphanumeric(self):
        text = random_text(10)
        assert all(c.isalnum() for c in text)


class TestTimestamp:
    def test_timestamp_type(self):
        ts = timestamp()
        assert isinstance(ts, int)
        assert ts > 0

    def test_timestamp_reasonable(self):
        ts = timestamp()
        # Should be after 2024-01-01
        assert ts > 1704067200


class TestGetDs:
    def test_get_ds_mobile(self):
        ds = get_ds(web=False)
        parts = ds.split(",")
        assert len(parts) == 3
        # timestamp, random, hash
        assert parts[0].isdigit()
        assert len(parts[1]) == 6
        assert len(parts[2]) == 32

    def test_get_ds_web(self):
        ds = get_ds(web=True)
        parts = ds.split(",")
        assert len(parts) == 3


class TestGetDs2:
    def test_get_ds2_basic(self):
        ds = get_ds2(query="test", body="{}")
        parts = ds.split(",")
        assert len(parts) == 3
        assert parts[0].isdigit()

    def test_get_ds2_empty(self):
        ds = get_ds2()
        parts = ds.split(",")
        assert len(parts) == 3


class TestGetDeviceId:
    def test_get_device_id_deterministic(self):
        cookie = "test_cookie"
        id1 = get_device_id(cookie)
        id2 = get_device_id(cookie)
        assert id1 == id2

    def test_get_device_id_format(self):
        device_id = get_device_id("test")
        # Should be UUID format
        assert len(device_id) == 36
        assert device_id.count("-") == 4


class TestGetItem:
    def test_get_item_basic(self):
        raw_data = {"name": "原石", "cnt": 60}
        result = get_item(raw_data)
        assert result == "「原石」x60"

    def test_get_item_single(self):
        raw_data = {"name": "纠缠之缘", "cnt": 1}
        result = get_item(raw_data)
        assert result == "「纠缠之缘」x1"


class TestGetNextDayTimestamp:
    def test_get_next_day_timestamp_type(self):
        ts = get_next_day_timestamp()
        assert isinstance(ts, int)

    def test_get_next_day_timestamp_future(self):
        ts = get_next_day_timestamp()
        assert ts > timestamp()


class TestTimeConversion:
    def test_time_conversion_hours_minutes(self):
        result = time_conversion(90)
        assert "1" in result  # 1 hour
        assert "30" in result  # 30 minutes

    def test_time_conversion_minutes_only(self):
        result = time_conversion(45)
        assert "0" in result or "小时" in result
        assert "45" in result


class TestTidyCookie:
    def test_tidy_cookie_normalizes(self):
        cookie = "a=1;  b=2;c=3"
        result = tidy_cookie(cookie)
        assert result == "a=1; b=2; c=3"

    def test_tidy_cookie_removes_empty(self):
        cookie = "a=1;;b=2"
        result = tidy_cookie(cookie)
        assert result == "a=1; b=2"

    def test_tidy_cookie_single(self):
        cookie = "single_value"
        result = tidy_cookie(cookie)
        assert result == "single_value"

    def test_tidy_cookie_preserves_order(self):
        cookie = "z=1; a=2; m=3"
        result = tidy_cookie(cookie)
        # Should preserve order, not sort
        assert result == "z=1; a=2; m=3"


class TestGetUseragent:
    def test_get_useragent_default(self):
        ua = get_useragent("")
        assert "miHoYoBBS" in ua

    def test_get_useragent_custom(self):
        ua = get_useragent("CustomAgent")
        assert "CustomAgent" in ua
        assert "miHoYoBBS" in ua

    def test_get_useragent_already_has_mihoyo(self):
        ua = get_useragent("miHoYoBBS/2.0")
        # Should not duplicate
        assert ua.count("miHoYoBBS") == 1
