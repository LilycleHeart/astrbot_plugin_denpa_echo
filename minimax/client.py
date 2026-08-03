"""Minimax HTTP 基础客户端。

提供鉴权、URL 拼接、重试、错误处理等共享能力，所有具体 API 服务都基于此客户端。
"""
import asyncio
from typing import Any, Optional

import aiohttp

from astrbot.api import logger


class MinimaxAPIError(Exception):
    """Minimax API 业务错误。"""

    def __init__(self, status_code: int, status_msg: str, trace_id: str = ""):
        self.status_code = status_code
        self.status_msg = status_msg
        self.trace_id = trace_id
        super().__init__(f"[{status_code}] {status_msg} (trace: {trace_id})")


class MinimaxClient:
    """所有 Minimax API 的共享基础客户端。"""

    # 区域 -> base_url 映射
    REGION_URLS = {
        "china": "https://api.minimaxi.com",
        "international": "https://api.minimax.io",
    }
    # 国际平台低延迟备用端点
    REGION_URLS_UW = {
        "international": "https://api-uw.minimax.io",
    }

    def __init__(
        self,
        api_key: str,
        group_id: str,
        region: str = "china",
        custom_url: str = "",
        timeout: int = 60,
        retry_times: int = 2,
        retry_backoff: float = 1.5,
    ):
        self.api_key = api_key
        self.group_id = group_id
        self.region = region
        if region == "custom" and custom_url:
            self.base_url = custom_url.rstrip("/")
        else:
            self.base_url = self.REGION_URLS.get(region, self.REGION_URLS["china"])
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.retry_times = retry_times
        self.retry_backoff = retry_backoff
        self._session: Optional[aiohttp.ClientSession] = None
        # 下载外部资源(对象存储 URL)用的 session，不带 Authorization header，
        # 否则会破坏对象存储的签名计算 -> SignatureDoesNotMatch
        self._download_session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """获取或创建 aiohttp 会话（带 Authorization，用于 Minimax API）。"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=self.timeout,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            )
        return self._session

    async def _get_download_session(self) -> aiohttp.ClientSession:
        """获取用于下载外部资源(对象存储)的 session，不带 Authorization。

        Minimax 的下载 URL 指向对象存储(OSS/COS/S3)，签名计算不包含额外
        header；若复用带 Authorization 的 session 会导致 SignatureDoesNotMatch。
        """
        if self._download_session is None or self._download_session.closed:
            self._download_session = aiohttp.ClientSession(timeout=self.timeout)
        return self._download_session

    def _build_url(self, path: str, with_group: bool = True) -> str:
        """拼接完整 URL，国内平台附加 GroupId。"""
        url = f"{self.base_url}{path}"
        if with_group and self.region == "china" and self.group_id:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}GroupId={self.group_id}"
        return url

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict | None = None,
        params: dict | None = None,
        data: Any = None,
        headers: dict | None = None,
        with_group: bool = True,
    ) -> dict:
        """带重试的请求封装。

        Args:
            method: HTTP 方法（GET/POST）
            path: API 路径（如 /v1/t2a_v2）
            json_body: JSON 请求体
            params: query 参数
            data: 表单/原始数据（用于文件上传）
            headers: 额外请求头
            with_group: 是否在 URL 末尾附加 GroupId
        """
        url = self._build_url(path, with_group=with_group)
        last_err: Exception | None = None

        for attempt in range(self.retry_times + 1):
            session = await self._get_session()
            try:
                async with session.request(
                    method,
                    url,
                    json=json_body,
                    params=params,
                    data=data,
                    headers=headers,
                ) as resp:
                    raw = await resp.text()
                    try:
                        payload = await resp.json(content_type=None)
                    except Exception:
                        payload = {"raw": raw}

                    # HTTP 层错误
                    if resp.status >= 400:
                        base_resp = payload.get("base_resp", {}) if isinstance(payload, dict) else {}
                        raise MinimaxAPIError(
                            resp.status,
                            base_resp.get("status_msg", f"HTTP {resp.status}"),
                            payload.get("trace_id", "") if isinstance(payload, dict) else "",
                        )

                    # 业务层错误（Minimax 用 base_resp.status_code 表示，0 为成功）
                    if isinstance(payload, dict):
                        base_resp = payload.get("base_resp", {})
                        biz_code = base_resp.get("status_code", 0)
                        if biz_code != 0:
                            raise MinimaxAPIError(
                                biz_code,
                                base_resp.get("status_msg", "unknown"),
                                payload.get("trace_id", ""),
                            )
                    return payload

            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_err = e
                if attempt < self.retry_times:
                    wait = self.retry_backoff * (attempt + 1)
                    logger.warning(
                        f"[Minimax] 请求失败（第 {attempt + 1} 次），{wait:.1f}s 后重试: {e}"
                    )
                    await asyncio.sleep(wait)
                continue
            except MinimaxAPIError:
                raise

        raise MinimaxAPIError(-1, f"重试 {self.retry_times} 次仍失败: {last_err}")

    async def upload_file(
        self,
        file_path: str,
        purpose: str = "voice_clone",
    ) -> int:
        """上传文件（multipart/form-data），返回 file_id。

        文件上传需要绕过 _request 的 JSON 假设，单独处理。
        """
        import os

        if not os.path.exists(file_path):
            raise FileNotFoundError(file_path)

        url = self._build_url("/v1/files/upload")
        session = await self._get_session()

        form = aiohttp.FormData()
        form.add_field("purpose", purpose)
        with open(file_path, "rb") as f:
            form.add_field(
                "file",
                f,
                filename=os.path.basename(file_path),
                content_type="application/octet-stream",
            )

        async with session.post(url, data=form) as resp:
            payload = await resp.json(content_type=None)
            if resp.status >= 400:
                base_resp = payload.get("base_resp", {}) if isinstance(payload, dict) else {}
                raise MinimaxAPIError(
                    resp.status,
                    base_resp.get("status_msg", "upload failed"),
                )
            file_id = payload.get("file", {}).get("file_id")
            if file_id is None:
                raise MinimaxAPIError(-1, f"上传响应缺少 file_id: {payload}")
            return file_id

    async def close(self):
        """关闭会话。"""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
        if self._download_session and not self._download_session.closed:
            await self._download_session.close()
            self._download_session = None
