from enum import IntEnum
from typing import Final

# =============================================================================
# Functional Constants (System, Env & Network)
# =============================================================================
ASYNC_TIMEOUT: Final[int] = 30
RETRY_TIMES: Final[int] = 3
RETRY_INTERVAL: Final[float] = 1.0

# Cache
CACHE_MAX_SIZE: Final[int] = 100
CACHE_TTL: Final[int] = 300  # 5 minutes

# Connection Pool
CONNECTOR_LIMIT: Final[int] = 100
CONNECTOR_LIMIT_PER_HOST: Final[int] = 20

# DNS
DNS_SERVERS: Final[list[str]] = [
    "223.5.5.5",  # AliDNS
    "119.29.29.29",  # DNSPod
    "8.8.8.8",  # Google
    "1.1.1.1",  # Cloudflare
]

# Rate-limit & anti-bot delay ranges (seconds)
DELAY_SIGN_RANGE: Final[tuple[int, int]] = (2, 8)
DELAY_BBS_RANGE: Final[tuple[int, int]] = (3, 8)
DELAY_ACCOUNT_RANGE: Final[tuple[int, int]] = (3, 10)
DELAY_CLOUD_RETRY_RANGE: Final[tuple[int, int]] = (3, 6)
DELAY_CAPTCHA_RETRY_RANGE: Final[tuple[int, int]] = (6, 15)
DELAY_REWARD_RETRY_SECONDS: Final[int] = 5
DELAY_RATE_LIMIT_SECONDS: Final[int] = 10


class EnvVar:
    """Centralized runtime & Pydantic environment variable names."""

    PREFIX: Final[str] = "HOYO_ASSISTANT_"
    CLI_OUTPUT: Final[str] = "HOYO_ASSISTANT_CLI_OUTPUT"
    LANGUAGE: Final[str] = "HOYO_ASSISTANT_LANGUAGE"
    LANG_FALLBACK: Final[str] = "LANG"
    LOG_DIR: Final[str] = "HOYO_ASSISTANT_LOG_DIR"
    LOG_ROTATION: Final[str] = "HOYO_ASSISTANT_LOG_ROTATION"
    LOG_RETENTION: Final[str] = "HOYO_ASSISTANT_LOG_RETENTION"
    LOG_CONSOLE_ENABLE: Final[str] = "HOYO_ASSISTANT_LOG_CONSOLE_ENABLE"
    LOG_FILE_ENABLE: Final[str] = "HOYO_ASSISTANT_LOG_FILE_ENABLE"
    LOG_LEVEL: Final[str] = "HOYO_ASSISTANT_LOG_LEVEL"
    PUSH_ENABLE: Final[str] = "HOYO_ASSISTANT_PUSH__ENABLE"


# =============================================================================
# Status & API Return Code Contracts
# =============================================================================
class StatusCode(IntEnum):
    """Shared task status contract across run and push modules."""

    SUCCESS = 0
    FAILURE = 1
    PARTIAL_FAILURE = 2
    CAPTCHA_TRIGGERED = 3


class RetCode(IntEnum):
    """Common MiYoUShe / HoYoLAB API return codes."""

    OK = 0
    UNAUTHORIZED = -100
    QR_EXPIRED = -106
    STOKEN_EXPIRED_V2 = -3260
    ALREADY_SIGNED_IN = -5003
    CAPTCHA_TRIGGERED = 1034


# =============================================================================
# Business Constants (Game, Client & BBS Protocol)
# =============================================================================
# Salt
MIHOYOBBS_SALT: Final[str] = "9c7b896d7483e9070b27c55f1959c4d5"
MIHOYOBBS_SALT_WEB: Final[str] = "4751cb5557bfad5e249e58462c39fb0a"
MIHOYOBBS_SALT_X6: Final[str] = "t0qEgfub6cvueAPgR5m9aQWWVciEer7v"
MIHOYOBBS_SALT_PASSPORT: Final[str] = "JwYDpKvLj6MrMqqYU6jTKF17KNO2PXoS"

MIHOYOBBS_APP_ID: Final[str] = "bll8iq97cem8"
MIHOYOBBS_VERIFY_KEY: Final[str] = MIHOYOBBS_APP_ID
MIHOYOBBS_VERSION: Final[str] = "2.117.0"
MIHOYOBBS_PASSPORT_VERSION: Final[str] = "2.44.0"

# Client protocol headers & defaults
MIHOYOBBS_CLIENT_TYPE: Final[str] = "2"  # 1: ios, 2: android
MIHOYOBBS_CLIENT_TYPE_WEB: Final[str] = "5"  # 4: pc web, 5: mobile web
MIHOYOBBS_CHANNEL: Final[str] = "miyousheluodi"
MIHOYOBBS_SYS_VERSION: Final[str] = "12"
MIHOYOBBS_X_REQUESTED_WITH: Final[str] = "com.mihoyo.hyperion"
MIHOYOBBS_ACCEPT_LANGUAGE: Final[str] = "zh-CN,en-US;q=0.8"
MIHOYOBBS_APP_UA: Final[str] = "okhttp/4.9.3"
OS_CLOUD_APP_UA: Final[str] = "okhttp/4.10.0"
DESKTOP_BROWSER_UA: Final[str] = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

DEFAULT_DEVICE_NAME: Final[str] = "OnePlus Ace 5 Pro"
DEFAULT_DEVICE_MODEL: Final[str] = "PKR110"
DEFAULT_OS_LANG: Final[str] = "zh-cn"

# Origins & Referers
ORIGIN_MIHOYO_WEBSTATIC: Final[str] = "https://webstatic.mihoyo.com"
ORIGIN_MIHOYO_ACT: Final[str] = "https://act.mihoyo.com"
REFERER_MIHOYO_APP: Final[str] = "https://app.mihoyo.com"
BBS_API_HOST: Final[str] = "bbs-api.miyoushe.com"

# Built-in community forum table (fallback; unknown IDs dynamically sync via API_BBS_GAME_LIST)
MIHOYOBBS_POST_TYPES: Final[dict[int, dict[str, str]]] = {
    1: {"id": "1", "forumId": "1", "name": "崩坏3"},
    2: {"id": "2", "forumId": "26", "name": "原神"},
    3: {"id": "3", "forumId": "30", "name": "崩坏2"},
    4: {"id": "4", "forumId": "37", "name": "未定事件簿"},
    5: {"id": "5", "forumId": "34", "name": "大别野"},
    6: {"id": "6", "forumId": "52", "name": "崩坏：星穹铁道"},
    8: {"id": "8", "forumId": "57", "name": "绝区零"},
    9: {"id": "9", "forumId": "948", "name": "崩坏：因缘精灵"},
    10: {"id": "10", "forumId": "950", "name": "星布谷地"},
}

# Game Info
GAME_INFO_ID_TO_NAME: Final[dict[str, str]] = {
    "bh2_cn": "崩坏2",
    "bh3_cn": "崩坏3",
    "nxx_cn": "未定事件簿",
    "hk4e_cn": "原神",
    "hkrpg_cn": "崩坏：星穹铁道",
    "nap_cn": "绝区零",
    "abc_cn": "崩坏：因缘精灵",
    "hyg_cn": "星布谷地",
}

GAME_INFO_ID_TO_CONFIG: Final[dict[str, str]] = {
    "bh2_cn": "honkai2",
    "bh3_cn": "honkai3rd",
    "nxx_cn": "tears_of_themis",
    "hk4e_cn": "genshin",
    "hkrpg_cn": "honkai_sr",
    "nap_cn": "zzz",
    "abc_cn": "hna",
    "hyg_cn": "planet",
}

# Supported built-in cloud game config keys
CN_CLOUD_GAME_KEYS: Final[tuple[str, ...]] = ("genshin", "zzz")
OS_CLOUD_GAME_KEYS: Final[tuple[str, ...]] = ("genshin", "zzz")

# Values for Headers Template (used below)
_UA_TEMPLATE = (
    "Mozilla/5.0 (Linux; Android 12; Unspecified Device) AppleWebKit/537.36 (KHTML, like Gecko) "
    f"Version/4.0 Chrome/103.0.5060.129 Mobile Safari/537.36 miHoYoBBS/{MIHOYOBBS_VERSION}"
)

# Headers Template
DEFAULT_HEADERS: Final[dict[str, str]] = {
    "Accept": "application/json, text/plain, */*",
    "DS": "",
    "x-rpc-channel": MIHOYOBBS_CHANNEL,
    "Origin": ORIGIN_MIHOYO_WEBSTATIC,
    "x-rpc-app_version": MIHOYOBBS_VERSION,
    "User-Agent": _UA_TEMPLATE,
    "x-rpc-client_type": MIHOYOBBS_CLIENT_TYPE_WEB,
    "Referer": "",
    "Accept-Encoding": "gzip, deflate",
    "Accept-Language": MIHOYOBBS_ACCEPT_LANGUAGE,
    "X-Requested-With": MIHOYOBBS_X_REQUESTED_WITH,
    "Cookie": "",
    "x-rpc-device_id": "",
}

# API Constants
# Base URLs
API_BBS: Final[str] = f"https://{BBS_API_HOST}"
API_WEB: Final[str] = "https://api-takumi.mihoyo.com"
API_PASSPORT: Final[str] = "https://passport-api.mihoyo.com"
API_CLOUD_GENSHIN: Final[str] = "https://api-cloudgame.mihoyo.com"
API_CLOUD_ZZZ: Final[str] = "https://cg-nap-api.mihoyo.com"
API_ZZZ_WEB: Final[str] = "https://act-nap-api.mihoyo.com"

# OS URLs
API_CLOUD_GENSHIN_OS: Final[str] = "https://sg-cg-api.hoyoverse.com"
API_OS_REFERER: Final[str] = "https://act.hoyolab.com/"

# QR Login & Cloud Game SDK constants (CN)
HK4E_CN_APP_ID: Final[str] = "4"
HK4E_CN_CHANNEL_ID: Final[str] = "1"
HK4E_CN_APP_KEY: Final[str] = "d0d3a7342df2026a70f650b907800111"
NAP_CN_APP_ID: Final[str] = "12"
QR_LOGIN_POLL_INTERVAL: Final[float] = 2.0
QR_LOGIN_DEFAULT_TIMEOUT: Final[int] = 120
QR_AUTO_PROMPT_TIMEOUT: Final[int] = 10

API_QR_FETCH: Final[str] = (
    "https://hk4e-sdk.mihoyo.com/hk4e_cn/combo/panda/qrcode/fetch"
)
API_QR_QUERY: Final[str] = (
    "https://hk4e-sdk.mihoyo.com/hk4e_cn/combo/panda/qrcode/query"
)
API_HK4E_COMBO_LOGIN: Final[str] = (
    "https://hk4e-sdk.mihoyo.com/hk4e_cn/combo/granter/login/v2/login"
)

# User & Token APIs
API_ACCOUNT_INFO: Final[str] = f"{API_WEB}/binding/api/getUserGameRolesByCookie"
API_PASSPORT_EXCHANGE: Final[str] = f"{API_PASSPORT}/account/ma-cn-session/app/exchange"
API_PASSPORT_GET_TOKEN_BY_GAME_TOKEN: Final[str] = (
    f"{API_WEB}/account/ma-cn-session/app/getTokenByGameToken"
)
API_BBS_GET_COOKIE_TOKEN: Final[str] = (
    f"{API_WEB}/auth/api/getCookieAccountInfoBySToken"
)

# BBS Tasks & Game List
API_BBS_GAME_LIST: Final[str] = f"{API_BBS}/apihub/wapi/getGameList"
API_BBS_TASKS_LIST: Final[str] = f"{API_BBS}/apihub/wapi/getUserMissionsState"
API_BBS_SIGN: Final[str] = f"{API_BBS}/apihub/app/api/signIn"

# Game Check-in
CN_GAME_LANG: Final[str] = "zh-cn"
API_CN_GAME_CHECKIN_REWARDS: Final[str] = (
    f"{API_WEB}/event/luna/home?lang={CN_GAME_LANG}"
)
API_CN_GAME_IS_SIGN: Final[str] = f"{API_WEB}/event/luna/info?lang={CN_GAME_LANG}"
API_CN_GAME_SIGN: Final[str] = f"{API_WEB}/event/luna/sign"

# Cloud Games - CN
API_CLOUD_GENSHIN_SIGN: Final[str] = f"{API_CLOUD_GENSHIN}/hk4e_cg_cn/wallet/wallet/get"
API_CLOUD_ZZZ_SIGN: Final[str] = f"{API_CLOUD_ZZZ}/nap_cn/cg/wallet/wallet/get"

# Cloud Games - OS
API_CLOUD_GENSHIN_SIGN_OS: Final[str] = (
    f"{API_CLOUD_GENSHIN_OS}/hk4e_global/cg/wallet/wallet/get"
)
API_CLOUD_ZZZ_SIGN_OS: Final[str] = (
    f"{API_CLOUD_GENSHIN_OS}/nap_global/cg/wallet/wallet/get"
)

# ZZZ Check-in
API_ZZZ_GAME_CHECKIN_REWARDS: Final[str] = (
    f"{API_ZZZ_WEB}/event/luna/zzz/home?lang={CN_GAME_LANG}"
)
API_ZZZ_GAME_IS_SIGN: Final[str] = (
    f"{API_ZZZ_WEB}/event/luna/zzz/info?lang={CN_GAME_LANG}"
)
API_ZZZ_GAME_SIGN: Final[str] = f"{API_ZZZ_WEB}/event/luna/zzz/sign"

# CN Game Signin Referers (Base)
REF_GENSHIN_SIGN: Final[str] = (
    f"{ORIGIN_MIHOYO_WEBSTATIC}/bbs/event/signin-ys/index.html"
)
REF_BH2_SIGN: Final[str] = f"{ORIGIN_MIHOYO_WEBSTATIC}/bbs/event/signin/bh2/index.html"
REF_BH3_SIGN: Final[str] = f"{ORIGIN_MIHOYO_WEBSTATIC}/bbs/event/signin/bh3/index.html"
REF_NXX_SIGN: Final[str] = f"{ORIGIN_MIHOYO_WEBSTATIC}/bbs/event/signin/nxx/index.html"

# OS Game Signin Base URL
API_OS_ACT: Final[str] = "https://sg-hk4e-api.hoyolab.com/event/sol"
API_OS_ACT_LUNA: Final[str] = "https://sg-public-api.hoyolab.com/event/luna/os"
API_OS_ACT_HSR: Final[str] = API_OS_ACT_LUNA
API_OS_ACT_HI3: Final[str] = "https://sg-public-api.hoyolab.com/event/mani"
API_OS_ACT_ZZZ: Final[str] = "https://sg-act-nap-api.hoyolab.com/event/luna/zzz/os"

# Activity IDs (Flattened)
# CN
ACT_ID_CN_HONKAI2: Final[str] = "e202203291431091"
ACT_ID_CN_HONKAI3RD: Final[str] = "e202306201626331"
ACT_ID_CN_TEARS_OF_THEMIS: Final[str] = "e202202251749321"
ACT_ID_CN_GENSHIN: Final[str] = "e202311201442471"
ACT_ID_CN_HONKAI_SR: Final[str] = "e202304121516551"
ACT_ID_CN_ZZZ: Final[str] = "e202406242138391"

# OS
ACT_ID_OS_GENSHIN: Final[str] = "e202102251931481"
ACT_ID_OS_HONKAI3RD: Final[str] = "e202110291205111"
ACT_ID_OS_TEARS_OF_THEMIS: Final[str] = "e202202281857121"
ACT_ID_OS_HONKAI_SR: Final[str] = "e202303301540311"
ACT_ID_OS_ZZZ: Final[str] = "e202406031448091"

OS_ACT_ID_TO_SIGNGAME: Final[dict[str, str]] = {
    ACT_ID_OS_GENSHIN: "hk4e",
    ACT_ID_OS_HONKAI3RD: "bh3",
    ACT_ID_OS_TEARS_OF_THEMIS: "nxx",
    ACT_ID_OS_HONKAI_SR: "hkrpg",
    ACT_ID_OS_ZZZ: "zzz",
}

# Push Provider Default URLs
PUSH_PUSHME_URL: Final[str] = "https://push.i-i.me/"
PUSH_NTFY_DEFAULT_URL: Final[str] = "https://ntfy.sh"

# Cookie Field Ordering & Key Aliases
COOKIE_ORDER: Final[tuple[str, ...]] = (
    "ltoken_v2",
    "ltuid_v2",
    "ltmid_v2",
    "cookie_token_v2",
    "account_id_v2",
    "account_mid_v2",
    "ltoken",
    "ltuid",
    "account_id",
    "cookie_token",
    "login_uid",
    "stuid",
    "stoken",
    "mid",
)
COOKIE_UID_KEYS: Final[tuple[str, ...]] = (
    "stuid",
    "account_id_v2",
    "ltuid_v2",
    "account_id",
    "ltuid",
    "login_uid",
)
COOKIE_MID_KEYS: Final[tuple[str, ...]] = ("mid", "account_mid_v2", "ltmid_v2")
COOKIE_V2_TO_V1_ALIASES: Final[tuple[tuple[str, str], ...]] = (
    ("ltoken_v2", "ltoken"),
    ("ltuid_v2", "ltuid"),
    ("account_id_v2", "account_id"),
    ("cookie_token_v2", "cookie_token"),
)
