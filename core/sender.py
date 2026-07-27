"""消息发送策略：拦截模式 + 追加模式。"""
import asyncio
from typing import Optional

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.message_components import Plain, Record

from .text_utils import extract_plain_text, quick_clean, truncate_text
from .tts_engine import TTSEngine
from ..minimax.client import MinimaxAPIError


class MessageSender:
    """根据 send_mode 配置选择发送策略。

    模式：
        - intercept: 拦截 bot 回复，TTS 合成后与文本一起发（或仅发语音）
        - append: bot 先发文本，后台异步合成语音，完成后追加语音
        - disabled: 关闭 TTS
    """

    def __init__(
        self,
        tts_engine: TTSEngine,
        context,
        config: dict,
    ):
        self.tts_engine = tts_engine
        self.context = context
        self.config = config

        sm = config.get("send_mode", {}) or {}
        self.mode = sm.get("mode", "intercept")
        self.keep_text = bool(sm.get("keep_text", True))
        self.use_sync = bool(sm.get("use_sync", True))
        self.append_silent = bool(sm.get("append_silent", False))
        self.min_length = int(sm.get("min_length", 1))
        self.max_length = int(sm.get("max_length", 5000))
        self.trigger_scope = sm.get("trigger_scope", "all")
        self.whitelist_groups = set(sm.get("whitelist_groups", []) or [])

    def should_process(self, event: AstrMessageEvent) -> bool:
        """判断是否应处理此事件。"""
        if self.mode == "disabled":
            return False
        if self.trigger_scope == "none":
            return False

        is_group = bool(getattr(event.message_obj, "group_id", ""))
        if self.trigger_scope == "group" and not is_group:
            return False
        if self.trigger_scope == "private" and is_group:
            return False

        if is_group and self.whitelist_groups:
            gid = event.message_obj.group_id
            # 白名单支持配置中存的是 dict 还是 str
            wl = set()
            for g in self.whitelist_groups:
                if isinstance(g, dict):
                    wl.add(str(g.get("group_id", "")))
                else:
                    wl.add(str(g))
            if str(gid) not in wl:
                return False

        return True

    def _extract_text(self, chain: list) -> str:
        """提取消息链中的纯文本并截断。"""
        text = extract_plain_text(chain)
        if not text:
            return ""
        if len(text) > self.max_length:
            text = truncate_text(text, self.max_length)
        return text

    async def handle_intercept(self, event: AstrMessageEvent) -> None:
        """拦截模式：在 on_decorating_result 钩子中替换消息链。

        流程：
            1. 提取消息链中的纯文本
            2. TTS 合成（润色 -> 合成 -> 转 wav）
            3. 替换消息链为 [Plain(可选), Record(wav)]
            4. 失败则保留原消息链（降级）
        """
        result = event.get_result()
        chain = result.chain
        text = self._extract_text(chain)
        if len(text) < self.min_length:
            return

        umo = event.unified_msg_origin
        try:
            tts_params = self.tts_engine.build_tts_params()
            wav_path, meta = await self.tts_engine.synthesize_to_wav(
                text=text,
                tts_params=tts_params,
                umo=umo,
                use_async=not self.use_sync,
            )

            # 构造新消息链
            new_chain = []
            if self.keep_text:
                # 保留原文（未经润色的原文，让用户看到完整回复）
                new_chain.append(Plain(text))
            new_chain.append(Record(file=wav_path, url=wav_path))
            result.chain = new_chain

            logger.info(
                f"[TTS] 拦截模式合成成功: {len(text)}字 -> {wav_path} "
                f"({meta.get('elapsed_ms', 0)}ms)"
            )
        except MinimaxAPIError as e:
            logger.error(f"[TTS] 拦截模式合成失败（API）: {e}，保留原文本")
            # 降级：保留原消息链
        except Exception as e:
            logger.error(f"[TTS] 拦截模式合成失败（异常）: {e}，保留原文本")

    async def handle_append(self, event: AstrMessageEvent) -> None:
        """追加模式：放行原文本，启动后台合成任务。

        流程：
            1. 提取消息链中的纯文本
            2. 启动 asyncio 后台任务
            3. 原消息链保持不变（bot 正常发文本）
        后台任务：
            合成 -> context.send_message 追加语音消息
        """
        result = event.get_result()
        chain = result.chain
        text = self._extract_text(chain)
        if len(text) < self.min_length:
            return

        umo = event.unified_msg_origin
        # 启动后台任务（不阻塞当前消息发送）
        asyncio.create_task(self._append_task(text, umo, event))
        logger.info(f"[TTS] 追加模式启动后台合成: {len(text)}字")

    async def _append_task(
        self, text: str, umo: str, event: AstrMessageEvent
    ) -> None:
        """追加模式后台任务。"""
        try:
            tts_params = self.tts_engine.build_tts_params()
            wav_path, meta = await self.tts_engine.synthesize_to_wav(
                text=text,
                tts_params=tts_params,
                umo=umo,
                use_async=True,  # 追加模式默认用异步
            )

            # 通过 context 主动发送语音
            # MessageChain 没有 .record() 便捷方法，直接构造 chain
            message_chain = MessageChain(chain=[Record(file=wav_path, url=wav_path)])
            await self.context.send_message(umo, message_chain)

            logger.info(
                f"[TTS] 追加模式合成完成并已发送: {len(text)}字 -> {wav_path} "
                f"({meta.get('elapsed_ms', 0)}ms)"
            )
        except MinimaxAPIError as e:
            logger.error(f"[TTS] 追加模式合成失败（API）: {e}")
            if not self.append_silent:
                try:
                    await self.context.send_message(
                        umo,
                        MessageChain().message("（语音合成失败）"),
                    )
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"[TTS] 追加模式合成失败（异常）: {e}")
            if not self.append_silent:
                try:
                    await self.context.send_message(
                        umo,
                        MessageChain().message(f"（语音合成异常: {e}）"),
                    )
                except Exception:
                    pass
