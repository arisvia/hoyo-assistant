import asyncio
import base64
import hashlib
import hmac
import inspect
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Final, cast
from urllib.parse import quote_plus

from . import StatusCode, http, log, setting, t

# =============================================================================
# Push Provider Endpoint & Branding Constants
# =============================================================================
PUSH_APP_NAME: Final[str] = "HoyoAssistant"
PUSH_REPO_URL: Final[str] = "https://github.com/arisvia/hoyo-assistant"
PUSH_FTQQ_BASE: Final[str] = "https://sctapi.ftqq.com"
PUSH_PUSHPLUS_URL: Final[str] = "https://www.pushplus.plus/send"
PUSH_PUSHME_URL: Final[str] = "https://push.i-i.me/"
PUSH_SMTP_BG_API: Final[str] = "https://www.loliapi.com/acg/pc/"
PUSH_WECOM_TOKEN_URL: Final[str] = "https://qyapi.weixin.qq.com/cgi-bin/gettoken"
PUSH_WECOM_SEND_URL: Final[str] = "https://qyapi.weixin.qq.com/cgi-bin/message/send"
PUSH_BARK_ICON_BASE: Final[str] = "https://cdn.jsdelivr.net/gh/tanmx/pic@main/mihoyo"
PUSH_IFTTT_BASE: Final[str] = "https://maker.ifttt.com/trigger"
PUSH_QMSG_BASE: Final[str] = "https://qmsg.zendee.cn/send"
PUSH_WXPUSHER_URL: Final[str] = "https://wxpusher.zjiecode.com/api/send/message"
PUSH_NTFY_DEFAULT_URL: Final[str] = "https://ntfy.sh"

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


class PushHandler:
    def __init__(self) -> None:
        self.http = http  # Use global async http

    def get_cfg(self) -> dict[str, Any]:
        """Get the push dictionary from the global config."""
        return cast(dict[str, Any], setting.config.get("push", {}))

    def get_channels(self) -> dict[str, Any]:
        """Get configured channels mapping from push config."""
        channels = self.get_cfg().get("channels")
        return cast(dict[str, Any], channels) if isinstance(channels, dict) else {}

    def get_val(self, section: str, key: str, default: Any = None) -> Any:
        """Get a value from a specific push channel configuration."""
        sec_cfg = self.get_channels().get(section)
        if isinstance(sec_cfg, dict):
            return sec_cfg.get(key, default)
        return default

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

    async def telegram(self, status_id: int, push_message: str | None) -> None:
        _, _, full_text = self._build_push_payload(status_id, push_message)
        api_url = self.get_val("telegram", "api_url", "api.telegram.org")
        bot_token = self.get_val("telegram", "bot_token", "")
        chat_id = self.get_val("telegram", "chat_id", "")
        url = f"https://{api_url}/bot{bot_token}/sendMessage"
        await self.http.post(url=url, data={"chat_id": chat_id, "text": full_text})

    async def ftqq(self, status_id: int, push_message: str | None) -> None:
        """Server酱推送，具体推送位置在server酱后台配置"""
        title, body, _ = self._build_push_payload(status_id, push_message)
        sendkey = self.get_val("ftqq", "sendkey", "")
        await self.http.post(
            url=f"{PUSH_FTQQ_BASE}/{sendkey}.send",
            data={"title": title, "desp": body},
        )

    async def pushplus(self, status_id: int, push_message: str | None) -> None:
        """PushPlus推送"""
        title, body, _ = self._build_push_payload(status_id, push_message)
        token = self.get_val("pushplus", "token", "")
        topic = self.get_val("pushplus", "topic", "")
        await self.http.post(
            url=PUSH_PUSHPLUS_URL,
            data={
                "token": token,
                "title": title,
                "content": body,
                "topic": topic,
            },
        )

    async def pushme(self, status_id: int, push_message: str | None) -> None:
        """PushMe推送"""
        pushme_key = self.get_val("pushme", "token", "")
        if not pushme_key:
            log.error(t("push.pushme_key_missing"))
            return
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
        url = self.get_val("pushme", "url", PUSH_PUSHME_URL)
        response = await self.http.post(url=url, data=data)
        log.debug(f"PushMe 响应状态码: {response.status}")
        text = await response.text()
        log.debug(f"PushMe 响应内容: {text}")
        if response.status == 200 and text == "success":
            log.info(t("push.pushme_success"))
        else:
            log.error(t("push.pushme_fail", status=response.status, text=text))

    async def cqhttp(self, status_id: int, push_message: str | None) -> None:
        """OneBot V11 (CqHttp) 协议推送"""
        qq = self.get_val("cqhttp", "qq", None)
        group = self.get_val("cqhttp", "group", None)

        if qq and group:
            log.error(t("push.cqhttp_config_err"))
            return

        _, _, full_text = self._build_push_payload(status_id, push_message)
        data: dict[str, Any] = {"message": full_text}
        if qq:
            data["user_id"] = int(qq)
        if group:
            data["group_id"] = int(group)

        url = self.get_val("cqhttp", "url", "")
        await self.http.post(url=url, json=data)

    async def smtp(self, status_id: int, push_message: str | None) -> None:
        """SMTP 电子邮件推送"""
        import smtplib
        from email.mime.text import MIMEText

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
        background = self.get_val("smtp", "background", False)
        if background:
            image_url = await get_background_url()

        def send_sync() -> None:
            try:
                with open("assets/email_example.html", encoding="utf-8") as f:
                    email_template = f.read()
            except FileNotFoundError:
                email_template = "{title}<br>{message}<br>{background_info}"

            message = email_template.format(
                title=title,
                message=body.replace("\n", "<br/>"),
                background_image=get_background_img_html(image_url),
                background_info=get_background_img_info(image_url),
            )
            msg_mime = MIMEText(message, "html", "utf-8")
            subject = self.get_val("smtp", "subject", "")
            toaddr = self.get_val("smtp", "toaddr", "")
            fromaddr = self.get_val("smtp", "fromaddr", "")
            msg_mime["Subject"] = subject
            msg_mime["To"] = toaddr
            msg_mime["From"] = f"{subject}<{fromaddr}>"

            mailhost = self.get_val("smtp", "mailhost", "")
            port = int(self.get_val("smtp", "port", 465))
            username = self.get_val("smtp", "username", "")
            password = self.get_val("smtp", "password", "")

            server: smtplib.SMTP
            ssl_enable = self.get_val("smtp", "ssl_enable", True)
            if ssl_enable:
                server = smtplib.SMTP_SSL(mailhost, port)
            else:
                server = smtplib.SMTP(mailhost, port)
            server.login(username, password)
            server.sendmail(fromaddr, toaddr, msg_mime.as_string())
            server.close()
            log.info(t("push.smtp_success"))

        await asyncio.to_thread(send_sync)

    async def wecom(self, status_id: int, push_message: str | None) -> None:
        """企业微信推送"""
        secret = self.get_val("wecom", "secret", "")
        corpid = self.get_val("wecom", "wechat_id", "")
        touser = self.get_val("wecom", "touser", "@all")

        _, _, full_text = self._build_push_payload(status_id, push_message)
        token_resp = await self.http.post(
            url=f"{PUSH_WECOM_TOKEN_URL}?corpid={corpid}&corpsecret={secret}",
            data="",
        )
        token_data = await token_resp.json()
        push_token = token_data.get("access_token")
        if not push_token:
            raise ValueError(
                f"WeCom token fetch failed: {token_data.get('errmsg', token_data)}"
            )
        push_data = {
            "agentid": self.get_val("wecom", "agentid", ""),
            "msgtype": "text",
            "touser": touser,
            "text": {"content": full_text},
            "safe": 0,
        }
        await self.http.post(
            f"{PUSH_WECOM_SEND_URL}?access_token={push_token}",
            json=push_data,
        )

    async def wecomrobot(self, status_id: int, push_message: str | None) -> None:
        """企业微信机器人"""
        _, _, full_text = self._build_push_payload(status_id, push_message)
        url = self.get_val("wecomrobot", "url", "")
        mobile = self.get_val("wecomrobot", "mobile", [])
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
        rep = await resp.json()
        log.info(t("push.result", result=rep.get("errmsg")))

    async def pushdeer(self, status_id: int, push_message: str | None) -> None:
        """PushDeer推送"""
        title, body, _ = self._build_push_payload(status_id, push_message)
        api_url = str(self.get_val("pushdeer", "api_url", "")).rstrip("/")
        token = self.get_val("pushdeer", "token", "")
        await self.http.get(
            url=f"{api_url}/message/push",
            params={
                "pushkey": token,
                "text": title,
                "desp": str(body).replace("\r\n", "\r\n\r\n"),
                "type": "markdown",
            },
            use_cache=False,
        )

    async def dingrobot(self, status_id: int, push_message: str | None) -> None:
        """钉钉群机器人推送"""
        _, _, full_text = self._build_push_payload(status_id, push_message)
        api_url = self.get_val("dingrobot", "webhook", "")
        secret = self.get_val("dingrobot", "secret", "")
        if secret:
            timestamp = str(round(time.time() * 1000))
            sign_string = f"{timestamp}\n{secret}"
            hmac_code = hmac.new(
                key=secret.encode("utf-8"),
                msg=sign_string.encode("utf-8"),
                digestmod=hashlib.sha256,
            ).digest()
            sign = quote_plus(base64.b64encode(hmac_code))
            api_url = f"{api_url}&timestamp={timestamp}&sign={sign}"

        resp = await self.http.post(
            url=api_url,
            headers={"Content-Type": "application/json; charset=utf-8"},
            json={"msgtype": "text", "text": {"content": full_text}},
        )
        rep = await resp.json()
        log.info(t("push.result", result=rep.get("errmsg")))

    async def feishubot(self, status_id: int, push_message: str | None) -> None:
        """飞书机器人(WebHook)，支持可选 secret 签名校验"""
        _, _, full_text = self._build_push_payload(status_id, push_message)
        api_url = self.get_val("feishubot", "webhook", "")
        secret = self.get_val("feishubot", "secret", "")
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
        rep = await resp.json()
        log.info(t("push.result", result=rep.get("msg")))

    async def bark(self, status_id: int, push_message: str | None) -> None:
        """Bark推送"""
        title, body, _ = self._build_push_payload(status_id, push_message)
        send_title = quote_plus(title)
        encoded_body = quote_plus(body)
        api_url = str(self.get_val("bark", "api_url", "")).rstrip("/")
        token = self.get_val("bark", "token", "")
        icon = self.get_val("bark", "icon", "")
        url = f"{api_url}/{token}/{send_title}/{encoded_body}"
        if icon:
            url = f"{url}?icon={PUSH_BARK_ICON_BASE}/{icon}.png"
        resp = await self.http.get(url=url, use_cache=False)
        rep = await resp.json()
        log.info(t("push.result", result=rep.get("message")))

    async def gotify(self, status_id: int, push_message: str | None) -> None:
        """Gotify推送"""
        title, body, _ = self._build_push_payload(status_id, push_message)
        api_url = str(self.get_val("gotify", "api_url", "")).rstrip("/")
        token = self.get_val("gotify", "token", "")
        priority = int(self.get_val("gotify", "priority", 0))
        resp = await self.http.post(
            url=f"{api_url}/message?token={token}",
            headers={"Content-Type": "application/json; charset=utf-8"},
            json={
                "title": title,
                "message": body,
                "priority": priority,
            },
        )
        rep = await resp.json()
        log.info(t("push.result", result=rep.get("errmsg")))

    async def ifttt(self, status_id: int, push_message: str | None) -> int:
        """IFTTT推送"""
        title, body, _ = self._build_push_payload(status_id, push_message)
        ifttt_event = self.get_val("ifttt", "event", "")
        ifttt_key = self.get_val("ifttt", "key", "")
        rep = await self.http.post(
            url=f"{PUSH_IFTTT_BASE}/{ifttt_event}/with/key/{ifttt_key}",
            headers={"Content-Type": "application/json; charset=utf-8"},
            json={"value1": title, "value2": body},
        )
        text = await rep.text()
        if "errors" in text:
            try:
                log.warning(t("push.ifttt_err", error=(await rep.json())["errors"]))
            except Exception:
                log.warning(t("push.ifttt_err", error=text))
            return 0
        log.info(t("push.ifttt_done"))
        return 1

    async def webhook(self, status_id: int, push_message: str | None) -> None:
        """Generic WebHook推送"""
        title, body, _ = self._build_push_payload(status_id, push_message)
        webhook_url = self.get_val("webhook", "url", "")
        resp = await self.http.post(
            url=webhook_url,
            headers={"Content-Type": "application/json; charset=utf-8"},
            json={"title": title, "message": body},
        )
        rep = await resp.json()
        log.info(t("push.result", result=rep.get("errmsg")))

    async def qmsg(self, status_id: int, push_message: str | None) -> None:
        """Qmsg酱推送"""
        _, _, full_text = self._build_push_payload(status_id, push_message)
        key = self.get_val("qmsg", "key", "")
        resp = await self.http.post(
            url=f"{PUSH_QMSG_BASE}/{key}",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={"msg": full_text},
        )
        rep = await resp.json()
        log.info(t("push.result", result=rep.get("reason")))

    async def discord(self, status_id: int, push_message: str | None) -> None:
        """Discord Webhook 推送"""
        title, body, _ = self._build_push_payload(status_id, push_message)
        webhook = self.get_val("discord", "webhook", "")
        avatar_url = str(self.get_val("discord", "avatar_url", "") or "")
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
        if rep.status != 204:
            log.warning(t("push.discord_err", error=await rep.text()))
        else:
            log.info(t("push.discord_success", status=rep.status))

    def wintoast(self, status_id: int, push_message: str | None) -> None:
        try:
            toast = __import__("win11toast").toast
            title, body, _ = self._build_push_payload(status_id, push_message)
            toast(app_id=PUSH_APP_NAME, title=title, body=body, icon="")
        except Exception:
            log.error(t("push.wintoast_err"))

    async def serverchan3(self, status_id: int, push_message: str | None) -> None:
        title, body, _ = self._build_push_payload(status_id, push_message)
        sendkey = self.get_val("serverchan3", "sendkey", "")
        match = re.match(r"sctp(\d+)t", sendkey)
        if match:
            num = match.group(1)
            url = f"https://{num}.push.ft07.com/send/{sendkey}.send"
        else:
            raise ValueError(t("push.serverchan3_invalid_key"))
        tags = self.get_val("serverchan3", "tags", "")
        rep = await self.http.post(
            url=url, json={"title": title, "desp": body, "tags": tags}
        )
        log.debug(await rep.text())

    async def wxpusher(self, status_id: int, push_message: str | None) -> None:
        """WxPusher HTTP REST API 推送"""
        title, body, _ = self._build_push_payload(status_id, push_message)
        app_token = self.get_val("wxpusher", "app_token", "")
        raw_uids = self.get_val("wxpusher", "uids", [])
        raw_topics = self.get_val("wxpusher", "topic_ids", [])
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
        rep = await resp.json()
        log.info(t("push.result", result=rep.get("msg")))

    async def ntfy(self, status_id: int, push_message: str | None) -> None:
        """ntfy 推送通知"""
        title, body, _ = self._build_push_payload(status_id, push_message)
        api_url = str(self.get_val("ntfy", "api_url", PUSH_NTFY_DEFAULT_URL)).rstrip(
            "/"
        )
        topic = str(self.get_val("ntfy", "topic", "")).strip()
        if not topic:
            raise ValueError(t("push.ntfy_config_err"))
        encoded_title = (
            title
            if title.isascii()
            else f"=?utf-8?b?{base64.b64encode(title.encode('utf-8')).decode('ascii')}?="
        )
        req_headers: dict[str, str] = {
            "Title": encoded_title,
            "Priority": str(self.get_val("ntfy", "priority", "default")),
        }
        token = self.get_val("ntfy", "token", "")
        if token:
            req_headers["Authorization"] = f"Bearer {token}"
        resp = await self.http.post(
            url=f"{api_url}/{topic}",
            headers=req_headers,
            data=body.encode("utf-8"),
        )
        log.info(t("push.result", result=resp.status))

    def _resolve_active_channels(self) -> list[str]:
        """Return explicit active channels, or auto-detect all configured channels."""
        cfg = self.get_cfg()
        explicit = cfg.get("active") or []
        if explicit:
            return [str(name) for name in explicit]
        channels = self.get_channels()
        return [name for name, val in channels.items() if isinstance(val, dict)]

    async def push(self, status: int, push_message: str | None) -> int:
        cfg = self.get_cfg()
        if not cfg.get("enable", False):
            return 0
        if cfg.get("error_only", False) and status == StatusCode.SUCCESS:
            return 0
        log.info(t("push.execution_start"))
        active_channels = self._resolve_active_channels()
        push_success = True
        for func_name in active_channels:
            func = getattr(self, func_name, None)
            if not func:
                log.warning(t("push.server_err", name=func_name))
                continue
            log.debug(t("push.service_name", name=func_name))
            try:
                if inspect.iscoroutinefunction(func):
                    await func(status, self.msg_replace(push_message))
                else:
                    func(status, self.msg_replace(push_message))
            except Exception as e:
                log.warning(t("push.exec_fail", name=func_name, error=str(e)))
                push_success = False
                continue
            log.info(t("push.exec_done", name=func_name))
        return 0 if push_success else 1


async def async_push(status: int, push_message: str | None) -> int:
    push_handler_instance = PushHandler()
    return await push_handler_instance.push(status, push_message)


# Export async_push as push for callers using await
push = async_push

if __name__ == "__main__":
    asyncio.run(async_push(0, f"推送验证{int(time.time())}"))
