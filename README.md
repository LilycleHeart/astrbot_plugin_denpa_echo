# AstrBot Denpa Echo 插件

> 接入 Minimax 官方 TTS API 的全功能语音合成插件

## 功能特性

- **Minimax 官方 API 全功能覆盖**
  - 同步/异步语音合成（短文本/长文本）
  - 流式合成（预留）
  - 语音克隆（上传音频 → 克隆自定义音色）
  - 音色列表查询与删除
  - 发音词典（自定义注音）
  - 声音效果器（音高/强度/音色调整、空旷回音等音效）
  - 情绪控制（happy/sad/angry 等 7 种）
  - 混音权重（最多 4 种音色混合）
  - 语气词标签（speech-2.8 系列：`(laughs)` `(sighs)` 等 22 种）
  - LaTeX 公式朗读、文本规范化
  - 语言增强（40+ 语种）

- **双发送模式可配置**
  - **拦截模式**：拦截 bot 回复，TTS 合成后与文本一起发（或仅发语音）
  - **追加模式**：bot 先发文本，后台异步合成语音，完成后追加
  - **关闭模式**：禁用自动 TTS，仅保留 `/tts` 手动指令

- **合成前 LLM 润色**
  - 调用 LLM 对将朗读的文本清洗润色
  - 去除 markdown/emoji/代码块/URL，调整语气
  - 可选指定 Provider 或使用会话默认
  - 失败可降级使用原文

- **Signal 声场控制台面板**
  - 通过 AstrBot Plugin Pages 提供 WebUI 高级面板
  - 采用 Signal 设计语言（亚克力/Mica 材质），**14px 圆角**
  - 支持**动态取色**（跟随 AstrBot 亮/暗主题）与**静态取色**（自定义品牌色）
  - 三种背景模式：跟随主题 / 主题色渐变 / 自定义颜色
  - 状态总览、音色管理（试听）、语音克隆、调试试听、运行日志、界面设置

## 安装

### 方式一：WebUI 插件市场
在 AstrBot WebUI → 插件管理 → 搜索 `minimax_tts` 安装。

### 方式二：手动克隆
```bash
cd AstrBot/data/plugins
git clone https://github.com/LilycleHeart/astrbot_plugin_minimax_tts
```
然后重启 AstrBot 或在 WebUI 重载插件。

### 系统依赖（可选但推荐）

插件需要将 Minimax 输出的音频转换为 wav 格式（AstrBot 的语音组件只支持 wav）：

- **mp3/flac → wav**：需要安装 **ffmpeg**
  - Windows：`choco install ffmpeg` 或下载放入 PATH
  - Linux：`apt install ffmpeg` / `yum install ffmpeg`
  - macOS：`brew install ffmpeg`
- **若不安装 ffmpeg**：在配置中将 `audio.format` 设为 `wav`（体积大，不支持流式）
- **pcm 格式**：无需 ffmpeg，插件自动加 wav 头

## 配置

安装后，在 AstrBot WebUI → 插件管理 → Denpa Echo → 配置：

### 必填
- **API Key**：Minimax 开放平台 > 账户管理 > 接口密钥
- **Group ID**：国内平台必填，国际平台留空
- **API 区域**：china（api.minimaxi.com）/ international（api.minimax.io）

### 语音合成
- 模型版本（推荐 `speech-02-hd` 稳定，`speech-2.8-hd` 支持语气词）
- 音色 ID（可在控制台面板试听后复制）
- 语速 / 音量 / 语调 / 情绪 / 语言增强

### 发送模式
- `intercept`：拦截 bot 回复与语音一起发（默认）
- `append`：先发文本再追加语音
- `disabled`：关闭自动 TTS

### LLM 润色（可选）
- 启用后，每次合成前调用 LLM 清洗文本
- 可指定 Provider 或使用会话默认
- 支持自定义润色 prompt

## 使用

### 自动模式（拦截/追加）
配置好发送模式后，bot 每次回复会自动触发 TTS。

### 手动指令
- `/tts <文本>`：手动合成语音
- `/tts_voices`：列出可用音色
- `/tts_mode [intercept|append|disabled]`：查看/切换模式
- `/tts_clear_cache`：清空音频缓存
- `/tts_panel`：提示打开 WebUI 控制台

### WebUI 控制台面板
AstrBot WebUI → 插件管理 → Denpa Echo → 打开「控制台」页面：

- **状态总览**：API 状态、今日合成次数、缓存大小、ffmpeg 可用性
- **音色管理**：加载系统/克隆音色，点击试听
- **语音克隆**：上传音频文件 → 输入自定义 voice_id → 克隆 → 试听
- **调试试听**：输入任意文本 + 选择参数 → 合成 → 在线播放
- **运行日志**：最近 200 条合成记录
- **界面设置**：取色模式、品牌色、背景模式、圆角大小

## 平台兼容性

语音消息（Record）并非所有平台都支持：

| 平台 | 语音支持 |
|------|---------|
| QQ 个人号（aiocqhttp） | ✅ |
| Telegram | ✅ |
| Discord | ✅ |
| 企业微信 | ✅ |
| QQ 官方接口 | ❌ |
| 飞书 | ❌ |
| 钉钉 | ❌ |

不支持语音的平台会自动降级为纯文本回复。

## 目录结构

```
astrbot_plugin_minimax_tts/
├── main.py                  # 主入口
├── metadata.yaml            # 元数据
├── _conf_schema.json        # 配置 schema
├── requirements.txt         # Python 依赖
├── minimax/                 # Minimax API 客户端
│   ├── client.py            # HTTP 基础客户端
│   ├── t2a.py               # 语音合成
│   ├── voice_clone.py       # 语音克隆
│   ├── voice_manage.py      # 音色管理
│   ├── file_api.py          # 文件上传/检索
│   └── models.py            # 系统音色字典
├── core/                    # 插件核心逻辑
│   ├── polisher.py          # LLM 润色
│   ├── tts_engine.py        # TTS 编排
│   ├── audio_utils.py       # 音频转换
│   ├── sender.py            # 消息发送
│   └── text_utils.py        # 文本清洗
├── pages/dashboard/         # Signal 声场控制台面板
│   ├── index.html
│   ├── styles/              # tokens.css, theme.css, components.css
│   ├── scripts/app.js
│   └── assets/logo.svg
└── i18n/                    # 国际化
    ├── zh-CN.json
    └── en-US.json
```

## 开发原则

- 全异步 HTTP（aiohttp），不使用 requests
- 持久化数据存放在 `data/` 目录
- 错误隔离：TTS 失败时降级为纯文本，不中断对话
- 配置驱动：所有行为可通过 WebUI 配置面板调整

## 许可证

MIT

## 反馈

- GitHub Issues：https://github.com/LilycleHeart/astrbot_plugin_minimax_tts/issues
- AstrBot 开发者 QQ 群：975206796
