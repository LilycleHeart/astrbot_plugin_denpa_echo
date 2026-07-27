"""Minimax API 客户端模块。"""

from .client import MinimaxClient, MinimaxAPIError
from .t2a import T2AService, T2AResult
from .file_api import FileService
from .voice_clone import VoiceCloneService
from .voice_manage import VoiceManageService

__all__ = [
    "MinimaxClient",
    "MinimaxAPIError",
    "T2AService",
    "T2AResult",
    "FileService",
    "VoiceCloneService",
    "VoiceManageService",
]
