"""同步/异步/流式语音合成。"""
import asyncio
import json
from typing import AsyncIterator, Optional

from astrbot.api import logger

from .client import MinimaxClient, MinimaxAPIError


class T2AResult:
    """合成结果。"""

    def __init__(
        self,
        audio_bytes: bytes,
        audio_format: str,
        sample_rate: int,
        audio_length: int,
        usage_characters: int,
        subtitle: Optional[list] = None,
        trace_id: str = "",
    ):
        self.audio_bytes = audio_bytes
        self.audio_format = audio_format
        self.sample_rate = sample_rate
        self.audio_length = audio_length  # 毫秒
        self.usage_characters = usage_characters
        self.subtitle = subtitle
        self.trace_id = trace_id

    def __repr__(self) -> str:
        return (
            f"T2AResult(format={self.audio_format}, "
            f"sample_rate={self.sample_rate}, "
            f"length={self.audio_length}ms, "
            f"chars={self.usage_characters}, "
            f"size={len(self.audio_bytes)}B)"
        )


class T2AService:
    """语音合成服务：封装同步、异步、流式三种合成方式。"""

    def __init__(self, client: MinimaxClient):
        self.client = client

    def build_payload(self, text: str, params: dict) -> dict:
        """从插件配置构造请求体。

        Args:
            text: 待合成文本
            params: 包含 tts/audio/voice_modify/pronunciation_dict 各组的合并字典
        """
        payload: dict = {
            "model": params.get("model", "speech-02-hd"),
            "text": text,
        }

        # === voice_setting ===
        vs: dict = {
            "speed": float(params.get("speed", 1.0)),
            "vol": float(params.get("vol", 1.0)),
            "pitch": int(params.get("pitch", 0)),
        }
        if params.get("use_timbre_weights") and params.get("timbre_weights"):
            weights = []
            for tw in params["timbre_weights"]:
                vid = tw.get("voice_id") if isinstance(tw, dict) else None
                w = tw.get("weight") if isinstance(tw, dict) else None
                if vid:
                    weights.append({"voice_id": vid, "weight": int(w or 50)})
            if weights:
                vs["timbre_weights"] = weights
        else:
            vs["voice_id"] = params.get("voice_id") or "female-shaonv"

        if params.get("emotion"):
            vs["emotion"] = params["emotion"]
        if params.get("latex_read"):
            vs["latex_read"] = True
        if params.get("text_normalization"):
            vs["text_normalization"] = True
        payload["voice_setting"] = vs

        # === audio_setting ===
        payload["audio_setting"] = {
            "sample_rate": int(params.get("sample_rate", 32000)),
            "bitrate": int(params.get("bitrate", 128000)),
            "format": params.get("format", "mp3"),
            "channel": int(params.get("channel", 1)),
        }

        # === language_boost ===
        if params.get("language_boost"):
            payload["language_boost"] = params["language_boost"]

        # === pronunciation_dict ===
        pd_cfg = params.get("pronunciation_dict", {}) or {}
        if pd_cfg.get("enabled") and pd_cfg.get("tone"):
            tone_list = []
            for item in pd_cfg["tone"]:
                entry = item.get("entry") if isinstance(item, dict) else None
                if entry:
                    tone_list.append(entry)
            if tone_list:
                payload["pronunciation_dict"] = {"tone": tone_list}

        # === voice_modify ===
        vm_cfg = params.get("voice_modify", {}) or {}
        if vm_cfg.get("enabled"):
            vm: dict = {
                "pitch": int(vm_cfg.get("pitch", 0)),
                "intensity": int(vm_cfg.get("intensity", 0)),
                "timbre": int(vm_cfg.get("timbre", 0)),
            }
            if vm_cfg.get("sound_effects"):
                vm["sound_effects"] = vm_cfg["sound_effects"]
            payload["voice_modify"] = vm

        return payload

    async def sync_synthesize(self, text: str, params: dict) -> T2AResult:
        """同步合成（短文本，<10000 字符）。返回完整音频。

        使用 output_format=hex 直接获取 base64 音频，避免二次下载。
        """
        payload = self.build_payload(text, params)
        payload["stream"] = False
        payload["output_format"] = "hex"

        resp = await self.client._request("POST", "/v1/t2a_v2", json_body=payload)

        audio_hex = resp.get("data", {}).get("audio", "")
        if not audio_hex:
            raise MinimaxAPIError(-1, "响应中无音频数据", resp.get("trace_id", ""))

        extra = resp.get("extra_info", {})
        return T2AResult(
            audio_bytes=bytes.fromhex(audio_hex),
            audio_format=extra.get("audio_format", params.get("format", "mp3")),
            sample_rate=extra.get("audio_sample_rate", params.get("sample_rate", 32000)),
            audio_length=extra.get("audio_length", 0),
            usage_characters=extra.get("usage_characters", 0),
            subtitle=resp.get("extra_info", {}).get("subtitle"),
            trace_id=resp.get("trace_id", ""),
        )

    async def async_synthesize(
        self,
        text: str,
        params: dict,
        file_id: Optional[int] = None,
    ) -> tuple[int, int]:
        """异步合成（长文本）。返回 (task_id, file_id_initial)。

        Args:
            text: 待合成文本（<50000 字符）
            params: 参数
            file_id: 已上传的文本文件 ID（此时忽略 text，支持 <100万字符）
        """
        payload = self.build_payload(text, params)
        # 异步接口 audio_setting 字段名是 audio_sample_rate（不是 sample_rate）
        audio_setting = payload.pop("audio_setting", {})
        payload["audio_setting"] = {
            "audio_sample_rate": audio_setting.get("sample_rate", 32000),
            "bitrate": audio_setting.get("bitrate", 128000),
            "format": audio_setting.get("format", "mp3"),
            "channel": audio_setting.get("channel", 1),
        }
        if file_id:
            payload.pop("text", None)
            payload["text_file_id"] = file_id

        resp = await self.client._request("POST", "/v1/t2a_async_v2", json_body=payload)
        return resp.get("task_id"), resp.get("file_id")

    async def query_task(self, task_id: int) -> dict:
        """查询异步任务状态。

        Returns:
            {"status": "Processing|Success|Failed|Expired", "file_id": int|None}
        """
        resp = await self.client._request(
            "GET",
            "/v1/query/t2a_async_query_v2",
            params={"task_id": task_id},
            with_group=False,  # 查询接口不需要 GroupId
        )
        return {
            "status": resp.get("status", "Processing"),
            "file_id": resp.get("file_id"),
        }

    async def wait_for_task(
        self,
        task_id: int,
        interval: float = 2.0,
        max_wait: float = 300.0,
    ) -> int:
        """轮询直到任务完成，返回 file_id。"""
        elapsed = 0.0
        while elapsed < max_wait:
            result = await self.query_task(task_id)
            status = result["status"]
            if status == "Success":
                file_id = result.get("file_id")
                if file_id is None:
                    raise MinimaxAPIError(-1, f"任务成功但无 file_id: task_id={task_id}")
                return file_id
            if status in ("Failed", "Expired"):
                raise MinimaxAPIError(
                    -1, f"异步任务 {status}: task_id={task_id}"
                )
            await asyncio.sleep(interval)
            elapsed += interval
        raise MinimaxAPIError(-1, f"异步任务超时: task_id={task_id}")

    async def stream_synthesize(
        self, text: str, params: dict
    ) -> AsyncIterator[bytes]:
        """流式合成，逐块返回音频字节。

        注意：AstrBot 的 Record 组件目前不支持流式播放，此方法为预留。
        """
        payload = self.build_payload(text, params)
        payload["stream"] = True

        url = self.client._build_url("/v1/t2a_v2")
        session = await self.client._get_session()
        async with session.post(url, json=payload) as resp:
            async for line in resp.content:
                line = line.strip()
                if not line:
                    continue
                # Minimax 流式返回 data: {...} 格式
                if line.startswith(b"data:"):
                    try:
                        chunk = json.loads(line[5:].decode())
                    except json.JSONDecodeError:
                        continue
                    audio_hex = chunk.get("data", {}).get("audio", "")
                    if audio_hex:
                        yield bytes.fromhex(audio_hex)
