"""Route handlers: /api/videos, /api/video, /api/videos/selected"""

from __future__ import annotations

import re
import threading
from copy import deepcopy
from http import HTTPStatus
from pathlib import Path
from typing import TYPE_CHECKING, Any

from clio._constants import VIDEO_EXTS
from clio.index import ArtifactIndex
from clio.tasks._video_loader import load_selected_videos, save_selected_videos
from clio.ui.services.file_service import (
    _find_compressed_for_original,
    _find_original_for_compressed,
    _find_texts_dirs,
    _is_safe_basename,
)
from clio.utils import get_duration_sec, resolve_binary
from clio.vmeta import VideoMeta

if TYPE_CHECKING:
    from clio.ui.handler_protocol import HandlerProtocol

_SEG_RE = re.compile(r"^(.+)_(?:seg|part|pt|chunk)(\d+)$", re.IGNORECASE)
_VIDEOS_CACHE_LOCK = threading.Lock()
_VIDEOS_CACHE_MAX = 20
_VIDEOS_CACHE: dict[tuple[str, str, str], tuple[tuple[Any, ...], dict[str, Any]]] = {}


def _parse_segment_info(stem: str) -> tuple[str | None, int | None]:
    """Extract group info from a compressed stem like '001_GL010683_seg01'.
    Also supports _partNN, _ptNN, _chunkNN suffixes (case-insensitive).
    Returns (group_key, segment_number) or (None, None).
    """
    if "_" not in stem:
        return None, None
    m = _SEG_RE.match(stem.split("_", 1)[1])
    if not m:
        return None, None
    return m.group(1), int(m.group(2))


def _original_rel_name(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _resolve_original_video_path(root: Path, requested: str) -> Path | None:
    parts = requested.split("_", 1)
    actual = parts[1] if len(parts) == 2 and parts[0].isdigit() else requested
    rel = Path(actual)
    if rel.is_absolute() or ".." in rel.parts:
        return None
    try:
        candidate = (root / rel).resolve()
        root_resolved = root.resolve()
        candidate.relative_to(root_resolved)
    except (OSError, ValueError):
        return None
    return candidate


def _load_videos_json_selection(proj_input: Path) -> set[Path] | None:
    """Load videos.json selection.

    Returns None only when videos.json is absent (legacy project).
    Empty list / offline paths still yield a set so selection mode stays active.
    """
    if not (proj_input / "videos.json").is_file():
        return None
    selected = load_selected_videos(proj_input)
    return {p.resolve() for p in selected}


def handle_get_videos(handler: HandlerProtocol, qs: dict[str, Any]) -> None:
    """Handle GET /api/videos. Sends JSON response directly."""

    proj_input = handler._resolve_project_input(qs)
    proj_out = handler._get_project_output(proj_input)
    source = qs.get("source", ["compressed"])[0]
    if source not in ("compressed", "original"):
        return handler._send_json({"ok": False, "error": "source must be compressed|original"}, 400)
    comp_dir = proj_out / "compressed"
    cfg = handler._get_config(proj_input)
    cache_key = (str(proj_input.resolve()), str(proj_out.resolve()), source)
    selected_set = _load_videos_json_selection(proj_input)
    signature = _videos_cache_signature(proj_input, proj_out, comp_dir, cfg)
    with _VIDEOS_CACHE_LOCK:
        cached = _VIDEOS_CACHE.get(cache_key)
        if cached is not None and cached[0] == signature:
            return handler._send_json(deepcopy(cached[1]))

    payload = _build_videos_payload(handler, proj_input, proj_out, comp_dir, source, cfg, selected_set=selected_set)
    with _VIDEOS_CACHE_LOCK:
        if len(_VIDEOS_CACHE) >= _VIDEOS_CACHE_MAX and cache_key not in _VIDEOS_CACHE:
            _VIDEOS_CACHE.pop(next(iter(_VIDEOS_CACHE)))
        _VIDEOS_CACHE[cache_key] = (signature, deepcopy(payload))
    handler._send_json(payload)


def _file_fingerprint(path: Path) -> tuple[Any, ...]:
    """Fingerprint a single file (size, mtime) for cache invalidation."""
    try:
        st = path.stat()
        return (st.st_size, st.st_mtime_ns)
    except OSError:
        return ()


def _videos_cache_signature(proj_input: Path, proj_out: Path, comp_dir: Path, cfg: Any) -> tuple[Any, ...]:
    text_dirs = tuple(_find_texts_dirs(proj_out))
    videos_json = proj_input / "videos.json"
    return (
        _file_fingerprint(videos_json),  # must invalidate when selection changes
        _dir_fingerprint(proj_input, video_only=True),
        _dir_fingerprint(comp_dir),
        tuple((str(td), _dir_fingerprint(td, json_only=True)) for td in text_dirs),
        _dir_fingerprint(proj_out / "scripts", json_only=True),
        _dir_fingerprint(proj_out / cfg.whisper.transcripts_subdir, json_only=True),
        cfg.whisper.transcripts_subdir,
        cfg.paths.ffprobe,
    )


def _invalidate_videos_cache(proj_input: Path | None = None) -> None:
    """Drop cached /api/videos payloads (all sources for a project, or entire cache)."""
    with _VIDEOS_CACHE_LOCK:
        if proj_input is None:
            _VIDEOS_CACHE.clear()
            return
        key_prefix = str(proj_input.resolve())
        for key in list(_VIDEOS_CACHE):
            if key[0] == key_prefix:
                _VIDEOS_CACHE.pop(key, None)


def _dir_fingerprint(path: Path, *, video_only: bool = False, json_only: bool = False) -> tuple[Any, ...]:
    if not path.is_dir():
        return ()
    entries = []
    for p in sorted(path.iterdir()):
        if video_only and p.suffix.lower() not in VIDEO_EXTS:
            continue
        if json_only and p.suffix.lower() != ".json":
            continue
        try:
            st = p.stat()
        except OSError:
            continue
        kind = "dir" if p.is_dir() else "file"
        entries.append((p.name, kind, st.st_size, st.st_mtime_ns))
    return tuple(entries)


def _build_videos_payload(
    handler: HandlerProtocol,
    proj_input: Path,
    proj_out: Path,
    comp_dir: Path,
    source: str,
    cfg: Any,
    *,
    selected_set: set[Path] | None = None,
) -> dict[str, Any]:
    # -- Build artifact index ------------------------------------------------
    index = ArtifactIndex(
        output_dir=proj_out,
        input_dir=proj_input,
        compressed_dir=comp_dir,
        texts_dir=proj_out / "texts",
        scripts_dir=proj_out / "scripts",
        transcripts_dir=proj_out / cfg.whisper.transcripts_subdir,
    )
    index.build()

    # Keep text_titles by index for original source view
    text_titles: dict[str, str] = {}
    for g in index.all_groups():
        if g.texts:
            text_titles[g.compressed.index] = g.texts[0].title

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
                group_key, seg_num = _parse_segment_info(stem)
                group = index.lookup(compressed_stem=stem)
                orig = _find_original_for_compressed(stem, proj_input, comp_dir, project_dir=proj_input)
                if selected_set is not None:
                    meta = VideoMeta.read(p)
                    if meta is not None:
                        if Path(meta.source_path).resolve() not in selected_set:
                            continue
                    elif orig:
                        op = Path(orig)
                        try:
                            orig_resolved = (
                                op.resolve() if op.is_file() or op.is_absolute() else (proj_input / op).resolve()
                            )
                        except OSError:
                            continue
                        if orig_resolved not in selected_set:
                            # also try basename membership for offline paths stored differently
                            if not any(s.name == Path(orig).name for s in selected_set):
                                continue
                    else:
                        # selection active but cannot link this compressed file → hide
                        continue
                match_file = None
                abs_match = None
                if orig:
                    op = Path(orig)
                    match_file = op.name
                    if op.is_absolute() or op.is_file():
                        try:
                            abs_match = str(op.resolve())
                        except OSError:
                            abs_match = str(op)
                v: dict[str, Any] = {
                    "file": p.name,
                    "source": "compressed",
                    "index": idx,
                    "title": group.texts[0].title if group and group.texts else text_titles.get(idx, ""),
                    "text_json": group.texts[0].path.name if group and group.texts else None,
                    "script_json": group.script.path.name if group and group.script else None,
                    "transcript_file": group.transcript.stem if group and group.transcript else None,
                    "match": (
                        {
                            "source": "original",
                            "file": match_file,
                            "abs_path": abs_match,
                        }
                        if orig
                        else None
                    ),
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
                offsets: dict[str, float] = {}
                durations: dict[str, float] = {}
                for member_idx, seg_num in members:
                    for v in videos:
                        if v["index"] == member_idx:
                            comp_file = comp_dir / v["file"]
                            meta = VideoMeta.read(comp_file)
                            if meta and meta.split_info:
                                offsets[member_idx] = meta.split_info.offset_sec
                                durations[member_idx] = meta.split_info.segment_duration_sec
                            break
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
                                durations[member_idx] = round(seg_dur, 1)
                        except Exception:
                            pass
                for member_idx, seg_num in members:
                    for v in videos:
                        if v["index"] == member_idx:
                            v["segment_label"] = f"{seg_num}/{total}"
                            v["offset_sec"] = offsets.get(member_idx, 0.0)
                            v["duration_sec"] = durations.get(member_idx, 0.0)
                            break
    else:  # original
        # resolve ffprobe once for segment offset computation
        try:
            cfg = handler._get_config(proj_input)
            _ffprobe = resolve_binary(cfg.paths.ffprobe, "ffprobe")
        except Exception:
            _ffprobe = None

        if selected_set is not None:
            video_paths = sorted(selected_set, key=lambda p: p.name.lower())
        else:
            # No videos.json selection → empty list (do not scan project_dir)
            video_paths = []
        for p in video_paths:
            if p.is_dir() or p.suffix.lower() not in VIDEO_EXTS:
                continue
            if selected_set is not None:
                abs_path = str(p.resolve())
                rel_name = p.name
                proj_input_abs = proj_input.resolve()
                try:
                    rel_name = p.relative_to(proj_input_abs).as_posix()
                except ValueError:
                    rel_name = p.name
            else:
                abs_path = None
                rel_name = _original_rel_name(p, proj_input)
            comp = _find_compressed_for_original(p.stem, comp_dir)
            if not comp:
                orig_groups = index.lookup(original_stem=p.stem)
                has_transcript = any(g.transcript is not None for g in (orig_groups or []))
                v = {
                    "file": rel_name,
                    "source": "original",
                    "index": None,
                    "match": None,
                    "transcript_file": p.stem if has_transcript else None,
                }
                if abs_path:
                    v["abs_path"] = abs_path
                videos.append(v)
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
                group = index.lookup(compressed_stem=Path(c_file).stem)
                seg_v: dict[str, Any] = {
                    "file": f"{c_idx}_{rel_name}",
                    "source": "original",
                    "index": c_idx,
                    "title": text_titles.get(c_idx, ""),
                    "offset_sec": seg_offsets.get(c_idx, 0.0),
                    "text_json": group.texts[0].path.name if group and group.texts else None,
                    "script_json": group.script.path.name if group and group.script else None,
                    "transcript_file": group.transcript.stem if group and group.transcript else None,
                    "match": {"source": "compressed", "file": c_file, "index": c_idx},
                }
                if abs_path:
                    seg_v["abs_path"] = abs_path
                if len(segment_matches) > 1:
                    seg_v["segment_matches"] = segment_matches
                videos.append(seg_v)
    videos.sort(key=_video_sort_key)
    return {"videos": videos, "source": source, "groups": groups}


def _video_sort_key(video: dict[str, Any]) -> tuple[str, int, int, str]:
    match_file = ""
    if isinstance(video.get("match"), dict):
        match_file = str(video["match"].get("file") or "")
    source_name = match_file if video.get("source") == "compressed" and match_file else str(video.get("file") or "")
    stem = Path(source_name).stem
    if "_" in stem and stem.split("_", 1)[0].isdigit():
        stem = stem.split("_", 1)[1]
    stem = re.sub(r"_(?:seg|part|pt|chunk)\d+$", "", stem, flags=re.IGNORECASE)
    seg = 0
    label = str(video.get("segment_label") or "")
    if "/" in label:
        try:
            seg = int(label.split("/", 1)[0])
        except ValueError:
            seg = 0
    elif video.get("offset_sec"):
        seg = int(float(video.get("offset_sec") or 0) * 1000)
    idx = str(video.get("index") or "")
    try:
        idx_num = int(idx)
    except ValueError:
        idx_num = 0
    return (stem.lower(), seg, idx_num, str(video.get("file") or "").lower())


def handle_get_video(handler: HandlerProtocol, qs: dict[str, Any]) -> None:
    """Handle GET /api/video. Sends video range response directly."""

    proj_input = handler._resolve_project_input(qs)
    proj_out = handler._get_project_output(proj_input)
    fname = qs.get("file", [""])[0]
    source = qs.get("source", ["compressed"])[0]
    if source == "original":
        abspath = qs.get("abspath", [None])[0]
        if abspath:
            vp = Path(abspath).resolve()
            if not vp.is_file() or vp.suffix.lower() not in VIDEO_EXTS:
                return handler.send_error(HTTPStatus.NOT_FOUND)
            selected = load_selected_videos(proj_input)
            if vp not in {p.resolve() for p in selected}:
                return handler.send_error(HTTPStatus.FORBIDDEN)
        else:
            vp = _resolve_original_video_path(proj_input, fname)
            if vp is None:
                return handler.send_error(HTTPStatus.FORBIDDEN)
    else:
        if not _is_safe_basename(fname):
            return handler.send_error(HTTPStatus.FORBIDDEN)
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
                from clio.vmeta import _meta_to_dict

                return handler._send_json(_meta_to_dict(meta))
    handler._send_json({"ok": False, "error": "not found"}, 404)


def handle_get_videos_selected(handler: HandlerProtocol, qs: dict[str, Any]) -> None:
    """Handle GET /api/videos/selected — load videos.json."""
    proj_input = handler._resolve_project_input(qs)
    videos = load_selected_videos(proj_input)
    data = [str(p) for p in videos]
    handler._send_json({"videos": data})


def handle_put_videos_selected(handler: HandlerProtocol, qs: dict[str, Any], obj: dict) -> None:
    """Handle PUT /api/videos/selected — save to videos.json."""
    proj_input = handler._resolve_project_input(qs)
    raw = obj.get("videos", [])
    if not isinstance(raw, list):
        return handler._send_json({"ok": False, "error": "videos must be a list"}, 400)
    paths: list[Path] = []
    rejected: list[str] = []
    for item in raw:
        p = Path(str(item)).expanduser()
        try:
            resolved = p.resolve()
        except OSError:
            rejected.append(str(item))
            continue
        if not resolved.is_file() or resolved.suffix.lower() not in VIDEO_EXTS:
            rejected.append(str(item))
            continue
        paths.append(resolved)
    # Dedup while preserving order
    seen: set[Path] = set()
    unique: list[Path] = []
    for p in paths:
        if p not in seen:
            seen.add(p)
            unique.append(p)
    save_selected_videos(proj_input, unique)
    _invalidate_videos_cache(proj_input)
    payload: dict[str, Any] = {"ok": True, "count": len(unique)}
    if rejected:
        payload["rejected"] = rejected[:20]
        payload["rejected_count"] = len(rejected)
    handler._send_json(payload)
