"""文件上传与检索。"""
import os

import aiohttp

from astrbot.api import logger

from .client import MinimaxClient, MinimaxAPIError


class FileService:
    """Minimax 文件管理服务：上传、检索、下载。"""

    def __init__(self, client: MinimaxClient):
        self.client = client

    async def upload(self, file_path: str, purpose: str = "voice_clone") -> int:
        """上传文件，返回 file_id。

        Args:
            file_path: 本地文件路径
            purpose: 用途，voice_clone（待克隆源音频）或 prompt_audio（示例音频）
        """
        return await self.client.upload_file(file_path, purpose=purpose)

    async def retrieve(self, file_id: int) -> dict:
        """检索文件信息（含下载 URL）。"""
        return await self.client._request(
            "GET",
            "/v1/files/retrieve",
            params={"file_id": file_id},
        )

    async def get_download_url(self, file_id: int) -> str:
        """获取文件下载 URL。"""
        info = await self.retrieve(file_id)
        url = info.get("file", {}).get("download_url")
        if not url:
            raise MinimaxAPIError(-1, f"文件 {file_id} 无下载 URL: {info}")
        return url

    async def download(self, file_id: int, save_path: str) -> str:
        """下载文件到本地，返回保存路径。

        Args:
            file_id: Minimax 文件 ID
            save_path: 本地保存路径
        """
        download_url = await self.get_download_url(file_id)
        os.makedirs(os.path.dirname(os.path.abspath(save_path)), exist_ok=True)

        # 用独立的下载 session，不带 Authorization，避免破坏对象存储签名
        session = await self.client._get_download_session()
        async with session.get(download_url) as resp:
            if resp.status >= 400:
                body = await resp.text()
                raise MinimaxAPIError(resp.status, f"下载失败: {body[:200]}")
            with open(save_path, "wb") as f:
                async for chunk in resp.content.iter_chunked(8192):
                    f.write(chunk)
        logger.debug(f"[Minimax] 文件 {file_id} 已下载到 {save_path}")
        return save_path

    async def download_bytes(self, file_id: int) -> bytes:
        """下载文件到内存，返回字节。"""
        download_url = await self.get_download_url(file_id)
        # 用独立的下载 session，不带 Authorization，避免破坏对象存储签名
        session = await self.client._get_download_session()
        async with session.get(download_url) as resp:
            if resp.status >= 400:
                body = await resp.text()
                raise MinimaxAPIError(resp.status, f"下载失败: {body[:200]}")
            return await resp.read()
