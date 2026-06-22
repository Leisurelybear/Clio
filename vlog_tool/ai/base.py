from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable


class TaskName(StrEnum):
    VIDEO_ANALYZE = "video_analyze"
    VOICEOVER = "voiceover"
    VLOG_PLAN = "vlog_plan"
    REFINE_TEXT = "refine_text"


@dataclass(frozen=True)
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class AIResponse:
    text: str
    token_usage: TokenUsage | None = None


@runtime_checkable
class TextAIProvider(Protocol):
    """纯文本 AI 能力（口播、规划等）。"""

    provider_id: str

    def generate_text(self, prompt: str, model: str) -> AIResponse: ...

    def close(self) -> None: ...


class VideoAIProvider(TextAIProvider, Protocol):
    """支持视频理解的 AI 能力。"""

    def analyze_video(
        self, video_path: str, prompt: str, model: str, progress_callback: Callable[[str], None] | None = None
    ) -> AIResponse: ...
