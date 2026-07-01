import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from hoyo_assistant.core import CookieError
from hoyo_assistant.core.account import get_game_name, get_account_list

def test_get_game_name():
    # Test fallback name when not mapped
    assert get_game_name("non_existent_game_biz") == "non_existent_game_biz"
    # Test mapped games (Genshin Impact CN biz: hk4e_cn)
    assert isinstance(get_game_name("hk4e_cn"), str)

@pytest.mark.asyncio
async def test_get_account_list_success():
    mock_response = AsyncMock()
    mock_response.json = AsyncMock(return_value={
        "retcode": 0,
        "data": {
            "list": [
                {"nickname": "Miku", "game_uid": "100000001", "region": "cn_gf01"}
            ]
        }
    })
    
    with patch("hoyo_assistant.core.account.http.get", return_value=mock_response):
        headers = {"Cookie": "test"}
        accounts = await get_account_list("hk4e_cn", headers)
        assert len(accounts) == 1
        assert accounts[0] == ("Miku", "100000001", "cn_gf01")

@pytest.mark.asyncio
async def test_get_account_list_cookie_expired_retry():
    mock_response_expired = AsyncMock()
    mock_response_expired.json = AsyncMock(return_value={"retcode": -100})
    
    mock_response_success = AsyncMock()
    mock_response_success.json = AsyncMock(return_value={
        "retcode": 0,
        "data": {
            "list": [
                {"nickname": "Lumine", "game_uid": "100000002", "region": "cn_gf01"}
            ]
        }
    })
    
    # We patch login.update_cookie_token to mock cookie update
    with patch("hoyo_assistant.core.account.http.get") as mock_get, \
         patch("hoyo_assistant.core.account.login.update_cookie_token", AsyncMock(return_value=True)), \
         patch("hoyo_assistant.core.account.config", {"account": {"cookie": "new_cookie"}}):
        
        mock_get.side_effect = [mock_response_expired, mock_response_success]
        
        headers = {"Cookie": "old_cookie"}
        accounts = await get_account_list("hk4e_cn", headers)
        assert len(accounts) == 1
        assert accounts[0] == ("Lumine", "100000002", "cn_gf01")
        assert headers["Cookie"] == "new_cookie"

@pytest.mark.asyncio
async def test_get_account_list_cookie_expired_raise():
    mock_response_expired = AsyncMock()
    mock_response_expired.json = AsyncMock(return_value={"retcode": -100})
    
    with patch("hoyo_assistant.core.account.http.get", return_value=mock_response_expired), \
         patch("hoyo_assistant.core.account.login.update_cookie_token", AsyncMock(return_value=False)):
        
        headers = {"Cookie": "old_cookie"}
        with pytest.raises(CookieError):
            await get_account_list("hk4e_cn", headers)
