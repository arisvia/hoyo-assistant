# HoyoAssistant

HoYoLAB/MiYoUShe 每日任务自动化助手。

## 功能

- **零模板初始化与终端扫码登录**: 首次运行无需任何模板即可自动初始化 `config.yaml`；支持 `hoyo-assistant login` 终端扫码一码同步获取国服米游社 Cookie 与云原神 Token，同 UID 自动覆盖更新不重复，交互终端失败自动 10 秒扫码续期、非交互环境立即跳过
- **平级多账号架构**: 单份根目录 `config.yaml` 内平级管理任意数量的国服（`region: cn`）与国际服（`region: os`）账号，均仅需单个 `cookie` 字段，凭据与任务互不干扰
- **账号概览**: 支持 `hoyo-assistant list` 安全展示全部账号的启用状态、启用任务、脱敏凭据状态与推送目标
- **社区任务**: 米游社社区讨论区签到（支持从米游社接口自动同步新上线游戏版块 ID）
- **游戏签到**: 国服/国际服游戏每日签到，支持通过 `custom_games` 零改代码扩展新游戏
- **云游戏签到**: 原神、绝区零云游戏签到（国服/国际服）
- **命名多级推送**: 全局 `push.targets` 集中定义推送鉴权（支持 21 种强类型渠道、同渠道多实例），支持默认汇总推送、单账号指定独立目标或静默
- **国际化**: 支持中文和英文界面
- **开箱即用**: 独立打包为单文件可执行程序时，自动读取程序同级或当前目录的 `config.yaml`/`.yml`，日志默认输出至同级 `logs/`；也支持通过 `-c/--config` 显式指定路径

## 安装

### 使用 uv（推荐）

```bash
# 从 PyPI 安装（发布后）
uv pip install hoyo-assistant

# 或从源码安装
git clone https://github.com/arisvia/hoyo-assistant.git
cd hoyo-assistant
uv sync
```

### 使用 pip

```bash
pip install hoyo-assistant

# 或从源码安装
git clone https://github.com/arisvia/hoyo-assistant.git
cd hoyo-assistant
pip install -e .
```

## 快速开始

安装包后同时提供 `hoyo-assistant` 与 `hoyo-cli` 两个命令行入口。

### 终端扫码登录（国服 & 云原神）

```bash
# 扫码新增国服账号；若扫描已存在的同 UID 账号则直接覆盖其凭据，不产生重复条目
hoyo-assistant login

# 指定仅更新某账号的云原神 Token（默认 --scope all 同时更新社区 Cookie 与云原神）
hoyo-assistant login -a 国服-2 --scope cloud
```

> 提示：正常执行 `hoyo-assistant` 时，若在**交互式终端（TTY）**遇到凭据缺失/失效或全新初始化无账号，会自动弹出 10 秒倒计时二维码（无人扫码即跳过）；在 **CI / 计划任务 / `server` 后台调度**等非交互环境下会**立即跳过**，不阻塞运行。可通过 `--no-qr` 显式关闭自动弹窗。

### 执行任务

```bash
# 首次无配置会自动初始化 config.yaml；默认读取可执行文件同级或当前目录的 config.yaml（.yml）
hoyo-assistant

# 指定配置文件（也适用于 list / login / check / format / server 任意子命令）
hoyo-assistant -c path/to/config.yaml

# 仅执行指定账号（按名称、自动标签如 cn#1，或 1-based 序号过滤）
hoyo-assistant -a 国服大号 国际服

# 查看版本 / 查看脱敏后的账号列表概览
hoyo-assistant -V
hoyo-assistant list

# 日志控制（全局及所有子命令均支持）
hoyo-assistant -d --log-dir ./my_logs
hoyo-assistant --no-log
```

### 服务器模式

```bash
# 交互式调度控制台
hoyo-assistant server

# 无交互守护模式（Docker / systemd）并每 360 分钟运行一次
hoyo-assistant server -c path/to/config.yaml --interval 360 --daemon
```

### 配置校验与格式化

```bash
# 按严格 v3 模型校验配置并提示非致命警告（校验失败时以退出码 1 退出）
hoyo-assistant check
hoyo-assistant check -c path/to/config.yaml --effective
hoyo-assistant format --no-backup
```

### 退出码（Exit Codes）

| 退出码 | 含义 |
|--------|------|
| `0` | 全部启用账号执行成功（或仅触发需要人工干预的验证码） |
| `1` | 全部账号执行失败、配置校验失败、或运行时出错 |
| `2` | 部分账号执行成功、部分账号失败 |

## 配置（v3 统一规范）

无需维护额外配置模板文件：直接运行 `hoyo-assistant` 或 `hoyo-assistant login` 即可自动创建最小可用的 `config.yaml`。顶层划分为全局开关（`enable`）、命名推送层（`push`）与平级账号列表（`accounts`）。v3 为严格校验模式，若检测到已废弃的顶层键（如 `cn`、`os`、`client`、`mihoyobbs`、`account`、`games`）或未知字段将直接报错提示迁移。

### 基础配置示例

```yaml
enable: true

push:
  enable: false
  error_only: false
  merge: true                     # true=同目标合并为 1 条汇总报告；false=逐账号分条发送
  block_keys: []
  default: [tg_main]              # 账号未单独配置 `push` 时继承此默认目标
  targets:                        # 同一种渠道可配置多套命名目标
    tg_main:
      type: telegram
      bot_token: "YOUR_BOT_TOKEN"
      chat_id: "YOUR_CHAT_ID"
    tg_friend:
      type: telegram
      bot_token: "OTHER_BOT_TOKEN"
      chat_id: "FRIEND_CHAT_ID"

accounts:
  - name: "国服大号"
    region: cn
    # push: 省略则继承 push.default（合入 tg_main 汇总）
    # 完整 Cookie 字符串（包含 stuid / stoken / mid 等；仅填 stuid=...;stoken=v2_...;mid=...; 也会自动换票补齐 Web Token）
    cookie: "your_full_cn_cookie"
    bbs:
      enable: true
      forums: [2, 5]              # 新游戏版块 ID（如 9=因缘精灵、10=星布谷地）自动同步
    games: [genshin, honkai_sr, zzz]
    cloud:
      genshin: ""
      zzz: ""

  - name: "国服小号"
    region: cn
    push: tg_friend               # 单独走 tg_friend 独立推送
    cookie: "your_full_cn_cookie_2"
    games: [genshin]

  - name: "国际服"
    region: os
    push: false                   # 显式静默，不推送
    cookie: "your_os_cookie"
    lang: "zh-cn"
    games: [honkai_sr, zzz]
```

### 国服 (`cn`) 与国际服 (`os`) 字段对比

| 类别 | 共用字段 | 仅 `region: cn` | 仅 `region: os` |
|------|----------|------------------|------------------|
| 基础与推送 | `name`、`enable`、`push`、`cookie`、`user_agent`、`cloud` | `device` | `lang` |
| 社区与游戏 | `games`、`custom_games` | `bbs`、`black_list` | — |

### 环境变量

顶层开关与推送总配置支持环境变量覆盖：

```bash
export HOYO_ASSISTANT_ENABLE="true"
export HOYO_ASSISTANT_PUSH__ENABLE="true"
export HOYO_ASSISTANT_PUSH__ERROR_ONLY="false"
export HOYO_ASSISTANT_PUSH__MERGE="true"
```

## 运行时环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `HOYO_ASSISTANT_LOG_DIR` | `logs` | 日志输出目录 |
| `HOYO_ASSISTANT_LOG_ROTATION` | `10 MB` | 日志轮转大小 |
| `HOYO_ASSISTANT_LOG_RETENTION` | `1 week` | 日志保留时间 |
| `HOYO_ASSISTANT_CLI_OUTPUT` | `auto` | 输出模式 (rich/plain/auto) |
| `HOYO_ASSISTANT_LANGUAGE` | - | 强制界面语言 (zh_CN/en_US) |

## 开发

### 安装开发依赖

```bash
uv sync --extra dev
# 或 pip install -e ".[dev]"
```

### 运行测试

```bash
uv run pytest
```

### 代码检查

```bash
uv run ruff check .
uv run mypy src/
```

## 许可证

MIT License
