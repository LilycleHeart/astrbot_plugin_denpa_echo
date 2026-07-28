"""TTS 引擎：润色 -> 合成 -> 转换 的完整编排。"""
import asyncio
import hashlib
import json
import os
import re
import time
from typing import Optional

from astrbot.api import logger

from .audio_utils import AudioConverter
from .polisher import TextPolisher
from .emotion_classifier import EmotionClassifier
from .text_utils import quick_clean
from ..minimax.client import MinimaxClient, MinimaxAPIError
from ..minimax.file_api import FileService
from ..minimax.t2a import T2AResult, T2AService


class TTSEngine:
    """TTS 全流程编排器。

    流程：
        1. （可选）LLM 润色
        2. 缓存命中检查
        3. 调用 Minimax 合成（同步/异步）
        4. 音频格式转换（-> wav）
        5. 写入缓存与本地文件
    """

    def __init__(
        self,
        client: MinimaxClient,
        polisher: TextPolisher,
        converter: AudioConverter,
        config: dict,
        plugin_data_dir: str,
        context=None,
    ):
        """
        Args:
            client: Minimax 客户端
            polisher: LLM 润色器
            converter: 音频转换器
            config: 完整插件配置
            plugin_data_dir: 插件数据目录（用于缓存）
            context: AstrBot Context（用于自动情绪识别的 LLM 调用）
        """
        self.client = client
        self.t2a = T2AService(client)
        self.file_service = FileService(client)
        self.polisher = polisher
        self.converter = converter
        self.config = config
        self.context = context
        self.emotion_classifier = EmotionClassifier(
            context, config.get("auto_emotion", {}) or {}
        )

        # 缓存配置
        adv = config.get("advanced", {}) or {}
        cache_dir = adv.get("cache_dir", "")
        if cache_dir and not os.path.isabs(cache_dir):
            # 相对路径基于插件数据目录
            cache_dir = os.path.join(plugin_data_dir, "cache")
        self.cache_dir = cache_dir
        self.cache_enabled = bool(self.cache_dir)
        self.cache_max_size_mb = int(adv.get("cache_max_size_mb", 500))
        if self.cache_enabled:
            os.makedirs(self.cache_dir, exist_ok=True)
            self._cleanup_cache_if_needed()

    def _cache_key(self, text: str, params: dict) -> str:
        """根据文本 + 关键参数生成缓存键。"""
        # 只取影响音频结果的关键参数
        key_fields = [
            "model", "voice_id", "speed", "vol", "pitch", "emotion",
            "language_boost", "format", "sample_rate", "bitrate", "channel",
        ]
        key_parts = [text]
        for k in key_fields:
            if k in params:
                key_parts.append(f"{k}={params[k]}")
        if params.get("use_timbre_weights") and params.get("timbre_weights"):
            tw = params["timbre_weights"]
            key_parts.append(
                "tw="
                + ",".join(
                    f"{t.get('voice_id')}:{t.get('weight')}" for t in tw
                )
            )
        vm = params.get("voice_modify", {}) or {}
        if vm.get("enabled"):
            key_parts.append(
                f"vm={vm.get('pitch',0)},{vm.get('intensity',0)},{vm.get('timbre',0)},{vm.get('sound_effects','')}"
            )
        return hashlib.md5("|".join(str(p) for p in key_parts).encode()).hexdigest()

    def _cache_path(self, key: str) -> str:
        return os.path.join(self.cache_dir, f"{key}.wav")

    def _cleanup_cache_if_needed(self) -> None:
        """若缓存超限，按最旧访问时间删除。"""
        if not self.cache_enabled or not os.path.isdir(self.cache_dir):
            return
        try:
            files = [
                os.path.join(self.cache_dir, f)
                for f in os.listdir(self.cache_dir)
                if f.endswith(".wav")
            ]
            if not files:
                return
            total_mb = sum(
                os.path.getsize(f) for f in files
            ) / (1024 * 1024)
            if total_mb <= self.cache_max_size_mb:
                return
            # 按 mtime 排序，删除最旧的直到低于阈值
            files.sort(key=lambda f: os.path.getmtime(f))
            while files and total_mb > self.cache_max_size_mb * 0.9:
                f = files.pop(0)
                size = os.path.getsize(f) / (1024 * 1024)
                try:
                    os.remove(f)
                    total_mb -= size
                    logger.debug(f"[TTS] 缓存清理: {f} ({size:.2f}MB)")
                except OSError:
                    pass
        except Exception as e:
            logger.warning(f"[TTS] 缓存清理失败: {e}")

    def build_tts_params(self) -> dict:
        """从插件配置构造 TTS 参数（合并 tts/audio/voice_modify/pronunciation_dict）。"""
        cfg = self.config
        params: dict = {}
        params.update(cfg.get("tts", {}) or {})
        # audio_setting 参数扁平化
        audio_cfg = cfg.get("audio", {}) or {}
        params.update(audio_cfg)
        params["voice_modify"] = cfg.get("voice_modify", {}) or {}
        params["pronunciation_dict"] = cfg.get("pronunciation_dict", {}) or {}
        return params

    async def _combined_polish_emotion(self, text: str, umo: str) -> tuple[str, str]:
        """单次 LLM 调用同时完成润色 + 情绪识别。

        仅当润色与自动情绪同时开启、且都未被 skip 时由 synthesize_to_wav 调用。
        使用润色配置的 Provider（用户选定的模型）。要求模型返回 JSON：
            {"text": "润色后的文本", "emotion": "情绪单词或 neutral"}
        任何解析/调用失败都抛异常，由调用方回退为两次独立调用（不降级），
        保证与未合并时行为完全一致。
        """
        polisher = self.polisher
        classifier = self.emotion_classifier

        provider = polisher._get_provider(umo)
        if provider is None:
            raise RuntimeError("未找到润色 Provider，无法合并调用")

        # 复用润色模板构造基础任务
        if "{text}" in polisher.prompt_template:
            base = polisher.prompt_template.replace("{text}", text)
        else:
            base = f"{polisher.prompt_template}\n\n原文：\n{text}"

        emotion_list = ", ".join(classifier._VALID_EMOTIONS + ["neutral"])
        json_instruction = (
            "\n\n--- 额外任务 ---\n"
            "同时，请判断这段文本朗读时应使用的情绪。\n"
            f"可选情绪（只能选一个，英文小写）：{emotion_list}。"
            "若文本没有强烈情绪请选 neutral。\n"
            "请严格以 JSON 格式输出，不要包含 markdown 代码块、不要任何额外解释文字，"
            '只输出一个 JSON 对象：\n{"text": "润色后的文本", "emotion": "情绪单词"}'
        )
        prompt = base + json_instruction

        timeout = max(polisher.timeout, classifier.timeout)
        try:
            resp = await asyncio.wait_for(
                provider.text_chat(
                    prompt=prompt,
                    system_prompt=(
                        "你是语音朗读文本润色与情绪分析助手。"
                        "请先按用户指令处理文本，再按要求以单个 JSON 对象输出结果，"
                        "不要输出 JSON 以外的任何内容。"
                    ),
                    contexts=[],
                ),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            raise RuntimeError(f"合并调用超时（{timeout}s）")
        except Exception as e:
            raise RuntimeError(f"合并调用 LLM 失败: {e}")

        raw = EmotionClassifier._extract_text(resp)
        if not raw:
            raise RuntimeError("合并调用 LLM 返回为空")

        data = self._parse_combined_json(raw)
        polished = (data.get("text") or "").strip()
        if not polished:
            raise RuntimeError("合并调用解析到的 text 为空")
        emotion = classifier._parse(data.get("emotion") or "")
        return polished, emotion

    @staticmethod
    def _parse_combined_json(raw: str) -> dict:
        """从 LLM 返回中提取并解析 JSON 对象（容忍 markdown 代码块/多余文字）。"""
        raw = (raw or "").strip()
        # 1. 直接解析
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass
        # 2. 提取第一个 {...}（支持跨行），容忍前后多余文字
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            try:
                obj = json.loads(m.group(0))
                if isinstance(obj, dict):
                    return obj
            except Exception:
                pass
        raise RuntimeError("无法从 LLM 返回解析出 JSON")

    async def synthesize_to_wav(
        self,
        text: str,
        tts_params: Optional[dict] = None,
        umo: str = "",
        use_async: bool = False,
        skip_polish: bool = False,
        skip_emotion_classify: bool = False,
    ) -> tuple[str, dict]:
        """完整流程：润色 -> 情绪识别 -> 合成 -> 转 wav。

        Args:
            text: 待合成文本
            tts_params: TTS 参数（None 则从配置读取）
            umo: unified_msg_origin（用于 LLM 润色/情绪识别获取 Provider）
            use_async: 是否使用异步合成（长文本）
            skip_polish: 跳过 LLM 润色（用于面板试听）
            skip_emotion_classify: 跳过自动情绪识别（用于面板手动选情绪时）

        Returns:
            (wav 文件路径, 元信息 dict)
        """
        if tts_params is None:
            tts_params = self.build_tts_params()

        # 文本预处理开关（配置 text_processing 各子项，默认全部开启）
        tp_cfg = self.config.get("text_processing", {}) or {}
        clean_kwargs = {
            "markdown": bool(tp_cfg.get("markdown_filter", True)),
            "emoji": bool(tp_cfg.get("emoji_filter", True)),
            "kaomoji": bool(tp_cfg.get("kaomoji_filter", True)),
            "url": bool(tp_cfg.get("url_filter", True)),
            "whitespace": bool(tp_cfg.get("normalize_whitespace", True)),
        }

        # 1. 润色 + 自动情绪（两者均开启且均未 skip 时，合并为单次 LLM 调用）
        combined_ok = False
        if (
            not skip_polish
            and not skip_emotion_classify
            and self.polisher.enabled
            and self.emotion_classifier.enabled
        ):
            try:
                polished, emo = await self._combined_polish_emotion(text, umo)
                tts_params["emotion"] = emo
                combined_ok = True
                logger.debug(f"[TTS] 润色+情绪 合并单次调用成功, emotion={emo!r}")
            except Exception as e:
                logger.warning(f"[TTS] 合并调用失败，回退为两次独立调用: {e}")

        if not combined_ok:
            # 1a. 润色
            if skip_polish:
                polished = quick_clean(text, **clean_kwargs)
            else:
                polished = await self.polisher.polish(text, umo)
                # 即使润色过，也做一次兜底清洗（去掉残留 markdown）
                if not self.polisher.enabled:
                    polished = quick_clean(polished, **clean_kwargs)

            # 1b. 自动情绪识别（开启且未跳过时，覆盖 tts_params 中的 emotion）
            if not skip_emotion_classify and self.emotion_classifier.enabled:
                try:
                    emo = await self.emotion_classifier.classify(polished, umo)
                    # "" 表示 neutral，build_payload 会忽略该字段
                    tts_params["emotion"] = emo
                    logger.debug(f"[TTS] 自动情绪识别结果: {emo!r}")
                except Exception as e:
                    logger.warning(f"[TTS] 情绪识别异常，使用默认/中性: {e}")

        if not polished:
            raise MinimaxAPIError(-1, "润色后文本为空")

        # 2. 缓存检查
        cache_key = self._cache_key(polished, tts_params)
        wav_cache_path = self._cache_path(cache_key)
        if self.cache_enabled and os.path.exists(wav_cache_path):
            # 更新访问时间
            os.utime(wav_cache_path)
            logger.debug(f"[TTS] 命中缓存: {wav_cache_path}")
            return wav_cache_path, {"cached": True, "text": polished}

        # 3. 合成
        src_format = tts_params.get("format", "mp3")
        sample_rate = int(tts_params.get("sample_rate", 32000))
        channels = int(tts_params.get("channel", 1))

        if use_async:
            wav_bytes, meta = await self._synthesize_async(
                polished, tts_params, src_format, sample_rate, channels
            )
        else:
            wav_bytes, meta = await self._synthesize_sync(
                polished, tts_params, src_format, sample_rate, channels
            )

        # 4. 写入缓存
        if self.cache_enabled:
            os.makedirs(os.path.dirname(os.path.abspath(wav_cache_path)), exist_ok=True)
            with open(wav_cache_path, "wb") as f:
                f.write(wav_bytes)
            meta["cache_path"] = wav_cache_path
            return wav_cache_path, meta

        # 5. 无缓存时写到临时文件
        import tempfile
        tmp = tempfile.NamedTemporaryFile(
            suffix=".wav", delete=False, dir=self.cache_dir or None
        )
        tmp.write(wav_bytes)
        tmp.close()
        meta["cache_path"] = tmp.name
        return tmp.name, meta

    async def _synthesize_sync(
        self,
        text: str,
        params: dict,
        src_format: str,
        sample_rate: int,
        channels: int,
    ) -> tuple[bytes, dict]:
        """同步合成。"""
        t0 = time.time()
        result = await self.t2a.sync_synthesize(text, params)
        elapsed = time.time() - t0
        logger.info(
            f"[TTS] 同步合成完成: {len(text)}字 -> "
            f"{len(result.audio_bytes)}B, 耗时 {elapsed:.2f}s, "
            f"trace={result.trace_id}"
        )

        # 转换为 wav
        if src_format == "wav":
            wav_bytes = result.audio_bytes
        else:
            wav_bytes = self.converter.to_wav(
                result.audio_bytes,
                src_format,
                sample_rate=sample_rate,
                channels=channels,
            )

        meta = {
            "mode": "sync",
            "elapsed_ms": int(elapsed * 1000),
            "usage_chars": result.usage_characters,
            "audio_length_ms": result.audio_length,
            "trace_id": result.trace_id,
            "text": text,
        }
        return wav_bytes, meta

    async def _synthesize_async(
        self,
        text: str,
        params: dict,
        src_format: str,
        sample_rate: int,
        channels: int,
    ) -> tuple[bytes, dict]:
        """异步合成（长文本）。"""
        t0 = time.time()
        task_id, _ = await self.t2a.async_synthesize(text, params)
        logger.info(f"[TTS] 异步任务已创建: task_id={task_id}")

        file_id = await self.t2a.wait_for_task(task_id)
        audio_bytes = await self.file_service.download_bytes(file_id)
        elapsed = time.time() - t0
        logger.info(
            f"[TTS] 异步合成完成: task_id={task_id}, "
            f"{len(text)}字 -> {len(audio_bytes)}B, 耗时 {elapsed:.2f}s"
        )

        if src_format == "wav":
            wav_bytes = audio_bytes
        else:
            wav_bytes = self.converter.to_wav(
                audio_bytes,
                src_format,
                sample_rate=sample_rate,
                channels=channels,
            )

        meta = {
            "mode": "async",
            "task_id": task_id,
            "file_id": file_id,
            "elapsed_ms": int(elapsed * 1000),
            "text": text,
        }
        return wav_bytes, meta

    def cache_size_mb(self) -> float:
        """返回当前缓存大小（MB）。"""
        if not self.cache_enabled or not os.path.isdir(self.cache_dir):
            return 0.0
        try:
            total = sum(
                os.path.getsize(os.path.join(self.cache_dir, f))
                for f in os.listdir(self.cache_dir)
                if f.endswith(".wav")
                and os.path.isfile(os.path.join(self.cache_dir, f))
            )
            return total / (1024 * 1024)
        except Exception:
            return 0.0

    def clear_cache(self) -> int:
        """清空缓存，返回删除的文件数。"""
        if not self.cache_enabled or not os.path.isdir(self.cache_dir):
            return 0
        count = 0
        for f in os.listdir(self.cache_dir):
            if f.endswith(".wav"):
                try:
                    os.remove(os.path.join(self.cache_dir, f))
                    count += 1
                except OSError:
                    pass
        return count
