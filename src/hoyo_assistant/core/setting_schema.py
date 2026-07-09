from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, Field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)


class BaseConfigModel(BaseModel):
    model_config = {"extra": "ignore"}


def coerce_to_str(v: Any) -> str:
    return str(v)


CoercedStr = Annotated[str, BeforeValidator(coerce_to_str)]


class PushConfig(BaseModel):
    model_config = {"extra": "allow"}
    enable: bool = Field(default=False)
    active: list[str] = Field(default_factory=list)
    push_block_keys: str = Field(default="")
    error_push_only: bool = Field(default=False)
    telegram: dict[str, Any] | None = Field(default=None)
    pushplus: dict[str, Any] | None = Field(default=None)
    pushme: dict[str, Any] | None = Field(default=None)
    cqhttp: dict[str, Any] | None = Field(default=None)
    smtp: dict[str, Any] | None = Field(default=None)
    wecom: dict[str, Any] | None = Field(default=None)
    wecomrobot: dict[str, Any] | None = Field(default=None)
    pushdeer: dict[str, Any] | None = Field(default=None)
    dingrobot: dict[str, Any] | None = Field(default=None)
    feishubot: dict[str, Any] | None = Field(default=None)
    bark: dict[str, Any] | None = Field(default=None)
    gotify: dict[str, Any] | None = Field(default=None)
    ifttt: dict[str, Any] | None = Field(default=None)
    webhook: dict[str, Any] | None = Field(default=None)
    qmsg: dict[str, Any] | None = Field(default=None)
    discord: dict[str, Any] | None = Field(default=None)
    ftqq: dict[str, Any] | None = Field(default=None)


def coerce_push_config(v: Any) -> Any:
    if isinstance(v, str):
        v_lower = v.strip().lower()
        if v_lower in {"true", "1", "on", "yes"}:
            return {"enable": True}
        elif v_lower in {"false", "0", "off", "no", ""}:
            return {"enable": False}
        else:
            channels = [c.strip() for c in v.split(",") if c.strip()]
            return {"enable": True, "active": channels}
    if isinstance(v, bool):
        return {"enable": v}
    return v


CoercedPush = Annotated[PushConfig, BeforeValidator(coerce_push_config)]


class AccountConfig(BaseConfigModel):
    cookie: str = Field(default="", description="MiHoYo BBS Cookie")
    stuid: CoercedStr = Field(default="", description="Account STUID")
    stoken: str = Field(default="", description="Account SToken")
    mid: CoercedStr = Field(default="", description="Account MID")


class DeviceConfig(BaseConfigModel):
    name: str = "Xiaomi MI 6"
    model: str = "Mi 6"
    id: str = ""
    fp: str = ""


class MihoyoBBSConfig(BaseConfigModel):
    checkin: bool = True
    checkin_list: list[int] = Field(
        default_factory=lambda: [5, 2], description="Forum IDs to checkin"
    )


class GameItemConfig(BaseConfigModel):
    checkin: bool = False
    black_list: list[str] = Field(
        default_factory=list, description="List of blacklisted account IDs"
    )


class BaseGamesConfig(BaseConfigModel):
    genshin: GameItemConfig = Field(default_factory=GameItemConfig)
    honkai2: GameItemConfig = Field(default_factory=GameItemConfig)
    honkai3rd: GameItemConfig = Field(default_factory=GameItemConfig)
    tears_of_themis: GameItemConfig = Field(default_factory=GameItemConfig)
    honkai_sr: GameItemConfig = Field(default_factory=GameItemConfig)
    zzz: GameItemConfig = Field(default_factory=GameItemConfig)


class GamesCNConfig(BaseGamesConfig):
    useragent: str = (
        "Mozilla/5.0 (Linux; Android 12; Unspecified Device) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Version/4.0 Chrome/103.0.5060.129 Mobile Safari/537.36"
    )
    retries: int = 3


class GamesOSConfig(BaseGamesConfig):
    cookie: str = ""
    lang: str = "zh-cn"


class GamesConfig(BaseConfigModel):
    cn: GamesCNConfig = Field(default_factory=GamesCNConfig)
    os: GamesOSConfig = Field(default_factory=GamesOSConfig)


class CloudGameItemConfig(BaseConfigModel):
    token: str = ""


class BaseCloudGamesConfig(BaseConfigModel):
    genshin: CloudGameItemConfig = Field(default_factory=CloudGameItemConfig)
    zzz: CloudGameItemConfig = Field(default_factory=CloudGameItemConfig)


class CloudGamesCNConfig(BaseCloudGamesConfig):
    pass


class CloudGamesOSConfig(BaseCloudGamesConfig):
    lang: str = "zh-cn"


class CloudGamesConfig(BaseConfigModel):
    cn: CloudGamesCNConfig = Field(default_factory=CloudGamesCNConfig)
    os: CloudGamesOSConfig = Field(default_factory=CloudGamesOSConfig)


class WebActivityConfig(BaseConfigModel):
    activities: list[str] = Field(default_factory=list)


class HoyoSettings(BaseSettings):
    enable: bool = True
    version: int = 15
    account: AccountConfig = Field(default_factory=lambda: AccountConfig())
    device: DeviceConfig = Field(default_factory=DeviceConfig)
    mihoyobbs: MihoyoBBSConfig = Field(default_factory=MihoyoBBSConfig)
    games: GamesConfig = Field(default_factory=GamesConfig)
    cloud_games: CloudGamesConfig = Field(default_factory=CloudGamesConfig)
    web_activity: WebActivityConfig = Field(default_factory=WebActivityConfig)
    push: CoercedPush = Field(default_factory=PushConfig)

    model_config = SettingsConfigDict(
        env_prefix="HOYO_ASSISTANT_",
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="ignore",
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
