import asyncio
import json
from contextlib import suppress
from typing import Any

import aiohttp
from cachetools import TTLCache
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from . import log, t
from .constants import (
    ASYNC_TIMEOUT,
    CACHE_MAX_SIZE,
    CACHE_TTL,
    CONNECTOR_LIMIT,
    CONNECTOR_LIMIT_PER_HOST,
    DNS_SERVERS,
    RETRY_INTERVAL,
    RETRY_TIMES,
)


class MockResponse:
    """模拟 aiohttp.ClientResponse 用于缓存返回"""

    def __init__(self, data: Any, status: int = 200, url: str = ""):
        self._data = data
        self._body: str | None = None
        self.url = url
        self.status = status
        self.headers: dict[str, str] = {}

    async def json(self, **kwargs: Any) -> Any:
        return self._data

    async def text(self, **kwargs: Any) -> str | None:
        if self._body is None:
            try:
                self._body = json.dumps(
                    self._data, separators=(",", ":"), ensure_ascii=False
                )
            except Exception:
                self._body = str(self._data)
        return self._body

    async def read(self) -> bytes:
        text = await self.text()
        # text may be None according to annotation; ensure bytes are returned
        return (text or "").encode("utf-8")

    async def __aenter__(self) -> "MockResponse":
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None


class HttpClient:
    """异步API客户端，支持连接池、缓存和智能重试"""

    def __init__(self) -> None:
        self.session: aiohttp.ClientSession | None = None
        self._session_loop: asyncio.AbstractEventLoop | None = None
        # Cache key: tuple(url, params_freeze, auth_scope_freeze) -> Any
        self.cache: TTLCache[tuple[str, Any, Any], Any] = TTLCache(
            maxsize=CACHE_MAX_SIZE, ttl=CACHE_TTL
        )
        self.request_count = 0
        self.cache_hits = 0

    def _is_session_usable(self) -> bool:
        """Return True if session exists, is open, and belongs to the running loop."""
        if not self.session or self.session.closed:
            return False
        if self._session_loop is None or self._session_loop.is_closed():
            return False
        try:
            return self._session_loop is asyncio.get_running_loop()
        except RuntimeError:
            return False

    @staticmethod
    def _freeze(value: Any) -> Any:
        """Convert nested request args into a hashable canonical form."""
        if isinstance(value, dict):
            return tuple(
                sorted((str(k), HttpClient._freeze(v)) for k, v in value.items())
            )
        if isinstance(value, (list, tuple, set)):
            return tuple(HttpClient._freeze(v) for v in value)
        return value

    def _build_cache_key(self, url: str, **kwargs: Any) -> tuple[str, Any, Any]:
        params = kwargs.get("params") or {}
        headers: dict[str, str] = kwargs.get("headers") or {}
        lower_headers = {k.lower(): v for k, v in headers.items()}
        auth_scope = {
            "cookie": lower_headers.get("cookie") or "",
            "authorization": lower_headers.get("authorization") or "",
        }
        combo_token = lower_headers.get("x-rpc-combo_token")
        if combo_token:
            auth_scope["combo_token"] = combo_token
        return url, self._freeze(params), self._freeze(auth_scope)

    async def __aenter__(self) -> "HttpClient":
        """异步上下文管理器入口"""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """异步上下文管理器出口"""
        await self.close()

    async def initialize(self) -> None:
        """初始化会话和连接池"""
        if self._is_session_usable():
            return

        resolver = None
        try:
            resolver = aiohttp.AsyncResolver(nameservers=DNS_SERVERS)
        except Exception:
            log.warning(t("system.dns_fail"))

        connector = aiohttp.TCPConnector(
            limit=CONNECTOR_LIMIT,
            limit_per_host=CONNECTOR_LIMIT_PER_HOST,
            ttl_dns_cache=300,
            resolver=resolver,
        )
        timeout = aiohttp.ClientTimeout(total=ASYNC_TIMEOUT)

        def json_serializer(x: Any) -> str:
            return json.dumps(x, separators=(",", ":"), ensure_ascii=False)

        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers={"Accept": "application/json, text/plain, */*"},
            json_serialize=json_serializer,
            trust_env=True,
        )
        self._session_loop = asyncio.get_running_loop()
        log.debug(t("system.client_init"))

    async def close(self) -> None:
        """关闭会话"""
        if self.session:
            if not self.session.closed and self._is_session_usable():
                await self.session.close()
            self.session = None
            self._session_loop = None
            log.debug(t("system.client_close"))

        rate = self.cache_hits / max(self.request_count, 1) * 100
        log.info(
            t(
                "system.client_stats",
                count=self.request_count,
                hits=self.cache_hits,
                rate=f"{rate:.1f}",
            )
        )

    async def request(self, method: str, url: str, **kwargs: Any) -> Any:
        """发送HTTP请求，支持缓存和重试"""
        self.request_count += 1
        use_cache = kwargs.pop("use_cache", True)
        cache_key = None

        # 检查缓存（仅GET请求）
        if method.upper() == "GET" and use_cache:
            cache_key = self._build_cache_key(url, **kwargs)
        if cache_key is not None and cache_key in self.cache:
            self.cache_hits += 1
            log.debug(t("system.cache_hit", url=url))
            return MockResponse(self.cache[cache_key], url=url)

        if not self._is_session_usable():
            await self.initialize()

        # Local alias to help the type checker know session is not None
        session = self.session
        if session is None:
            # Defensive: if initialization failed unexpectedly, return None
            return None

        try:
            async for attempt in AsyncRetrying(
                retry=retry_if_exception_type(
                    (aiohttp.ClientError, asyncio.TimeoutError)
                ),
                stop=stop_after_attempt(RETRY_TIMES),
                wait=wait_exponential(multiplier=RETRY_INTERVAL, min=1, max=10),
                reraise=True,
            ):
                with attempt:
                    response = await session.request(method, url, **kwargs)

                    try:
                        await response.read()

                        if response.status == 200 and cache_key is not None:
                            with suppress(aiohttp.ClientError, ValueError):
                                if (
                                    "application/json"
                                    in response.headers.get("Content-Type", "").lower()
                                ):
                                    data = await response.json()
                                    if not (
                                        isinstance(data, dict)
                                        and data.get("retcode", 0) != 0
                                    ):
                                        self.cache[cache_key] = data

                        if response.status == 429:  # Rate limit
                            reset_time = response.headers.get("X-RateLimit-Reset")
                            log.warning(t("system.rate_limit", reset_time=reset_time))
                            if attempt.retry_state.attempt_number < RETRY_TIMES:
                                # Raise so tenacity backs off and retries transient 429s;
                                # on the final attempt return the 429 response for caller handling.
                                raise aiohttp.ClientError("Rate limited")
                            return response

                        return response

                    except Exception as e:
                        response.release()
                        log.debug(t("system.request_exception", error=str(e)))
                        raise e

        except Exception as e:
            if isinstance(e, aiohttp.ClientError):
                log.error(t("system.retry_fail", retry=RETRY_TIMES, url=url))
            else:
                log.error(t("system.request_exception", error=str(e)))
            raise e

        # 理论上不会走到这里（AsyncRetrying 至少会尝试一次），但加上让类型检查更安心
        raise RuntimeError("Request finished without returning a response")

    async def get(self, url: str, **kwargs: Any) -> Any:
        """发送GET请求"""
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> Any:
        """发送POST请求"""
        return await self.request("POST", url, **kwargs)

    def clear_cache(self, include_public: bool = True) -> None:
        """Clear cached HTTP GET responses.

        When ``include_public`` is False, retain unauthenticated (public) entries
        whose cache scope contains no cookie, authorization, or combo token.
        """
        if include_public:
            self.cache.clear()
        else:
            public_scope = self._freeze({"cookie": "", "authorization": ""})
            for key in [k for k in self.cache if k[2] != public_scope]:
                self.cache.pop(key, None)
        log.debug(t("system.cache_cleared"))

    def clear_cookies(self) -> None:
        """清空会话Cookie"""
        if self.session:
            self.session.cookie_jar.clear()
        log.debug(t("system.cookies_cleared"))


# Export global instance
http: HttpClient = HttpClient()
