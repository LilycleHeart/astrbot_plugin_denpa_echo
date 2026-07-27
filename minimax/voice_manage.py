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
            voice_type: 'all' | 'system' | 'voice_clone'

        Returns:
            Minimax 返回的音色列表数据
        """
        return await self.client._request(
            "GET",
            "/v1/get_voice",
            params={"voice_type": voice_type},
        )

    async def list_system_voices_static(self) -> list:
        """返回内置的系统音色列表（不调用 API，用于离线展示）。"""
        return [
            {"name": name, "voice_id": vid, "type": "system"}
            for name, vid in ALL_SYSTEM_VOICES
        ]

    async def delete_voice(self, voice_id: str) -> dict:
        """删除克隆音色。

        Args:
            voice_id: 待删除的音色 ID
        """
        resp = await self.client._request(
            "POST", "/v1/del_voice", json_body={"voice_id": voice_id}
        )
        logger.info(f"[Minimax] 已删除音色: {voice_id}")
        return resp
