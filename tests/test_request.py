"""Tests for hoyo_assistant.core.request module."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hoyo_assistant.core.request import HttpClient, MockResponse


@pytest.mark.asyncio
async def test_mock_response_json_text_read():
    data = {"a": 1}
    m = MockResponse(data)
    assert await m.json() == data
    assert isinstance(await m.text(), str)
    assert isinstance(await m.read(), bytes)


@pytest.mark.asyncio
async def test_httpclient_freeze_and_cache():
    c = HttpClient()
    # freeze simple structures
    a = c._freeze({"x": [1, 2]})
    assert isinstance(a, tuple)

    # cache behaviour: set cache directly and then ensure MockResponse returned
    auth_scope = {"cookie": "", "authorization": ""}
    key = ("http://example", c._freeze({}), c._freeze(auth_scope))
    c.cache[key] = {"ok": True}

    resp = await c.get("http://example")
    assert isinstance(resp, MockResponse)
    assert await resp.json() == {"ok": True}


def test_httpclient_cache_key_isolates_combo_token():
    c = HttpClient()
    k1 = c._build_cache_key(
        "https://api-cloudgame.mihoyo.com/wallet",
        headers={"x-rpc-combo_token": "tok_account_1"},
    )
    k2 = c._build_cache_key(
        "https://api-cloudgame.mihoyo.com/wallet",
        headers={"X-Rpc-Combo_Token": "tok_account_2"},
    )
    k_none = c._build_cache_key("https://api-cloudgame.mihoyo.com/wallet", headers={})
    assert k1 != k2
    assert k1 != k_none


def test_httpclient_session_usable_false_initially():
    c = HttpClient()
    assert c._is_session_usable() is False


@pytest.mark.asyncio
async def test_httpclient_returns_429_response_on_final_retry():
    c = HttpClient()
    resp_429 = AsyncMock()
    resp_429.status = 429
    resp_429.headers = {"X-RateLimit-Reset": "10"}
    resp_429.read = AsyncMock(return_value=b"")
    resp_429.release = MagicMock()

    mock_session = MagicMock()
    mock_session.request = AsyncMock(return_value=resp_429)
    c.session = mock_session

    with (
        patch.object(c, "_is_session_usable", return_value=True),
        patch("hoyo_assistant.core.request.RETRY_TIMES", 2),
        patch("asyncio.sleep", new=AsyncMock()),
    ):
        res = await c.post("https://example.com/sign", json={})

    assert res is resp_429
    assert res.status == 429
    assert mock_session.request.await_count == 2


def test_httpclient_clear_cache_preserves_public_entries_when_requested():
    c = HttpClient()
    pub_key = c._build_cache_key("https://public.example/games")
    cookie_key = c._build_cache_key(
        "https://private.example/sign", headers={"Cookie": "stuid=1;"}
    )
    auth_key = c._build_cache_key(
        "https://private.example/auth", headers={"Authorization": "Bearer x"}
    )
    combo_key = c._build_cache_key(
        "https://cloud.example/wallet", headers={"x-rpc-combo_token": "tok"}
    )
    for k in (pub_key, cookie_key, auth_key, combo_key):
        c.cache[k] = {"retcode": 0}

    c.clear_cache(include_public=False)
    assert pub_key in c.cache
    assert cookie_key not in c.cache
    assert auth_key not in c.cache
    assert combo_key not in c.cache

    c.clear_cache()
    assert len(c.cache) == 0
