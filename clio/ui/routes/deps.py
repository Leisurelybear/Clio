"""Dependency availability endpoints (ffmpeg/ffprobe)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from clio.utils import probe_ffmpeg_deps

if TYPE_CHECKING:
    from clio.ui.handler_protocol import HandlerProtocol


def handle_get_deps_ffmpeg(handler: HandlerProtocol, qs: dict[str, Any]) -> None:
    """GET /api/deps/ffmpeg — probe ffmpeg/ffprobe without side effects."""
    proj_dir = handler._resolve_project_dir(qs)
    cfg = handler._get_config(proj_dir)
    paths = getattr(cfg, "paths", None)
    ffmpeg = getattr(paths, "ffmpeg", "") or ""
    ffprobe = getattr(paths, "ffprobe", "") or ""
    handler._send_json(probe_ffmpeg_deps(ffmpeg, ffprobe))
