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
    from hoyo_assistant import run_account, run_accounts
    from hoyo_assistant.runner import executor

    assert callable(run_account)
    assert callable(run_accounts)
    assert callable(executor.handle_cn_login)
    assert callable(executor.run_account)
    assert callable(executor.run_accounts)


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
    assert hasattr(setting, "get_account")
    assert hasattr(setting, "set_current_account")
    assert hasattr(request, "http")
