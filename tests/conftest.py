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
        "device": {
            "name": "TestDevice",
            "model": "TestModel",
            "id": "test-device-id",
            "fp": "",
        },
        "mihoyobbs": {
            "checkin": False,
            "checkin_list": [],
        },
        "games": {
            "cn": {
                "genshin": {"checkin": False, "black_list": []},
                "honkai2": {"checkin": False, "black_list": []},
                "honkai3rd": {"checkin": False, "black_list": []},
                "tears_of_themis": {"checkin": False, "black_list": []},
                "honkai_sr": {"checkin": False, "black_list": []},
                "zzz": {"checkin": False, "black_list": []},
                "useragent": "TestUA",
                "retries": 1,
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
                "genshin": {"enable": False, "token": ""},
                "honkai2": {"enable": False, "token": ""},
                "honkai3rd": {"enable": False, "token": ""},
                "tears_of_themis": {"enable": False, "token": ""},
                "honkai_sr": {"enable": False, "token": ""},
                "zzz": {"enable": False, "token": ""},
            },
            "os": {
                "genshin": {"enable": False, "token": ""},
                "honkai2": {"enable": False, "token": ""},
                "honkai3rd": {"enable": False, "token": ""},
                "tears_of_themis": {"enable": False, "token": ""},
                "honkai_sr": {"enable": False, "token": ""},
                "zzz": {"enable": False, "token": ""},
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
