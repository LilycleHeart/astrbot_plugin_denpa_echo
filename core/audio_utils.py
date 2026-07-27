"""音频格式转换（mp3/pcm/flac -> wav）。

AstrBot 的 Comp.Record 组件只接受 wav 格式，因此所有 Minimax 合成结果
都需要转换为 wav。
"""
import io
import os
import shutil
import tempfile
import wave
from typing import Optional

from astrbot.api import logger


class AudioConverter:
    """音频转换器，依赖 pydub（需系统 ffmpeg）。

    转换策略：
        - wav: 直接使用
        - pcm: 自加 wav 头（无需 ffmpeg）
        - mp3/flac: 使用 pydub + ffmpeg 转换
    """

    def __init__(self, ffmpeg_path: str = "ffmpeg"):
        self.ffmpeg_path = ffmpeg_path
        self._available = self._check_ffmpeg()
        if not self._available:
            logger.warning(
                "[AudioConverter] ffmpeg 未检测到。mp3/flac 转 wav 将失败。\n"
                "  解决方案：\n"
                "  - Windows: choco install ffmpeg 或下载放入 PATH\n"
                "  - Linux:   apt install ffmpeg / yum install ffmpeg\n"
                "  - macOS:   brew install ffmpeg\n"
                "  - 或在插件配置中将 audio.format 设为 'wav'（体积大，不支持流式）"
            )

    def _check_ffmpeg(self) -> bool:
        """检测 ffmpeg 是否可用。"""
        try:
            return shutil.which(self.ffmpeg_path) is not None
        except Exception:
            return False

    @property
    def available(self) -> bool:
        """ffmpeg 是否可用。"""
        return self._available

    def to_wav(
        self,
        audio_bytes: bytes,
        src_format: str,
        sample_rate: int = 32000,
        channels: int = 1,
        sample_width: int = 2,
    ) -> bytes:
        """将音频字节转换为 wav 字节。

        Args:
            audio_bytes: 原始音频字节
            src_format: 源格式（mp3/wav/flac/pcm）
            sample_rate: 采样率（仅 pcm 生效）
            channels: 声道数（仅 pcm 生效）
            sample_width: 采样位宽（仅 pcm 生效，2 = 16bit）

        Returns:
            wav 格式字节
        """
        if src_format == "wav":
            return audio_bytes
        if src_format == "pcm":
            return self._pcm_to_wav(
                audio_bytes,
                sample_rate=sample_rate,
                channels=channels,
                sample_width=sample_width,
            )

        # mp3 / flac 需要 ffmpeg
        if not self._available:
            raise RuntimeError(
                f"ffmpeg 不可用，无法转换 {src_format} -> wav。"
                "请安装 ffmpeg，或在配置中将 audio.format 设为 'wav'。"
            )

        return self._pydub_to_wav(audio_bytes, src_format)

    def _pcm_to_wav(
        self,
        pcm_bytes: bytes,
        sample_rate: int = 32000,
        channels: int = 1,
        sample_width: int = 2,
    ) -> bytes:
        """PCM 原始数据加 wav 头。"""
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(sample_width)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm_bytes)
        return buf.getvalue()

    def _pydub_to_wav(self, audio_bytes: bytes, src_format: str) -> bytes:
        """使用 pydub 转换。"""
        try:
            from pydub import AudioSegment
        except ImportError:
            raise RuntimeError(
                "pydub 未安装。请在插件 requirements.txt 中加入 pydub>=0.25.1"
            )

        # pydub 需要从文件读取，写到临时文件
        with tempfile.NamedTemporaryFile(
            suffix=f".{src_format}", delete=False
        ) as tmp_in:
            tmp_in.write(audio_bytes)
            tmp_in_path = tmp_in.name
        try:
            audio = AudioSegment.from_file(tmp_in_path, format=src_format)
            buf = io.BytesIO()
            audio.export(buf, format="wav")
            return buf.getvalue()
        finally:
            try:
                os.unlink(tmp_in_path)
            except OSError:
                pass

    def convert_file(
        self,
        src_path: str,
        dst_path: str,
        src_format: Optional[str] = None,
    ) -> str:
        """转换文件，返回目标路径。"""
        if src_format is None:
            src_format = os.path.splitext(src_path)[1].lstrip(".")
        with open(src_path, "rb") as f:
            audio_bytes = f.read()
        wav_bytes = self.to_wav(audio_bytes, src_format)
        os.makedirs(os.path.dirname(os.path.abspath(dst_path)), exist_ok=True)
        with open(dst_path, "wb") as f:
            f.write(wav_bytes)
        return dst_path
