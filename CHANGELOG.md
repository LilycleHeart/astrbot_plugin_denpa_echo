# Changelog

本文件记录插件所有 notable 变更，格式参考 [Keep a Changelog](https://keepachangelog.com/)。

版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### Added
- **LLM 自动情绪识别**（`auto_emotion` 配置组）：从 AstrBot 已配置模型中选择 Provider，自动判断朗读情绪并应用到合成；带超时 / 降级 / 容错，旧接口 `text_chat` 兜底。
- **文本预处理自定义正则规则**（`text_processing.custom_rules`）：用户自行配置正则表达式，匹配内容从朗读文本中删除；始终生效（不受润色开关影响），无效正则自动忽略并告警，不中断合成。
- **润色 + 自动情绪合并为单次 LLM 调用**：两者同时开启时使用润色配置的模型一次性完成，解析失败自动回退为两次独立调用，行为不变不降级。
- **文本预处理多项独立开关**：`markdown` / `emoji` / `url` / 空白规范化 各自可独立开启关闭。

### Changed
- `send_mode` 改为运行时实时读取，在面板修改发送模式后无需重启即可生效。
- 追加（append）模式短文本改用同步合成，显著降低等待延迟（原异步约 130s）。

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
