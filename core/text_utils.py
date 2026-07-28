"""文本清洗工具（不调用 LLM 的轻量级清洗）。"""
import re

from astrbot.api import logger
from astrbot.api.message_components import Plain


def strip_markdown(text: str) -> str:
    """去除 markdown 标记，保留可读文本。"""
    # 代码块 ```...``` -> （代码块）
    text = re.sub(r"```[\s\S]*?```", "（代码块）", text)
    # 行内代码 `code` -> code
    text = re.sub(r"`([^`]+)`", r"\1", text)
    # 标题 # / ## / ###
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    # 粗体 **text** / __text__
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"__([^_]+)__", r"\1", text)
    # 斜体 *text* / _text_
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"(?<!\w)_([^_]+)_(?!\w)", r"\1", text)
    # 链接 [text](url) -> text
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    # 图片 ![alt](url) -> alt 或 （图片）
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", lambda m: m.group(1) or "（图片）", text)
    # 引用 >
    text = re.sub(r"^>\s*", "", text, flags=re.MULTILINE)
    # 无序列表 - * +
    text = re.sub(r"^[\s]*[-*+]\s+", "", text, flags=re.MULTILINE)
    # 有序列表 1.
    text = re.sub(r"^[\s]*\d+\.\s+", "", text, flags=re.MULTILINE)
    # 水平线 --- / ***
    text = re.sub(r"^[-*_]{3,}$", "", text, flags=re.MULTILINE)
    return text


def strip_emoji(text: str) -> str:
    """去除 emoji（仅覆盖常见 Unicode emoji 区段，不影响中日韩文字）。"""
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # 表情符号
        "\U0001F300-\U0001F5FF"  # 符号和象形文字
        "\U0001F680-\U0001F6FF"  # 交通和地图符号
        "\U0001F1E0-\U0001F1FF"  # 旗帜
        "\U0001F900-\U0001F9FF"  # 补充表情符号
        "\U0001FA70-\U0001FAFF"  # 符号和象形文字扩展A
        "\U00002600-\U000026FF"  # 杂项符号
        "\U00002702-\U000027B0"  # Dingbats
        "\U0000FE00-\U0000FE0F"  # 变体选择符
        "]+",
        flags=re.UNICODE,
    )
    return emoji_pattern.sub("", text)


def strip_urls(text: str) -> str:
    """移除 URL，保留可读描述。"""
    # http(s)://...
    text = re.sub(r"https?://[^\s<>\)]+", "（链接）", text)
    return text


def normalize_whitespace(text: str) -> str:
    """规范化空白。"""
    # 连续 3+ 换行 -> 2 个
    text = re.sub(r"\n{3,}", "\n\n", text)
    # 连续 2+ 空格/制表符 -> 1 个
    text = re.sub(r"[ \t]{2,}", " ", text)
    # 行首尾空白
    text = "\n".join(line.strip() for line in text.split("\n"))
    return text.strip()


def strip_custom_rules(text: str, patterns: list) -> str:
    """按用户自定义正则规则删除匹配到的文本。

    Args:
        text: 待处理文本
        patterns: 正则表达式字符串列表，每个匹配到的内容都会被删除。
                  无效的正则会被跳过并打印告警，不会中断合成流程。

    该规则始终对最终文本生效（无论是否启用 LLM 润色），优先级低于
    markdown/emoji/url/空白等内置开关，在它们之后执行。
    """
    if not patterns:
        return text
    for pat in patterns:
        try:
            rx = re.compile(pat)
        except re.error as e:
            logger.warning(f"[TextClean] 自定义规则正则无效，已跳过: {pat!r} ({e})")
            continue
        text = rx.sub("", text)
    return text


def extract_plain_text(message_chain: list) -> str:
    """从 AstrBot 消息链中提取纯文本。

    Args:
        message_chain: AstrMessageEvent.get_result().chain 列表

    Returns:
        拼接后的纯文本
    """
    parts = []
    for comp in message_chain:
        if isinstance(comp, Plain):
            parts.append(comp.text)
    return "".join(parts).strip()


def quick_clean(
    text: str,
    markdown: bool = True,
    emoji: bool = True,
    url: bool = True,
    whitespace: bool = True,
) -> str:
    """不调用 LLM 的快速清洗（作为润色关闭时的兜底）。

    各步骤可由配置 text_processing 的对应开关独立控制（默认全部开启，保持原行为）。
    顺序：markdown -> emoji -> url -> 空白规范化。
    自定义正则清洗规则（custom_rules）在 tts_engine 统一对最终文本生效，不在此函数内。
    """
    if not text:
        return ""
    if markdown:
        text = strip_markdown(text)
    if emoji:
        text = strip_emoji(text)
    if url:
        text = strip_urls(text)
    if whitespace:
        text = normalize_whitespace(text)
    return text


def truncate_text(text: str, max_length: int) -> str:
    """截断文本到指定长度，添加省略号。"""
    if len(text) <= max_length:
        return text
    return text[:max_length].rstrip() + "……"
