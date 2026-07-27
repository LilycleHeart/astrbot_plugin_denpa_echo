"""音色列表查询与删除。"""
from astrbot.api import logger

from .client import MinimaxClient
from .models import ALL_SYSTEM_VOICES


class VoiceManageService:
    """音色管理服务：列出系统音色与克隆音色，删除克隆音色。"""

    def __init__(self, client: MinimaxClient):
        self.client = client

    async def list_voices(self, voice_type: str = "all") -> dict:
        """获取音色列表。

        Args:
            voice_type: 'all' | 'system' | 'voice_cloning' | 'voice_generation'

        Returns:
            Minimax 返回的音色列表数据（含 system_voice / voice_cloning /
            voice_generation 三个列表）

        Note:
            官方接口为 POST /v1/get_voice，voice_type 放在 JSON body 中。
            克隆音色需成功用于一次语音合成后才会在 voice_cloning 中出现。
        """
        return await self.client._request(
            "POST",
            "/v1/get_voice",
            json_body={"voice_type": voice_type},
        )

    async def list_system_voices_static(self) -> list:
        """返回内置的系统音色列表（不调用 API，用于离线展示）。"""
        return [
            {"name": name, "voice_id": vid, "type": "system"}
            for name, vid in ALL_SYSTEM_VOICES
        ]

    async def delete_voice(
        self, voice_id: str, voice_type: str = "voice_cloning"
    ) -> dict:
        """删除克隆/生成音色。

        Args:
            voice_id: 待删除的音色 ID
            voice_type: 'voice_cloning' 或 'voice_generation'（系统音色不可删除）

        Note:
            官方接口为 POST /v1/delete_voice，body 需同时包含 voice_type 与 voice_id。
            删除后该 voice_id 无法再次使用。
        """
        resp = await self.client._request(
            "POST",
            "/v1/delete_voice",
            json_body={"voice_type": voice_type, "voice_id": voice_id},
        )
        logger.info(f"[Minimax] 已删除音色: {voice_id} (type={voice_type})")
        return resp
