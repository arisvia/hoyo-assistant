# AGENTS Guide

## Purpose and Entry

- This repo automates HoYoLAB/MiYoUShe daily tasks plus optional push notifications.
- Main entrypoint is `hoyo-cli` or `hoyo-assistant` -> `src/hoyo_assistant/cli.py:main` (defined in `pyproject.toml`).
- Direct run mode defaults to single account; add `--multi` for multi-account.

## Build and CI/CD

- **Build**: Use `.github/workflows/build.yml` to generate artifacts.
    - Triggers on push/dispatch.
    - Builds Wheel and Sdist packages.
    - Compiles standalone executable using PyInstaller (`dist/hoyo-assistant`).
- **Test & Run**: Use `.github/workflows/test_run.yml` for execution.
    - Triggers on push/schedule/dispatch.
    - Runs `pytest` for unit tests.
    - Runs `tests/test_smoke.py` for integration validation.

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

- `src/hoyo_assistant/cli.py`: arg parsing (`build_parser`), run-mode resolution, config bootstrap/reload, runner dispatch.
- `src/hoyo_assistant/core/constants.py`: centralized constants (`EnvVar`, `StatusCode`, `RetCode`, protocol headers/UAs/URLs, delay ranges, built-in game & forum tables).
- `src/hoyo_assistant/core/setting.py` + `core/setting_schema.py`: pure v2 strict Pydantic config schema + file/env merge + runtime overrides. Top-level config keys: `enable`, `cn` (`cookie`/`stuid`/`stoken`/`mid`/`retries`/`bbs`/`games`/`black_list`/`custom_games`/`cloud`), `os` (`cookie`/`lang`/`games`/`custom_games`/`cloud`), `client` (`user_agent` + `device`), `push` (`enable`/`error_only`/`block_keys`/`active`/`channels` with strongly typed per-channel models). `client.user_agent` is the single global UA source; empty falls back to the default template (see `tools.resolve_user_agent`).
- `src/hoyo_assistant/runner/single_account.py`: one-account orchestration + optional push.
- `src/hoyo_assistant/runner/multi_account.py`: config target discovery, per-account loop, summary aggregation.
- `src/hoyo_assistant/core/request.py`: shared async HTTP client (retry + GET cache, stdlib `json`). Exports a global `http` client instance used across modules; supports TTL caching (GET, skips `retcode != 0`), `MockResponse` for cache hits, and tenacity-based retries.
- `src/hoyo_assistant/core/push.py`: `PushHandler` provider dispatch reading typed configs from `push.channels` (auto-dispatches all configured channels when `push.active` is empty).
- `src/hoyo_assistant/tasks/**`: feature modules (`chinese`, `overseas`, `community`, `base`) exposing `run_task()`. `tasks/community/miyoushe.py` dynamically resolves unknown forum IDs in `cn.bbs.forums` via `API_BBS_GAME_LIST`.
- `src/hoyo_assistant/server.py`: interactive scheduler / server console (implements `ServerSettings`, `start_interactive_console`, `scheduler_loop` and `execute_task`). Used by the `server` CLI subcommand to run scheduled multi/single account runs with an interactive prompt.
