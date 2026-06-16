"""API handlers for transcript GET and text PUT."""

from __future__ import annotations

import json
import re
from pathlib import Path

from vlog_tool.ui.services.file_service import _is_safe_basename, _save_atomic


_SEG_SUFFIX_RE = re.compile(r"_seg\d+$")


def _resolve_stem(file: str) -> str | None:
    """Extract source stem from video filename.
    Strips index prefix and _segNN suffix to find the original source stem.
    E.g., '001_GL010683_seg01.mp4' -> 'GL010683', 'GL010683.MP4' -> 'GL010683'.
    """
    safe = _is_safe_basename(file)
    if not safe:
        return None
    name = file.rsplit(".", 1)[0]
    parts = name.split("_", 1)
    if len(parts) >= 2 and parts[0].isdigit():
        stem = parts[1]
    else:
        stem = name
    stem = _SEG_SUFFIX_RE.sub("", stem)
    return stem


def _transcript_path(handler, qs: dict, video: str) -> Path | None:
    stem = _resolve_stem(video)
    if not stem:
        return None
    proj_out = handler._get_project_output(qs)
    if not proj_out:
        return None
    proj_input = handler._resolve_project_input(qs)
    cfg = handler._get_config(proj_input)
    transcripts_dir = proj_out / cfg.whisper.transcripts_subdir
    return transcripts_dir / f"{stem}_transcript.json"


def handle_get_transcripts(handler, qs: dict) -> None:
    video = qs.get("video", [None])[0]
    if not video:
        return handler._send_json({"ok": False, "error": "missing video param"}, 400)

    tp = _transcript_path(handler, qs, video)
    if not tp or not tp.is_file():
        return handler._send_json({"ok": False}, 404)

    try:
        data = json.loads(tp.read_text(encoding="utf-8"))
        data.pop("ok", None)
        handler._send_json({"ok": True, **data})
    except Exception as e:
        handler._send_json({"ok": False, "error": str(e)}, 500)


def handle_put_transcripts(handler, qs: dict, obj: dict) -> None:
    video = qs.get("video", [None])[0]
    if not video:
        return handler._send_json({"ok": False, "error": "missing video param"}, 400)

    segment_index = obj.get("segment_index")
    if segment_index is None or not isinstance(segment_index, int):
        return handler._send_json({"ok": False, "error": "missing/invalid segment_index"}, 400)

    tp = _transcript_path(handler, qs, video)
    if not tp or not tp.is_file():
        return handler._send_json({"ok": False, "error": "transcript not found"}, 404)

    try:
        data = json.loads(tp.read_text(encoding="utf-8"))
        segments = data.get("segments", [])
        if segment_index < 0 or segment_index >= len(segments):
            return handler._send_json({"ok": False, "error": f"segment_index {segment_index} out of range"}, 400)

        if obj.get("delete"):
            del segments[segment_index]
        else:
            new_text = obj.get("text", "")
            if not isinstance(new_text, str):
                return handler._send_json({"ok": False, "error": "text must be a string"}, 400)
            segments[segment_index]["text"] = new_text

        _save_atomic(tp, json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))
        handler._send_json({"ok": True})
    except Exception as e:
        handler._send_json({"ok": False, "error": str(e)}, 500)
