# AGENTS Guide

## Purpose and Entry

- This repo automates HoYoLAB/MiYoUShe daily tasks plus optional push notifications.
- Main entrypoint is `hoyo-cli` or `hoyo-assistant` -> `src/hoyo_assistant/cli.py:main` (defined in `pyproject.toml`).
- Single unified root config (`config.yaml` / `config.yml`, auto-discovered next to frozen `.exe`, in cwd, or at repo root; auto-initialized with minimal `enable: true` / `accounts: []` on first run when absent; or passed via `-c/--config`) contains peer `cn` and `os` entries in `accounts`; use `--account` (`-a`) to filter specific accounts on run.

## Build and CI/CD

- **Build**: Use `.github/workflows/build.yml` for CI validation and artifact builds.
    - Triggers on push/PR/dispatch.
    - Runs `ruff`, `mypy`, and `pytest`.
    - Builds Wheel and Sdist packages.
    - Compiles standalone executable using PyInstaller (`dist/hoyo-assistant`) and runs `--version` / `--help` smoke checks.
- **Release**: Use `.github/workflows/release.yml` for tagged releases (`v*` tag push or `workflow_dispatch`).
    - Validates `ruff`, `mypy`, `pytest`, version match with `pyproject.toml`, and `CHANGELOG.md` (`## [X.Y.Z]`).
    - Publishes `.whl`, `.tar.gz`, Windows/Linux standalone binaries, and `checksums.txt` to GitHub Releases using notes extracted from `CHANGELOG.md`.
- **Test & Run**: Use `.github/workflows/test_run.yml` for execution.
    - Triggers on schedule/dispatch.
    - Runs `pytest` for unit tests.
    - Fetches `secrets.CONFIG` -> `config.yaml` and runs `hoyo-cli`.

## Runtime Environment Variables (Non-Pydantic)

All environment variable names are centralized in `core/constants.py:EnvVar`. These variables control system behavior outside the main configuration schema:

- **Logging**:
    - `HOYO_ASSISTANT_LOG_DIR` (default: `logs`): Log output directory.
    - `HOYO_ASSISTANT_LOG_ROTATION` (default: `10 MB`): Log rotation size.
    - `HOYO_ASSISTANT_LOG_RETENTION` (default: `1 week`): Log retention period.
    - `HOYO_ASSISTANT_LOG_CONSOLE_ENABLE` (default: `true`): Toggle console logging.
    - `HOYO_ASSISTANT_LOG_FILE_ENABLE` (default: `true`): Toggle file logging.
    - `HOYO_ASSISTANT_LOG_LEVEL` (default: `INFO`): Global log level.

- **Interface**:
    - `HOYO_ASSISTANT_CLI_OUTPUT`: Output mode (`rich`, `plain`, `auto`).
    - `HOYO_ASSISTANT_LANGUAGE`: Force UI language (`zh_CN`, `en_US`).
    - `LANG`: System language fallback.

- **Validation**:
    - `HOYO_ASSISTANT_PUSH__ENABLE` (default: `false`): Global master switch for push notifications (supports explicit `true`/`false`).

## Architecture Quick Map

- `src/hoyo_assistant/cli.py`: unified arg parsing (`build_parser` with `-V/--version`, shared `-c/--config` & logging flags), first-run config bootstrap (`ensure_config_initialized`), unified runner dispatch, `--account` filter, `list`/`login`/`check`/`format`/`server` (`--interval`, `--daemon`) subcommands, and non-zero status exit codes.
- `src/hoyo_assistant/core/qr_login.py`: terminal QR login for CN accounts (`qr_login_cn`, `render_qr_terminal`, `exchange_stoken_by_game_token`, `exchange_cloud_genshin_token`, `upsert_cn_account` with UID overwrite deduplication, `is_interactive_terminal`).
- `src/hoyo_assistant/core/constants.py`: centralized constants (`EnvVar`, `StatusCode`, `RetCode`, cookie ordering/alias keys, push default URLs, protocol headers/UAs/URLs, delay ranges, built-in game & forum tables).
- `src/hoyo_assistant/core/tools.py`: crypto/DS signing, lifecycle ID helpers, `parse_bool_str`, `is_tty`, `use_rich_output`, `parse_cookie`/`format_cookie`/`tidy_cookie`, and `resolve_user_agent`/`get_useragent`.
- `src/hoyo_assistant/core/setting.py` + `core/setting_schema.py`: unified v3 strict Pydantic schema (`enable`, `push`, `accounts` discriminated union of `CNAccountConfig` / `OSAccountConfig` sharing `AccountBase` & `CustomGameBase`, explicit legacy v2 key rejection, `collect_config_warnings`). Both CN and OS use a single `cookie` credential field; `_find_default_config_file()` resolves `config.yaml`/`.yml` next to frozen `.exe` (`sys.frozen`), in cwd, or at repo root. `_overlay_diffs`/`_restore_overlay_diffs` prevent env/override values from persisting on `save_config_sync()`. `setting.set_current_account()` / `setting.get_account()` bind the active account dict for in-place credential refresh and clearing (`clear_cookie`, `clear_stoken`, `clear_cloud_token`).
- `src/hoyo_assistant/core/login.py`: parses `stuid`/`stoken`/`mid` and web tokens from the active CN account's `cookie` string (`get_stoken`, `get_uid`, `get_mid`, `get_stoken_cookie`, `get_web_cookie`), stripping `stoken`/`stuid` from web/Luna requests and hydrating missing V2 web tokens via Passport exchange.
- `src/hoyo_assistant/core/loghelper.py` + `core/i18n.py`: frozen-executable aware defaults (`<exe_dir>/logs` and `sys._MEIPASS/hoyo_assistant/locales`).
- `src/hoyo_assistant/runner/executor.py`: unified peer-account orchestration (`run_accounts` with `force_reload` avoiding duplicate loads when matching `setting.config_path`, `run_account`, `handle_cn_login`), per-account isolation (keeping unauthenticated public HTTP cache via `clear_cache(include_public=False)`), summary & status aggregation, and `dispatch_push` call.
- `src/hoyo_assistant/core/request.py`: shared async HTTP client (retry + GET cache, stdlib `json`). Exports a global `http` client instance used across modules; supports TTL caching (GET, skips `retcode != 0`), `MockResponse` for cache hits, and tenacity-based retries.
- `src/hoyo_assistant/core/push.py`: `PushHandler` named-target dispatch reading `push.targets` (`type`-discriminated across 21 providers), `push.default`, and `push.merge` (per-target aggregation & independent `error_only` evaluation via `dispatch_results`).
- `src/hoyo_assistant/tasks/**`: feature modules (`chinese`, `overseas`, `community`, `base`) reading active account via `setting.get_account()` and exposing `run_task()`. `tasks/community/miyoushe.py` dynamically resolves unknown forum IDs in `bbs.forums` via `API_BBS_GAME_LIST`.
- `src/hoyo_assistant/server.py`: interactive scheduler / server console (`ServerSettings`, `start_interactive_console`, `scheduler_loop`, `execute_task`) calling `runner.run_accounts`.
