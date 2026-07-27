"""合成前 LLM 文本润色。"""
import asyncio
from typing import Optional

from astrbot.api import logger


class TextPolisher:
    """调用 LLM 对将朗读的文本进行清洗润色。

    目标：去除 markdown/emoji/代码块，调整语气，让文本更适合语音朗读。
    失败时根据配置降级为使用原文。
    """

    def __init__(self, context, config: dict):
        """
        Args:
            context: AstrBot Context 对象
            config: polish 配置组
        """
        self.context = context
        self.enabled = bool(config.get("enabled", False))
        self.provider_id = config.get("provider_id", "")
        self.prompt_template = config.get("prompt", "")
        self.max_tokens = int(config.get("max_tokens", 2048))
        self.timeout = float(config.get("timeout", 15))
        self.fallback_on_error = bool(config.get("fallback_on_error", True))

    async def polish(self, text: str, umo: str) -> str:
        """润色文本。

        Args:
            text: 原始文本
            umo: unified_msg_origin，用于获取会话默认 Provider

        Returns:
            润色后的文本；失败时根据配置返回原文或抛错
        """
        if not self.enabled or not text.strip():
            return text

        try:
            provider = self._get_provider(umo)
            if provider is None:
                logger.warning("[Polisher] 未找到可用 LLM Provider，跳过润色")
                return text

            # 构造 prompt：若模板含 {text} 占位符则替换，否则拼接
            if "{text}" in self.prompt_template:
                prompt = self.prompt_template.replace("{text}", text)
            else:
                prompt = f"{self.prompt_template}\n\n原文：\n{text}"

            resp = await asyncio.wait_for(
                provider.text_chat(
                    prompt=prompt,
                    system_prompt="你是一个专业的语音朗读文本润色助手。只输出润色后的纯文本，不要任何解释或额外内容。",
                    contexts=[],
                ),
                timeout=self.timeout,
            )

            polished = ""
            if hasattr(resp, "completion_text"):
                polished = resp.completion_text.strip()
            elif isinstance(resp, str):
                polished = resp.strip()
            elif isinstance(resp, dict):
                polished = (
                    resp.get("completion_text")
                    or resp.get("content")
                    or ""
                ).strip()

            if not polished:
                logger.warning("[Polisher] LLM 返回空，使用原文")
                return text

            logger.debug(
                f"[Polisher] 原文({len(text)}字): {text[:80]}... "
                f"-> 润色({len(polished)}字): {polished[:80]}..."
            )
            return polished

        except asyncio.TimeoutError:
            logger.warning(f"[Polisher] 润色超时（{self.timeout}s），使用原文")
            if self.fallback_on_error:
                return text
            raise
        except Exception as e:
            logger.warning(f"[Polisher] 润色失败: {e}，使用原文")
            if self.fallback_on_error:
                return text
            raise

    def _get_provider(self, umo: str):
        """获取 LLM Provider：优先配置指定，其次会话默认。"""
        if self.provider_id:
            try:
                return self.context.get_provider_by_id(self.provider_id)
            except Exception as e:
                logger.warning(
                    f"[Polisher] 指定的 Provider {self.provider_id} 获取失败: {e}"
                )
                return None
        try:
            return self.context.get_using_provider(umo=umo)
        except Exception:
            return None
