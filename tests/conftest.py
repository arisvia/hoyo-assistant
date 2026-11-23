"""Test configuration and fixtures (pure v2 schema)."""

import pytest


@pytest.fixture
def mock_config():
    """Provide a minimal v2 config dict for testing."""
    return {
        "enable": True,
        "cn": {
            "cookie": "",
            "stoken": "",
            "stuid": "",
            "mid": "",
            "retries": 1,
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
        },
        "os": {
            "cookie": "",
            "lang": "en-us",
            "games": [],
            "custom_games": {},
            "cloud": {
                "genshin": "",
                "zzz": "",
            },
        },
        "client": {
            "user_agent": "TestUA",
            "device": {
                "name": "TestDevice",
                "model": "TestModel",
                "id": "test-device-id",
                "fp": "",
            },
        },
        "push": {
            "enable": False,
            "error_only": False,
            "block_keys": [],
            "active": [],
            "channels": {
                "telegram": {
                    "api_url": "api.telegram.org",
                    "bot_token": "",
                    "chat_id": "",
                },
            },
        },
    }
