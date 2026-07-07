"""Tests for hoyo_assistant.core.request module."""

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
