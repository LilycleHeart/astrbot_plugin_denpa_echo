"""合成前 LLM 自动情绪识别。

根据待朗读文本，调用 AstrBot 配置的某个 LLM（由用户在配置里从
AstrBot 已配置的模型中选择）判断朗读时应使用的情绪，返回 Minimax
T2A 支持的 emotion 枚举值（或空串表示 neutral）。

失败时按配置降级为 default_emotion / 空串，不影响正常合成。
"""
import asyncio
from typing import Optional

from astrbot.api import logger

from ..minimax.models import EMOTION_OPTIONS


class EmotionClassifier:
    """调用 LLM 对文本做情绪分类，输出 Minimax 支持的情绪标签。"""

    # 可被 LLM 识别并映射为情绪的词 -> 最终 emotion 值
    # neutral/none/normal 映射到空串（neutral，不传 emotion 字段）
    _TOKEN_MAP: dict[str, str] = {
        "happy": "happy",
        "sad": "sad",
        "angry": "angry",
        "fearful": "fearful",
        "disgusted": "disgusted",
        "surprised": "surprised",
        "calm": "calm",
        "neutral": "",
        "none": "",
        "normal": "",
    }

    # LLM 可调用的真实情绪枚举（不含空串），用于 prompt 约束
    _VALID_EMOTIONS = [e for e in EMOTION_OPTIONS if e]

    def __init__(self, context, config: dict):
        """
        Args:
            context: AstrBot Context 对象
            config: auto_emotion 配置组
        """
        self.context = context
        self.enabled = bool(config.get("enabled", False))
        self.provider_id = config.get("provider_id", "") or ""
        # default_emotion 必须是合法值或空串
        de = config.get("default_emotion", "") or ""
        self.default_emotion = de if de in EMOTION_OPTIONS else ""
        self.timeout = float(config.get("timeout", 10))
        self.fallback_on_error = bool(config.get("fallback_on_error", True))

    async def classify(self, text: str, umo: str) -> str:
        """识别文本情绪。

        Args:
            text: 待合成文本（已润色/清洗）
            umo: unified_msg_origin，用于获取会话默认 Provider

        Returns:
            emotion 字符串（""=neutral，或 happy/sad/... 之一）；
            失败/未开启时返回 default_emotion。
        """
        if not self.enabled or not text.strip():
            return self.default_emotion

        # 1. 解析 provider_id：优先配置指定，其次会话默认
        pid = self.provider_id
        if not pid:
            try:
                pid = await self.context.get_current_chat_provider_id(umo=umo)
            except Exception as e:
                logger.warning(f"[Emotion] 获取会话默认模型失败: {e}")
                pid = ""
        if not pid:
            logger.warning("[Emotion] 未找到可用 LLM，跳过情绪识别")
            return self.default_emotion

        # 2. 调用 LLM
        prompt = self._build_prompt(text)
        try:
            raw = await asyncio.wait_for(
                self._call_llm(pid, prompt),
                timeout=self.timeout,
            )
        except asyncio.TimeoutError:
            logger.warning(f"[Emotion] 情绪识别超时（{self.timeout}s）")
            return self._on_error()
        except Exception as e:
            logger.warning(f"[Emotion] 情绪识别失败: {e}")
            return self._on_error()

        # 3. 解析结果
        return self._parse(raw)

    def _on_error(self) -> str:
        if self.fallback_on_error:
            return self.default_emotion
        # 不降级则返回一个明确的空（neutral），避免抛错中断合成
        return ""

    async def _call_llm(self, provider_id: str, prompt: str) -> str:
        """调用 LLM，返回纯文本。优先新接口 llm_generate，旧接口兜底。"""
        # 新接口（AstrBot v4.5.7+ 推荐）
        if hasattr(self.context, "llm_generate"):
            try:
                resp = await self.context.llm_generate(
                    chat_provider_id=provider_id,
                    prompt=prompt,
                )
                text = self._extract_text(resp)
                if text:
                    return text
            except Exception as e:
                logger.warning(f"[Emotion] llm_generate 失败: {e}")

        # 旧接口兜底（get_provider_by_id + text_chat）
        try:
            provider = self.context.get_provider_by_id(provider_id)
            resp = await provider.text_chat(prompt=prompt, contexts=[])
            text = self._extract_text(resp)
            if text:
                return text
        except Exception as e:
            logger.warning(f"[Emotion] 旧接口 text_chat 失败: {e}")
        return ""

    @staticmethod
    def _extract_text(resp) -> str:
        if resp is None:
            return ""
        if hasattr(resp, "completion_text"):
            return (resp.completion_text or "").strip()
        if isinstance(resp, str):
            return resp.strip()
        if isinstance(resp, dict):
            return (resp.get("completion_text") or resp.get("content") or "").strip()
        return ""

    def _build_prompt(self, text: str) -> str:
        emotions = ", ".join(self._VALID_EMOTIONS + ["neutral"])
        return (
            "你是语音合成的情绪识别器。根据下面这段文本，判断朗读它时应该"
            "使用的情绪。\n"
            f"可选情绪（只能选一个，英文小写）：{emotions}。"
            "若文本没有强烈情绪，选 neutral。\n"
            "只输出一个英文单词，不要任何解释、标点或换行。\n\n"
            f"文本：{text}\n\n情绪："
        )

    def _parse(self, raw: str) -> str:
        """把 LLM 返回的文本解析为 emotion 值。"""
        if not raw:
            return self.default_emotion
        low = raw.lower().strip()
        # 整串精确匹配
        if low in self._TOKEN_MAP:
            return self._TOKEN_MAP[low]
        # 子串匹配（容忍 LLM 啰嗦）
        for token, emo in self._TOKEN_MAP.items():
            if token in low:
                return emo
        # 无法识别 -> 降级
        return self.default_emotion
