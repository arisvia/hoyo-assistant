"""Test configuration and fixtures (unified v3 schema)."""

from copy import deepcopy

import pytest


@pytest.fixture
def mock_cn_account():
    """Provide a minimal CN peer account dict for testing."""
    return {
        "name": "CN-1",
        "enable": True,
        "region": "cn",
        "push": None,
        "cookie": "",
        "user_agent": "TestUA",
        "device": {
            "name": "TestDevice",
            "model": "TestModel",
            "id": "test-device-id",
            "fp": "",
        },
        "bbs": {
            "enable": False,
            "forums": [],
        },
        "games": [],
        "black_list": {},
        "custom_games": {},
        "cloud": {
            "genshin": "",
            "zzz": "",
        },
    }


@pytest.fixture
def mock_os_account():
    """Provide a minimal OS peer account dict for testing."""
    return {
        "name": "OS-1",
        "enable": True,
        "region": "os",
        "push": None,
        "cookie": "",
        "user_agent": "",
        "lang": "en-us",
        "games": [],
        "custom_games": {},
        "cloud": {
            "genshin": "",
            "zzz": "",
        },
    }


@pytest.fixture
def mock_root_config(mock_cn_account, mock_os_account):
    """Provide a minimal unified v3 root config dict."""
    return {
        "enable": True,
        "push": {
            "enable": False,
            "error_only": False,
            "merge": True,
            "block_keys": [],
            "default": ["tg_main"],
            "targets": {
                "tg_main": {
                    "type": "telegram",
                    "api_url": "api.telegram.org",
                    "bot_token": "",
                    "chat_id": "",
                }
            },
        },
        "accounts": [deepcopy(mock_cn_account), deepcopy(mock_os_account)],
    }
