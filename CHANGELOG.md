# Changelog

所有显著变更记录于此。格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本遵循[语义化版本](https://semver.org/lang/zh-CN/)。

## [1.0.0] - 2026-11-25

### Breaking
- **统一 v3 配置模型（无历史兼容包袱）**：废弃旧版双配置文件与顶层键（`cn`、`os`、`client`、`mihoyobbs`、`account`、`games`），若检测到旧版顶层键将直接拒绝加载并提示迁移；单份 `config.yaml` / `config.yml` 内仅保留顶层 `enable`、`push` 与平级 `accounts` 列表（`region: cn | os`），每个账号仅需单一 `cookie` 字段。
- **配置格式自动初始化与零模板化**：移除静态配置模板与 `template` 子命令、移除旧 `--multi` 运行参数；首次运行 `hoyo-assistant` 或 `hoyo-assistant login` 时自动生成极简 `config.yaml`。
- **推送模型收敛**：`push.targets` 采用按 `type` 区分的 21 种强类型通道与命名引用调度（`push.default` + 账号级 `push`），移除多余的 `WinToastPushTarget.enable` 开关与 `setting.config_raw` / `setting.path` 冗余全局状态。

### Added
- **终端扫码登录与无感续期（国服 & 云原神）**：新增 `hoyo-assistant login` 子命令及交互终端 10 秒自动扫码兜底（支持 `--scope all|bbs|cloud`、`--account`、`--name`、`--timeout` 及 `--no-qr`），支持按扫码 UID 自动覆盖更新同一账号凭据并杜绝重复条目；非交互环境（CI / Docker / `server` 调度）自动跳过扫码弹窗。
- **账号概览命令 `list`**：新增 `hoyo-cli list`（支持 `-c/--config`），安全展示全部账号的 `region#idx`、名称、启用状态、启用任务、脱敏凭据状态及解析后的推送目标。
- **新游戏与版块扩展**：米游社社区支持从在线游戏列表接口自动同步未知 `bbs.forums` 版块 ID；新增国服/国际服自定义活动扩展能力（`custom_games`）与国服/国际服云绝区零签到支持。
- **CLI 与服务端能力增强**：新增 `-V/--version`、共享日志参数（`--log-level`、`--log-dir`、`--no-log`）、`server` 调度参数（`-c/--config`、`--interval`、`--daemon` 守护模式），以及配置校验非致命警告检查（`check` / `collect_config_warnings`）和非零退出码约定。

### Changed
- **统一单账号与多账号执行引擎**：将原有分散执行入口收口为 `runner.executor`（`run_accounts` / `run_account`），统一账号隔离生命周期、公共 HTTP GET 缓存复用（`clear_cache(include_public=False)`）及状态汇总。
- **米游社验证码早期熔断**：当某轮论坛签到全部触发验证码（`1034`）且 0 成功、无非验证码错误时，立即跳过第 2 轮重试与多余任务查询及等待。
- **CLI 与缓存加载收敛**：根命令及所有子命令的 `-c/--config` 统一收敛至 `args.config`，子命令前后传参行为一致；`login` 新建配置及 `run_accounts` 同路径复用时跳过重复读取 YAML，`server` 周期调度通过 `force_reload=True` 支持配置热更新。
- **公共常量与工具函数收口**：将布尔环境变量解析、TTY/Rich 检测、Cookie 解析与标准化排版、`User-Agent` 规范化、Cookie 字段表及推送默认地址集中收敛至 `core/constants.py` 与 `core/tools.py`。

### Fixed
- **凭据与环境变量隔离**：修复 `use_env=True` 时可能绕过严格顶层 Schema 校验的问题；保存配置时自动还原 `HOYO_ASSISTANT_*` 环境变量与运行时覆盖，防止环境变量被误写回 `config.yaml`。
- **Cookie 误清与任务异常判定**：修复米游社任务列表接口 `-100` 时误删完整 Cookie 导致游戏签到连带失效的问题（改为仅清理 `stoken`）；引入结构化 `TaskReport`，修正云游戏与国际服签到失败被吞为成功、以及部分非验证码错误被误判为触发验证码的问题；修复账号列表接口 `-100` 无穷递归风险。
- **HTTP 客户端、终端输出与推送稳定性**：修复 429 最终重试返回空响应、缓存 `MockResponse` 异步上下文退出、`default_qr_printer`/`cli_print` 中 ANSI 二维码渲染与 Rich 方括号转义、以及推送信道 HTTP `>= 400` 漏判、Telegram API 前缀、钉钉签名分隔符和 SMTP 资源释放问题；修复文件日志在仅导入模块时过早创建的问题。

### Removed
- **废弃模板与旧 runner 目录**：移除 `config/config.yaml.template`、`core/captcha.py`、`runner/single_account.py` 与 `runner/multi_account.py`。
