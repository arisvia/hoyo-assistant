"""Unified v3 Pydantic configuration schema for HoyoAssistant."""

from typing import Annotated, Any, Final, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    Field,
    field_validator,
    model_validator,
)
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from .constants import (
    API_OS_ACT_LUNA,
    COOKIE_UID_KEYS,
    COOKIE_V2_TO_V1_ALIASES,
    DEFAULT_DEVICE_MODEL,
    DEFAULT_DEVICE_NAME,
    DEFAULT_OS_LANG,
    ORIGIN_MIHOYO_ACT,
    PUSH_NTFY_DEFAULT_URL,
    PUSH_PUSHME_URL,
    EnvVar,
)
from .tools import format_cookie, parse_cookie

CNGameId = Literal[
    "genshin",
    "honkai_sr",
    "zzz",
    "honkai3rd",
    "tears_of_themis",
    "honkai2",
]
OSGameId = Literal[
    "genshin",
    "honkai_sr",
    "zzz",
    "honkai3rd",
    "tears_of_themis",
]

PUSH_PROVIDER_NAMES: Final[frozenset[str]] = frozenset(
    {
        "telegram",
        "discord",
        "ftqq",
        "serverchan3",
        "pushplus",
        "pushme",
        "cqhttp",
        "smtp",
        "wecom",
        "wecomrobot",
        "pushdeer",
        "dingrobot",
        "feishubot",
        "bark",
        "gotify",
        "ifttt",
        "webhook",
        "qmsg",
        "wintoast",
        "wxpusher",
        "ntfy",
    }
)


class StrictConfigModel(BaseModel):
    """Strict sub-config model that rejects typos and unknown fields."""

    model_config = {"extra": "forbid"}


def _none_to_empty_dict(v: Any) -> Any:
    return {} if v is None else v


def _none_to_empty_list(v: Any) -> Any:
    return [] if v is None else v


def _coerce_to_str(v: Any) -> str:
    return "" if v is None else str(v)


def _coerce_str_list(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, str):
        return [item.strip() for item in v.split(",") if item.strip()]
    if isinstance(v, list):
        return [str(item).strip() for item in v if str(item).strip()]
    return [str(v).strip()]


def _coerce_int_list(v: Any) -> list[int]:
    if v is None:
        return []
    if isinstance(v, str):
        return [int(item.strip()) for item in v.split(",") if item.strip()]
    if isinstance(v, list):
        return [int(item) for item in v if str(item).strip()]
    return [int(v)]


def _coerce_account_push(v: Any) -> list[str] | None:
    """Normalize per-account push routing (`None`=default, `[]`=silent, `[...]`=targets)."""
    if v is None:
        return None
    if isinstance(v, bool):
        return None if v else []
    if isinstance(v, str):
        text = v.strip()
        lowered = text.lower()
        if lowered in {"", "false", "none", "off", "0"}:
            return []
        if lowered in {"true", "default"}:
            return None
        return [item.strip() for item in text.split(",") if item.strip()]
    if isinstance(v, list):
        return [str(item).strip() for item in v if str(item).strip()]
    return [str(v).strip()]


CoercedStr = Annotated[str, BeforeValidator(_coerce_to_str)]
CoercedStrList = Annotated[list[str], BeforeValidator(_coerce_str_list)]
CoercedIntList = Annotated[list[int], BeforeValidator(_coerce_int_list)]
AccountPushRef = Annotated[list[str] | None, BeforeValidator(_coerce_account_push)]


# ---------------------------------------------------------------------------
# Strongly-typed Named Push Target Models
# ---------------------------------------------------------------------------
class TelegramPushTarget(StrictConfigModel):
    type: Literal["telegram"]
    api_url: str = "api.telegram.org"
    bot_token: str = ""
    chat_id: CoercedStr = ""


class DiscordPushTarget(StrictConfigModel):
    type: Literal["discord"]
    webhook: str = ""
    avatar_url: str = ""


class FtqqPushTarget(StrictConfigModel):
    type: Literal["ftqq"]
    sendkey: str = ""


class ServerChan3PushTarget(StrictConfigModel):
    type: Literal["serverchan3"]
    sendkey: str = ""
    tags: str = ""


class PushPlusPushTarget(StrictConfigModel):
    type: Literal["pushplus"]
    token: str = ""
    topic: str = ""


class PushMePushTarget(StrictConfigModel):
    type: Literal["pushme"]
    token: str = ""
    url: str = PUSH_PUSHME_URL


class CqHttpPushTarget(StrictConfigModel):
    type: Literal["cqhttp"]
    url: str = ""
    qq: CoercedStr | None = None
    group: CoercedStr | None = None


class SmtpPushTarget(StrictConfigModel):
    type: Literal["smtp"]
    mailhost: str = ""
    port: int = 465
    username: str = ""
    password: str = ""
    fromaddr: str = ""
    toaddr: str = ""
    subject: str = "HoyoAssistant Signin Report"
    ssl_enable: bool = True
    background: bool = False


class WeComPushTarget(StrictConfigModel):
    type: Literal["wecom"]
    wechat_id: str = ""
    secret: str = ""
    agentid: CoercedStr = ""
    touser: str = "@all"


class WeComRobotPushTarget(StrictConfigModel):
    type: Literal["wecomrobot"]
    url: str = ""
    mobile: CoercedStrList = Field(default_factory=list)


class PushDeerPushTarget(StrictConfigModel):
    type: Literal["pushdeer"]
    api_url: str = ""
    token: str = ""


class DingRobotPushTarget(StrictConfigModel):
    type: Literal["dingrobot"]
    webhook: str = ""
    secret: str = ""


class FeishuBotPushTarget(StrictConfigModel):
    type: Literal["feishubot"]
    webhook: str = ""
    secret: str = ""


class BarkPushTarget(StrictConfigModel):
    type: Literal["bark"]
    api_url: str = ""
    token: str = ""
    icon: str = ""


class GotifyPushTarget(StrictConfigModel):
    type: Literal["gotify"]
    api_url: str = ""
    token: str = ""
    priority: int = 0


class IftttPushTarget(StrictConfigModel):
    type: Literal["ifttt"]
    event: str = ""
    key: str = ""


class WebhookPushTarget(StrictConfigModel):
    type: Literal["webhook"]
    url: str = ""


class QmsgPushTarget(StrictConfigModel):
    type: Literal["qmsg"]
    key: str = ""


class WinToastPushTarget(StrictConfigModel):
    type: Literal["wintoast"]


class WxPusherPushTarget(StrictConfigModel):
    type: Literal["wxpusher"]
    app_token: str = ""
    uids: CoercedStrList = Field(default_factory=list)
    topic_ids: CoercedIntList = Field(default_factory=list)


class NtfyPushTarget(StrictConfigModel):
    type: Literal["ntfy"]
    api_url: str = PUSH_NTFY_DEFAULT_URL
    topic: str = ""
    token: str = ""
    priority: str = "default"


PushTarget = Annotated[
    TelegramPushTarget
    | DiscordPushTarget
    | FtqqPushTarget
    | ServerChan3PushTarget
    | PushPlusPushTarget
    | PushMePushTarget
    | CqHttpPushTarget
    | SmtpPushTarget
    | WeComPushTarget
    | WeComRobotPushTarget
    | PushDeerPushTarget
    | DingRobotPushTarget
    | FeishuBotPushTarget
    | BarkPushTarget
    | GotifyPushTarget
    | IftttPushTarget
    | WebhookPushTarget
    | QmsgPushTarget
    | WinToastPushTarget
    | WxPusherPushTarget
    | NtfyPushTarget,
    Field(discriminator="type"),
]


def _normalize_push_targets(v: Any) -> Any:
    """Allow target shorthand where key equals provider name and `type` is omitted."""
    if v is None:
        return {}
    if not isinstance(v, dict):
        return v
    normalized: dict[str, Any] = {}
    for name, spec in v.items():
        if (
            isinstance(spec, dict)
            and "type" not in spec
            and name in PUSH_PROVIDER_NAMES
        ):
            normalized[name] = {**spec, "type": name}
        else:
            normalized[name] = spec
    return normalized


class PushConfig(StrictConfigModel):
    enable: bool = False
    error_only: bool = False
    merge: bool = Field(
        default=True,
        description="Aggregate accounts sharing the same push target into one message",
    )
    block_keys: CoercedStrList = Field(default_factory=list)
    default: CoercedStrList = Field(
        default_factory=list,
        description="Default target names used when an account omits `push`",
    )
    targets: Annotated[
        dict[str, PushTarget], BeforeValidator(_normalize_push_targets)
    ] = Field(default_factory=dict)


def coerce_push_config(v: Any) -> Any:
    if v is None:
        return {}
    if isinstance(v, str):
        v_lower = v.strip().lower()
        if v_lower in {"true", "1", "on", "yes"}:
            return {"enable": True}
        if v_lower in {"false", "0", "off", "no", ""}:
            return {"enable": False}
        targets = [c.strip() for c in v.split(",") if c.strip()]
        return {"enable": True, "default": targets}
    if isinstance(v, bool):
        return {"enable": v}
    return v


CoercedPush = Annotated[PushConfig, BeforeValidator(coerce_push_config)]


# ---------------------------------------------------------------------------
# Cookie Parsing, Canonical Ordering & Region-Aware Pruning
# ---------------------------------------------------------------------------
_CN_V2_APP_COOKIE_KEYS: Final[frozenset[str]] = frozenset(
    {
        "ltoken_v2",
        "ltuid_v2",
        "ltmid_v2",
        "cookie_token_v2",
        "account_id_v2",
        "account_mid_v2",
        "stuid",
        "stoken",
        "mid",
    }
)
_OS_V2_COOKIE_KEYS: Final[frozenset[str]] = frozenset(
    {
        "ltoken_v2",
        "ltuid_v2",
        "ltmid_v2",
        "cookie_token_v2",
        "account_id_v2",
        "account_mid_v2",
    }
)
_CN_UID_COOKIE_KEYS: Final[tuple[str, ...]] = tuple(
    k for k in COOKIE_UID_KEYS if k != "login_uid"
)


def clean_cookie(cookie: str, *, region: Literal["cn", "os"]) -> str:
    """Prune non-auth browser noise and redundant V1 aliases from a cookie string."""
    raw = (cookie or "").strip()
    if not raw:
        return ""

    fields = parse_cookie(raw)
    if not fields:
        return raw

    base_keys = _CN_V2_APP_COOKIE_KEYS if region == "cn" else _OS_V2_COOKIE_KEYS
    kept: dict[str, str] = {k: v for k, v in fields.items() if k in base_keys}

    for v2_key, v1_key in COOKIE_V2_TO_V1_ALIASES:
        if v2_key not in kept and v1_key in fields:
            kept[v1_key] = fields[v1_key]

    if (
        region == "cn"
        and "login_uid" in fields
        and not any(k in kept for k in _CN_UID_COOKIE_KEYS)
    ):
        kept["login_uid"] = fields["login_uid"]

    if not kept:
        return format_cookie(fields)
    return format_cookie(kept)


# ---------------------------------------------------------------------------
# Shared & Region-Specific Account Models
# ---------------------------------------------------------------------------
class DeviceConfig(StrictConfigModel):
    name: str = DEFAULT_DEVICE_NAME
    model: str = DEFAULT_DEVICE_MODEL
    id: str = ""
    fp: str = ""


class BBSConfig(StrictConfigModel):
    enable: bool = True
    forums: Annotated[list[int], BeforeValidator(_none_to_empty_list)] = Field(
        default_factory=lambda: [2, 5],
        description="MiYoUShe forum IDs to check in (unknown IDs auto-sync)",
    )


class CloudTokensConfig(StrictConfigModel):
    genshin: str = ""
    zzz: str = ""


class CustomGameBase(StrictConfigModel):
    """Shared custom daily check-in fields across CN and OS regions."""

    enable: bool = True
    name: str = ""
    act_id: str = ""
    signgame: str = ""
    api_base: str = ""


class CustomCNGameConfig(CustomGameBase):
    """Custom CN game daily check-in spec for newly launched miHoYo games."""

    game_biz: str = ""
    origin: str = ORIGIN_MIHOYO_ACT
    referer: str = ""
    player_name: str = ""
    black_list: Annotated[list[str], BeforeValidator(_none_to_empty_list)] = Field(
        default_factory=list
    )


class CustomOSGameConfig(CustomGameBase):
    """Custom OS game daily check-in spec for newly launched HoYoverse games."""

    api_base: str = API_OS_ACT_LUNA


class AccountBase(StrictConfigModel):
    """Shared fields across peer CN and OS account entries."""

    name: str = ""
    enable: bool = True
    push: AccountPushRef = None
    cookie: str = ""
    user_agent: str = ""
    cloud: Annotated[CloudTokensConfig, BeforeValidator(_none_to_empty_dict)] = Field(
        default_factory=CloudTokensConfig
    )


class CNAccountConfig(AccountBase):
    """China mainland (MiYoUShe) peer account configuration."""

    region: Literal["cn"]
    device: Annotated[DeviceConfig, BeforeValidator(_none_to_empty_dict)] = Field(
        default_factory=DeviceConfig
    )
    bbs: Annotated[BBSConfig, BeforeValidator(_none_to_empty_dict)] = Field(
        default_factory=BBSConfig
    )
    games: Annotated[list[CNGameId], BeforeValidator(_none_to_empty_list)] = Field(
        default_factory=list
    )
    black_list: Annotated[
        dict[str, list[str]], BeforeValidator(_none_to_empty_dict)
    ] = Field(
        default_factory=dict,
        description="Per-game blacklisted UIDs keyed by game ID (e.g. genshin)",
    )
    custom_games: Annotated[
        dict[str, CustomCNGameConfig], BeforeValidator(_none_to_empty_dict)
    ] = Field(default_factory=dict)

    @field_validator("games")
    @classmethod
    def _dedupe_games(cls, v: list[CNGameId]) -> list[CNGameId]:
        return list(dict.fromkeys(v))

    @field_validator("cookie")
    @classmethod
    def _clean_cn_cookie(cls, v: str) -> str:
        return clean_cookie(v, region="cn")


class OSAccountConfig(AccountBase):
    """Global (HoYoLAB) peer account configuration."""

    region: Literal["os"]
    lang: str = DEFAULT_OS_LANG
    games: Annotated[list[OSGameId], BeforeValidator(_none_to_empty_list)] = Field(
        default_factory=list
    )
    custom_games: Annotated[
        dict[str, CustomOSGameConfig], BeforeValidator(_none_to_empty_dict)
    ] = Field(default_factory=dict)

    @field_validator("games")
    @classmethod
    def _dedupe_games(cls, v: list[OSGameId]) -> list[OSGameId]:
        return list(dict.fromkeys(v))

    @field_validator("cookie")
    @classmethod
    def _clean_os_cookie(cls, v: str) -> str:
        return clean_cookie(v, region="os")


AccountConfig = Annotated[
    CNAccountConfig | OSAccountConfig,
    Field(discriminator="region"),
]


_LEGACY_V2_TOP_LEVEL_KEYS: Final[frozenset[str]] = frozenset(
    {"cn", "os", "client", "mihoyobbs", "account", "games"}
)


class HoyoConfig(StrictConfigModel):
    """Unified v3 configuration model (isolated from shell env, forbids unknown keys)."""

    enable: bool = True
    push: CoercedPush = Field(default_factory=PushConfig)
    accounts: Annotated[list[AccountConfig], BeforeValidator(_none_to_empty_list)] = (
        Field(default_factory=list)
    )

    @model_validator(mode="before")
    @classmethod
    def _reject_legacy_v2_keys(cls, data: Any) -> Any:
        if isinstance(data, dict):
            found = sorted(_LEGACY_V2_TOP_LEVEL_KEYS.intersection(data.keys()))
            if found:
                joined = ", ".join(found)
                raise ValueError(
                    f"Legacy v2 top-level key(s) detected ({joined}); "
                    "this version requires the unified v3 config schema (`enable`, `push`, `accounts`)."
                )
        return data

    @model_validator(mode="after")
    def _validate_push_references(self) -> "HoyoConfig":
        defined = set(self.push.targets.keys())
        for target in self.push.default:
            if target not in defined:
                raise ValueError(f"push.default references undefined target '{target}'")
        for idx, acct in enumerate(self.accounts):
            if acct.push:
                label = acct.name.strip() or f"{acct.region}#{idx + 1}"
                for target in acct.push:
                    if target not in defined:
                        raise ValueError(
                            f"accounts[{idx}] ({label}) references undefined push target '{target}'"
                        )
        return self


class HoyoSettings(HoyoConfig, BaseSettings):
    """Runtime settings model that overlays HOYO_ASSISTANT_* environment variables."""

    model_config = SettingsConfigDict(
        env_prefix=EnvVar.PREFIX,
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="ignore",  # allow non-Pydantic runtime env vars (LOG_*, LANGUAGE, CLI_OUTPUT)
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Priority: Env > Init (YAML/Kwargs) > DotEnv > Secrets
        return (
            env_settings,
            init_settings,
            dotenv_settings,
            file_secret_settings,
        )


def collect_config_warnings(cfg: HoyoConfig) -> list[str]:
    """Return non-fatal configuration warnings (incomplete targets, duplicates, etc.)."""
    warnings: list[str] = []

    seen_names: dict[str, int] = {}
    for idx, acct in enumerate(cfg.accounts):
        name = acct.name.strip()
        if name:
            key = name.lower()
            if key in seen_names:
                warnings.append(
                    f"Duplicate account name '{name}' at accounts[{idx}] (first at accounts[{seen_names[key]}])"
                )
            else:
                seen_names[key] = idx

        if not acct.enable:
            continue

        label = name or f"{acct.region}#{idx + 1}"
        for game_key, spec in acct.custom_games.items():
            if not spec.enable:
                continue
            if not spec.act_id.strip():
                warnings.append(
                    f"accounts[{idx}] ({label}) custom_games.{game_key} is enabled but missing act_id"
                )
            if isinstance(spec, CustomCNGameConfig) and not spec.game_biz.strip():
                warnings.append(
                    f"accounts[{idx}] ({label}) custom_games.{game_key} is enabled but missing game_biz"
                )

        if (
            isinstance(acct, CNAccountConfig)
            and acct.bbs.enable
            and not acct.bbs.forums
        ):
            warnings.append(
                f"accounts[{idx}] ({label}) has bbs.enable=true but bbs.forums is empty"
            )

    if cfg.push.enable:
        active_targets: set[str] = set()
        for acct in cfg.accounts:
            if not acct.enable:
                continue
            if acct.push is None:
                active_targets.update(cfg.push.default)
            else:
                active_targets.update(acct.push)

        if not active_targets:
            warnings.append(
                "push.enable is true, but no active accounts resolve to any push target"
            )

        required_fields: dict[str, tuple[str, ...]] = {
            "telegram": ("bot_token", "chat_id"),
            "discord": ("webhook",),
            "ftqq": ("sendkey",),
            "serverchan3": ("sendkey",),
            "pushplus": ("token",),
            "pushme": ("token",),
            "smtp": ("mailhost", "username", "password", "fromaddr", "toaddr"),
            "wecom": ("wechat_id", "secret", "agentid"),
            "wecomrobot": ("url",),
            "pushdeer": ("api_url", "token"),
            "dingrobot": ("webhook",),
            "feishubot": ("webhook",),
            "bark": ("api_url", "token"),
            "gotify": ("api_url", "token"),
            "ifttt": ("event", "key"),
            "webhook": ("url",),
            "qmsg": ("key",),
            "ntfy": ("topic",),
        }
        for target_name in sorted(active_targets):
            target = cfg.push.targets.get(target_name)
            if target is None:
                continue
            if isinstance(target, CqHttpPushTarget):
                if not target.url.strip():
                    warnings.append(
                        f"push.targets.{target_name} (cqhttp) is missing url"
                    )
                if bool(target.qq) == bool(target.group):
                    warnings.append(
                        f"push.targets.{target_name} (cqhttp) should set exactly one of qq or group"
                    )
                continue
            if isinstance(target, WxPusherPushTarget):
                if not target.app_token.strip() or (
                    not target.uids and not target.topic_ids
                ):
                    warnings.append(
                        f"push.targets.{target_name} (wxpusher) requires app_token and uids or topic_ids"
                    )
                continue
            for field_name in required_fields.get(target.type, ()):
                if not str(getattr(target, field_name, "")).strip():
                    warnings.append(
                        f"push.targets.{target_name} ({target.type}) is missing {field_name}"
                    )

    return warnings
