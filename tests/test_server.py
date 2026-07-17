"""Tests for hoyo_assistant.server module."""

import threading
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hoyo_assistant.core.models import ServerSettings
from hoyo_assistant.server import (
    execute_task,
    print_help,
    scheduler_loop,
    start_interactive_console,
)


# ---------------------------------------------------------------------------
# ServerSettings model tests
# ---------------------------------------------------------------------------
class TestServerSettingsModel:
    def test_default_values(self):
        s = ServerSettings()
        assert s.mode == "multi"
        assert s.interval == 720 * 60
        assert s.config_path is None
        assert s.use_env is False
        assert s.next_run == 0.0
        assert s.last_run == 0.0
        assert s.running is False
        assert isinstance(s.stop_event, threading.Event)

    def test_mode_setter_valid_single(self):
        s = ServerSettings()
        s.mode = "single"
        assert s.mode == "single"

    def test_mode_setter_valid_multi(self):
        s = ServerSettings()
        s.mode = "single"
        s.mode = "multi"
        assert s.mode == "multi"

    def test_mode_setter_invalid_raises(self):
        s = ServerSettings()
        with pytest.raises(ValueError):
            s.mode = "invalid"

    def test_interval_setter_normal(self):
        s = ServerSettings()
        s.interval = 300
        assert s.interval == 300

    def test_interval_setter_below_minimum_clamped(self):
        s = ServerSettings()
        s.interval = 10
        assert s.interval == 60

    def test_interval_setter_exact_minimum(self):
        s = ServerSettings()
        s.interval = 60
        assert s.interval == 60


# ---------------------------------------------------------------------------
# execute_task tests
# ---------------------------------------------------------------------------
class TestExecuteTask:
    @pytest.fixture
    def _patches(self):
        """Common patches for execute_task dependencies."""
        with (
            patch(
                "hoyo_assistant.server.run_single_account", new_callable=AsyncMock
            ) as mock_single,
            patch(
                "hoyo_assistant.server.run_multi_account", new_callable=AsyncMock
            ) as mock_multi,
            patch(
                "hoyo_assistant.server.push.push", new_callable=AsyncMock
            ) as mock_push,
            patch(
                "hoyo_assistant.server.is_push_enabled", return_value=False
            ) as mock_push_enabled,
            patch("hoyo_assistant.server.log") as mock_log,
            patch("hoyo_assistant.server.t", side_effect=lambda k, **kw: k),
        ):
            yield {
                "single": mock_single,
                "multi": mock_multi,
                "push": mock_push,
                "push_enabled": mock_push_enabled,
                "log": mock_log,
            }

    async def test_single_mode_calls_run_single_account(self, _patches):
        mock_single = _patches["single"]
        mock_single.return_value = (0, "ok")
        cfg = ServerSettings(_mode="single", config_path="/path/to/config.yaml")

        await execute_task(cfg)

        mock_single.assert_awaited_once_with(
            config_path="/path/to/config.yaml", use_env=False
        )

    async def test_multi_mode_calls_run_multi_account(self, _patches):
        mock_multi = _patches["multi"]
        mock_multi.return_value = (0, "ok")
        cfg = ServerSettings(_mode="multi", config_path="/path/to/targets")

        await execute_task(cfg)

        mock_multi.assert_awaited_once_with(
            target_path="/path/to/targets", use_env=False
        )

    async def test_single_mode_list_config_path_takes_first(self, _patches):
        mock_single = _patches["single"]
        mock_single.return_value = (0, "ok")
        cfg = ServerSettings(_mode="single", config_path=["/a.yaml", "/b.yaml"])

        await execute_task(cfg)

        mock_single.assert_awaited_once_with(config_path="/a.yaml", use_env=False)

    async def test_single_mode_empty_list_config_path_none(self, _patches):
        mock_single = _patches["single"]
        mock_single.return_value = (0, "ok")
        cfg = ServerSettings(_mode="single", config_path=[])

        await execute_task(cfg)

        mock_single.assert_awaited_once_with(config_path=None, use_env=False)

    async def test_exception_caught_and_logged(self, _patches):
        mock_single = _patches["single"]
        mock_single.side_effect = RuntimeError("boom")
        cfg = ServerSettings(_mode="single")

        # Should not raise
        await execute_task(cfg)

        _patches["log"].error.assert_called_once()

    async def test_push_disabled_no_push_call(self, _patches):
        _patches["multi"].return_value = (0, "ok")
        cfg = ServerSettings(_mode="multi")

        await execute_task(cfg)

        _patches["push"].assert_not_awaited()

    async def test_push_enabled_via_config(self, _patches):
        _patches["multi"].return_value = (0, "ok")
        cfg = ServerSettings(_mode="multi")

        with patch("hoyo_assistant.server.is_push_enabled", return_value=True):
            await execute_task(cfg)

        _patches["push"].assert_awaited_once_with(0, "ok")

    async def test_push_enabled_via_env(self, _patches):
        """Env var HOYO_ASSISTANT_PUSH__ENABLE overrides a disabled config.

        execute_task delegates the push decision entirely to is_push_enabled(), so the
        env-override semantics live there. Verify them directly against the real
        function: with config push disabled, the env var still flips it to enabled.
        """
        _patches["multi"].return_value = (0, "ok")

        from hoyo_assistant.core import is_push_enabled

        with (
            patch("hoyo_assistant.core.config", {"push": {"enable": False}}),
            patch.dict("os.environ", {"HOYO_ASSISTANT_PUSH__ENABLE": "true"}),
        ):
            assert is_push_enabled() is True

    async def test_push_exception_logged(self, _patches):
        _patches["multi"].return_value = (0, "ok")
        _patches["push"].side_effect = RuntimeError("push failed")
        cfg = ServerSettings(_mode="multi")

        with patch("hoyo_assistant.server.is_push_enabled", return_value=True):
            # Should not raise
            await execute_task(cfg)

        _patches["log"].error.assert_called()

    async def test_use_env_passed_through(self, _patches):
        _patches["single"].return_value = (0, "ok")
        cfg = ServerSettings(_mode="single", use_env=True)

        await execute_task(cfg)

        _, kwargs = _patches["single"].call_args
        assert kwargs["use_env"] is True

    async def test_task_done_logged(self, _patches):
        _patches["multi"].return_value = (0, "ok")
        cfg = ServerSettings(_mode="multi")

        await execute_task(cfg)

        _patches["log"].info.assert_called()


# ---------------------------------------------------------------------------
# print_help tests
# ---------------------------------------------------------------------------
class TestPrintHelp:
    def test_does_not_raise(self):
        with (
            patch("hoyo_assistant.server.console") as mock_console,
            patch("hoyo_assistant.server.t", side_effect=lambda k, **kw: k),
        ):
            print_help()
            mock_console.print.assert_called_once()


# ---------------------------------------------------------------------------
# scheduler_loop tests
# ---------------------------------------------------------------------------
class TestSchedulerLoop:
    def test_runs_task_when_time_reached(self):
        cfg = ServerSettings(_mode="multi")
        cfg.running = True
        cfg.next_run = 0  # immediate

        call_count = {"n": 0}

        async def fake_execute(_cfg):
            call_count["n"] += 1
            _cfg.stop_event.set()
            _cfg.running = False

        with (
            patch("hoyo_assistant.server.time.sleep", side_effect=lambda *a: None),
            patch("hoyo_assistant.server.time.time", return_value=1000.0),
            patch("hoyo_assistant.server.execute_task", fake_execute),
            patch("hoyo_assistant.server.log"),
            patch("hoyo_assistant.server.t", side_effect=lambda k, **kw: k),
        ):
            scheduler_loop(cfg)

        assert call_count["n"] == 1

    def test_does_not_run_when_not_time(self):
        cfg = ServerSettings(_mode="multi")
        cfg.running = True
        cfg.next_run = 999999.0  # far future

        call_count = {"n": 0}

        async def fake_execute(_cfg):
            call_count["n"] += 1

        def fake_sleep(_):
            cfg.stop_event.set()
            cfg.running = False

        with (
            patch("hoyo_assistant.server.time.sleep", side_effect=fake_sleep),
            patch("hoyo_assistant.server.time.time", return_value=0.0),
            patch("hoyo_assistant.server.execute_task", fake_execute),
            patch("hoyo_assistant.server.log"),
            patch("hoyo_assistant.server.t", side_effect=lambda k, **kw: k),
        ):
            scheduler_loop(cfg)

        assert call_count["n"] == 0

    def test_exception_in_task_handled(self):
        cfg = ServerSettings(_mode="multi")
        cfg.running = True
        cfg.next_run = 0

        async def fake_execute(_cfg):
            _cfg.stop_event.set()
            _cfg.running = False
            raise RuntimeError("task error")

        with (
            patch("hoyo_assistant.server.time.sleep", side_effect=lambda *a: None),
            patch("hoyo_assistant.server.time.time", return_value=1000.0),
            patch("hoyo_assistant.server.execute_task", fake_execute),
            patch("hoyo_assistant.server.log") as mock_log,
            patch("hoyo_assistant.server.t", side_effect=lambda k, **kw: k),
        ):
            scheduler_loop(cfg)

        mock_log.error.assert_called()

    def test_stops_when_running_false(self):
        cfg = ServerSettings(_mode="multi")
        cfg.running = False
        cfg.next_run = 0

        call_count = {"n": 0}

        async def fake_execute(_cfg):
            call_count["n"] += 1

        with (
            patch("hoyo_assistant.server.time.sleep", side_effect=lambda *a: None),
            patch("hoyo_assistant.server.execute_task", fake_execute),
            patch("hoyo_assistant.server.log"),
            patch("hoyo_assistant.server.t", side_effect=lambda k, **kw: k),
        ):
            scheduler_loop(cfg)

        assert call_count["n"] == 0

    def test_next_run_zero_sets_to_current_time(self):
        cfg = ServerSettings(_mode="multi")
        cfg.running = True
        cfg.next_run = 0

        def fake_sleep(_):
            cfg.stop_event.set()
            cfg.running = False

        with (
            patch("hoyo_assistant.server.time.sleep", side_effect=fake_sleep),
            patch("hoyo_assistant.server.time.time", return_value=500.0),
            patch("hoyo_assistant.server.execute_task", AsyncMock()),
            patch("hoyo_assistant.server.log"),
            patch("hoyo_assistant.server.t", side_effect=lambda k, **kw: k),
        ):
            scheduler_loop(cfg)

        # next_run should have been set to current time (500) then updated to 500 + interval
        assert cfg.next_run == 500.0 + cfg.interval


# ---------------------------------------------------------------------------
# start_interactive_console tests
# ---------------------------------------------------------------------------
class TestStartInteractiveConsole:
    def _common_patches(self, cfg=None):
        """Return a context manager stack for common server patches."""
        ctxs = []
        ctxs.append(patch("hoyo_assistant.server.console"))
        ctxs.append(patch("hoyo_assistant.server.execute_task", new_callable=AsyncMock))
        ctxs.append(
            patch("hoyo_assistant.server.time.sleep", side_effect=lambda *a: None)
        )
        ctxs.append(patch("hoyo_assistant.server.threading.Thread"))
        ctxs.append(
            patch("hoyo_assistant.server.asyncio.run", side_effect=lambda coro: None)
        )
        ctxs.append(patch("hoyo_assistant.server.log"))
        ctxs.append(patch("hoyo_assistant.server.t", side_effect=lambda k, **kw: k))
        ctxs.append(patch("hoyo_assistant.server.setting.reload_config"))
        return ctxs

    def test_exit_command_stops_console(self):
        cfg = ServerSettings()
        mock_console = MagicMock()
        mock_console.input.return_value = "exit"

        with (
            patch("hoyo_assistant.server.console", mock_console),
            patch("hoyo_assistant.server.execute_task", new_callable=AsyncMock),
            patch("hoyo_assistant.server.time.sleep", side_effect=lambda *a: None),
            patch("hoyo_assistant.server.threading.Thread") as mock_thread,
            patch("hoyo_assistant.server.asyncio.run", side_effect=lambda coro: None),
            patch("hoyo_assistant.server.log"),
            patch("hoyo_assistant.server.t", side_effect=lambda k, **kw: k),
            patch("hoyo_assistant.server.setting.reload_config"),
            pytest.raises(SystemExit),
        ):
            start_interactive_console(cfg)

        assert cfg.running is False
        assert cfg.stop_event.is_set()
        mock_thread_instance = mock_thread.return_value
        mock_thread_instance.join.assert_called_once()

    def test_quit_command_stops_console(self):
        cfg = ServerSettings()
        mock_console = MagicMock()
        mock_console.input.return_value = "quit"

        with (
            patch("hoyo_assistant.server.console", mock_console),
            patch("hoyo_assistant.server.execute_task", new_callable=AsyncMock),
            patch("hoyo_assistant.server.time.sleep", side_effect=lambda *a: None),
            patch("hoyo_assistant.server.threading.Thread"),
            patch("hoyo_assistant.server.asyncio.run", side_effect=lambda coro: None),
            patch("hoyo_assistant.server.log"),
            patch("hoyo_assistant.server.t", side_effect=lambda k, **kw: k),
            patch("hoyo_assistant.server.setting.reload_config"),
            pytest.raises(SystemExit),
        ):
            start_interactive_console(cfg)

        assert cfg.running is False

    def test_help_command_calls_print_help(self):
        cfg = ServerSettings()
        mock_console = MagicMock()
        mock_console.input.side_effect = ["help", "exit"]

        with (
            patch("hoyo_assistant.server.console", mock_console),
            patch("hoyo_assistant.server.execute_task", new_callable=AsyncMock),
            patch("hoyo_assistant.server.time.sleep", side_effect=lambda *a: None),
            patch("hoyo_assistant.server.threading.Thread"),
            patch("hoyo_assistant.server.asyncio.run", side_effect=lambda coro: None),
            patch("hoyo_assistant.server.log"),
            patch("hoyo_assistant.server.t", side_effect=lambda k, **kw: k),
            patch("hoyo_assistant.server.print_help") as mock_print_help,
            patch("hoyo_assistant.server.setting.reload_config"),
            pytest.raises(SystemExit),
        ):
            start_interactive_console(cfg)

        mock_print_help.assert_called_once()

    def test_run_command_sets_next_run_zero(self):
        cfg = ServerSettings()
        cfg.next_run = 999999
        mock_console = MagicMock()
        mock_console.input.side_effect = ["run", "exit"]

        with (
            patch("hoyo_assistant.server.console", mock_console),
            patch("hoyo_assistant.server.execute_task", new_callable=AsyncMock),
            patch("hoyo_assistant.server.time.sleep", side_effect=lambda *a: None),
            patch("hoyo_assistant.server.threading.Thread"),
            patch("hoyo_assistant.server.asyncio.run", side_effect=lambda coro: None),
            patch("hoyo_assistant.server.log"),
            patch("hoyo_assistant.server.t", side_effect=lambda k, **kw: k),
            patch("hoyo_assistant.server.setting.reload_config"),
            pytest.raises(SystemExit),
        ):
            start_interactive_console(cfg)

        assert cfg.next_run == 0

    def test_reload_command_calls_reload_config(self):
        cfg = ServerSettings()
        mock_console = MagicMock()
        mock_console.input.side_effect = ["reload", "exit"]

        with (
            patch("hoyo_assistant.server.console", mock_console),
            patch("hoyo_assistant.server.execute_task", new_callable=AsyncMock),
            patch("hoyo_assistant.server.time.sleep", side_effect=lambda *a: None),
            patch("hoyo_assistant.server.threading.Thread"),
            patch("hoyo_assistant.server.asyncio.run", side_effect=lambda coro: None),
            patch("hoyo_assistant.server.log"),
            patch("hoyo_assistant.server.t", side_effect=lambda k, **kw: k),
            patch("hoyo_assistant.server.setting.reload_config") as mock_reload,
            pytest.raises(SystemExit),
        ):
            start_interactive_console(cfg)

        mock_reload.assert_called_once_with(use_env=cfg.use_env)

    def test_mode_command_changes_mode(self):
        cfg = ServerSettings()
        mock_console = MagicMock()
        mock_console.input.side_effect = ["mode single", "exit"]

        with (
            patch("hoyo_assistant.server.console", mock_console),
            patch("hoyo_assistant.server.execute_task", new_callable=AsyncMock),
            patch("hoyo_assistant.server.time.sleep", side_effect=lambda *a: None),
            patch("hoyo_assistant.server.threading.Thread"),
            patch("hoyo_assistant.server.asyncio.run", side_effect=lambda coro: None),
            patch("hoyo_assistant.server.log"),
            patch("hoyo_assistant.server.t", side_effect=lambda k, **kw: k),
            patch("hoyo_assistant.server.setting.reload_config"),
            pytest.raises(SystemExit),
        ):
            start_interactive_console(cfg)

        assert cfg.mode == "single"

    def test_interval_command_changes_interval(self):
        cfg = ServerSettings()
        mock_console = MagicMock()
        mock_console.input.side_effect = ["interval 30", "exit"]

        with (
            patch("hoyo_assistant.server.console", mock_console),
            patch("hoyo_assistant.server.execute_task", new_callable=AsyncMock),
            patch("hoyo_assistant.server.time.sleep", side_effect=lambda *a: None),
            patch("hoyo_assistant.server.threading.Thread"),
            patch("hoyo_assistant.server.asyncio.run", side_effect=lambda coro: None),
            patch("hoyo_assistant.server.log"),
            patch("hoyo_assistant.server.t", side_effect=lambda k, **kw: k),
            patch("hoyo_assistant.server.setting.reload_config"),
            pytest.raises(SystemExit),
        ):
            start_interactive_console(cfg)

        # "interval 30" => 30 minutes * 60 = 1800 seconds
        assert cfg.interval == 30 * 60

    def test_status_command_prints_panel(self):
        cfg = ServerSettings()
        cfg.next_run = 999999.0
        mock_console = MagicMock()
        mock_console.input.side_effect = ["status", "exit"]

        with (
            patch("hoyo_assistant.server.console", mock_console),
            patch("hoyo_assistant.server.execute_task", new_callable=AsyncMock),
            patch("hoyo_assistant.server.time.sleep", side_effect=lambda *a: None),
            patch("hoyo_assistant.server.threading.Thread"),
            patch("hoyo_assistant.server.asyncio.run", side_effect=lambda coro: None),
            patch("hoyo_assistant.server.log"),
            patch("hoyo_assistant.server.t", side_effect=lambda k, **kw: k),
            patch("hoyo_assistant.server.setting.reload_config"),
            pytest.raises(SystemExit),
        ):
            start_interactive_console(cfg)

        # console.print should have been called many times including for status Panel
        assert mock_console.print.call_count >= 2

    def test_unknown_command_prints_error(self):
        cfg = ServerSettings()
        mock_console = MagicMock()
        mock_console.input.side_effect = ["boguscmd", "exit"]

        with (
            patch("hoyo_assistant.server.console", mock_console),
            patch("hoyo_assistant.server.execute_task", new_callable=AsyncMock),
            patch("hoyo_assistant.server.time.sleep", side_effect=lambda *a: None),
            patch("hoyo_assistant.server.threading.Thread"),
            patch("hoyo_assistant.server.asyncio.run", side_effect=lambda coro: None),
            patch("hoyo_assistant.server.log"),
            patch("hoyo_assistant.server.t", side_effect=lambda k, **kw: k),
            patch("hoyo_assistant.server.setting.reload_config"),
            pytest.raises(SystemExit),
        ):
            start_interactive_console(cfg)

        # Should have printed (at least the unknown command message)
        assert mock_console.print.call_count >= 1

    def test_default_cfg_created_when_none(self):
        mock_console = MagicMock()
        mock_console.input.return_value = "exit"

        with (
            patch("hoyo_assistant.server.console", mock_console),
            patch("hoyo_assistant.server.execute_task", new_callable=AsyncMock),
            patch("hoyo_assistant.server.time.sleep", side_effect=lambda *a: None),
            patch("hoyo_assistant.server.threading.Thread"),
            patch("hoyo_assistant.server.asyncio.run", side_effect=lambda coro: None),
            patch("hoyo_assistant.server.log"),
            patch("hoyo_assistant.server.t", side_effect=lambda k, **kw: k),
            patch("hoyo_assistant.server.setting.reload_config"),
            pytest.raises(SystemExit),
        ):
            start_interactive_console(None)

    def test_initial_task_exception_handled(self):
        cfg = ServerSettings()
        mock_console = MagicMock()
        mock_console.input.return_value = "exit"

        with (
            patch("hoyo_assistant.server.console", mock_console),
            patch("hoyo_assistant.server.execute_task", new_callable=AsyncMock),
            patch("hoyo_assistant.server.time.sleep", side_effect=lambda *a: None),
            patch("hoyo_assistant.server.threading.Thread"),
            patch(
                "hoyo_assistant.server.asyncio.run",
                side_effect=RuntimeError("init fail"),
            ),
            patch("hoyo_assistant.server.log") as mock_log,
            patch("hoyo_assistant.server.t", side_effect=lambda k, **kw: k),
            patch("hoyo_assistant.server.setting.reload_config"),
            pytest.raises(SystemExit),
        ):
            start_interactive_console(cfg)

        # The initial exception should have been logged, not propagated
        mock_log.error.assert_called()

    def test_eof_error_stops_console(self):
        cfg = ServerSettings()
        mock_console = MagicMock()
        mock_console.input.side_effect = EOFError()

        with (
            patch("hoyo_assistant.server.console", mock_console),
            patch("hoyo_assistant.server.execute_task", new_callable=AsyncMock),
            patch("hoyo_assistant.server.time.sleep", side_effect=lambda *a: None),
            patch("hoyo_assistant.server.threading.Thread"),
            patch("hoyo_assistant.server.asyncio.run", side_effect=lambda coro: None),
            patch("hoyo_assistant.server.log"),
            patch("hoyo_assistant.server.t", side_effect=lambda k, **kw: k),
            patch("hoyo_assistant.server.setting.reload_config"),
            pytest.raises(SystemExit),
        ):
            start_interactive_console(cfg)

        assert cfg.running is False
        assert cfg.stop_event.is_set()
