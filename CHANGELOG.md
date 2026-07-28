# Changelog

本文件记录插件所有 notable 变更，格式参考 [Keep a Changelog](https://keepachangelog.com/)。

版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [1.2.0] - 2026-07-29

### Added
- **面板按 Fluent 2 设计体系还原重做**：依据 microsoft/fluentui（Fluent 2 设计语言）实现真实设计令牌，彻底替代上一版的深色自定义风格。
  - 完整 Fluent 2 令牌系统（tokens.css）：品牌色 `#0078D4`（brand[80]，及 hover `#106EBE`/pressed `#004578`、暗色 `#2899F5`）、中性色分层（白画布 + `#fafafa` 卡片）、描边、状态色、圆角（控件 4px / 卡片 8px / 胶囊 999px）、Segoe UI 字体阶梯、4px 间距、阴影层级、2px 焦点环。
  - **亮 / 暗双主题**：`[data-theme="light"]` 与 `[data-theme="dark"]`（由 AstrBot PluginPage bridge 维护），默认跟随宿主主题。
  - **HTML5 `<canvas>` 实时波形可视化器**（签名元素，Fluent 品牌色线条）：空闲态播放环境波形动画；试听/调试/克隆音频播放时通过 WebAudio `AnalyserNode` 真实分析同源音频驱动频谱柱状图。3 处接线点全覆盖（音色试听 / 调试合成 / 克隆结果）。
  - 15+ 组件按 Fluent 2 规范重写（card / stat-card / badge / button(primary·secondary·subtle) / input / select / slider / table / toast / file-drop / progress / audio-player / skeleton），含 focus-visible 焦点环与 `prefers-reduced-motion` 降级。

### Changed
- 默认品牌色采用 Fluent 2 官方品牌蓝 `#0078D4`（此前误用旧版 `#0F6CBD`）；默认圆角恢复 Fluent 卡片 8px（用户「圆角」设置仍可调，覆盖 `--radius-large/xlarge`）。
- HTML 布局重构为 hero（标题 + 波形 canvas）→ tabs → panels 三段式，保留全部 62 个功能 DOM ID 与 `app.js` 变量契约（`--color-brand*` / `--color-app-bg` / `--radius-large/xlarge` / `bg-mode-*`）不变，逻辑层零破坏。

### Fixed
- 修正品牌色为 Fluent 2 真实值（`#0078D4`，原误用旧版 Fluent `#0F6CBD`），暗色同步修正为 `#2899F5`。
- 修正背景分层：页面画布改为白色（`--color-app-bg`），卡片用 `#fafafa` 浮起 + 克制阴影，消除原先「整页发灰、卡片陷进灰底」的闷感；卡片增加 hover 浮起交互。

## [1.1.0] - 2026-07-29

### Added
- **LLM 自动情绪识别**（`auto_emotion` 配置组）：从 AstrBot 已配置模型中选择 Provider，自动判断朗读情绪并应用到合成；带超时 / 降级 / 容错，旧接口 `text_chat` 兜底。
- **文本预处理自定义正则规则**（`text_processing.custom_rules`）：用户自行配置正则表达式，匹配内容从朗读文本中删除；始终生效（不受润色开关影响），无效正则自动忽略并告警，不中断合成。
- **润色 + 自动情绪合并为单次 LLM 调用**：两者同时开启时使用润色配置的模型一次性完成，解析失败自动回退为两次独立调用，行为不变不降级。
- **文本预处理多项独立开关**：`markdown` / `emoji` / `url` / 空白规范化 各自可独立开启关闭。

### Changed
- `send_mode` 改为运行时实时读取，在面板修改发送模式后无需重启即可生效。
- 追加（append）模式短文本改用同步合成，显著降低等待延迟（原异步约 130s）。
- **背景图改为 base64 内联存储**：上传时直接将图片编码为 `data:image/...;base64,...` 写入 `ui.background_image`，不再依赖服务端文件路径与 `/bg` 端点。换机器 / 走代理 / 清缓存均可正常显示，彻底修复旧方案"文件不在当前运行机器导致 404 背景不生效"的问题。旧路径式配置仍兼容（面板自动回退走 `/bg` 端点）。

### Fixed
- 修复 `strip_emoji` 误删全部中文字符导致润色后文本为空的问题。
- 修复 `synthesize_to_wav` 参数名误用（`use_sync` → `use_async`）导致试听 / 拦截 / 指令全部失效。
- 修复 `get_voice` 接口 404（改为 POST + JSON body）。
- 修复同步合成音频解码异常与克隆试听下载问题（API 端点审计）。
- 修复下载对象存储文件时签名错误（`SignatureDoesNotMatch`），改用独立 session。
- 对照 AstrBot 官方文档修复两处 API 写法。

### Removed
- 移除内置颜文字过滤（高频精确清单 + 通用正则双层）。相关需求可由 `custom_rules` 自定义正则替代（如 `（[^（）]*）` 删除全角括号及其内容）。

## [1.0.0] - 2026-07-27

### Added
- 插件初始发布：接入 Minimax 官方 TTS API（同步 / 异步合成、语音克隆、按音色 ID 加载、UI 背景图上传）。
- Fluent UI 2 自定义控制台面板（10px 圆角 + 动态 / 静态取色）。
- 拦截（intercept）/ 追加（append）双发送模式，支持触发范围与群白名单。
- LLM 合成前润色（`polish`）与高级设置（缓存、重试、超时、日志级别等）。
- 克隆音色、发音词典、声音效果器、语言增强等合成参数可调。
