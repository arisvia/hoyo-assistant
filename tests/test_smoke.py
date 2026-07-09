"""Smoke tests: verify all core modules import and expose expected interfaces."""


def test_status_code():
    from hoyo_assistant.core.constants import StatusCode

    assert hasattr(StatusCode, "SUCCESS")
    assert StatusCode.SUCCESS.value == 0
    assert StatusCode.FAILURE.value == 1


def test_core_exports():
    from hoyo_assistant.core import (
        CookieError,
        StatusCode,
        t,
    )

    assert StatusCode is not None
    assert CookieError is not None
    assert callable(t)


def test_runners_callable():
    from hoyo_assistant.runner import multi_account, single_account

    assert callable(single_account.run_once)
    assert callable(single_account.run_single_account)
    assert callable(multi_account.run_multi_account)


def test_task_modules_callable():
    from hoyo_assistant.tasks.chinese import (
        cloud_games as cn_cloud,
        game_signin as cn_signin,
    )
    from hoyo_assistant.tasks.overseas import (
        cloud_games as os_cloud,
        game_signin as os_signin,
    )

    assert callable(cn_signin.run_task)
    assert callable(cn_cloud.run_task)
    assert callable(os_signin.run_task)
    assert callable(os_cloud.run_task)


def test_setting_and_request():
    from hoyo_assistant.core import request, setting

    assert hasattr(setting, "load_config")
    assert hasattr(request, "http")
