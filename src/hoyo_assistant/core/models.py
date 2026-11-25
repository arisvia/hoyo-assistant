from dataclasses import dataclass, field
from threading import Event, Lock


@dataclass
class CloudGameInfo:
    name: str
    api: str
    biz: str
    hostname: str | None = None


class TaskReport(str):
    """String task output carrying explicit execution outcome flags."""

    had_error: bool
    had_success: bool
    had_captcha: bool

    def __new__(
        cls,
        text: str = "",
        *,
        had_error: bool = False,
        had_success: bool | None = None,
        had_captcha: bool = False,
    ) -> "TaskReport":
        instance = super().__new__(cls, text)
        instance.had_error = had_error
        instance.had_success = (
            bool(text.strip()) if had_success is None else had_success
        )
        instance.had_captcha = had_captcha
        return instance


@dataclass
class AccountRunResult:
    """Execution result and push routing metadata for one peer account."""

    name: str
    region: str
    status: int
    message: str
    push_targets: list[str] | None = None


@dataclass
class ServerSettings:
    """Server runtime settings / state."""

    config_path: str | None = None

    # interval stored in seconds
    _interval: int = 720 * 60  # 12 hours

    use_env: bool = True
    daemon: bool = False

    # runtime state
    next_run: float = 0.0
    last_run: float = 0.0
    running: bool = False
    stop_event: Event = field(default_factory=Event)
    task_lock: Lock = field(default_factory=Lock)

    @property
    def interval(self) -> int:
        return self._interval

    @interval.setter
    def interval(self, seconds: int) -> None:
        self._interval = max(60, seconds)
