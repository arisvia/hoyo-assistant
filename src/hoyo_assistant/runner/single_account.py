import asyncio
import random
import re

from ..core import (
    CookieError,
    StatusCode,
    StokenError,
    config,
    http,
    is_push_enabled,
    log,
    login,
    push,
    setting,
    t,
    tools,
)
from ..core.constants import (
    CN_CLOUD_GAME_KEYS,
    COOKIE_ERROR_SENTINEL,
    DELAY_BBS_RANGE,
    OS_CLOUD_GAME_KEYS,
    STOKEN_ERROR_SENTINEL,
)
from ..tasks import chinese, community, overseas


def _normalize_output_text(text: str) -> str:
    """Normalize output text for console/push/log readability."""
    if not text:
        return ""
    normalized = str(text).replace("\r\n", "\n").replace("\r", "\n")
    normalized = "\n".join(line.rstrip() for line in normalized.split("\n"))
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


async def initialize_config(
    config_path: str | None = None, use_env: bool = True
) -> tuple[bool, str | None]:
    if config_path:
        setting.load_config(config_path, use_env=use_env)
    elif not setting.config_path:
        setting.load_config(None, use_env=use_env)

    if not config.get("enable"):
        log.warning(t("config.not_enabled"))
        return False, t("config.not_enabled")
    return True, None


async def handle_login() -> None:
    cn_cfg = config["cn"]
    if any(
        (
            cn_cfg["stuid"] == "",
            cn_cfg["stoken"] == "",
            cn_cfg["mid"] == "",
        )
    ):
        if cn_cfg["bbs"]["enable"]:
            await login.login()
            await asyncio.sleep(random.randint(*DELAY_BBS_RANGE))
        cn_cfg["cookie"] = tools.tidy_cookie(cn_cfg["cookie"])

    # Fill missing V2 cookie tokens (ltoken_v2 / cookie_token_v2) and sync V1 aliases
    if (
        cn_cfg.get("cookie")
        and cn_cfg.get("cookie") != COOKIE_ERROR_SENTINEL
        and str(cn_cfg.get("stoken", "")).startswith("v2_")
        and cn_cfg.get("mid")
    ):
        try:
            cn_cfg["cookie"] = await login.build_account_cookie()
        except CookieError as e:
            log.warning(t("account.cookie_fill_fail", error=e))


async def run_miyoushe_tasks() -> tuple[str, bool]:
    """Run MiYoUShe community tasks.

    Returns:
        tuple[str, bool]: (result_message, is_stoken_error)
    """
    return_data = ""
    raise_stoken = False

    cn_cfg = config["cn"]
    if not cn_cfg["bbs"]["enable"]:
        return return_data, raise_stoken

    if cn_cfg["stoken"] == STOKEN_ERROR_SENTINEL:
        return t("mihoyobbs.stoken_error"), True

    try:
        bbs = community.Mihoyobbs()
        task_result = await bbs.run_task()
        return_data += task_result
    except StokenError:
        return_data = t("mihoyobbs.stoken_error")
        raise_stoken = True
    except Exception as e:
        return_data = t("mihoyobbs.task_error", error=e)
        log.error(t("mihoyobbs.task_error", error=e))

    return return_data, raise_stoken


async def run_cn_signin_tasks() -> str:
    result = []
    cn_cfg = config.get("cn", {})
    cn_games = cn_cfg.get("games") or []
    cn_custom = cn_cfg.get("custom_games") or {}
    cn_signin_enabled = bool(cn_games) or any(
        isinstance(spec, dict) and spec.get("enable", True)
        for spec in cn_custom.values()
    )
    if cn_signin_enabled:
        result.append(await chinese.run_signin_task())

    cn_cloud = cn_cfg.get("cloud") or {}
    cn_cloud_enabled = any(cn_cloud.get(key) for key in CN_CLOUD_GAME_KEYS)
    if cn_cloud_enabled:
        result.append(await chinese.run_cloud_task())
    return "\n\n".join(filter(None, result))


async def run_os_signin_tasks() -> str:
    result = []
    os_cfg = config.get("os", {})
    os_cookie = os_cfg.get("cookie", "")
    os_games = os_cfg.get("games") or []
    os_custom = os_cfg.get("custom_games") or {}
    os_signin_enabled = bool(os_cookie) and (
        bool(os_games)
        or any(
            isinstance(spec, dict) and spec.get("enable", True)
            for spec in os_custom.values()
        )
    )
    if os_signin_enabled:
        os_result = await overseas.run_signin_task()
        if os_result:
            result.append(f"{t('games.os.title')}{os_result}")

    os_cloud = os_cfg.get("cloud") or {}
    os_cloud_enabled = any(os_cloud.get(key) for key in OS_CLOUD_GAME_KEYS)
    if os_cloud_enabled:
        result.append(await overseas.run_cloud_task())

    return "\n\n".join(filter(None, result))


async def run_once(
    config_path: str | None = None, use_env: bool = True
) -> tuple[int, str]:
    success, msg = await initialize_config(config_path, use_env=use_env)
    if not success:
        return StatusCode.FAILURE.value, msg or ""

    tools.refresh_lifecycle_id()

    from ..core.request import http

    http.clear_cache()
    http.clear_cookies()
    log.debug("HTTP cache cleared after config load")

    await handle_login()

    if config["cn"]["cookie"] == COOKIE_ERROR_SENTINEL:
        raise CookieError(t("account.cookie_invalid"))

    return_data = []
    status_code = StatusCode.SUCCESS.value

    raise_stoken = False
    try:
        miyoushe_result, raise_stoken = await run_miyoushe_tasks()
        return_data.append(miyoushe_result)
    except Exception as e:
        log.error(t("mihoyobbs.task_error", error=e))
        return_data.append(t("mihoyobbs.task_error", error=e))

    try:
        cn_result = await run_cn_signin_tasks()
        return_data.append(cn_result)
    except Exception as e:
        log.error(t("games.cn.task_error", error=e))
        return_data.append(t("games.cn.task_error", error=e))

    try:
        os_result = await run_os_signin_tasks()
        return_data.append(os_result)
    except Exception as e:
        log.error(t("games.os.task_error", error=e))
        return_data.append(t("games.os.task_error", error=e))

    if raise_stoken:
        raise StokenError(t("account.stoken_error"))

    normalized_parts = [_normalize_output_text(x) for x in return_data if x]
    normalized_parts = [x for x in normalized_parts if x]
    result_msg = "\n\n".join(normalized_parts)
    if not result_msg:
        result_msg = t("cli.task.no_result")

    if t("games.cn.captcha_trigger") in result_msg or "验证码" in result_msg:
        status_code = StatusCode.CAPTCHA_TRIGGERED.value

    return status_code, result_msg


async def run_single_account(
    config_path: str | None = None,
    use_env: bool = True,
) -> tuple[int, str]:
    async with http:
        try:
            if use_env:
                run_code, run_msg = await run_once(config_path)
            else:
                run_code, run_msg = await run_once(config_path, use_env=use_env)
        except (CookieError, StokenError) as e:
            if is_push_enabled():
                try:
                    await push.push(StatusCode.FAILURE.value, str(e))
                except Exception as pe:
                    log.error(t("cli.task.push_failed", error=pe))
            raise e

        if not is_push_enabled():
            return run_code, run_msg

        await push.push(run_code, run_msg)

        return run_code, run_msg
