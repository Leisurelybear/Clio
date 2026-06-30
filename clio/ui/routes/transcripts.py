"""API handlers for transcript GET, POST, and PUT."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

from clio.ui.handler_protocol import HandlerProtocol
from clio.ui.services.file_service import _is_safe_basename, _save_atomic

_MAX_SEGMENT_TEXT_LENGTH = 5000
_MAX_TIME_SEC = 86400  # 24h

_SEG_SUFFIX_RE = re.compile(r"_seg\d+$")


def _resolve_stem(file: str) -> str | None:
    safe = _is_safe_basename(file)
    if not safe:
        return None
    name = file.rsplit(".", 1)[0]
    stem = _SEG_SUFFIX_RE.sub("", name)
    return stem


def _transcript_path(handler: HandlerProtocol, qs: dict[str, Any], video: str) -> Path | None:
    stem = _resolve_stem(video)
    if not stem:
        return None
    proj_out = handler._get_project_output(qs)
    if not proj_out:
        return None
    proj_input = handler._resolve_project_input(qs)
    cfg = handler._get_config(proj_input)
    transcripts_dir = proj_out / cfg.whisper.transcripts_subdir
    # Try compressed stem first (e.g., "001_GX010682_transcript.json")
    compressed_path = transcripts_dir / f"{stem}_transcript.json"
    if compressed_path.is_file():
        return compressed_path
    # Fallback: try original stem (e.g., "GX010682_transcript.json")
    # Strip index prefix if present (e.g., "001_" from "001_GX010682")
    orig_stem = stem
    if "_" in stem:
        _, orig_stem = stem.split("_", 1)
        orig_stem = _SEG_SUFFIX_RE.sub("", orig_stem)
        orig_path = transcripts_dir / f"{orig_stem}_transcript.json"
        if orig_path.is_file():
            return orig_path
    return None


def handle_get_transcripts(handler: HandlerProtocol, qs: dict[str, Any]) -> None:
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


def handle_put_transcripts(handler: HandlerProtocol, qs: dict[str, Any], obj: dict) -> None:
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
            new_text = new_text.strip()
            if not new_text:
                return handler._send_json({"ok": False, "error": "text cannot be empty"}, 400)
            if len(new_text) > _MAX_SEGMENT_TEXT_LENGTH:
                return handler._send_json(
                    {"ok": False, "error": f"text too long ({len(new_text)} > {_MAX_SEGMENT_TEXT_LENGTH} chars)"}, 400
                )
            segments[segment_index]["text"] = new_text

        _save_atomic(tp, json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))
        handler._send_json({"ok": True})
    except Exception as e:
        handler._send_json({"ok": False, "error": str(e)}, 500)


def handle_post_transcripts(handler: HandlerProtocol, qs: dict[str, Any], obj: dict) -> None:
    video = qs.get("video", [None])[0]
    if not video:
        return handler._send_json({"ok": False, "error": "missing video param"}, 400)

    start = obj.get("start")
    end = obj.get("end")
    text = obj.get("text", "")
    if start is None or end is None:
        return handler._send_json({"ok": False, "error": "missing start/end"}, 400)
    if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
        return handler._send_json({"ok": False, "error": "start/end must be numbers"}, 400)
    if not isinstance(text, str):
        return handler._send_json({"ok": False, "error": "text must be a string"}, 400)

    if not math.isfinite(start) or not math.isfinite(end):
        return handler._send_json({"ok": False, "error": "start/end must be finite numbers"}, 400)

    if start < 0:
        return handler._send_json({"ok": False, "error": "start time cannot be negative"}, 400)
    if end <= start:
        return handler._send_json({"ok": False, "error": "end time must be greater than start time"}, 400)
    if end > _MAX_TIME_SEC:
        return handler._send_json({"ok": False, "error": f"end time exceeds maximum ({_MAX_TIME_SEC}s)"}, 400)

    text = text.strip()
    if not text:
        return handler._send_json({"ok": False, "error": "text cannot be empty"}, 400)
    if len(text) > _MAX_SEGMENT_TEXT_LENGTH:
        return handler._send_json(
            {"ok": False, "error": f"text too long ({len(text)} > {_MAX_SEGMENT_TEXT_LENGTH} chars)"}, 400
        )

    tp = _transcript_path(handler, qs, video)
    if not tp or not tp.is_file():
        return handler._send_json({"ok": False, "error": "transcript not found"}, 404)

    try:
        data = json.loads(tp.read_text(encoding="utf-8"))
        segments = data.get("segments", [])

        new_seg = {
            "start": round(start, 2),
            "end": round(end, 2),
            "text": text,
            "avg_logprob": 0.0,
            "low_confidence": False,
        }

        insert_idx = len(segments)
        for i, seg in enumerate(segments):
            if seg.get("start", 0) > start:
                insert_idx = i
                break
        segments.insert(insert_idx, new_seg)
        data["segments"] = segments

        _save_atomic(tp, json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))
        handler._send_json({"ok": True, "segment_index": insert_idx, "segment": new_seg})
    except Exception as e:
        handler._send_json({"ok": False, "error": str(e)}, 500)
