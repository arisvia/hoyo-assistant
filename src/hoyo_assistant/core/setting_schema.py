"""Pure v2 Pydantic configuration schema for HoyoAssistant."""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, Field, field_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from .constants import (
    API_OS_ACT_LUNA,
    DEFAULT_DEVICE_MODEL,
    DEFAULT_DEVICE_NAME,
    DEFAULT_OS_LANG,
    ORIGIN_MIHOYO_ACT,
    EnvVar,
)

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


class StrictConfigModel(BaseModel):
    """Strict sub-config model that rejects typos and unknown fields."""

    model_config = {"extra": "forbid"}


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


CoercedStr = Annotated[str, BeforeValidator(_coerce_to_str)]
CoercedStrList = Annotated[list[str], BeforeValidator(_coerce_str_list)]
CoercedIntList = Annotated[list[int], BeforeValidator(_coerce_int_list)]


# ---------------------------------------------------------------------------
# Strongly-typed Push Channel Models
# ---------------------------------------------------------------------------
class TelegramPushConfig(StrictConfigModel):
    api_url: str = "api.telegram.org"
    bot_token: str = ""
    chat_id: CoercedStr = ""


class DiscordPushConfig(StrictConfigModel):
    webhook: str = ""
    avatar_url: str = ""


class FtqqPushConfig(StrictConfigModel):
    sendkey: str = ""


class ServerChan3PushConfig(StrictConfigModel):
    sendkey: str = ""
    tags: str = ""


class PushPlusPushConfig(StrictConfigModel):
    token: str = ""
    topic: str = ""


class PushMePushConfig(StrictConfigModel):
    token: str = ""
    url: str = "https://push.i-i.me/"


class CqHttpPushConfig(StrictConfigModel):
    url: str = ""
    qq: CoercedStr | None = None
    group: CoercedStr | None = None


class SmtpPushConfig(StrictConfigModel):
    mailhost: str = ""
    port: int = 465
    username: str = ""
    password: str = ""
    fromaddr: str = ""
    toaddr: str = ""
    subject: str = "HoyoAssistant Signin Report"
    ssl_enable: bool = True
    background: bool = False


class WeComPushConfig(StrictConfigModel):
    wechat_id: str = ""
    secret: str = ""
    agentid: CoercedStr = ""
    touser: str = "@all"


class WeComRobotPushConfig(StrictConfigModel):
    url: str = ""
    mobile: CoercedStrList = Field(default_factory=list)


class PushDeerPushConfig(StrictConfigModel):
    api_url: str = ""
    token: str = ""


class DingRobotPushConfig(StrictConfigModel):
    webhook: str = ""
    secret: str = ""


class FeishuBotPushConfig(StrictConfigModel):
    webhook: str = ""
    secret: str = ""


class BarkPushConfig(StrictConfigModel):
    api_url: str = ""
    token: str = ""
    icon: str = ""


class GotifyPushConfig(StrictConfigModel):
    api_url: str = ""
    token: str = ""
    priority: int = 0


class IftttPushConfig(StrictConfigModel):
    event: str = ""
    key: str = ""


class WebhookPushConfig(StrictConfigModel):
    url: str = ""


class QmsgPushConfig(StrictConfigModel):
    key: str = ""


class WinToastPushConfig(StrictConfigModel):
    enable: bool = True


class WxPusherPushConfig(StrictConfigModel):
    app_token: str = ""
    uids: CoercedStrList = Field(default_factory=list)
    topic_ids: CoercedIntList = Field(default_factory=list)


class NtfyPushConfig(StrictConfigModel):
    api_url: str = "https://ntfy.sh"
    topic: str = ""
    token: str = ""
    priority: str = "default"


class PushChannelsConfig(StrictConfigModel):
    telegram: TelegramPushConfig | None = None
    discord: DiscordPushConfig | None = None
    ftqq: FtqqPushConfig | None = None
    serverchan3: ServerChan3PushConfig | None = None
    pushplus: PushPlusPushConfig | None = None
    pushme: PushMePushConfig | None = None
    cqhttp: CqHttpPushConfig | None = None
    smtp: SmtpPushConfig | None = None
    wecom: WeComPushConfig | None = None
    wecomrobot: WeComRobotPushConfig | None = None
    pushdeer: PushDeerPushConfig | None = None
    dingrobot: DingRobotPushConfig | None = None
    feishubot: FeishuBotPushConfig | None = None
    bark: BarkPushConfig | None = None
    gotify: GotifyPushConfig | None = None
    ifttt: IftttPushConfig | None = None
    webhook: WebhookPushConfig | None = None
    qmsg: QmsgPushConfig | None = None
    wintoast: WinToastPushConfig | None = None
    wxpusher: WxPusherPushConfig | None = None
    ntfy: NtfyPushConfig | None = None


def _none_to_empty_dict(v: Any) -> Any:
    return {} if v is None else v


def _none_to_empty_list(v: Any) -> Any:
    return [] if v is None else v


class PushConfig(StrictConfigModel):
    enable: bool = False
    error_only: bool = False
    block_keys: CoercedStrList = Field(default_factory=list)
    active: CoercedStrList = Field(
        default_factory=list,
        description="Channel names to trigger; empty means all configured channels",
    )
    channels: Annotated[PushChannelsConfig, BeforeValidator(_none_to_empty_dict)] = (
        Field(default_factory=PushChannelsConfig)
    )


def coerce_push_config(v: Any) -> Any:
    if v is None:
        return {}
    if isinstance(v, str):
        v_lower = v.strip().lower()
        if v_lower in {"true", "1", "on", "yes"}:
            return {"enable": True}
        if v_lower in {"false", "0", "off", "no", ""}:
            return {"enable": False}
        channels = [c.strip() for c in v.split(",") if c.strip()]
        return {"enable": True, "active": channels}
    if isinstance(v, bool):
        return {"enable": v}
    return v


CoercedPush = Annotated[PushConfig, BeforeValidator(coerce_push_config)]


# ---------------------------------------------------------------------------
# Client / Region / Task Config Models
# ---------------------------------------------------------------------------
class DeviceConfig(StrictConfigModel):
    name: str = DEFAULT_DEVICE_NAME
    model: str = DEFAULT_DEVICE_MODEL
    id: str = ""
    fp: str = ""


class ClientConfig(StrictConfigModel):
    """Client identity: user agent + device fingerprint."""

    user_agent: str = ""
    device: Annotated[DeviceConfig, BeforeValidator(_none_to_empty_dict)] = Field(
        default_factory=DeviceConfig
    )


class BBSConfig(StrictConfigModel):
    enable: bool = True
    forums: Annotated[list[int], BeforeValidator(_none_to_empty_list)] = Field(
        default_factory=lambda: [5, 2],
        description="MiYoUShe forum IDs to check in (unknown IDs auto-sync)",
    )


class CloudTokensConfig(StrictConfigModel):
    genshin: str = ""
    zzz: str = ""


class CustomCNGameConfig(StrictConfigModel):
    """Custom CN game daily check-in spec for newly launched miHoYo games."""

    enable: bool = True
    name: str = ""
    game_biz: str = ""
    act_id: str = ""
    signgame: str = ""
    api_base: str = ""
    origin: str = ORIGIN_MIHOYO_ACT
    referer: str = ""
    player_name: str = ""
    black_list: list[str] = Field(default_factory=list)


class CustomOSGameConfig(StrictConfigModel):
    """Custom OS game daily check-in spec for newly launched HoYoverse games."""

    enable: bool = True
    name: str = ""
    act_id: str = ""
    api_base: str = API_OS_ACT_LUNA
    signgame: str = ""


class CNConfig(StrictConfigModel):
    """China mainland (MiYoUShe) credentials, BBS, game & cloud check-in settings."""

    cookie: str = ""
    stuid: CoercedStr = ""
    stoken: str = ""
    mid: CoercedStr = ""
    retries: int = 3
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
    cloud: Annotated[CloudTokensConfig, BeforeValidator(_none_to_empty_dict)] = Field(
        default_factory=CloudTokensConfig
    )

    @field_validator("games")
    @classmethod
    def _dedupe_games(cls, v: list[CNGameId]) -> list[CNGameId]:
        return list(dict.fromkeys(v))


class OSConfig(StrictConfigModel):
    """Global (HoYoLAB) credentials, language, game & cloud check-in settings."""

    cookie: str = ""
    lang: str = DEFAULT_OS_LANG
    games: Annotated[list[OSGameId], BeforeValidator(_none_to_empty_list)] = Field(
        default_factory=list
    )
    custom_games: Annotated[
        dict[str, CustomOSGameConfig], BeforeValidator(_none_to_empty_dict)
    ] = Field(default_factory=dict)
    cloud: Annotated[CloudTokensConfig, BeforeValidator(_none_to_empty_dict)] = Field(
        default_factory=CloudTokensConfig
    )

    @field_validator("games")
    @classmethod
    def _dedupe_games(cls, v: list[OSGameId]) -> list[OSGameId]:
        return list(dict.fromkeys(v))


class HoyoConfig(StrictConfigModel):
    """Pure v2 configuration model (isolated from shell env, forbids unknown keys)."""

    enable: bool = True
    cn: Annotated[CNConfig, BeforeValidator(_none_to_empty_dict)] = Field(
        default_factory=CNConfig
    )
    os: Annotated[OSConfig, BeforeValidator(_none_to_empty_dict)] = Field(
        default_factory=OSConfig
    )
    client: Annotated[ClientConfig, BeforeValidator(_none_to_empty_dict)] = Field(
        default_factory=ClientConfig
    )
    push: CoercedPush = Field(default_factory=PushConfig)


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
