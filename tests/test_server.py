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


class TestServerSettingsModel:
    def test_default_values(self):
        s = ServerSettings()
        assert s.interval == 720 * 60
        assert s.config_path is None
        assert s.use_env is True
        assert s.next_run == 0.0
        assert s.last_run == 0.0
        assert s.running is False
        assert isinstance(s.stop_event, threading.Event)

    def test_interval_setter_clamps_minimum(self):
        s = ServerSettings()
        s.interval = 300
        assert s.interval == 300
        s.interval = 10
        assert s.interval == 60


class TestExecuteTask:
    @pytest.fixture
    def _patches(self):
        with (
            patch(
                "hoyo_assistant.server.run_accounts", new_callable=AsyncMock
            ) as mock_run,
            patch("hoyo_assistant.server.log") as mock_log,
            patch("hoyo_assistant.server.t", side_effect=lambda k, **kw: k),
        ):
            yield {"run": mock_run, "log": mock_log}

    async def test_calls_run_accounts_with_push(self, _patches):
        _patches["run"].return_value = (0, "ok", [])
        cfg = ServerSettings(config_path="/path/to/config.yaml", use_env=False)

        await execute_task(cfg)

        _patches["run"].assert_awaited_once_with(
            config_path="/path/to/config.yaml",
            use_env=False,
            send_push=True,
            allow_qr_login=False,
            force_reload=True,
        )
        _patches["log"].info.assert_called()

    async def test_exception_caught_and_logged(self, _patches):
        _patches["run"].side_effect = RuntimeError("boom")
        cfg = ServerSettings()

        await execute_task(cfg)

        _patches["log"].error.assert_called_once()


class TestPrintHelp:
    def test_does_not_raise(self):
        with (
            patch("hoyo_assistant.server.console") as mock_console,
            patch("hoyo_assistant.server.t", side_effect=lambda k, **kw: k),
        ):
            print_help()
            mock_console.print.assert_called_once()


class TestSchedulerLoop:
    def test_runs_task_when_time_reached(self):
        cfg = ServerSettings()
        cfg.running = True
        cfg.next_run = 0

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
        cfg = ServerSettings()
        cfg.running = True
        cfg.next_run = 999999.0

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
        cfg = ServerSettings()
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


class TestStartInteractiveConsole:
    def test_exit_and_reload_and_interval_commands(self):
        cfg = ServerSettings(config_path="c.yaml")
        mock_console = MagicMock()
        mock_console.input.side_effect = [
            "help",
            "run",
            "reload",
            "interval 30",
            "status",
            "bogus",
            "exit",
        ]

        with (
            patch("hoyo_assistant.server.console", mock_console),
            patch("hoyo_assistant.server.execute_task", new_callable=AsyncMock),
            patch("hoyo_assistant.server.time.sleep", side_effect=lambda *a: None),
            patch("hoyo_assistant.server.threading.Thread") as mock_thread,
            patch("hoyo_assistant.server.asyncio.run", side_effect=lambda coro: None),
            patch("hoyo_assistant.server.log"),
            patch("hoyo_assistant.server.t", side_effect=lambda k, **kw: k),
            patch("hoyo_assistant.server.setting.reload_config") as mock_reload,
            pytest.raises(SystemExit),
        ):
            start_interactive_console(cfg)

        assert cfg.running is False
        assert cfg.stop_event.is_set()
        assert cfg.next_run == 0
        assert cfg.interval == 1800
        mock_reload.assert_called_once_with(config_file="c.yaml", use_env=cfg.use_env)
        mock_thread.return_value.join.assert_called_once()

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
            pytest.raises(SystemExit),
        ):
            start_interactive_console(cfg)

        assert cfg.running is False
        assert cfg.stop_event.is_set()

    def test_reload_config_error_does_not_crash_server_loop(self):
        cfg = ServerSettings(config_path="bad.yaml")
        mock_console = MagicMock()
        mock_console.input.side_effect = ["reload", "exit"]

        with (
            patch("hoyo_assistant.server.console", mock_console),
            patch("hoyo_assistant.server.execute_task", new_callable=AsyncMock),
            patch("hoyo_assistant.server.time.sleep", side_effect=lambda *a: None),
            patch("hoyo_assistant.server.threading.Thread"),
            patch("hoyo_assistant.server.asyncio.run", side_effect=lambda coro: None),
            patch("hoyo_assistant.server.log") as mock_log,
            patch("hoyo_assistant.server.t", side_effect=lambda k, **kw: k),
            patch(
                "hoyo_assistant.server.setting.reload_config",
                side_effect=ValueError("invalid yaml"),
            ),
            pytest.raises(SystemExit) as e,
        ):
            start_interactive_console(cfg)

        assert e.value.code == 0
        mock_log.error.assert_called()

    def test_daemon_mode_waits_without_console_input(self):
        cfg = ServerSettings(daemon=True)
        mock_console = MagicMock()

        def fake_wait(timeout=None):
            cfg.running = False
            cfg.stop_event.set()
            return True

        with (
            patch("hoyo_assistant.server.console", mock_console),
            patch("hoyo_assistant.server.execute_task", new_callable=AsyncMock),
            patch("hoyo_assistant.server.time.sleep", side_effect=lambda *a: None),
            patch("hoyo_assistant.server.threading.Thread"),
            patch("hoyo_assistant.server.asyncio.run", side_effect=lambda coro: None),
            patch("hoyo_assistant.server.t", side_effect=lambda k, **kw: k),
            patch.object(cfg.stop_event, "wait", side_effect=fake_wait) as mock_wait,
            pytest.raises(SystemExit),
        ):
            start_interactive_console(cfg)

        mock_console.clear.assert_not_called()
        mock_console.input.assert_not_called()
        mock_wait.assert_called()
