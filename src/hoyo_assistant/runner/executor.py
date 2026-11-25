import asyncio
import os
import random
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from ..core import (
    CookieError,
    StatusCode,
    StokenError,
    config,
    http,
    log,
    login,
    qr_login,
    setting,
    t,
    tools,
)
from ..core.constants import (
    CN_CLOUD_GAME_KEYS,
    DELAY_ACCOUNT_RANGE,
    DELAY_BBS_RANGE,
    OS_CLOUD_GAME_KEYS,
    QR_AUTO_PROMPT_TIMEOUT,
)
from ..core.models import AccountRunResult
from ..core.push import dispatch_push
from ..tasks import chinese, community, overseas


def _normalize_output_text(text: str) -> str:
    """Normalize output text for console/push/log readability."""
    if not text:
        return ""
    normalized = str(text).replace("\r\n", "\n").replace("\r", "\n")
    normalized = "\n".join(line.rstrip() for line in normalized.split("\n"))
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def _resolve_account_label(account: dict[str, Any], index: int) -> str:
    """Return explicit account name or a deterministic region#index fallback."""
    name = str(account.get("name", "")).strip()
    region = str(account.get("region", "account")).strip() or "account"
    return name or f"{region}#{index + 1}"


def _matches_filter(
    account: dict[str, Any], index: int, filter_tokens: set[str]
) -> bool:
    """Match an account by explicit name, auto label, or 1-based index."""
    region = str(account.get("region", "")).strip()
    candidates = {
        str(index + 1),
        f"{region}#{index + 1}".lower(),
        _resolve_account_label(account, index).lower(),
    }
    raw_name = str(account.get("name", "")).strip()
    if raw_name:
        candidates.add(raw_name.lower())
    return bool(candidates & filter_tokens)


def _compute_status(
    *,
    had_error: bool,
    had_success: bool,
    result_msg: str,
    had_captcha: bool = False,
) -> int:
    if had_error and had_success:
        return StatusCode.PARTIAL_FAILURE.value
    if had_error:
        return StatusCode.FAILURE.value
    if (
        had_captcha
        or t("games.cn.captcha_trigger") in result_msg
        or "验证码" in result_msg
    ):
        return StatusCode.CAPTCHA_TRIGGERED.value
    return StatusCode.SUCCESS.value


def _aggregate_overall_status(results: list[AccountRunResult]) -> int:
    if not results:
        return StatusCode.FAILURE.value
    statuses = [r.status for r in results]
    if all(s == StatusCode.FAILURE.value for s in statuses):
        return StatusCode.FAILURE.value
    if any(
        s in (StatusCode.FAILURE.value, StatusCode.PARTIAL_FAILURE.value)
        for s in statuses
    ):
        return StatusCode.PARTIAL_FAILURE.value
    if any(s == StatusCode.CAPTCHA_TRIGGERED.value for s in statuses):
        return StatusCode.CAPTCHA_TRIGGERED.value
    return StatusCode.SUCCESS.value


async def handle_cn_login(account: dict[str, Any]) -> None:
    """Verify/complete CN credentials and hydrate V2 cookie fields when possible."""
    raw_cookie = str(account.get("cookie", "")).strip()
    if not raw_cookie:
        raise CookieError(t("account.missing_cookie"))

    if (account.get("bbs") or {}).get("enable"):
        needs_login = (
            not login.get_stoken()
            or not login.get_uid()
            or (login.require_mid() and not login.get_mid())
            or login.require_stoken()
        )
        if needs_login:
            await login.login()
            await asyncio.sleep(random.randint(*DELAY_BBS_RANGE))

    if login.require_cookie_token() and login.get_mid():
        try:
            account["cookie"] = await login.build_account_cookie()
        except CookieError as e:
            log.warning(t("account.cookie_fill_fail", error=e))
    else:
        account["cookie"] = tools.tidy_cookie(str(account.get("cookie", "")))


async def _try_auto_qr_login(
    account: dict[str, Any] | None,
    *,
    scope: qr_login.QRScope,
    timeout: int = QR_AUTO_PROMPT_TIMEOUT,
) -> dict[str, Any] | None:
    """Attempt an interactive terminal QR login with a short timeout; skip on failure."""
    device = account.get("device") if isinstance(account, dict) else None
    try:
        result = await qr_login.qr_login_cn(
            scope=scope,
            timeout=timeout,
            device=device if isinstance(device, dict) else None,
        )
    except TimeoutError:
        log.warning(t("qr.auto_skip_timeout", timeout=timeout))
        return None
    except (KeyboardInterrupt, asyncio.CancelledError):
        log.warning(t("qr.cancelled"))
        return None
    except Exception as e:
        log.warning(t("qr.failed", error=e))
        return None

    saved_acct, created_new = await qr_login.upsert_cn_account(
        result,
        target_account=account,
        scope=scope,
    )
    msg_key = "qr.saved_new" if created_new else "qr.saved_overwrite"
    log.info(
        t(
            msg_key,
            name=str(saved_acct.get("name") or result.uid),
            uid=result.uid,
            path=setting.config_path or "memory",
        )
    )
    return saved_acct


async def _run_cn_account(
    account: dict[str, Any], *, allow_qr_login: bool = False
) -> tuple[int, str]:
    """Execute MiYoUShe BBS, CN game sign-ins, and CN cloud game tasks."""
    qr_attempted = False
    acct_label = str(account.get("name") or "cn")

    try:
        await handle_cn_login(account)
    except (CookieError, StokenError) as e:
        if not allow_qr_login or qr_attempted:
            return StatusCode.FAILURE.value, str(e)
        qr_attempted = True
        log.warning(
            t(
                "qr.auto_trigger_account",
                name=acct_label,
                timeout=QR_AUTO_PROMPT_TIMEOUT,
            )
        )
        if await _try_auto_qr_login(account, scope="all") is None:
            return StatusCode.FAILURE.value, str(e)
        try:
            await handle_cn_login(account)
        except (CookieError, StokenError) as retry_err:
            return StatusCode.FAILURE.value, str(retry_err)

    parts: list[str] = []
    had_error = False
    had_success = False
    had_captcha = False

    # 1. MiYoUShe BBS tasks
    bbs_cfg = account.get("bbs") or {}
    if bbs_cfg.get("enable"):
        if not login.get_stoken():
            had_error = True
            parts.append(t("mihoyobbs.stoken_error"))
        else:
            try:
                bbs = community.Mihoyobbs()
                bbs_msg = await bbs.run_task()
                if bbs_msg:
                    parts.append(bbs_msg)
                    if getattr(bbs_msg, "had_error", False):
                        had_error = True
                    if getattr(bbs_msg, "had_success", True):
                        had_success = True
                    if getattr(bbs_msg, "had_captcha", False):
                        had_captcha = True
            except StokenError:
                bbs_recovered = False
                if allow_qr_login and not qr_attempted:
                    qr_attempted = True
                    log.warning(
                        t(
                            "qr.auto_trigger_account",
                            name=acct_label,
                            timeout=QR_AUTO_PROMPT_TIMEOUT,
                        )
                    )
                    if await _try_auto_qr_login(account, scope="all") is not None:
                        try:
                            bbs_retry = community.Mihoyobbs()
                            bbs_msg = await bbs_retry.run_task()
                            if bbs_msg:
                                parts.append(bbs_msg)
                                if getattr(bbs_msg, "had_error", False):
                                    had_error = True
                                if getattr(bbs_msg, "had_success", True):
                                    had_success = True
                                if getattr(bbs_msg, "had_captcha", False):
                                    had_captcha = True
                            bbs_recovered = True
                        except Exception as retry_err:
                            log.error(t("mihoyobbs.task_error", error=retry_err))
                if not bbs_recovered:
                    had_error = True
                    parts.append(t("mihoyobbs.stoken_error"))
            except Exception as e:
                had_error = True
                err_msg = t("mihoyobbs.task_error", error=e)
                log.error(err_msg)
                parts.append(err_msg)

    # 2. CN Game check-ins
    cn_games = account.get("games") or []
    cn_custom = account.get("custom_games") or {}
    cn_signin_enabled = bool(cn_games) or any(
        isinstance(spec, dict) and spec.get("enable", True)
        for spec in cn_custom.values()
    )
    if cn_signin_enabled:
        try:
            cn_msg = await chinese.run_signin_task()
            if cn_msg:
                parts.append(cn_msg)
                if getattr(cn_msg, "had_error", False):
                    had_error = True
                if getattr(cn_msg, "had_success", True):
                    had_success = True
                if getattr(cn_msg, "had_captcha", False):
                    had_captcha = True
        except (CookieError, StokenError) as auth_err:
            cn_recovered = False
            if allow_qr_login and not qr_attempted:
                qr_attempted = True
                log.warning(
                    t(
                        "qr.auto_trigger_account",
                        name=acct_label,
                        timeout=QR_AUTO_PROMPT_TIMEOUT,
                    )
                )
                if await _try_auto_qr_login(account, scope="all") is not None:
                    try:
                        cn_msg = await chinese.run_signin_task()
                        if cn_msg:
                            parts.append(cn_msg)
                            if getattr(cn_msg, "had_error", False):
                                had_error = True
                            if getattr(cn_msg, "had_success", True):
                                had_success = True
                            if getattr(cn_msg, "had_captcha", False):
                                had_captcha = True
                        cn_recovered = True
                    except Exception as retry_err:
                        err_msg = t("games.cn.task_error", error=retry_err)
                        log.error(err_msg)
                        parts.append(err_msg)
            if not cn_recovered:
                had_error = True
                err_msg = t("games.cn.task_error", error=auth_err)
                log.error(err_msg)
                parts.append(err_msg)
        except Exception as e:
            had_error = True
            err_msg = t("games.cn.task_error", error=e)
            log.error(err_msg)
            parts.append(err_msg)

    # 3. CN Cloud games
    cn_cloud = account.get("cloud") or {}
    if any(cn_cloud.get(key) for key in CN_CLOUD_GAME_KEYS):
        had_cloud_genshin = bool(cn_cloud.get("genshin"))
        try:
            cloud_msg = await chinese.run_cloud_task()
            cloud_cleared = had_cloud_genshin and not (
                (account.get("cloud") or {}).get("genshin")
            )
            if cloud_cleared and allow_qr_login and not qr_attempted:
                qr_attempted = True
                log.warning(
                    t(
                        "qr.auto_trigger_cloud",
                        name=acct_label,
                        timeout=QR_AUTO_PROMPT_TIMEOUT,
                    )
                )
                if await _try_auto_qr_login(account, scope="cloud") is not None:
                    cloud_msg = await chinese.run_cloud_task()
            if cloud_msg:
                parts.append(cloud_msg)
                if getattr(cloud_msg, "had_error", False):
                    had_error = True
                if getattr(cloud_msg, "had_success", True):
                    had_success = True
        except Exception as e:
            had_error = True
            err_msg = t("games.cn.task_error", error=e)
            log.error(err_msg)
            parts.append(err_msg)

    normalized = [
        cleaned for part in parts if (cleaned := _normalize_output_text(part))
    ]
    result_msg = "\n\n".join(normalized) or t("cli.task.no_result")
    status = _compute_status(
        had_error=had_error,
        had_success=had_success,
        result_msg=result_msg,
        had_captcha=had_captcha,
    )
    return status, result_msg


async def _run_os_account(account: dict[str, Any]) -> tuple[int, str]:
    """Execute HoYoLAB OS game sign-ins and OS cloud game tasks."""
    parts: list[str] = []
    had_error = False
    had_success = False

    os_cookie = str(account.get("cookie", ""))
    os_games = account.get("games") or []
    os_custom = account.get("custom_games") or {}
    os_signin_enabled = bool(os_games) or any(
        isinstance(spec, dict) and spec.get("enable", True)
        for spec in os_custom.values()
    )

    if os_signin_enabled:
        if not os_cookie:
            had_error = True
            parts.append(t("account.missing_cookie"))
        else:
            try:
                os_result = await overseas.run_signin_task()
                if os_result:
                    parts.append(f"{t('games.os.title')}{os_result}")
                    if getattr(os_result, "had_error", False):
                        had_error = True
                    if getattr(os_result, "had_success", True):
                        had_success = True
            except Exception as e:
                had_error = True
                err_msg = t("games.os.task_error", error=e)
                log.error(err_msg)
                parts.append(err_msg)

    os_cloud = account.get("cloud") or {}
    if any(os_cloud.get(key) for key in OS_CLOUD_GAME_KEYS):
        try:
            cloud_msg = await overseas.run_cloud_task()
            if cloud_msg:
                parts.append(cloud_msg)
                if getattr(cloud_msg, "had_error", False):
                    had_error = True
                if getattr(cloud_msg, "had_success", True):
                    had_success = True
        except Exception as e:
            had_error = True
            err_msg = t("games.os.task_error", error=e)
            log.error(err_msg)
            parts.append(err_msg)

    normalized = [
        cleaned for part in parts if (cleaned := _normalize_output_text(part))
    ]
    result_msg = "\n\n".join(normalized) or t("cli.task.no_result")
    status = _compute_status(
        had_error=had_error, had_success=had_success, result_msg=result_msg
    )
    return status, result_msg


async def run_account(
    account: dict[str, Any],
    index: int = 0,
    *,
    allow_qr_login: bool = False,
) -> AccountRunResult:
    """Run all tasks for a single peer account with isolated HTTP state."""
    label = _resolve_account_label(account, index)
    region = str(account.get("region", "")).strip()

    tools.refresh_lifecycle_id()
    http.clear_cache(include_public=False)
    http.clear_cookies()
    log.debug("HTTP cache cleared before account execution")

    setting.set_current_account(account)
    try:
        if region == "cn":
            status, message = await _run_cn_account(
                account, allow_qr_login=allow_qr_login
            )
        elif region == "os":
            status, message = await _run_os_account(account)
        else:
            raise ValueError(f"Unsupported account region: {region!r}")
    finally:
        setting.set_current_account(None)

    raw_push = account.get("push")
    push_targets = list(raw_push) if isinstance(raw_push, list) else None
    return AccountRunResult(
        name=label,
        region=region,
        status=status,
        message=message,
        push_targets=push_targets,
    )


def _same_config_path(requested: str | None, loaded: str | None) -> bool:
    """Return True when the requested config path matches what is already loaded."""
    if not loaded:
        return False
    if not requested:
        return True
    try:
        return (
            Path(os.path.expanduser(requested)).resolve()
            == Path(os.path.expanduser(loaded)).resolve()
        )
    except OSError:
        return os.path.expanduser(requested) == os.path.expanduser(loaded)


async def run_accounts(
    config_path: str | None = None,
    account_filter: Iterable[str] | None = None,
    use_env: bool = True,
    send_push: bool = True,
    allow_qr_login: bool | None = None,
    *,
    force_reload: bool = False,
) -> tuple[int, str, list[AccountRunResult]]:
    """Load unified config and execute all matching enabled accounts sequentially."""
    if force_reload or not _same_config_path(config_path, setting.config_path):
        setting.load_config(config_path, use_env=use_env)

    if not config.get("enable"):
        log.warning(t("config.not_enabled"))
        return StatusCode.FAILURE.value, t("config.not_enabled"), []

    qr_enabled = (
        qr_login.is_interactive_terminal()
        if allow_qr_login is None
        else bool(allow_qr_login)
    )

    all_accounts = config.get("accounts") or []
    if not all_accounts and qr_enabled:
        log.info(t("qr.auto_trigger_first_run", timeout=QR_AUTO_PROMPT_TIMEOUT))
        async with http:
            await _try_auto_qr_login(None, scope="all")
        all_accounts = config.get("accounts") or []

    enabled_accounts: list[tuple[int, dict[str, Any]]] = [
        (idx, acct)
        for idx, acct in enumerate(all_accounts)
        if isinstance(acct, dict) and acct.get("enable", True)
    ]

    if not enabled_accounts:
        log.warning(t("runner.no_accounts"))
        return StatusCode.FAILURE.value, t("runner.no_accounts"), []

    filter_list = [
        str(item).strip() for item in (account_filter or []) if str(item).strip()
    ]
    if filter_list:
        filter_tokens = {item.lower() for item in filter_list}
        selected = [
            (idx, acct)
            for idx, acct in enabled_accounts
            if _matches_filter(acct, idx, filter_tokens)
        ]
        if not selected:
            msg = t("runner.no_matching_accounts", filter=", ".join(filter_list))
            log.warning(msg)
            return StatusCode.FAILURE.value, msg, []
    else:
        selected = enabled_accounts

    log.info(t("runner.found_accounts", count=len(selected)))

    results: list[AccountRunResult] = []
    buckets: dict[str, list[str]] = {
        "ok": [],
        "partial": [],
        "error": [],
        "captcha": [],
    }

    async with http:
        for pos, (orig_idx, acct) in enumerate(selected):
            label = _resolve_account_label(acct, orig_idx)
            region = str(acct.get("region", ""))
            log.info(t("runner.executing", name=label, region=region))

            try:
                res = await run_account(acct, orig_idx, allow_qr_login=qr_enabled)
            except Exception as e:
                log.error(t("runner.exec_failed", name=label, error=e))
                raw_push = acct.get("push")
                res = AccountRunResult(
                    name=label,
                    region=region,
                    status=StatusCode.FAILURE.value,
                    message=str(e),
                    push_targets=list(raw_push) if isinstance(raw_push, list) else None,
                )

            results.append(res)
            if res.status == StatusCode.SUCCESS.value:
                buckets["ok"].append(label)
            elif res.status == StatusCode.PARTIAL_FAILURE.value:
                buckets["partial"].append(label)
            elif res.status == StatusCode.CAPTCHA_TRIGGERED.value:
                buckets["captcha"].append(label)
            else:
                buckets["error"].append(label)

            log.info(t("runner.exec_done", name=label))
            if pos < len(selected) - 1:
                await asyncio.sleep(random.randint(*DELAY_ACCOUNT_RANGE))

        if send_push:
            try:
                await dispatch_push(results)
            except Exception as pe:
                log.error(t("cli.task.push_failed", error=pe))

    summary_message = t(
        "runner.summary",
        total=len(selected),
        ok=len(buckets["ok"]),
        partial=len(buckets["partial"]),
        error=len(buckets["error"]),
        captcha=len(buckets["captcha"]),
        partial_list=buckets["partial"],
        error_list=buckets["error"],
        captcha_list=buckets["captcha"],
    )
    log.debug(summary_message)

    overall_status = _aggregate_overall_status(results)
    return overall_status, summary_message, results
