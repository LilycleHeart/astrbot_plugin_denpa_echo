"""语音克隆：上传音频 -> 调用克隆 API。"""
from typing import Optional

from astrbot.api import logger

from .client import MinimaxClient, MinimaxAPIError
from .file_api import FileService


class VoiceCloneService:
    """语音克隆服务。

    完整流程：
        1. 上传源音频（10s-5min, mp3/wav/m4a）-> file_id
        2. （可选）上传示例音频（<8s）-> prompt_file_id，提升克隆质量
        3. 调用 /v1/voice_clone 执行克隆 -> 返回试听音频

    注意：克隆产生的音色是临时的，需在 168 小时（7 天）内用 T2A 合成一次
    才能永久保留。
    """

    def __init__(self, client: MinimaxClient):
        self.client = client
        self.file_service = FileService(client)

    async def upload_clone_audio(self, file_path: str) -> int:
        """上传待克隆音频，返回 file_id。"""
        return await self.file_service.upload(file_path, purpose="voice_clone")

    async def upload_prompt_audio(self, file_path: str) -> int:
        """上传示例音频（可选，提升克隆质量）。"""
        return await self.file_service.upload(file_path, purpose="prompt_audio")

    async def clone(
        self,
        source_file_id: int,
        voice_id: str,
        model: str = "speech-02-hd",
        prompt_audio_file_id: Optional[int] = None,
        prompt_text: Optional[str] = None,
        preview_text: str = "你好，这是克隆音色的试听样本。",
    ) -> dict:
        """执行克隆。

        Args:
            source_file_id: 源音频 file_id
            voice_id: 自定义音色 ID（用户指定，需唯一）
            model: 克隆使用的模型
            prompt_audio_file_id: 示例音频 file_id（可选）
            prompt_text: 示例音频对应的文本（可选）
            preview_text: 试听文本

        Returns:
            克隆响应（含试听音频的 file_id）
        """
        payload: dict = {
            "file_id": source_file_id,
            "voice_id": voice_id,
            "model": model,
            "text": preview_text,
        }
        if prompt_audio_file_id:
            clone_prompt: dict = {"prompt_audio": prompt_audio_file_id}
            if prompt_text:
                clone_prompt["prompt_text"] = prompt_text
            payload["clone_prompt"] = clone_prompt

        resp = await self.client._request(
            "POST", "/v1/voice_clone", json_body=payload
        )
        logger.info(
            f"[Minimax] 语音克隆成功: voice_id={voice_id}, "
            f"file_id={resp.get('file_id')}"
        )
        return resp

    async def clone_from_files(
        self,
        source_path: str,
        voice_id: str,
        model: str = "speech-02-hd",
        prompt_path: Optional[str] = None,
        prompt_text: Optional[str] = None,
        preview_text: str = "你好，这是克隆音色的试听样本。",
    ) -> dict:
        """完整流程：上传 -> 克隆。

        Args:
            source_path: 源音频本地路径
            voice_id: 自定义音色 ID
            model: 克隆模型
            prompt_path: 示例音频本地路径（可选）
            prompt_text: 示例音频对应文本（可选）
            preview_text: 试听文本
        """
        source_fid = await self.upload_clone_audio(source_path)
        prompt_fid = None
        if prompt_path:
            prompt_fid = await self.upload_prompt_audio(prompt_path)
        return await self.clone(
            source_file_id=source_fid,
            voice_id=voice_id,
            model=model,
            prompt_audio_file_id=prompt_fid,
            prompt_text=prompt_text,
            preview_text=preview_text,
        )

    async def get_clone_preview_audio(
        self, clone_resp: dict, save_path: str
    ) -> str:
        """从克隆响应中提取试听音频并下载。

        克隆成功后响应里的 file_id 对应一段试听音频。
        """
        file_id = clone_resp.get("file_id")
        if file_id is None:
            raise MinimaxAPIError(-1, "克隆响应中无 file_id")
        return await self.file_service.download(file_id, save_path)
