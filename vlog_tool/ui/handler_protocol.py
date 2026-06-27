"""Typed Protocol for dynamic handler methods attached in server.py's make_handler()."""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar, Protocol

from vlog_tool.config import AppConfig


class HandlerProtocol(Protocol):
    """Minimal typed interface for stable cross-route handler capabilities.

    Route-specific helpers (_get_state, _resolve_texts, _resolve_in, etc.)
    remain dynamically typed until they stabilize — mark with
    ``# type: ignore[attr-defined]  # TODO(phase4): add to Protocol when stable``.
    """

    # -- Instance methods --
    def _send_json(self, data: Any, status: int = 200) -> None: ...
    def _send_bytes(self, data: bytes, content_type: str = "application/octet-stream", status: int = 200) -> None: ...
    def _send_static(self, rel: str) -> None: ...
    def _resolve_project_input(self, qs: dict[str, str]) -> Path | None: ...
    def _get_project_output(self, qs_or_proj_dir: dict[str, str] | Path) -> Path | None: ...  # type: ignore[overload-overlap]
    def _get_config(self, project_dir: Path | None = None) -> AppConfig: ...
    def _send_video_range(self, path: Path, range_header: str | None = None) -> None: ...

    # -- Stable class-level attributes --
    config_path: Path | None
    input_dir: Path | None
    output_dir: Path | None
    DEFAULT_PROJECT: dict[str, Any]
    _api_token: str | None
    _config_cache: ClassVar[Any]
