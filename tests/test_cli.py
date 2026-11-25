"""Tests for hoyo_assistant.cli (unified v3 CLI + terminal QR login)."""

import io
import os
from copy import deepcopy
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from rich.console import Console

from hoyo_assistant import cli
from hoyo_assistant.core import qr_login, setting


class TestParserFlags:
    def test_no_args_defaults(self):
        with patch("sys.argv", ["hoyo-cli"]):
            args = cli.build_parser().parse_args()
        assert args.config is None
        assert args.accounts is None
        assert args.no_qr is False
        assert args.debug is False
        assert args.command is None

    def test_config_account_and_no_qr_flags(self):
        with patch(
            "sys.argv",
            [
                "hoyo-cli",
                "-c",
                "config.yaml",
                "-a",
                "国服大号",
                "国际服",
                "--no-qr",
                "-d",
            ],
        ):
            args = cli.build_parser().parse_args()
        assert args.config == "config.yaml"
        assert args.accounts == ["国服大号", "国际服"]
        assert args.no_qr is True
        assert args.debug is True

    def test_removed_multi_flag_rejected(self):
        with patch("sys.argv", ["hoyo-cli", "--multi"]), pytest.raises(SystemExit):
            cli.build_parser().parse_args()

    def test_log_flags(self):
        with patch(
            "sys.argv",
            [
                "hoyo-cli",
                "--log-level",
                "DEBUG",
                "--log-dir",
                "/tmp/logs",
                "--no-log",
            ],
        ):
            args = cli.build_parser().parse_args()
        assert args.log_level == "DEBUG"
        assert args.log_dir == "/tmp/logs"
        assert args.no_log is True

    def test_log_level_invalid_rejected(self):
        with patch("sys.argv", ["hoyo-cli", "--log-level", "TRACE"]):
            with pytest.raises(SystemExit):
                cli.build_parser().parse_args()

    def test_help_shows_login_and_omits_template(self):
        help_text = cli.build_parser().format_help()
        assert "login" in help_text
        assert "--no-qr" in help_text
        assert "template" not in help_text


class TestSubcommands:
    def test_login_subcommand(self):
        with patch(
            "sys.argv",
            [
                "hoyo-cli",
                "login",
                "-c",
                "my.yaml",
                "-a",
                "国服-2",
                "--name",
                "新名称",
                "--scope",
                "cloud",
                "--timeout",
                "60",
            ],
        ):
            args = cli.build_parser().parse_args()
        assert args.command == "login"
        assert args.config == "my.yaml"
        assert args.login_account == "国服-2"
        assert args.login_name == "新名称"
        assert args.scope == "cloud"
        assert args.timeout == 60

    def test_login_subcommand_defaults(self):
        with patch("sys.argv", ["hoyo-cli", "login"]):
            args = cli.build_parser().parse_args()
        assert args.command == "login"
        assert args.scope == "all"
        assert args.timeout == 120

    def test_server_subcommand(self):
        with patch("sys.argv", ["hoyo-cli", "server"]):
            args = cli.build_parser().parse_args()
        assert args.command == "server"

    def test_check_subcommand(self):
        with patch(
            "sys.argv",
            ["hoyo-cli", "check", "-c", "config.yaml", "--effective"],
        ):
            args = cli.build_parser().parse_args()
        assert args.command == "check"
        assert args.config == "config.yaml"
        assert args.effective is True

    def test_removed_template_subcommand_rejected(self):
        with (
            patch("sys.argv", ["hoyo-cli", "template"]),
            pytest.raises(SystemExit),
        ):
            cli.build_parser().parse_args()

    def test_format_subcommand(self):
        with patch(
            "sys.argv",
            ["hoyo-cli", "format", "-c", "config.yaml", "--no-backup"],
        ):
            args = cli.build_parser().parse_args()
        assert args.command == "format"
        assert args.config == "config.yaml"
        assert args.no_backup is True

    def test_format_subcommand_optional_config(self):
        with patch("sys.argv", ["hoyo-cli", "format"]):
            args = cli.build_parser().parse_args()
        assert args.command == "format"
        assert args.config is None


class TestRichAndOutputHelpers:
    def test_is_interactive_terminal(self):
        fake_out = MagicMock()
        fake_err = MagicMock()
        fake_out.isatty.return_value = True
        fake_err.isatty.return_value = True
        with patch("sys.stdout", fake_out), patch("sys.stderr", fake_err):
            assert cli._is_interactive_terminal() is True
        fake_err.isatty.return_value = False
        with patch("sys.stdout", fake_out), patch("sys.stderr", fake_err):
            assert cli._is_interactive_terminal() is False

    @pytest.mark.parametrize(
        "val,expected",
        [("plain", False), ("0", False), ("rich", True), ("1", True)],
    )
    def test_use_rich_output_explicit(self, val, expected):
        with patch.dict(os.environ, {"HOYO_ASSISTANT_CLI_OUTPUT": val}):
            assert cli._use_rich_output() is expected

    def test_cli_panel_plain(self, capsys):
        with patch("hoyo_assistant.cli.RICH_OUTPUT", False):
            cli.cli_panel("body content", title="MyTitle")
        captured = capsys.readouterr()
        assert "body content" in captured.out
        assert "MyTitle" in captured.out


@pytest.fixture
def isolated_setting():
    saved = (
        setting.config.copy(),
        deepcopy(setting.runtime_overrides),
        setting.config_path,
    )
    yield setting
    setting.config.clear()
    setting.config.update(saved[0])
    setting.runtime_overrides.clear()
    setting.runtime_overrides.update(saved[1])
    setting.config_path = saved[2]


class TestMainDispatch:
    def test_default_runs_unified_runner_with_account_filter(self, isolated_setting):
        with (
            patch("sys.argv", ["hoyo-cli", "-c", "c.yaml", "-a", "CN-1"]),
            patch("hoyo_assistant.cli.print_banner"),
            patch("hoyo_assistant.cli.loghelper.setup_logger"),
            patch(
                "hoyo_assistant.core.setting.ensure_config_initialized",
                return_value=("c.yaml", False),
            ) as mock_init,
            patch("hoyo_assistant.core.setting.reload_config") as mock_reload,
            patch(
                "hoyo_assistant.cli.runner.run_accounts",
                new=AsyncMock(return_value=(0, "report", [])),
            ) as mock_run,
        ):
            cli.main()
        mock_init.assert_called_once_with("c.yaml")
        mock_reload.assert_called_once_with(config_file="c.yaml", overrides={})
        mock_run.assert_awaited_once_with(
            config_path="c.yaml",
            account_filter=["CN-1"],
            allow_qr_login=None,
        )

    def test_no_qr_flag_disables_auto_qr(self, isolated_setting):
        with (
            patch("sys.argv", ["hoyo-cli", "-c", "c.yaml", "--no-qr"]),
            patch("hoyo_assistant.cli.print_banner"),
            patch("hoyo_assistant.cli.loghelper.setup_logger"),
            patch(
                "hoyo_assistant.core.setting.ensure_config_initialized",
                return_value=("c.yaml", False),
            ),
            patch("hoyo_assistant.core.setting.reload_config"),
            patch(
                "hoyo_assistant.cli.runner.run_accounts",
                new=AsyncMock(return_value=(0, "report", [])),
            ) as mock_run,
        ):
            cli.main()
        mock_run.assert_awaited_once_with(
            config_path="c.yaml",
            account_filter=None,
            allow_qr_login=False,
        )

    def test_login_command_dispatch(self, isolated_setting):
        with (
            patch(
                "sys.argv",
                [
                    "hoyo-cli",
                    "login",
                    "-c",
                    "l.yaml",
                    "--scope",
                    "cloud",
                    "--timeout",
                    "45",
                ],
            ),
            patch("hoyo_assistant.cli.print_banner"),
            patch("hoyo_assistant.cli.loghelper.setup_logger"),
            patch(
                "hoyo_assistant.cli.login_command", new=AsyncMock()
            ) as mock_login_cmd,
        ):
            cli.main()
        mock_login_cmd.assert_awaited_once_with(
            config_path="l.yaml",
            account_selector=None,
            name=None,
            scope="cloud",
            timeout=45,
        )

    def test_check_command_does_not_abort_before_validate(self, isolated_setting):
        with (
            patch("sys.argv", ["hoyo-cli", "check", "-c", "x.yaml"]),
            patch("hoyo_assistant.cli.validate_config") as mock_val,
            patch("hoyo_assistant.cli.print_banner"),
            patch("hoyo_assistant.cli.loghelper.setup_logger"),
            patch("hoyo_assistant.core.setting.reload_config") as mock_reload,
        ):
            cli.main()
        mock_reload.assert_not_called()
        mock_val.assert_called_once_with("x.yaml", False)

    def test_check_subcommand_auto_discovers_default_config(self, isolated_setting):
        with (
            patch("sys.argv", ["hoyo-cli", "check"]),
            patch(
                "hoyo_assistant.core.setting._find_default_config_file",
                return_value="auto.yaml",
            ),
            patch("hoyo_assistant.cli.validate_config") as mock_val,
            patch("hoyo_assistant.cli.print_banner"),
            patch("hoyo_assistant.cli.loghelper.setup_logger"),
        ):
            cli.main()
        mock_val.assert_called_once_with("auto.yaml", False)

    def test_format_command_calls_fill_config(self, isolated_setting):
        with (
            patch("sys.argv", ["hoyo-cli", "format", "-c", "c.yaml", "--no-backup"]),
            patch("hoyo_assistant.cli.fill_config_command") as mock_fill,
            patch("hoyo_assistant.cli.print_banner"),
            patch("hoyo_assistant.cli.loghelper.setup_logger"),
        ):
            cli.main()
        mock_fill.assert_called_once_with("c.yaml", False)

    def test_server_command_starts_console(self, isolated_setting):
        mock_server = MagicMock()
        mock_server.start_interactive_console = MagicMock()
        with (
            patch("sys.argv", ["hoyo-cli", "-c", "srv.yaml", "server"]),
            patch("hoyo_assistant.cli.print_banner"),
            patch("hoyo_assistant.cli.loghelper.setup_logger"),
            patch("hoyo_assistant.core.setting.reload_config"),
            patch("hoyo_assistant.cli.server", mock_server),
            patch("hoyo_assistant.cli.ServerSettings") as mock_srv_cls,
        ):
            cli.main()
        mock_srv_cls.assert_called_once_with(config_path="srv.yaml")
        mock_server.start_interactive_console.assert_called_once()

    def test_main_config_error_exits(self, isolated_setting):
        with (
            patch("sys.argv", ["hoyo-cli", "-c", "bad.yaml"]),
            patch("hoyo_assistant.cli.print_banner"),
            patch(
                "hoyo_assistant.core.setting.ensure_config_initialized",
                return_value=("bad.yaml", False),
            ),
            patch(
                "hoyo_assistant.core.setting.reload_config",
                side_effect=ValueError("bad config"),
            ),
            pytest.raises(SystemExit),
        ):
            cli.main()

    def test_main_debug_uses_debug_log_level(self, isolated_setting):
        with (
            patch("sys.argv", ["hoyo-cli", "-d", "-c", "c.yaml"]),
            patch("hoyo_assistant.cli.print_banner"),
            patch("hoyo_assistant.cli.loghelper.setup_logger") as mock_log,
            patch("hoyo_assistant.cli.run_tasks", new=AsyncMock()),
            patch(
                "hoyo_assistant.core.setting.ensure_config_initialized",
                return_value=("c.yaml", False),
            ),
            patch("hoyo_assistant.core.setting.reload_config"),
        ):
            cli.main()
        mock_log.assert_called_once_with("DEBUG")


class TestLoginCommand:
    @pytest.mark.asyncio
    async def test_login_command_rejects_non_tty(self, isolated_setting):
        with (
            patch(
                "hoyo_assistant.core.qr_login.is_interactive_terminal",
                return_value=False,
            ),
            patch("hoyo_assistant.cli.cli_print"),
            pytest.raises(SystemExit),
        ):
            await cli.login_command()

    @pytest.mark.asyncio
    async def test_login_command_initializes_and_saves_account(
        self, isolated_setting, tmp_path
    ):
        cfg_file = tmp_path / "config.yaml"
        mock_http = MagicMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)
        fake_res = qr_login.QRLoginResult(
            uid="10086",
            device_id="dev-1",
            stoken="v2_st",
            mid="mid1",
            cloud_genshin_token="cloud_tok",
        )
        with (
            patch(
                "hoyo_assistant.core.qr_login.is_interactive_terminal",
                return_value=True,
            ),
            patch("hoyo_assistant.cli.http", mock_http),
            patch(
                "hoyo_assistant.core.qr_login.qr_login_cn",
                new=AsyncMock(return_value=fake_res),
            ),
            patch(
                "hoyo_assistant.core.qr_login.upsert_cn_account",
                new=AsyncMock(return_value=({"name": "国服-10086"}, True)),
            ) as mock_upsert,
            patch("hoyo_assistant.cli.cli_print"),
        ):
            await cli.login_command(config_path=str(cfg_file), scope="all", timeout=90)
        assert cfg_file.exists()
        mock_upsert.assert_awaited_once()


class TestCliFixes:
    def test_version_flag_exits_zero(self):
        with (
            patch("sys.argv", ["hoyo-cli", "--version"]),
            pytest.raises(SystemExit) as e,
        ):
            cli.build_parser().parse_args()
        assert e.value.code == 0

    def test_logging_flags_accepted_after_subcommands(self):
        with patch("sys.argv", ["hoyo-cli", "login", "-d", "--no-log"]):
            args = cli.build_parser().parse_args()
        assert args.command == "login"
        assert args.debug is True
        assert args.no_log is True

    def test_server_subcommand_accepts_config_interval_and_daemon(self):
        with patch(
            "sys.argv",
            ["hoyo-cli", "server", "-c", "srv.yaml", "--interval", "30", "--daemon"],
        ):
            args = cli.build_parser().parse_args()
        assert args.command == "server"
        assert args.config == "srv.yaml"
        assert args.interval == 30
        assert args.daemon is True

    def test_rejects_no_qr_and_account_on_incompatible_subcommands(self):
        with (
            patch("sys.argv", ["hoyo-cli", "--no-qr", "check"]),
            pytest.raises(SystemExit),
        ):
            cli.main()
        with (
            patch("sys.argv", ["hoyo-cli", "-a", "CN-1", "check"]),
            pytest.raises(SystemExit),
        ):
            cli.main()

    def test_cli_print_renders_ansi_qr_and_escapes_brackets(self):
        buf = io.StringIO()
        test_console = Console(file=buf, force_terminal=True, color_system="truecolor")
        qr_line = qr_login.render_qr_terminal(
            "https://example.com?ticket=1", use_ansi=True
        ).splitlines()[0]
        with (
            patch.object(cli, "console", test_console),
            patch.object(cli, "RICH_OUTPUT", True),
        ):
            cli.cli_print(qr_line)
            cli.cli_print("Error in accounts[0] and [bold]", style="red")
        out = buf.getvalue()
        qr_line_out = out.splitlines()[0]
        assert ";30m" not in qr_line_out
        assert "\x1b[30;47m" in qr_line_out
        assert "[bold]" in out

    def test_check_invalid_config_exits_nonzero(self, isolated_setting, tmp_path):
        bad = tmp_path / "bad.yaml"
        bad.write_text("accounts: not_a_list\n", encoding="utf-8")
        with (
            patch("sys.argv", ["hoyo-cli", "check", "-c", str(bad)]),
            patch("hoyo_assistant.cli.print_banner"),
            patch("hoyo_assistant.cli.loghelper.setup_logger"),
            pytest.raises(SystemExit) as e,
        ):
            cli.main()
        assert e.value.code == 1

    def test_default_run_failure_exits_with_status_code(self, isolated_setting):
        with (
            patch("sys.argv", ["hoyo-cli", "-c", "c.yaml"]),
            patch("hoyo_assistant.cli.print_banner"),
            patch("hoyo_assistant.cli.loghelper.setup_logger"),
            patch(
                "hoyo_assistant.core.setting.ensure_config_initialized",
                return_value=("c.yaml", False),
            ),
            patch("hoyo_assistant.core.setting.reload_config"),
            patch(
                "hoyo_assistant.cli.runner.run_accounts",
                new=AsyncMock(return_value=(1, "failed", [])),
            ),
            pytest.raises(SystemExit) as e,
        ):
            cli.main()
        assert e.value.code == 1

    @pytest.mark.parametrize(
        "argv,expected_cmd,expected_cfg",
        [
            (["hoyo-cli", "-c", "a.yaml", "login"], "login", "a.yaml"),
            (["hoyo-cli", "login", "-c", "b.yaml"], "login", "b.yaml"),
            (["hoyo-cli", "-c", "a.yaml", "check"], "check", "a.yaml"),
            (["hoyo-cli", "check", "-c", "b.yaml"], "check", "b.yaml"),
            (["hoyo-cli", "-c", "a.yaml", "list"], "list", "a.yaml"),
            (["hoyo-cli", "list", "-c", "b.yaml"], "list", "b.yaml"),
        ],
    )
    def test_unified_config_flag_before_and_after_subcommand(
        self, argv, expected_cmd, expected_cfg
    ):
        with patch("sys.argv", argv):
            args = cli.build_parser().parse_args()
        assert args.command == expected_cmd
        assert args.config == expected_cfg

    @pytest.mark.asyncio
    async def test_login_command_skips_reload_when_newly_created(
        self, isolated_setting, tmp_path
    ):
        cfg_file = tmp_path / "fresh.yaml"
        mock_http = MagicMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)
        fake_res = qr_login.QRLoginResult(uid="10086", device_id="dev-1", stoken="v2_s")
        with (
            patch(
                "hoyo_assistant.core.qr_login.is_interactive_terminal",
                return_value=True,
            ),
            patch("hoyo_assistant.cli.http", mock_http),
            patch.object(setting, "reload_config") as mock_reload,
            patch(
                "hoyo_assistant.core.qr_login.qr_login_cn",
                new=AsyncMock(return_value=fake_res),
            ),
            patch(
                "hoyo_assistant.core.qr_login.upsert_cn_account",
                new=AsyncMock(return_value=({"name": "CN"}, True)),
            ),
            patch("hoyo_assistant.cli.cli_print"),
        ):
            await cli.login_command(config_path=str(cfg_file))
        mock_reload.assert_not_called()

    def test_list_subcommand_displays_redacted_overview_and_handles_empty(
        self, isolated_setting, tmp_path
    ):
        cfg_file = tmp_path / "accounts.yaml"
        cfg_file.write_text(
            "enable: true\n"
            "push:\n"
            "  default: [tg_main]\n"
            "  targets:\n"
            "    tg_main:\n"
            "      type: telegram\n"
            "accounts:\n"
            "  - name: 主号\n"
            "    region: cn\n"
            "    cookie: stuid=123;stoken=v2_SUPER_SECRET;ltoken_v2=SECRET_LT;mid=m1;\n"
            "    bbs:\n"
            "      enable: true\n"
            "      forums: [2, 5]\n"
            "    games: [genshin]\n"
            "    cloud:\n"
            "      genshin: SUPER_SECRET_CLOUD\n"
            "  - name: 国际\n"
            "    region: os\n"
            "    enable: false\n"
            "    push: []\n",
            encoding="utf-8",
        )
        buf = io.StringIO()
        plain_console = Console(file=buf, no_color=True, force_terminal=False)
        with (
            patch("sys.argv", ["hoyo-cli", "list", "-c", str(cfg_file)]),
            patch.object(cli, "console", plain_console),
            patch.object(cli, "RICH_OUTPUT", False),
            patch("hoyo_assistant.cli.print_banner"),
            patch("hoyo_assistant.cli.loghelper.setup_logger"),
        ):
            cli.main()
        out = buf.getvalue()
        assert "cn#1" in out
        assert "主号" in out
        assert "os#2" in out
        assert "stoken+web" in out
        assert "bbs(2)" in out
        assert "games:genshin" in out
        assert "cloud:genshin" in out
        assert "SUPER_SECRET" not in out
        assert "SECRET_LT" not in out

        buf_rich = io.StringIO()
        rich_console = Console(file=buf_rich, force_terminal=True, width=120)
        with (
            patch("sys.argv", ["hoyo-cli", "list", "-c", str(cfg_file)]),
            patch.object(cli, "console", rich_console),
            patch.object(cli, "RICH_OUTPUT", True),
            patch("hoyo_assistant.cli.print_banner"),
            patch("hoyo_assistant.cli.loghelper.setup_logger"),
        ):
            cli.main()
        rich_out = buf_rich.getvalue()
        assert "cn#1" in rich_out
        assert "SUPER_SECRET" not in rich_out

        # Empty accounts renders empty notice without crashing
        empty_file = tmp_path / "empty.yaml"
        empty_file.write_text("enable: true\naccounts: []\n", encoding="utf-8")
        buf2 = io.StringIO()
        with (
            patch("sys.argv", ["hoyo-cli", "list", "-c", str(empty_file)]),
            patch.object(cli, "console", Console(file=buf2, no_color=True)),
            patch.object(cli, "RICH_OUTPUT", False),
            patch("hoyo_assistant.cli.print_banner"),
            patch("hoyo_assistant.cli.loghelper.setup_logger"),
        ):
            cli.main()
        assert str(empty_file) in buf2.getvalue()

        # Missing config file exits non-zero
        with (
            patch("sys.argv", ["hoyo-cli", "list", "-c", str(tmp_path / "nope.yaml")]),
            patch("hoyo_assistant.cli.print_banner"),
            patch("hoyo_assistant.cli.loghelper.setup_logger"),
            pytest.raises(SystemExit) as e,
        ):
            cli.main()
        assert e.value.code == 1
