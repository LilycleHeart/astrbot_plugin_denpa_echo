"""文本清洗工具（不调用 LLM 的轻量级清洗）。"""
import re

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


# 颜文字（kaomoji）特征字符与括号
# 成对括号（半角/全角）包裹，内部由符号/假名/全角标点构成，且至少包含一个"五官"特征字符；
# 允许左右手臂字符（ヽヾノつっ⊂ 等）与尾部装饰（✧☆★ 等）。
# 注：'['（U+005B）作为字符类成员必须写成 '\['（转义），否则在 Python 3.11+ 会被当作嵌套字符类
_KAO_OPEN = (
    "\u0028\u005c\u005b\u007b\uff08\uff7b\uff3b\u2308\u230a\u27e6\u2983"
    "\u2220\u2266\u222a\u2229\u256d\u003c\uff1c\u27e8\u00ab\u2039\u300c\u300e\u3010"
)
# 注：']'（U+005D）作为字符类成员必须放在类首，否则会提前闭合字符类
_KAO_CLOSE = (
    "\u005d\u0029\u007d\uff09\uff7d\uff3d\u2309\u230b\u27e7\u2984"
    "\u2220\u2267\u222a\u2229\u256e\u003e\uff1e\u27e9\u00bb\u203a\u300d\u300f\u3011"
)
# 颜文字"五官"特征字符：强烈指示为颜文字，几乎不会出现在正常文本里
_KAO_FACE = (
    "\u3041-\u3096\u30a1-\u30f6\uff66-\uff9d"          # 平/片假名、半角片假名
    "\u30fb\uff65\u309c\u30fc"                          # ・･゜ー
    "\u25ef\u25cb\u25cf\u25cc\u25cd\u25ce\u25d5\u25d4\u25d0\u25d1"  # 眼睛类圆
    "\u226a\u226b\u2266\u2267\u25bd\u25b3\u25b2\u25bc\u25bf\u25ff\u25c7\u25a0\u25a1"  # 嘴/表情形状
    "\u2661\u2665\u2764\u2606\u2605\u266a\u266b\u273f\u2740\u272a\u203b\u273d\u25ca\u2660\u2663\u2666"  # 装饰
    "\u30fd\u30fe\u30ce\u3064\u3063\u2282\u2514\u2518\u250c\u2510\u256d\u256e\u256f\u2570\u00ab\u00bb\u2039\u203a\u301c\u3030\u303d"  # 手臂/装饰
    "\u00b0\u00ba\u1d54\u2256\u25e0\u25e1\u203f\u0414\u0434\u047f"  # 眼/嘴符号
    "\ufe4f\u0f0e\u0eb6\u2022\u1d417\uff61\u02d8"        # ﹏༎ຶ•ᴗ｡˘
)
# 颜文字内部允许的字符（符号、空白、标点，但不含汉字/拉丁字母/数字/换行）
_KAO_INNER = r"[^一-鿿A-Za-z0-9\n]"
# 手臂字符：左右挥舞的假名/符号/半角片假名/桌腿，以及少量拉丁臂（q p b d）
_KAO_ARM = "\u30fd\u30fe\u30ce\u3064\u3063\u2282\u2310\u00ac\uff3e\u00af\u309d\u309e\uff89\uff82\uff9f\u3065\u30c5\u256f\u0071\u0070\u0062\u0064"
_KAO_DECO = "\u2727\u2606\u2605\u2661\u2665\u2764\u266a\u266b\u301c\u3030"

_KAO_BRACKET = (
    "[" + _KAO_OPEN + "]"
    + _KAO_INNER + "{0,30}"
    + "[" + _KAO_FACE + "]"
    + _KAO_INNER + "{0,30}"
    + "[" + _KAO_CLOSE + "]"
)

_KAOMOJI_RE = re.compile(
    "("
    # 带手臂/尾饰的括号颜文字
    "[" + _KAO_ARM + "]?" + _KAO_BRACKET + "[" + _KAO_ARM + "]?" + "[" + _KAO_DECO + "]*"
    "|"
    # 纯 ASCII 颜文字：(T_T) (>_<) (^_^) (o_o) (x_x) (;_;) (0_0) (8_8) 等
    "[\u005c\u005b\u0028]"
    "[\u0054\u0074\u004f\u006f\u0030\u0058\u0064\u0050\u0062\u0038\u002a\u005e\u0076\u0056\u003e\u003c\u003a\u003b\u003d\u0078]{1,2}"  # 左眼
    "[\u002d\u005f\u007e\u005e\u0076\u003e\u003c]{1,3}"  # 嘴
    "[\u0054\u0074\u004f\u006f\u0030\u0058\u0064\u0050\u0062\u0038\u002a\u005e\u0076\u0056\u003e\u003c\u003a\u003b\u003d\u0078]{1,2}"  # 右眼
    "[\u005d\u0029]"
    ")"
)

# 高频颜文字精确清单（语料按使用频率排序，来自小赤羽颜文字数据集）。
# 作为字面量精确匹配，零误伤、零正则歧义，优先于下方通用正则执行。
_KAOMOJI_EXACT_LIST = [
    "(๑•̀ㅂ•́)",
    "(≧▽≦)",
    "(★ω★)",
    "(ﾉ◕ヮ◕)",
    "(๑¯◡¯๑)",
    "(´・ω・`)",
    "(◕‿◕)",
    "(｀・ω・´)",
    "(◕ᴗ◕✿)",
    "(・ω・)",
    "(´･ω･`)",
    "(´；ω；`)",
]
_KAOMOJI_EXACT_RE = re.compile("|".join(re.escape(k) for k in _KAOMOJI_EXACT_LIST))


def strip_kaomoji(text: str) -> str:
    """去除颜文字（kaomoji），如 (´・ω・`)、(≧▽≦)、ヽ(°▽°)ノ、(T_T)、(>_<) 等。

    匹配规则：
      0. 高频颜文字精确清单：按语料频率排序的 12 个常见颜文字，字面量精确匹配，
         零误伤、零歧义。
      1. 括号型：成对半角/全角括号包裹，内部由符号/假名/全角标点构成，且至少含一个
         "五官"特征字符（假名、◯○●▽△☆★ 等），可选左右手臂(ヽヾノ)与尾部装饰(✧★)。
      2. ASCII 型：(T_T)(>_<)(^_^)(o_o)(x_x)(;_;)(0_0) 等字母/符号脸。

    不会误伤正常中文/英文文本（括号内若含汉字或可读英文单词则不匹配）。
    """
    # 先跑精确清单（全匹配），再跑通用正则兜底长尾，避免通用正则部分匹配残留尾饰
    text = _KAOMOJI_EXACT_RE.sub("", text)
    return _KAOMOJI_RE.sub("", text)


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


def quick_clean(text: str, enable_kaomoji: bool = True) -> str:
    """不调用 LLM 的快速清洗（作为润色关闭时的兜底）。

    顺序：markdown -> emoji -> [颜文字] -> url -> 空白规范化
    颜文字过滤受 enable_kaomoji 控制（由配置 text_processing.kaomoji_filter 传入）。
    """
    if not text:
        return ""
    text = strip_markdown(text)
    text = strip_emoji(text)
    if enable_kaomoji:
        text = strip_kaomoji(text)
    text = strip_urls(text)
    text = normalize_whitespace(text)
    return text


def truncate_text(text: str, max_length: int) -> str:
    """截断文本到指定长度，添加省略号。"""
    if len(text) <= max_length:
        return text
    return text[:max_length].rstrip() + "……"
