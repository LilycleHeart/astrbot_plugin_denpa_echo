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
        record_stat=None,
    ):
        self.tts_engine = tts_engine
        self.context = context
        # 持有 config 引用；send_mode 相关配置在每次事件时【实时读取】，
        # 不再在 __init__ 缓存，避免面板/配置 UI 修改模式后运行时仍不生效。
        self.config = config
        # 统计回调（由 Main._record_stat 注入）：合成成功后记录今日/累计统计
        self.record_stat = record_stat

    # —— send_mode 配置实时读取（不缓存）——
    def _sm(self) -> dict:
        return self.config.get("send_mode", {}) or {}

    @property
    def mode(self) -> str:
        return self._sm().get("mode", "intercept")

    @property
    def keep_text(self) -> bool:
        return bool(self._sm().get("keep_text", True))

    @property
    def use_sync(self) -> bool:
        return bool(self._sm().get("use_sync", True))

    @property
    def append_silent(self) -> bool:
        return bool(self._sm().get("append_silent", False))

    @property
    def min_length(self) -> int:
        return int(self._sm().get("min_length", 1))

    @property
    def max_length(self) -> int:
        return int(self._sm().get("max_length", 5000))

    @property
    def skip_long(self) -> bool:
        return bool(self._sm().get("skip_long", False))

    @property
    def skip_long_length(self) -> int:
        return int(self._sm().get("skip_long_length", 5000))

    @property
    def trigger_scope(self) -> str:
        return self._sm().get("trigger_scope", "all")

    @property
    def whitelist_groups(self) -> set:
        return set(self._sm().get("whitelist_groups", []) or [])

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

    def _extract_text(self, chain: list) -> tuple[str, int]:
        """提取消息链中的纯文本并截断。

        Returns:
            (合成用文本, 原始长度)。原始长度用于「超长不合成」判断，
            避免先截断后无法感知原始文本的真实长度。
        """
        text = extract_plain_text(chain)
        if not text:
            return "", 0
        raw_len = len(text)
        if raw_len > self.max_length:
            text = truncate_text(text, self.max_length)
        return text, raw_len

    def _should_skip_tts(self, text: str, raw_len: int) -> bool:
        """按长度规则决定是否跳过本次合成。

        - 短于 min_length 的回复不合成（保留原有行为）
        - 开启 skip_long 且原始长度超过 skip_long_length 时不合成
        """
        if len(text) < self.min_length:
            return True
        if self.skip_long and raw_len > self.skip_long_length:
            logger.info(
                f"[TTS] 超长不合成: 原始 {raw_len}字 > 阈值 "
                f"{self.skip_long_length}字，跳过语音合成"
            )
            return True
        return False

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
        text, raw_len = self._extract_text(chain)
        if self._should_skip_tts(text, raw_len):
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

            if self.record_stat:
                self.record_stat(text, meta)

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
        text, raw_len = self._extract_text(chain)
        if self._should_skip_tts(text, raw_len):
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
            # 短文本用同步合成（秒级完成，单次 HTTP 请求即返回音频）；
            # 仅当文本超长(>8000字符，超过同步 t2a_v2 的 10000 上限安全余量)
            # 才降级用异步合成（创建任务+轮询+下载，慢但支持超长文本）。
            use_async = len(text) > 8000
            logger.info(
                f"[TTS] 追加模式后台合成: {len(text)}字, "
                f"{'异步' if use_async else '同步'}"
            )
            wav_path, meta = await self.tts_engine.synthesize_to_wav(
                text=text,
                tts_params=tts_params,
                umo=umo,
                use_async=use_async,
            )

            # 通过 context 主动发送语音
            # MessageChain 没有 .record() 便捷方法，直接构造 chain
            message_chain = MessageChain(chain=[Record(file=wav_path, url=wav_path)])
            await self.context.send_message(umo, message_chain)

            if self.record_stat:
                self.record_stat(text, meta)

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
