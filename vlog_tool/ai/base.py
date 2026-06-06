from __future__ import annotations

from enum import Enum
from typing import Protocol


class TaskName(str, Enum):
    VIDEO_ANALYZE = "video_analyze"
    VOICEOVER = "voiceover"
    VLOG_PLAN = "vlog_plan"
    REFINE_TEXT = "refine_text"


class TextAIProvider(Protocol):
    """纯文本 AI 能力（口播、规划等）。"""

    provider_id: str

    def generate_text(self, prompt: str, model: str) -> str: ...


class VideoAIProvider(TextAIProvider, Protocol):
    """支持视频理解的 AI 能力。"""

    def analyze_video(self, video_path: str, prompt: str, model: str) -> str: ...
