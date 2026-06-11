"""Route handlers: /api/videos, /api/video"""

from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING

from vlog_tool._constants import VIDEO_EXTS
from vlog_tool.ui.services.file_service import (
    _find_compressed_for_original,
    _find_original_for_compressed,
    _find_texts_dirs,
    _is_safe_basename,
)

if TYPE_CHECKING:
    from http.server import BaseHTTPRequestHandler


def handle_get_videos(handler: BaseHTTPRequestHandler, qs: dict) -> None:
    """Handle GET /api/videos. Sends JSON response directly."""

    proj_input = handler._resolve_project_input(qs)
    proj_out = handler._get_project_output(proj_input)
    source = qs.get("source", ["compressed"])[0]
    if source not in ("compressed", "original"):
        return handler._send_json({"ok": False, "error": "source must be compressed|original"}, 400)
    comp_dir = proj_out / "compressed"

    # texts/scripts sidecars are keyed by the compressed index in both views
    text_sidecars: dict[str, list[str]] = {}
    for td in _find_texts_dirs(proj_out):
        for f in td.iterdir():
            if f.suffix != ".json" or "_" not in f.stem:
                continue
            idx = f.stem.split("_", 1)[0]
            text_sidecars.setdefault(idx, []).append(f.name)
    script_sidecars: dict[str, list[str]] = {}
    sd = proj_out / "scripts"
    if sd.is_dir():
        for f in sd.iterdir():
            if f.suffix != ".json" or "_" not in f.stem:
                continue
            idx = f.stem.split("_", 1)[0]
            script_sidecars.setdefault(idx, []).append(f.name)

    videos: list[dict] = []
    if source == "compressed":
        if comp_dir.is_dir():
            for p in sorted(comp_dir.iterdir()):
                if p.suffix.lower() not in VIDEO_EXTS:
                    continue
                stem = p.stem
                idx = stem.split("_", 1)[0] if "_" in stem else ""
                orig = _find_original_for_compressed(stem, proj_input)
                videos.append(
                    {
                        "file": p.name,
                        "source": "compressed",
                        "index": idx,
                        "text_json": (text_sidecars.get(idx) or [None])[0],
                        "script_json": (script_sidecars.get(idx) or [None])[0],
                        "match": ({"source": "original", "file": orig} if orig else None),
                    }
                )
    else:  # original
        if proj_input.is_dir():
            for p in sorted(proj_input.iterdir()):
                if p.suffix.lower() not in VIDEO_EXTS:
                    continue
                comp = _find_compressed_for_original(p.stem, comp_dir)
                idx = comp[1] if comp else None
                videos.append(
                    {
                        "file": p.name,
                        "source": "original",
                        "index": idx,
                        "text_json": (text_sidecars.get(idx) or [None])[0] if idx else None,
                        "script_json": (script_sidecars.get(idx) or [None])[0] if idx else None,
                        "match": (
                            {"source": "compressed", "file": comp[0], "index": comp[1]} if comp else None
                        ),
                    }
                )
    handler._send_json({"videos": videos, "source": source})


def handle_get_video(handler: BaseHTTPRequestHandler, qs: dict) -> None:
    """Handle GET /api/video. Sends video range response directly."""

    proj_input = handler._resolve_project_input(qs)
    proj_out = handler._get_project_output(proj_input)
    fname = qs.get("file", [""])[0]
    source = qs.get("source", ["compressed"])[0]
    if not _is_safe_basename(fname):
        return handler.send_error(HTTPStatus.FORBIDDEN)
    if source == "original":
        vp = proj_input / fname
    else:
        vp = proj_out / "compressed" / fname
    if not vp.is_file() or vp.suffix.lower() not in VIDEO_EXTS:
        return handler.send_error(HTTPStatus.NOT_FOUND)
    handler._send_video_range(vp)
