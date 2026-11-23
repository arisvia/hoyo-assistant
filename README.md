# HoyoAssistant

HoYoLAB/MiYoUShe 每日任务自动化助手。

## 功能

- **社区任务**: 米游社社区讨论区签到（支持从米游社接口自动同步新上线游戏版块 ID）
- **游戏签到**: 国服/国际服游戏每日签到，支持通过 `cn.custom_games` / `os.custom_games` 零改代码扩展新游戏
- **云游戏签到**: 原神、绝区零云游戏签到（国服/国际服）
- **多账户支持**: 支持多账户配置与运行
- **推送通知**: 支持 21 种强类型校验推送渠道（Telegram、Discord、ServerChan、Bark、飞书/钉钉/企微、WxPusher、ntfy、SMTP 等）
- **国际化**: 支持中文和英文界面

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

### 单账户模式

```bash
hoyo-assistant --config config/config.yaml
```

### 多账户模式

```bash
hoyo-assistant --multi --config config/
```

### 服务器模式

```bash
hoyo-assistant server
```

### 配置校验与模板生成

```bash
hoyo-assistant check --config config/config.yaml
hoyo-assistant template --output config/config.yaml
```

## 配置（v2 规范）

配置文件按 **国服 (`cn`) / 国际服 (`os`) / 客户端 (`client`) / 推送 (`push`)** 四个区域内聚组织，完整示例见 [config/config.yaml.template](config/config.yaml.template)。

### 基础配置示例

```yaml
enable: true

cn:
  cookie: "your_cookie_here"
  stuid: "your_stuid"
  stoken: "v2_your_stoken_here"
  mid: "your_mid"
  bbs:
    enable: true
    forums: [2, 5]                 # 新游戏版块 ID（如 9=因缘精灵、10=星布谷地）自动同步
  games: [genshin, honkai_sr, zzz] # 支持 genshin, honkai_sr, zzz, honkai3rd, tears_of_themis, honkai2
  cloud:
    genshin: ""                    # 填写 token 即启用云游戏签到
    zzz: ""

os:
  cookie: ""
  lang: "zh-cn"
  games: []                        # 支持 genshin, honkai_sr, zzz, honkai3rd, tears_of_themis
  cloud:
    genshin: ""
    zzz: ""

push:
  enable: false
  error_only: false
  block_keys: []
  channels:                        # active 留空时自动向 channels 内已配置渠道推送
    telegram:
      bot_token: "YOUR_BOT_TOKEN"
      chat_id: "YOUR_CHAT_ID"
```

### 新游戏扩展配置（无需等待发版）

米游社社区版块只需在 `cn.bbs.forums` 中填入对应版块 ID，运行时会自动通过 `apihub/wapi/getGameList` 同步元数据。

新游戏公测并开放福利中心每日签到（如《星布谷地》《崩坏：因缘精灵》）后，可直接在配置中添加 `custom_games` 条目：

```yaml
cn:
  custom_games:
    planet:
      enable: true
      name: "星布谷地"
      game_biz: "hyg_cn"
      act_id: "e2026xxxxxxxxxx"
      signgame: "planet"
      # api_base: "https://api-takumi.mihoyo.com/event/luna/hyg"  # 可选，默认标准 luna 接口

os:
  custom_games:
    planet:
      enable: true
      name: "Petit Planet"
      act_id: "e2026xxxxxxxxxx"
      signgame: "planet"
```

### 环境变量

所有配置项均可通过环境变量覆盖，格式为 `HOYO_ASSISTANT_<SECTION>__<KEY>`：

```bash
export HOYO_ASSISTANT_CN__COOKIE="your_cookie"
export HOYO_ASSISTANT_CN__STOKEN="v2_your_stoken"
export HOYO_ASSISTANT_OS__COOKIE="your_os_cookie"
export HOYO_ASSISTANT_PUSH__ENABLE="true"
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
