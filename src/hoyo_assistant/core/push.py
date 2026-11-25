import asyncio
import base64
import hashlib
import hmac
import inspect
import re
import time
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from typing import Any, Final, cast
from urllib.parse import quote_plus

from . import StatusCode, http, is_push_enabled, log, setting, t
from .constants import PUSH_NTFY_DEFAULT_URL, PUSH_PUSHME_URL
from .models import AccountRunResult

# =============================================================================
# Push Provider Endpoint & Branding Constants
# =============================================================================
PUSH_APP_NAME: Final[str] = "HoyoAssistant"
PUSH_REPO_URL: Final[str] = "https://github.com/arisvia/hoyo-assistant"
PUSH_FTQQ_BASE: Final[str] = "https://sctapi.ftqq.com"
PUSH_PUSHPLUS_URL: Final[str] = "https://www.pushplus.plus/send"
PUSH_SMTP_BG_API: Final[str] = "https://www.loliapi.com/acg/pc/"
PUSH_WECOM_TOKEN_URL: Final[str] = "https://qyapi.weixin.qq.com/cgi-bin/gettoken"
PUSH_WECOM_SEND_URL: Final[str] = "https://qyapi.weixin.qq.com/cgi-bin/message/send"
PUSH_BARK_ICON_BASE: Final[str] = "https://cdn.jsdelivr.net/gh/tanmx/pic@main/mihoyo"
PUSH_IFTTT_BASE: Final[str] = "https://maker.ifttt.com/trigger"
PUSH_QMSG_BASE: Final[str] = "https://qmsg.zendee.cn/send"
PUSH_WXPUSHER_URL: Final[str] = "https://wxpusher.zjiecode.com/api/send/message"

_STATUS_TITLE_KEYS: Final[dict[int, str]] = {
    -99: "push.status_missing_dep",
    -2: "push.status_error_id",
    -1: "push.status_config_update",
    StatusCode.SUCCESS: "push.status_success",
    StatusCode.FAILURE: "push.status_fail",
    StatusCode.PARTIAL_FAILURE: "push.status_partial_fail",
    StatusCode.CAPTCHA_TRIGGERED: "push.status_captcha",
}

_DISCORD_COLORS: Final[dict[int, int]] = {
    StatusCode.SUCCESS: 1926125,
    StatusCode.FAILURE: 14368575,
    StatusCode.PARTIAL_FAILURE: 16744192,
    StatusCode.CAPTCHA_TRIGGERED: 16744192,
}


def get_push_title(status_id: int) -> str:
    """获取推送标题"""
    key = _STATUS_TITLE_KEYS.get(status_id, "push.status_unknown")
    return t(key)


def _aggregate_status(statuses: list[int]) -> int:
    """Compute combined status code across multiple account results."""
    if not statuses:
        return StatusCode.SUCCESS.value
    if all(s == StatusCode.FAILURE for s in statuses):
        return StatusCode.FAILURE.value
    if any(s in (StatusCode.FAILURE, StatusCode.PARTIAL_FAILURE) for s in statuses):
        return StatusCode.PARTIAL_FAILURE.value
    if any(s == StatusCode.CAPTCHA_TRIGGERED for s in statuses):
        return StatusCode.CAPTCHA_TRIGGERED.value
    return StatusCode.SUCCESS.value


def _format_bucket_message(items: list[AccountRunResult]) -> str:
    """Format one or more account results into a unified notification body."""
    return "\n\n---\n\n".join(f"【{item.name}】\n{item.message}" for item in items)


class PushHandler:
    def __init__(self) -> None:
        self.http = http  # Use global async http

    def get_cfg(self) -> dict[str, Any]:
        """Get the push dictionary from the global config."""
        return cast(dict[str, Any], setting.config.get("push", {}))

    def get_targets(self) -> dict[str, Any]:
        """Get named push targets mapping from push config."""
        targets = self.get_cfg().get("targets")
        return cast(dict[str, Any], targets) if isinstance(targets, dict) else {}

    # 推送消息中屏蔽关键词
    def msg_replace(self, msg: Any) -> str:
        cfg = self.get_cfg()
        raw_keys = cfg.get("block_keys", [])
        if not raw_keys:
            return str(msg)
        block_keys = (
            raw_keys
            if isinstance(raw_keys, list)
            else [k.strip() for k in str(raw_keys).split(",")]
        )
        result = str(msg)
        for block_key in block_keys:
            block_key_trim = str(block_key).strip()
            if block_key_trim:
                result = result.replace(block_key_trim, "*" * len(block_key_trim))
        return result

    def _build_push_payload(
        self, status_id: int, push_message: str | None
    ) -> tuple[str, str, str]:
        """Build unified push payload for all channels."""
        title = get_push_title(status_id)
        content = str(push_message).strip() if push_message else ""
        if not content:
            content = t("push.empty_message")
        push_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        body = t("push.template_body", time=push_time, content=content)
        full_text = t("push.template_full", title=title, body=body)
        return title, body, full_text

    async def _read_response(
        self, resp: Any, provider: str
    ) -> tuple[dict[str, Any] | None, str]:
        """Read response body safely and raise ValueError on HTTP >= 400."""
        status = getattr(resp, "status", 200)
        data: dict[str, Any] | None = None
        raw_text = ""

        with suppress(Exception):
            parsed = await resp.json()
            if isinstance(parsed, dict):
                data = parsed

        if data is None or (isinstance(status, int) and status >= 400):
            with suppress(Exception):
                raw_text = str(await resp.text() or "")

        if isinstance(status, int) and status >= 400:
            detail = raw_text or str(data or "")
            raise ValueError(f"{provider} HTTP {status}: {detail}")
        return data, raw_text

    async def telegram(
        self, status_id: int, push_message: str | None, cfg: dict[str, Any]
    ) -> None:
        _, _, full_text = self._build_push_payload(status_id, push_message)
        raw_api = str(cfg.get("api_url") or "api.telegram.org").strip().rstrip("/")
        if not raw_api.startswith(("http://", "https://")):
            raw_api = f"https://{raw_api}"
        bot_token = cfg.get("bot_token", "")
        chat_id = str(cfg.get("chat_id", ""))
        url = f"{raw_api}/bot{bot_token}/sendMessage"
        resp = await self.http.post(
            url=url, data={"chat_id": chat_id, "text": full_text}
        )
        data, raw_text = await self._read_response(resp, "telegram")
        if data is not None and data.get("ok") is False:
            raise ValueError(f"telegram error: {data.get('description', raw_text)}")

    async def ftqq(
        self, status_id: int, push_message: str | None, cfg: dict[str, Any]
    ) -> None:
        """Server酱推送，具体推送位置在server酱后台配置"""
        title, body, _ = self._build_push_payload(status_id, push_message)
        sendkey = cfg.get("sendkey", "")
        resp = await self.http.post(
            url=f"{PUSH_FTQQ_BASE}/{sendkey}.send",
            data={"title": title, "desp": body},
        )
        data, raw_text = await self._read_response(resp, "ftqq")
        if data is not None and data.get("code") not in (None, 0):
            raise ValueError(f"ftqq error: {data.get('message', raw_text)}")

    async def pushplus(
        self, status_id: int, push_message: str | None, cfg: dict[str, Any]
    ) -> None:
        """PushPlus推送"""
        title, body, _ = self._build_push_payload(status_id, push_message)
        token = cfg.get("token", "")
        topic = cfg.get("topic", "")
        resp = await self.http.post(
            url=PUSH_PUSHPLUS_URL,
            data={
                "token": token,
                "title": title,
                "content": body,
                "topic": topic,
            },
        )
        data, raw_text = await self._read_response(resp, "pushplus")
        if data is not None and data.get("code") not in (None, 200):
            raise ValueError(f"pushplus error: {data.get('msg', raw_text)}")

    async def pushme(
        self, status_id: int, push_message: str | None, cfg: dict[str, Any]
    ) -> bool:
        """PushMe推送"""
        pushme_key = cfg.get("token", "")
        if not pushme_key:
            log.error(t("push.pushme_key_missing"))
            return False
        log.info(t("push.pushme_start"))
        title, body, _ = self._build_push_payload(status_id, push_message)
        data = {
            "push_key": pushme_key,
            "title": title,
            "content": body,
            "date": "",
            "type": "",
        }
        log.debug(f"PushMe 请求数据: {data}")
        url = cfg.get("url") or PUSH_PUSHME_URL
        response = await self.http.post(url=url, data=data)
        log.debug(f"PushMe 响应状态码: {response.status}")
        text = await response.text()
        log.debug(f"PushMe 响应内容: {text}")
        if response.status == 200 and text == "success":
            log.info(t("push.pushme_success"))
            return True
        log.error(t("push.pushme_fail", status=response.status, text=text))
        return False

    async def cqhttp(
        self, status_id: int, push_message: str | None, cfg: dict[str, Any]
    ) -> bool:
        """OneBot V11 (CqHttp) 协议推送"""
        qq = cfg.get("qq")
        group = cfg.get("group")

        if (qq and group) or (not qq and not group):
            log.error(t("push.cqhttp_config_err"))
            return False

        _, _, full_text = self._build_push_payload(status_id, push_message)
        data: dict[str, Any] = {"message": full_text}
        if qq:
            data["user_id"] = int(qq)
        if group:
            data["group_id"] = int(group)

        url = cfg.get("url", "")
        resp = await self.http.post(url=url, json=data)
        await self._read_response(resp, "cqhttp")
        return True

    async def smtp(
        self, status_id: int, push_message: str | None, cfg: dict[str, Any]
    ) -> None:
        """SMTP 电子邮件推送"""
        import smtplib
        from email.header import Header
        from email.mime.text import MIMEText
        from email.utils import formataddr
        from pathlib import Path

        title, body, _ = self._build_push_payload(status_id, push_message)

        async def get_background_url() -> str:
            try:
                resp = await self.http.get(PUSH_SMTP_BG_API, use_cache=False)
                return str(resp.url)
            except Exception:
                log.warning(t("push.smtp_img_fail"))
                return "unable to get the image"

        def get_background_img_html(background_url: str | None) -> str:
            if background_url:
                return f'<img src="{background_url}" alt="background" style="width: 100%; filter: brightness(50%)">'
            return ""

        def get_background_img_info(background_url: str | None) -> str:
            if background_url:
                return (
                    f'<p style="color: #fff;text-shadow:0px 0px 10px #000;">{t("push.smtp_img_title")}</p>\n'
                    f'<a href="{background_url}" style="color: #fff;text-shadow:0px 0px 10px #000;">{background_url}</a>'
                )
            return ""

        image_url = None
        if cfg.get("background", False):
            image_url = await get_background_url()

        def send_sync() -> None:
            template_file = Path("assets/email_example.html")
            if template_file.is_file():
                email_template = template_file.read_text(encoding="utf-8")
            else:
                email_template = "{title}<br>{message}<br>{background_info}"

            message = email_template.format(
                title=title,
                message=body.replace("\n", "<br/>"),
                background_image=get_background_img_html(image_url),
                background_info=get_background_img_info(image_url),
            )
            msg_mime = MIMEText(message, "html", "utf-8")
            subject = str(cfg.get("subject", ""))
            toaddr = str(cfg.get("toaddr", ""))
            fromaddr = str(cfg.get("fromaddr", ""))
            msg_mime["Subject"] = str(Header(subject, "utf-8"))
            msg_mime["To"] = toaddr
            msg_mime["From"] = formataddr((str(Header(subject, "utf-8")), fromaddr))

            mailhost = str(cfg.get("mailhost", ""))
            port = int(cfg.get("port", 465))
            username = str(cfg.get("username", ""))
            password = str(cfg.get("password", ""))

            smtp_cls = smtplib.SMTP_SSL if cfg.get("ssl_enable", True) else smtplib.SMTP
            with smtp_cls(mailhost, port) as server:
                server.login(username, password)
                server.sendmail(fromaddr, toaddr, msg_mime.as_string())
            log.info(t("push.smtp_success"))

        await asyncio.to_thread(send_sync)

    async def wecom(
        self, status_id: int, push_message: str | None, cfg: dict[str, Any]
    ) -> None:
        """企业微信推送"""
        secret = cfg.get("secret", "")
        corpid = cfg.get("wechat_id", "")
        touser = cfg.get("touser", "@all")

        _, _, full_text = self._build_push_payload(status_id, push_message)
        token_resp = await self.http.post(
            url=f"{PUSH_WECOM_TOKEN_URL}?corpid={corpid}&corpsecret={secret}",
            data="",
        )
        token_data, raw_tok = await self._read_response(token_resp, "wecom")
        push_token = (token_data or {}).get("access_token")
        if not push_token:
            raise ValueError(
                f"WeCom token fetch failed: {(token_data or {}).get('errmsg', raw_tok)}"
            )
        push_data = {
            "agentid": cfg.get("agentid", ""),
            "msgtype": "text",
            "touser": touser,
            "text": {"content": full_text},
            "safe": 0,
        }
        send_resp = await self.http.post(
            f"{PUSH_WECOM_SEND_URL}?access_token={push_token}",
            json=push_data,
        )
        send_data, raw_send = await self._read_response(send_resp, "wecom")
        if send_data is not None and send_data.get("errcode") not in (None, 0):
            raise ValueError(f"wecom error: {send_data.get('errmsg', raw_send)}")

    async def wecomrobot(
        self, status_id: int, push_message: str | None, cfg: dict[str, Any]
    ) -> None:
        """企业微信机器人"""
        _, _, full_text = self._build_push_payload(status_id, push_message)
        url = cfg.get("url", "")
        mobile = cfg.get("mobile", [])
        mentioned = (
            [str(m).strip() for m in mobile if str(m).strip()]
            if isinstance(mobile, list)
            else [m.strip() for m in str(mobile).split(",") if m.strip()]
        )
        text_payload: dict[str, Any] = {"content": full_text}
        if mentioned:
            text_payload["mentioned_mobile_list"] = mentioned
        resp = await self.http.post(
            url=url,
            headers={"Content-Type": "application/json; charset=utf-8"},
            json={
                "msgtype": "text",
                "text": text_payload,
            },
        )
        rep, _ = await self._read_response(resp, "wecomrobot")
        if rep is not None and rep.get("errcode") not in (None, 0):
            raise ValueError(f"wecomrobot error: {rep.get('errmsg', rep)}")
        log.info(t("push.result", result=(rep or {}).get("errmsg")))

    async def pushdeer(
        self, status_id: int, push_message: str | None, cfg: dict[str, Any]
    ) -> None:
        """PushDeer推送"""
        title, body, _ = self._build_push_payload(status_id, push_message)
        api_url = str(cfg.get("api_url", "")).rstrip("/")
        token = cfg.get("token", "")
        resp = await self.http.get(
            url=f"{api_url}/message/push",
            params={
                "pushkey": token,
                "text": title,
                "desp": str(body).replace("\r\n", "\r\n\r\n"),
                "type": "markdown",
            },
            use_cache=False,
        )
        await self._read_response(resp, "pushdeer")

    async def dingrobot(
        self, status_id: int, push_message: str | None, cfg: dict[str, Any]
    ) -> None:
        """钉钉群机器人推送"""
        _, _, full_text = self._build_push_payload(status_id, push_message)
        api_url = cfg.get("webhook", "")
        secret = cfg.get("secret", "")
        if secret:
            timestamp = str(round(time.time() * 1000))
            sign_string = f"{timestamp}\n{secret}"
            hmac_code = hmac.new(
                key=secret.encode("utf-8"),
                msg=sign_string.encode("utf-8"),
                digestmod=hashlib.sha256,
            ).digest()
            sign = quote_plus(base64.b64encode(hmac_code))
            sep = "&" if "?" in api_url else "?"
            api_url = f"{api_url}{sep}timestamp={timestamp}&sign={sign}"

        resp = await self.http.post(
            url=api_url,
            headers={"Content-Type": "application/json; charset=utf-8"},
            json={"msgtype": "text", "text": {"content": full_text}},
        )
        rep, _ = await self._read_response(resp, "dingrobot")
        if rep is not None and rep.get("errcode") not in (None, 0):
            raise ValueError(f"dingrobot error: {rep.get('errmsg', rep)}")
        log.info(t("push.result", result=(rep or {}).get("errmsg")))

    async def feishubot(
        self, status_id: int, push_message: str | None, cfg: dict[str, Any]
    ) -> None:
        """飞书机器人(WebHook)，支持可选 secret 签名校验"""
        _, _, full_text = self._build_push_payload(status_id, push_message)
        api_url = cfg.get("webhook", "")
        secret = cfg.get("secret", "")
        payload: dict[str, Any] = {
            "msg_type": "text",
            "content": {"text": full_text},
        }
        if secret:
            ts = str(int(time.time()))
            string_to_sign = f"{ts}\n{secret}"
            hmac_code = hmac.new(
                key=string_to_sign.encode("utf-8"),
                msg=b"",
                digestmod=hashlib.sha256,
            ).digest()
            payload["timestamp"] = ts
            payload["sign"] = base64.b64encode(hmac_code).decode("utf-8")
        resp = await self.http.post(
            url=api_url,
            headers={"Content-Type": "application/json; charset=utf-8"},
            json=payload,
        )
        rep, _ = await self._read_response(resp, "feishubot")
        if rep is not None and rep.get("code") not in (None, 0):
            raise ValueError(f"feishubot error: {rep.get('msg', rep)}")
        log.info(t("push.result", result=(rep or {}).get("msg")))

    async def bark(
        self, status_id: int, push_message: str | None, cfg: dict[str, Any]
    ) -> None:
        """Bark推送"""
        title, body, _ = self._build_push_payload(status_id, push_message)
        send_title = quote_plus(title)
        encoded_body = quote_plus(body)
        api_url = str(cfg.get("api_url", "")).rstrip("/")
        token = cfg.get("token", "")
        icon = cfg.get("icon", "")
        url = f"{api_url}/{token}/{send_title}/{encoded_body}"
        if icon:
            url = f"{url}?icon={PUSH_BARK_ICON_BASE}/{icon}.png"
        resp = await self.http.get(url=url, use_cache=False)
        rep, _ = await self._read_response(resp, "bark")
        log.info(t("push.result", result=(rep or {}).get("message")))

    async def gotify(
        self, status_id: int, push_message: str | None, cfg: dict[str, Any]
    ) -> None:
        """Gotify推送"""
        title, body, _ = self._build_push_payload(status_id, push_message)
        api_url = str(cfg.get("api_url", "")).rstrip("/")
        token = cfg.get("token", "")
        priority = int(cfg.get("priority", 0))
        resp = await self.http.post(
            url=f"{api_url}/message?token={token}",
            headers={"Content-Type": "application/json; charset=utf-8"},
            json={
                "title": title,
                "message": body,
                "priority": priority,
            },
        )
        rep, _ = await self._read_response(resp, "gotify")
        log.info(t("push.result", result=(rep or {}).get("errmsg")))

    async def ifttt(
        self, status_id: int, push_message: str | None, cfg: dict[str, Any]
    ) -> int:
        """IFTTT推送"""
        title, body, _ = self._build_push_payload(status_id, push_message)
        ifttt_event = cfg.get("event", "")
        ifttt_key = cfg.get("key", "")
        rep = await self.http.post(
            url=f"{PUSH_IFTTT_BASE}/{ifttt_event}/with/key/{ifttt_key}",
            headers={"Content-Type": "application/json; charset=utf-8"},
            json={"value1": title, "value2": body},
        )
        text = await rep.text()
        if getattr(rep, "status", 200) >= 400 or "errors" in text:
            try:
                log.warning(t("push.ifttt_err", error=(await rep.json())["errors"]))
            except Exception:
                log.warning(t("push.ifttt_err", error=text))
            return 0
        log.info(t("push.ifttt_done"))
        return 1

    async def webhook(
        self, status_id: int, push_message: str | None, cfg: dict[str, Any]
    ) -> None:
        """Generic WebHook推送"""
        title, body, _ = self._build_push_payload(status_id, push_message)
        webhook_url = cfg.get("url", "")
        resp = await self.http.post(
            url=webhook_url,
            headers={"Content-Type": "application/json; charset=utf-8"},
            json={"title": title, "message": body},
        )
        rep, raw_text = await self._read_response(resp, "webhook")
        result_msg = (
            rep.get("errmsg") or rep.get("msg") or rep.get("message")
            if rep is not None
            else (raw_text or f"HTTP {getattr(resp, 'status', 200)}")
        )
        log.info(t("push.result", result=result_msg))

    async def qmsg(
        self, status_id: int, push_message: str | None, cfg: dict[str, Any]
    ) -> None:
        """Qmsg酱推送"""
        _, _, full_text = self._build_push_payload(status_id, push_message)
        key = cfg.get("key", "")
        resp = await self.http.post(
            url=f"{PUSH_QMSG_BASE}/{key}",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={"msg": full_text},
        )
        rep, _ = await self._read_response(resp, "qmsg")
        log.info(t("push.result", result=(rep or {}).get("reason")))

    async def discord(
        self, status_id: int, push_message: str | None, cfg: dict[str, Any]
    ) -> bool:
        """Discord Webhook 推送"""
        title, body, _ = self._build_push_payload(status_id, push_message)
        webhook = cfg.get("webhook", "")
        avatar_url = str(cfg.get("avatar_url", "") or "")
        author: dict[str, Any] = {
            "name": PUSH_APP_NAME,
            "url": PUSH_REPO_URL,
        }
        if avatar_url:
            author["icon_url"] = avatar_url

        payload: dict[str, Any] = {
            "content": None,
            "embeds": [
                {
                    "title": title,
                    "description": body,
                    "color": _DISCORD_COLORS.get(status_id, 16744192),
                    "author": author,
                    "timestamp": datetime.now(timezone(timedelta(hours=8))).isoformat(),
                }
            ],
            "username": PUSH_APP_NAME,
            "attachments": [],
        }
        if avatar_url:
            payload["avatar_url"] = avatar_url

        rep = await self.http.post(
            url=webhook,
            headers={"Content-Type": "application/json; charset=utf-8"},
            json=payload,
        )
        if rep.status not in (200, 204):
            log.warning(t("push.discord_err", error=await rep.text()))
            return False
        log.info(t("push.discord_success", status=rep.status))
        return True

    def wintoast(
        self, status_id: int, push_message: str | None, cfg: dict[str, Any]
    ) -> bool:
        try:
            toast = __import__("win11toast").toast
            title, body, _ = self._build_push_payload(status_id, push_message)
            toast(app_id=PUSH_APP_NAME, title=title, body=body, icon="")
            return True
        except Exception:
            log.error(t("push.wintoast_err"))
            return False

    async def serverchan3(
        self, status_id: int, push_message: str | None, cfg: dict[str, Any]
    ) -> None:
        title, body, _ = self._build_push_payload(status_id, push_message)
        sendkey = cfg.get("sendkey", "")
        match = re.match(r"sctp(\d+)t", sendkey)
        if match:
            num = match.group(1)
            url = f"https://{num}.push.ft07.com/send/{sendkey}.send"
        else:
            raise ValueError(t("push.serverchan3_invalid_key"))
        tags = cfg.get("tags", "")
        rep = await self.http.post(
            url=url, json={"title": title, "desp": body, "tags": tags}
        )
        await self._read_response(rep, "serverchan3")
        log.debug(await rep.text())

    async def wxpusher(
        self, status_id: int, push_message: str | None, cfg: dict[str, Any]
    ) -> None:
        """WxPusher HTTP REST API 推送"""
        title, body, _ = self._build_push_payload(status_id, push_message)
        app_token = cfg.get("app_token", "")
        raw_uids = cfg.get("uids", [])
        raw_topics = cfg.get("topic_ids", [])
        uids = (
            [str(u).strip() for u in raw_uids if str(u).strip()]
            if isinstance(raw_uids, list)
            else [u.strip() for u in str(raw_uids).split(",") if u.strip()]
        )
        topic_items = (
            raw_topics if isinstance(raw_topics, list) else str(raw_topics).split(",")
        )
        topic_ids = [
            int(str(tid).strip()) for tid in topic_items if str(tid).strip().isdigit()
        ]
        if not app_token or (not uids and not topic_ids):
            raise ValueError(t("push.wxpusher_config_err"))
        payload: dict[str, Any] = {
            "appToken": app_token,
            "content": body,
            "summary": title,
            "contentType": 1,
            "uids": uids,
            "topicIds": topic_ids,
        }
        resp = await self.http.post(
            url=PUSH_WXPUSHER_URL,
            headers={"Content-Type": "application/json; charset=utf-8"},
            json=payload,
        )
        rep, _ = await self._read_response(resp, "wxpusher")
        log.info(t("push.result", result=(rep or {}).get("msg")))

    async def ntfy(
        self, status_id: int, push_message: str | None, cfg: dict[str, Any]
    ) -> None:
        """ntfy 推送通知"""
        title, body, _ = self._build_push_payload(status_id, push_message)
        api_url = str(cfg.get("api_url", PUSH_NTFY_DEFAULT_URL)).rstrip("/")
        topic = str(cfg.get("topic", "")).strip()
        if not topic:
            raise ValueError(t("push.ntfy_config_err"))
        encoded_title = (
            title
            if title.isascii()
            else f"=?utf-8?b?{base64.b64encode(title.encode('utf-8')).decode('ascii')}?="
        )
        req_headers: dict[str, str] = {
            "Title": encoded_title,
            "Priority": str(cfg.get("priority", "default")),
        }
        token = cfg.get("token", "")
        if token:
            req_headers["Authorization"] = f"Bearer {token}"
        resp = await self.http.post(
            url=f"{api_url}/{topic}",
            headers=req_headers,
            data=body.encode("utf-8"),
        )
        await self._read_response(resp, "ntfy")
        log.info(t("push.result", result=resp.status))

    async def send_to_target(
        self, target_name: str, status: int, push_message: str | None
    ) -> bool:
        """Dispatch a formatted message to a single named push target."""
        target_cfg = self.get_targets().get(target_name)
        if not isinstance(target_cfg, dict):
            log.warning(t("push.server_err", name=target_name))
            return False

        provider = str(target_cfg.get("type") or "").strip()
        func = getattr(self, provider, None)
        if not func or not callable(func):
            log.warning(t("push.server_err", name=provider or target_name))
            return False

        log.debug(t("push.service_name", name=f"{target_name} ({provider})"))
        sanitized = self.msg_replace(push_message)
        try:
            if inspect.iscoroutinefunction(func):
                res = await func(status, sanitized, target_cfg)
            else:
                res = func(status, sanitized, target_cfg)
        except Exception as e:
            log.warning(t("push.exec_fail", name=target_name, error=str(e)))
            return False

        if res is False or (provider == "ifttt" and res == 0):
            return False
        log.info(t("push.exec_done", name=target_name))
        return True

    async def dispatch_results(self, results: list[AccountRunResult]) -> int:
        """Route per-account execution results to configured push targets."""
        if not is_push_enabled() or not results:
            return 0

        cfg = self.get_cfg()
        error_only = bool(cfg.get("error_only", False))
        merge = bool(cfg.get("merge", True))
        default_targets = [
            str(item).strip()
            for item in (cfg.get("default") or [])
            if str(item).strip()
        ]

        if merge:
            buckets: dict[str, list[AccountRunResult]] = {}
            for res in results:
                resolved = (
                    default_targets
                    if res.push_targets is None
                    else [str(x).strip() for x in res.push_targets if str(x).strip()]
                )
                for target_name in dict.fromkeys(resolved):
                    buckets.setdefault(target_name, []).append(res)

            if not buckets:
                return 0

            started = False
            all_ok = True
            for target_name, items in buckets.items():
                target_status = _aggregate_status([item.status for item in items])
                if error_only and target_status == StatusCode.SUCCESS:
                    continue
                if not started:
                    log.info(t("push.execution_start"))
                    started = True
                if not await self.send_to_target(
                    target_name, target_status, _format_bucket_message(items)
                ):
                    all_ok = False
            return 0 if all_ok else 1

        started = False
        all_ok = True
        for res in results:
            if error_only and res.status == StatusCode.SUCCESS:
                continue
            resolved = (
                default_targets
                if res.push_targets is None
                else [str(x).strip() for x in res.push_targets if str(x).strip()]
            )
            for target_name in dict.fromkeys(resolved):
                if not started:
                    log.info(t("push.execution_start"))
                    started = True
                if not await self.send_to_target(
                    target_name, res.status, f"【{res.name}】\n{res.message}"
                ):
                    all_ok = False
        return 0 if all_ok else 1

    async def push(
        self,
        status: int,
        push_message: str | None,
        targets: list[str] | None = None,
    ) -> int:
        if not is_push_enabled():
            return 0
        cfg = self.get_cfg()
        if cfg.get("error_only", False) and status == StatusCode.SUCCESS:
            return 0

        raw_targets = targets if targets is not None else (cfg.get("default") or [])
        resolved = list(
            dict.fromkeys(
                str(name).strip() for name in raw_targets if str(name).strip()
            )
        )
        if not resolved:
            return 0

        log.info(t("push.execution_start"))
        all_ok = True
        for target_name in resolved:
            if not await self.send_to_target(target_name, status, push_message):
                all_ok = False
        return 0 if all_ok else 1


async def async_push(
    status: int,
    push_message: str | None,
    targets: list[str] | None = None,
) -> int:
    return await PushHandler().push(status, push_message, targets=targets)


async def dispatch_push(results: list[AccountRunResult]) -> int:
    return await PushHandler().dispatch_results(results)


# Export async_push as push for callers using await
push = async_push

if __name__ == "__main__":
    asyncio.run(async_push(0, f"推送验证{int(time.time())}"))
