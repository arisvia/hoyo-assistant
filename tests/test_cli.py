"""Tests for hoyo_assistant.cli."""

import argparse
import os
import sys
from copy import deepcopy
from unittest.mock import MagicMock, patch

import pytest

from hoyo_assistant import cli


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    """Reproduce the parser defined inline in cli.main for flag-level tests.

    ponytail: source defines the parser inside main() (no extracted factory).
    If main() ever exposes init_command_args(), switch these tests to call it.
    """
    parser = argparse.ArgumentParser(
        description="test",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("-c", "--config", dest="configs", nargs="+")
    parser.add_argument("-m", "--multi", action="store_true")
    parser.add_argument("-d", "--debug", action="store_true")
    parser.add_argument(
        "--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"]
    )
    parser.add_argument("--log-dir")
    parser.add_argument("--no-log", action="store_true")

    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("server")
    check_parser = subparsers.add_parser("check")
    check_parser.add_argument("-c", "--config")
    check_parser.add_argument("--effective", action="store_true")
    template_parser = subparsers.add_parser("template")
    template_parser.add_argument("-o", "--output")
    fill_config_parser = subparsers.add_parser("format")
    fill_config_parser.add_argument("-c", "--config", required=True)
    fill_config_parser.add_argument("--no-backup", action="store_true")
    return parser


# ---------------------------------------------------------------------------
# init_command_args / parser flag coverage
# ---------------------------------------------------------------------------


class TestParserFlags:
    def test_no_args_defaults(self):
        with patch("sys.argv", ["hoyo-cli"]):
            args = _build_parser().parse_args()
        assert args.configs is None
        assert args.multi is False
        assert args.debug is False
        assert args.command is None

    def test_config_single(self):
        with patch("sys.argv", ["hoyo-cli", "-c", "config.yaml"]):
            args = _build_parser().parse_args()
        assert args.configs == ["config.yaml"]

    def test_config_multiple(self):
        with patch("sys.argv", ["hoyo-cli", "-c", "a.yaml", "b.yaml"]):
            args = _build_parser().parse_args()
        assert args.configs == ["a.yaml", "b.yaml"]

    def test_multi_flag_short(self):
        with patch("sys.argv", ["hoyo-cli", "-m"]):
            args = _build_parser().parse_args()
        assert args.multi is True

    def test_multi_flag_long(self):
        with patch("sys.argv", ["hoyo-cli", "--multi"]):
            args = _build_parser().parse_args()
        assert args.multi is True

    def test_debug_flag(self):
        with patch("sys.argv", ["hoyo-cli", "-d"]):
            args = _build_parser().parse_args()
        assert args.debug is True

    def test_log_level_valid(self):
        for level in ["DEBUG", "INFO", "WARNING", "ERROR"]:
            with patch("sys.argv", ["hoyo-cli", "--log-level", level]):
                args = _build_parser().parse_args()
                assert args.log_level == level

    def test_log_level_invalid_rejected(self):
        with patch("sys.argv", ["hoyo-cli", "--log-level", "TRACE"]):
            with pytest.raises(SystemExit):
                _build_parser().parse_args()

    def test_log_dir(self):
        with patch("sys.argv", ["hoyo-cli", "--log-dir", "/tmp/logs"]):
            args = _build_parser().parse_args()
        assert args.log_dir == "/tmp/logs"

    def test_no_log_flag(self):
        with patch("sys.argv", ["hoyo-cli", "--no-log"]):
            args = _build_parser().parse_args()
        assert args.no_log is True

    def test_combined_global_flags(self):
        with patch(
            "sys.argv",
            [
                "hoyo-cli",
                "-c",
                "c.yaml",
                "-m",
                "-d",
                "--log-level",
                "DEBUG",
                "--log-dir",
                "logs",
                "--no-log",
            ],
        ):
            args = _build_parser().parse_args()
        assert args.configs == ["c.yaml"]
        assert args.multi is True
        assert args.debug is True
        assert args.log_level == "DEBUG"
        assert args.log_dir == "logs"
        assert args.no_log is True


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


class TestSubcommands:
    def test_server_subcommand(self):
        with patch("sys.argv", ["hoyo-cli", "server"]):
            args = _build_parser().parse_args()
        assert args.command == "server"

    def test_check_subcommand_default(self):
        with patch("sys.argv", ["hoyo-cli", "check"]):
            args = _build_parser().parse_args()
        assert args.command == "check"
        assert args.config is None
        assert args.effective is False

    def test_check_subcommand_with_config_and_effective(self):
        with patch(
            "sys.argv",
            ["hoyo-cli", "check", "-c", "config.yaml", "--effective"],
        ):
            args = _build_parser().parse_args()
        assert args.command == "check"
        assert args.config == "config.yaml"
        assert args.effective is True

    def test_template_subcommand_default(self):
        with patch("sys.argv", ["hoyo-cli", "template"]):
            args = _build_parser().parse_args()
        assert args.command == "template"
        assert args.output is None

    def test_template_subcommand_with_output(self):
        with patch("sys.argv", ["hoyo-cli", "template", "-o", "out.yaml"]):
            args = _build_parser().parse_args()
        assert args.command == "template"
        assert args.output == "out.yaml"

    def test_format_subcommand(self):
        with patch(
            "sys.argv",
            ["hoyo-cli", "format", "-c", "config.yaml", "--no-backup"],
        ):
            args = _build_parser().parse_args()
        assert args.command == "format"
        assert args.config == "config.yaml"
        assert args.no_backup is True

    def test_format_requires_config(self):
        with patch("sys.argv", ["hoyo-cli", "format"]):
            with pytest.raises(SystemExit):
                _build_parser().parse_args()


# ---------------------------------------------------------------------------
# _resolve_run_mode
# ---------------------------------------------------------------------------


class TestResolveRunMode:
    def _args(self, multi=False, configs=None):
        return argparse.Namespace(multi=multi, configs=configs, command=None)

    def test_multi_flag_forces_multi(self):
        args = self._args(multi=True)
        assert cli._resolve_run_mode(args) == "multi"

    def test_multiple_configs_implies_multi(self):
        args = self._args(configs=["a.yaml", "b.yaml"])
        assert cli._resolve_run_mode(args) == "multi"

    def test_single_config_is_single(self):
        args = self._args(configs=["a.yaml"])
        assert cli._resolve_run_mode(args) == "single"

    def test_no_config_is_single(self):
        args = self._args()
        assert cli._resolve_run_mode(args) == "single"

    def test_multi_flag_with_single_config_is_multi(self):
        args = self._args(multi=True, configs=["a.yaml"])
        assert cli._resolve_run_mode(args) == "multi"

    def test_configs_empty_list_is_single(self):
        args = self._args(configs=[])
        assert cli._resolve_run_mode(args) == "single"


# ---------------------------------------------------------------------------
# build_cli_overrides
# ---------------------------------------------------------------------------


class TestBuildCliOverrides:
    def test_no_config_returns_none_empty(self):
        args = argparse.Namespace(configs=None)
        target, overrides = cli.build_cli_overrides(args, "single")
        assert target is None
        assert overrides == {}

    def test_single_config_single_mode_returns_str(self):
        args = argparse.Namespace(configs=["a.yaml"])
        target, overrides = cli.build_cli_overrides(args, "single")
        assert target == "a.yaml"
        assert overrides == {}

    def test_multi_config_multi_mode_returns_list(self):
        args = argparse.Namespace(configs=["a.yaml", "b.yaml"])
        target, overrides = cli.build_cli_overrides(args, "multi")
        assert target == ["a.yaml", "b.yaml"]
        assert overrides == {}

    def test_single_config_in_multi_mode_returns_str(self):
        args = argparse.Namespace(configs=["a.yaml"])
        target, _ = cli.build_cli_overrides(args, "multi")
        assert target == "a.yaml"

    def test_strips_whitespace_and_skips_empty(self):
        args = argparse.Namespace(configs=["  a.yaml  ", "  ", "b.yaml"])
        target, _ = cli.build_cli_overrides(args, "multi")
        assert target == ["a.yaml", "b.yaml"]

    def test_all_empty_entries_returns_none(self):
        args = argparse.Namespace(configs=["  ", ""])
        target, _ = cli.build_cli_overrides(args, "single")
        assert target is None

    def test_string_config_value(self):
        args = argparse.Namespace(configs="a.yaml")
        target, _ = cli.build_cli_overrides(args, "single")
        assert target == "a.yaml"


# ---------------------------------------------------------------------------
# _use_rich_output and _is_interactive_terminal
# ---------------------------------------------------------------------------


class TestRichAndInteractive:
    def test_is_interactive_terminal_true_when_both_tty(self):
        fake_out = MagicMock()
        fake_err = MagicMock()
        fake_out.isatty.return_value = True
        fake_err.isatty.return_value = True
        with patch("sys.stdout", fake_out), patch("sys.stderr", fake_err):
            assert cli._is_interactive_terminal() is True

    def test_is_interactive_terminal_false_when_stdout_not_tty(self):
        fake_out = MagicMock()
        fake_err = MagicMock()
        fake_out.isatty.return_value = False
        fake_err.isatty.return_value = True
        with patch("sys.stdout", fake_out), patch("sys.stderr", fake_err):
            assert cli._is_interactive_terminal() is False

    def test_is_interactive_terminal_false_when_stderr_not_tty(self):
        fake_out = MagicMock()
        fake_err = MagicMock()
        fake_out.isatty.return_value = True
        fake_err.isatty.return_value = False
        with patch("sys.stdout", fake_out), patch("sys.stderr", fake_err):
            assert cli._is_interactive_terminal() is False

    def test_is_interactive_terminal_handles_missing_attr(self):
        class NoIsatty:
            pass

        with patch("sys.stdout", NoIsatty()), patch("sys.stderr", NoIsatty()):
            assert cli._is_interactive_terminal() is False

    @pytest.mark.parametrize(
        "val,expected",
        [
            ("plain", False),
            ("text", False),
            ("simple", False),
            ("0", False),
            ("false", False),
            ("off", False),
            ("PLAIN", False),
            ("rich", True),
            ("pretty", True),
            ("1", True),
            ("true", True),
            ("on", True),
            ("RICH", True),
        ],
    )
    def test_use_rich_output_explicit(self, val, expected):
        with patch.dict(os.environ, {"HOYO_ASSISTANT_CLI_OUTPUT": val}):
            assert cli._use_rich_output() is expected

    def test_use_rich_output_auto_falls_back_to_interactive(self):
        env = {k: v for k, v in os.environ.items() if k != "HOYO_ASSISTANT_CLI_OUTPUT"}
        with patch.dict(os.environ, env, clear=True), \
             patch("hoyo_assistant.cli._is_interactive_terminal", return_value=True):
            assert cli._use_rich_output() is True
        with patch.dict(os.environ, env, clear=True), \
             patch("hoyo_assistant.cli._is_interactive_terminal", return_value=False):
            assert cli._use_rich_output() is False

    def test_use_rich_output_auto_empty_env(self):
        env = {k: v for k, v in os.environ.items() if k != "HOYO_ASSISTANT_CLI_OUTPUT"}
        with patch.dict(os.environ, env, clear=True), \
             patch("hoyo_assistant.cli._is_interactive_terminal", return_value=False):
            assert cli._use_rich_output() is False


# ---------------------------------------------------------------------------
# print_banner, cli_print, cli_panel
# ---------------------------------------------------------------------------


class TestOutputHelpers:
    def test_print_banner_noop_when_plain(self, capsys):
        with patch("hoyo_assistant.cli.RICH_OUTPUT", False):
            cli.print_banner()
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_print_banner_emits_when_rich(self, capsys):
        with patch("hoyo_assistant.cli.RICH_OUTPUT", True):
            cli.print_banner()
        captured = capsys.readouterr()
        assert captured.out != ""

    def test_cli_print_plain(self, capsys):
        with patch("hoyo_assistant.cli.RICH_OUTPUT", False):
            cli.cli_print("hello world")
        captured = capsys.readouterr()
        assert "hello world" in captured.out

    def test_cli_print_with_style_plain_ignores_style(self, capsys):
        with patch("hoyo_assistant.cli.RICH_OUTPUT", False):
            cli.cli_print("hello", style="green")
        captured = capsys.readouterr()
        assert "hello" in captured.out

    def test_cli_print_rich_with_style(self, capsys):
        with patch("hoyo_assistant.cli.RICH_OUTPUT", True):
            cli.cli_print("hello", style="green")
        captured = capsys.readouterr()
        assert "hello" in captured.out

    def test_cli_panel_plain_no_title(self, capsys):
        with patch("hoyo_assistant.cli.RICH_OUTPUT", False):
            cli.cli_panel("body content")
        captured = capsys.readouterr()
        assert "body content" in captured.out

    def test_cli_panel_plain_with_title(self, capsys):
        with patch("hoyo_assistant.cli.RICH_OUTPUT", False):
            cli.cli_panel("body content", title="MyTitle")
        captured = capsys.readouterr()
        assert "body content" in captured.out
        assert "MyTitle" in captured.out

    def test_cli_panel_rich(self, capsys):
        with patch("hoyo_assistant.cli.RICH_OUTPUT", True):
            cli.cli_panel("body content", title="MyTitle", border_style="cyan")
        captured = capsys.readouterr()
        assert "body content" in captured.out


# ---------------------------------------------------------------------------
# Command dispatch via main() with mocked dependencies
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_setting():
    """Reset setting module globals between tests."""
    from hoyo_assistant.core import setting

    saved = (
        setting.config.copy(),
        deepcopy(setting.config_raw),
        deepcopy(setting.runtime_overrides),
        setting.config_path,
        setting.path,
    )
    yield setting
    setting.config.clear()
    setting.config.update(saved[0])
    setting.config_raw.clear()
    setting.config_raw.update(saved[1])
    setting.runtime_overrides.clear()
    setting.runtime_overrides.update(saved[2])
    setting.config_path = saved[3]
    setting.path = saved[4]


class TestMainDispatch:
    def test_check_command_calls_validate_config(self, isolated_setting):
        with patch("sys.argv", ["hoyo-cli", "check", "-c", "x.yaml"]), \
             patch("hoyo_assistant.cli.validate_config") as mock_val, \
             patch("hoyo_assistant.cli.print_banner"), \
             patch("hoyo_assistant.cli.loghelper.setup_logger"), \
             patch("hoyo_assistant.core.setting.reload_config") as mock_reload:
            cli.main()
        mock_val.assert_called_once()
        mock_reload.assert_called_once()

    def test_template_command_calls_generate_template(self, isolated_setting):
        with patch("sys.argv", ["hoyo-cli", "template", "-o", "out.yaml"]), \
             patch("hoyo_assistant.cli.generate_template") as mock_gen, \
             patch("hoyo_assistant.cli.print_banner"), \
             patch("hoyo_assistant.cli.loghelper.setup_logger"), \
             patch("hoyo_assistant.core.setting.reload_config"):
            cli.main()
        mock_gen.assert_called_once_with("out.yaml")

    def test_format_command_calls_fill_config(self, isolated_setting):
        with patch("sys.argv", ["hoyo-cli", "format", "-c", "c.yaml"]), \
             patch("hoyo_assistant.cli.fill_config_command") as mock_fill, \
             patch("hoyo_assistant.cli.print_banner"), \
             patch("hoyo_assistant.cli.loghelper.setup_logger"), \
             patch("hoyo_assistant.core.setting.reload_config"):
            cli.main()
        mock_fill.assert_called_once_with("c.yaml", True)

    def test_format_command_no_backup(self, isolated_setting):
        with patch(
            "sys.argv", ["hoyo-cli", "format", "-c", "c.yaml", "--no-backup"]
        ), \
             patch("hoyo_assistant.cli.fill_config_command") as mock_fill, \
             patch("hoyo_assistant.cli.print_banner"), \
             patch("hoyo_assistant.cli.loghelper.setup_logger"), \
             patch("hoyo_assistant.core.setting.reload_config"):
            cli.main()
        mock_fill.assert_called_once_with("c.yaml", False)

    def test_server_command_starts_console(self, isolated_setting):
        mock_server = MagicMock()
        mock_server.start_interactive_console = MagicMock()
        with patch("sys.argv", ["hoyo-cli", "server"]), \
             patch("hoyo_assistant.cli.print_banner"), \
             patch("hoyo_assistant.cli.loghelper.setup_logger"), \
             patch("hoyo_assistant.core.setting.reload_config"), \
             patch("hoyo_assistant.cli.server", mock_server), \
             patch("hoyo_assistant.cli.ServerSettings"):
            cli.main()
        mock_server.start_interactive_console.assert_called_once()

    def test_main_config_error_exits(self, isolated_setting):
        with patch("sys.argv", ["hoyo-cli"]), \
             patch("hoyo_assistant.cli.print_banner"), \
             patch(
                 "hoyo_assistant.core.setting.reload_config",
                 side_effect=ValueError("bad config"),
             ):
            with pytest.raises(SystemExit):
                cli.main()

    def test_main_debug_uses_debug_log_level(self, isolated_setting):
        with patch("sys.argv", ["hoyo-cli", "-d"]), \
             patch("hoyo_assistant.cli.print_banner"), \
             patch(
                 "hoyo_assistant.cli.loghelper.setup_logger"
             ) as mock_log, \
             patch(
                 "hoyo_assistant.cli.run_single"
             ) as mock_run, \
             patch("hoyo_assistant.core.setting.reload_config"):
            cli.main()
        # debug path calls setup_logger("DEBUG")
        mock_log.assert_called_once_with("DEBUG")


class TestRunHelpers:
    def test_bootstrap_config_target_str(self):
        assert cli._bootstrap_config_target("a.yaml") == "a.yaml"

    def test_bootstrap_config_target_list_first(self):
        assert cli._bootstrap_config_target(["a.yaml", "b.yaml"]) == "a.yaml"

    def test_bootstrap_config_target_empty_list(self):
        assert cli._bootstrap_config_target([]) is None

    def test_bootstrap_config_target_none(self):
        assert cli._bootstrap_config_target(None) is None
