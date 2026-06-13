"""Route handlers: /api/videos, /api/video"""

from __future__ import annotations

import re
from http import HTTPStatus
from typing import TYPE_CHECKING, Any

from vlog_tool._constants import VIDEO_EXTS
from vlog_tool.ui.services.file_service import (
    _find_compressed_for_original,
    _find_original_for_compressed,
    _find_texts_dirs,
    _is_safe_basename,
)

if TYPE_CHECKING:
    from http.server import BaseHTTPRequestHandler

_SEG_RE = re.compile(r"^(.+)_seg(\d+)$")


def _parse_segment_info(stem: str) -> tuple[str | None, int | None]:
    """Extract group info from a compressed stem like '001_GL010683_seg01'.
    Returns (group_key, segment_number) or (None, None).
    """
    if "_" not in stem:
        return None, None
    m = _SEG_RE.match(stem.split("_", 1)[1])
    if not m:
        return None, None
    return m.group(1), int(m.group(2))


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
        for f in sorted(td.iterdir()):
            if f.suffix != ".json" or "_" not in f.stem:
                continue
            idx = f.stem.split("_", 1)[0]
            text_sidecars.setdefault(idx, []).append(f.name)
    script_sidecars: dict[str, list[str]] = {}
    sd = proj_out / "scripts"
    if sd.is_dir():
        for f in sorted(sd.iterdir()):
            if f.suffix != ".json" or "_" not in f.stem:
                continue
            idx = f.stem.split("_", 1)[0]
            script_sidecars.setdefault(idx, []).append(f.name)

    videos: list[dict] = []
    groups: dict[str, dict] = {}

    if source == "compressed":
        if comp_dir.is_dir():
            # Pass 1: build flat video list + collect group members
            group_members: dict[str, list[tuple[str, int]]] = {}
            for p in sorted(comp_dir.iterdir()):
                if p.suffix.lower() not in VIDEO_EXTS:
                    continue
                stem = p.stem
                idx = stem.split("_", 1)[0] if "_" in stem else ""
                orig = _find_original_for_compressed(stem, proj_input)
                group_key, seg_num = _parse_segment_info(stem)
                v: dict[str, Any] = {
                    "file": p.name,
                    "source": "compressed",
                    "index": idx,
                    "text_json": (text_sidecars.get(idx) or [None])[0],
                    "script_json": (script_sidecars.get(idx) or [None])[0],
                    "match": ({"source": "original", "file": orig} if orig else None),
                    "group_key": group_key,
                    "segment_label": None,
                }
                if group_key is not None and seg_num is not None:
                    group_members.setdefault(group_key, []).append((idx, seg_num))
                videos.append(v)

            # Pass 2: compute totals and fill segment labels
            for gk, members in group_members.items():
                members.sort(key=lambda x: x[1])
                total = len(members)
                groups[gk] = {
                    "original_stem": gk,
                    "indices": [m[0] for m in members],
                    "total": total,
                }
                for member_idx, seg_num in members:
                    for v in videos:
                        if v["index"] == member_idx:
                            v["segment_label"] = f"{seg_num}/{total}"
                            break
    else:  # original
        if proj_input.is_dir():
            for p in sorted(proj_input.iterdir()):
                if p.suffix.lower() not in VIDEO_EXTS:
                    continue
                comp = _find_compressed_for_original(p.stem, comp_dir)
                first = comp[0] if comp else None
                idx = first[1] if first else None
                v: dict[str, Any] = {
                    "file": p.name,
                    "source": "original",
                    "index": idx,
                    "text_json": (text_sidecars.get(idx) or [None])[0] if idx else None,
                    "script_json": (script_sidecars.get(idx) or [None])[0] if idx else None,
                    "match": ({"source": "compressed", "file": first[0], "index": first[1]} if first else None),
                }
                if comp and len(comp) > 1:
                    v["segment_matches"] = [{"file": f, "index": i} for f, i in comp]
                videos.append(v)
    handler._send_json({"videos": videos, "source": source, "groups": groups})


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
