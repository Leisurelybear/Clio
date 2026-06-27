"""Route handlers: /api/videos, /api/video"""

from __future__ import annotations

import json
import re
from http import HTTPStatus
from pathlib import Path
from typing import TYPE_CHECKING, Any

from vlog_tool._constants import VIDEO_EXTS
from vlog_tool.identity import load_identity
from vlog_tool.ui.services.file_service import (
    _find_compressed_for_original,
    _find_original_for_compressed,
    _find_texts_dirs,
    _is_safe_basename,
)
from vlog_tool.utils import get_duration_sec, resolve_binary
from vlog_tool.vmeta import VideoMeta

if TYPE_CHECKING:
    from vlog_tool.ui.handler_protocol import HandlerProtocol

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


def handle_get_videos(handler: HandlerProtocol, qs: dict[str, Any]) -> None:
    """Handle GET /api/videos. Sends JSON response directly."""

    proj_input = handler._resolve_project_input(qs)
    proj_out = handler._get_project_output(proj_input)
    source = qs.get("source", ["compressed"])[0]
    if source not in ("compressed", "original"):
        return handler._send_json({"ok": False, "error": "source must be compressed|original"}, 400)
    comp_dir = proj_out / "compressed"

    # texts/scripts sidecars are keyed by the compressed index in both views
    text_sidecars: dict[str, list[str]] = {}
    text_titles: dict[str, str] = {}
    text_identities: dict[str, Any] = {}  # index -> MediaIdentity (for v2)
    for td in _find_texts_dirs(proj_out):
        for f in sorted(td.iterdir()):
            if f.suffix != ".json":
                continue
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            idx = str(data.get("index", ""))
            if not idx:
                if "_" not in f.stem:
                    continue
                idx = f.stem.split("_", 1)[0]
            text_sidecars.setdefault(idx, []).append(f.name)
            if idx not in text_titles:
                text_titles[idx] = data.get("title", "")
            if idx not in text_identities:
                identity = load_identity(data)
                if identity is not None:
                    text_identities[idx] = identity
    script_sidecars: dict[str, list[str]] = {}
    sd = proj_out / "scripts"
    if sd.is_dir():
        for f in sorted(sd.iterdir()):
            if f.suffix != ".json" or "_" not in f.stem:
                continue
            idx = f.stem.split("_", 1)[0]
            script_sidecars.setdefault(idx, []).append(f.name)

    # build transcript lookup: original stem -> bool
    cfg = handler._get_config(proj_input)
    transcripts_dir = proj_out / cfg.whisper.transcripts_subdir
    transcripts_set: set[str] = set()
    if transcripts_dir.is_dir():
        for f in transcripts_dir.iterdir():
            if f.suffix == ".json" and f.stem.endswith("_transcript"):
                # Add compressed stem (v1 behavior)
                transcripts_set.add(f.stem[: -len("_transcript")])
                # Also add original_stem if v2 (in case transcript files were re-run)
                try:
                    tf_data = json.loads(f.read_text(encoding="utf-8"))
                    identity = load_identity(tf_data)
                    if identity is not None:
                        transcripts_set.add(identity.original_stem)
                except Exception:
                    pass

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
                orig = _find_original_for_compressed(stem, proj_input, comp_dir)
                orig_stem = Path(orig).stem if orig else None
                group_key, seg_num = _parse_segment_info(stem)
                v: dict[str, Any] = {
                    "file": p.name,
                    "source": "compressed",
                    "index": idx,
                    "title": text_titles.get(idx, ""),
                    "text_json": next((x for x in text_sidecars.get(idx, []) if x is not None), None),
                    "script_json": next((x for x in script_sidecars.get(idx, []) if x is not None), None),
                    "transcript_file": (
                        text_identities[idx].original_stem
                        if idx in text_identities and text_identities[idx].original_stem in transcripts_set
                        else orig_stem
                        if orig_stem and orig_stem in transcripts_set
                        else None
                    ),
                    "match": ({"source": "original", "file": orig} if orig else None),
                    "group_key": group_key,
                    "segment_label": None,
                }
                if group_key is not None and seg_num is not None:
                    group_members.setdefault(group_key, []).append((idx, seg_num))
                videos.append(v)

            # Pass 2: compute totals, fill segment labels and offsets
            # resolve ffprobe once for segment offset computation
            try:
                _ffprobe = resolve_binary(cfg.paths.ffprobe, "ffprobe")
            except Exception:
                _ffprobe = None
            for gk, members in group_members.items():
                members.sort(key=lambda x: x[1])
                total = len(members)
                groups[gk] = {
                    "original_stem": gk,
                    "indices": [m[0] for m in members],
                    "total": total,
                }
                # compute segment offset from .vmeta first, then fallback to estimation
                offsets: dict[str, float] = {}
                for member_idx, seg_num in members:
                    for v in videos:
                        if v["index"] == member_idx:
                            comp_file = comp_dir / v["file"]
                            meta = VideoMeta.read(comp_file)
                            if meta and meta.split_info:
                                offsets[member_idx] = meta.split_info.offset_sec
                            break
                # legacy estimation for files without .vmeta
                missing = [m for m in members if m[0] not in offsets]
                if missing and total > 1 and _ffprobe:
                    orig_video: Path | None = None
                    for ext in VIDEO_EXTS:
                        candidate = proj_input / f"{gk}{ext}"
                        if candidate.is_file():
                            orig_video = candidate
                            break
                    if orig_video is not None:
                        try:
                            dur = get_duration_sec(orig_video, _ffprobe)
                            seg_dur = dur / total
                            for i, (member_idx, _) in enumerate(missing):
                                offsets[member_idx] = round(i * seg_dur, 1)
                        except Exception:
                            pass
                for member_idx, seg_num in members:
                    for v in videos:
                        if v["index"] == member_idx:
                            v["segment_label"] = f"{seg_num}/{total}"
                            v["offset_sec"] = offsets.get(member_idx, 0.0)
                            break
    else:  # original
        if proj_input.is_dir():
            # resolve ffprobe once for segment offset computation
            try:
                cfg = handler._get_config(proj_input)
                _ffprobe = resolve_binary(cfg.paths.ffprobe, "ffprobe")
            except Exception:
                _ffprobe = None
            for p in sorted(proj_input.iterdir()):
                if p.suffix.lower() not in VIDEO_EXTS:
                    continue
                comp = _find_compressed_for_original(p.stem, comp_dir)
                if not comp:
                    videos.append(
                        {
                            "file": p.name,
                            "source": "original",
                            "index": None,
                            "match": None,
                            "transcript_file": p.stem if p.stem in transcripts_set else None,
                        }
                    )
                    continue
                # Compute per-segment offsets
                seg_offsets: dict[str, float] = {}
                if len(comp) > 1 and _ffprobe:
                    try:
                        dur = get_duration_sec(p, _ffprobe)
                        seg_dur = dur / len(comp)
                        for i, (_, idx) in enumerate(comp):
                            seg_offsets[idx] = round(i * seg_dur, 1)
                    except Exception:
                        pass
                segment_matches = [{"source": "compressed", "file": cf, "index": ci} for cf, ci in comp]
                for c_file, c_idx in comp:
                    seg_v: dict[str, Any] = {
                        "file": f"{c_idx}_{p.name}",
                        "source": "original",
                        "index": c_idx,
                        "title": text_titles.get(c_idx, ""),
                        "offset_sec": seg_offsets.get(c_idx, 0.0),
                        "text_json": next((x for x in text_sidecars.get(c_idx, []) if x is not None), None),
                        "script_json": next((x for x in script_sidecars.get(c_idx, []) if x is not None), None),
                        "transcript_file": p.stem if p.stem in transcripts_set else None,
                        "match": {"source": "compressed", "file": c_file, "index": c_idx},
                    }
                    if len(segment_matches) > 1:
                        seg_v["segment_matches"] = segment_matches
                    videos.append(seg_v)
    handler._send_json({"videos": videos, "source": source, "groups": groups})


def handle_get_video(handler: HandlerProtocol, qs: dict[str, Any]) -> None:
    """Handle GET /api/video. Sends video range response directly."""

    proj_input = handler._resolve_project_input(qs)
    proj_out = handler._get_project_output(proj_input)
    fname = qs.get("file", [""])[0]
    source = qs.get("source", ["compressed"])[0]
    if not _is_safe_basename(fname):
        return handler.send_error(HTTPStatus.FORBIDDEN)
    if source == "original":
        parts = fname.split("_", 1)
        actual_fname = parts[1] if len(parts) == 2 and parts[0].isdigit() else fname
        vp = proj_input / actual_fname
    else:
        vp = proj_out / "compressed" / fname
    if not vp.is_file() or vp.suffix.lower() not in VIDEO_EXTS:
        return handler.send_error(HTTPStatus.NOT_FOUND)
    handler._send_video_range(vp)


def handle_get_vmeta(handler: HandlerProtocol, qs: dict[str, Any], stem: str) -> None:
    """Handle GET /api/vmeta/{stem} → .vmeta JSON content."""
    if not stem:
        return handler._send_json({"ok": False, "error": "missing stem"}, 400)
    proj_input = handler._resolve_project_input(qs)
    proj_out = handler._get_project_output(proj_input)
    comp_dir = proj_out / "compressed"
    for p in comp_dir.glob(f"{stem}.*"):
        if p.suffix.lower() in VIDEO_EXTS:
            meta = VideoMeta.read(p)
            if meta is not None:
                from vlog_tool.vmeta import _meta_to_dict

                return handler._send_json(_meta_to_dict(meta))
    handler._send_json({"ok": False, "error": "not found"}, 404)
