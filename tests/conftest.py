"""Test configuration and fixtures."""

import pytest


@pytest.fixture
def mock_config():
    """Provide a minimal config dict for testing."""
    return {
        "account": {
            "cookie": "",
            "stoken": "",
            "stuid": "",
            "mid": "",
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
        "mihoyobbs": {
            "checkin": False,
            "checkin_list": [],
        },
        "games": {
            "cn": {
                "retries": 1,
                "genshin": {"checkin": False, "black_list": []},
                "honkai2": {"checkin": False, "black_list": []},
                "honkai3rd": {"checkin": False, "black_list": []},
                "tears_of_themis": {"checkin": False, "black_list": []},
                "honkai_sr": {"checkin": False, "black_list": []},
                "zzz": {"checkin": False, "black_list": []},
            },
            "os": {
                "cookie": "",
                "lang": "en-us",
                "genshin": {"checkin": False, "black_list": []},
                "honkai2": {"checkin": False, "black_list": []},
                "honkai3rd": {"checkin": False, "black_list": []},
                "tears_of_themis": {"checkin": False, "black_list": []},
                "honkai_sr": {"checkin": False, "black_list": []},
                "zzz": {"checkin": False, "black_list": []},
            },
        },
        "cloud_games": {
            "cn": {
                "genshin": {"token": ""},
                "zzz": {"token": ""},
            },
            "os": {
                "lang": "en-us",
                "genshin": {"token": ""},
                "zzz": {"token": ""},
            },
        },
        "push": {
            "enable": False,
            "telegram": {
                "token": "",
                "chat_id": "",
            },
        },
    }
