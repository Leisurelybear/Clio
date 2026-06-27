"""Cut task — clip video segments based on plan."""

from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path

from vlog_tool._constants import VIDEO_EXTS
from vlog_tool.config import AppConfig
from vlog_tool.cut import cut_one, parse_time_range
from vlog_tool.identity import load_identity
from vlog_tool.log import format_duration, timed
from vlog_tool.processing_state import ProcessingState
from vlog_tool.tasks._helpers import _eta_line
from vlog_tool.utils import (
    find_videos,
    get_duration_sec,
    resolve_binary,
    sanitize_name,
    write_json_atomic,
    write_text_atomic,
)
from vlog_tool.vmeta import VideoMeta

_SEG_RE = re.compile(r"^(.+)_seg(\d+)$")


def _compute_segment_offset(compressed_stem: str, comp_dir: Path, original_path: Path, ffprobe: str) -> float:
    """For a split segment, compute its start offset in the original video.
    Returns 0.0 if the file is not a segment or offset cannot be computed.
    """
    for p in comp_dir.glob(f"{compressed_stem}.*"):
        if p.suffix.lower() in VIDEO_EXTS:
            meta = VideoMeta.read(p)
            if meta and meta.split_info:
                return meta.split_info.offset_sec

    # 降级：原有估算逻辑
    m = _SEG_RE.match(compressed_stem.split("_", 1)[1] if "_" in compressed_stem else "")
    if not m:
        return 0.0
    prefix = m.group(1).lower()
    seg_num = int(m.group(2))
    total = 0
    for p in sorted(comp_dir.iterdir()):
        if p.suffix.lower() not in VIDEO_EXTS:
            continue
        pm = _SEG_RE.match(p.stem.split("_", 1)[1] if "_" in p.stem else "")
        if pm and pm.group(1).lower() == prefix:
            total = max(total, int(pm.group(2)))
    if total <= 1:
        return 0.0
    try:
        dur = get_duration_sec(original_path, ffprobe)
    except Exception:
        return 0.0
    return round((seg_num - 1) * dur / total, 1)


def run_cut_all(
    config: AppConfig,
    day_label: str = "day1",
    output_dir: Path | None = None,
    reencode: bool = False,
    source: str = "compressed",
    cancel_event: threading.Event | None = None,
) -> list[dict]:
    """根据 plan 按时间区间裁剪视频片段。

    读取 plans/<day_label>_plan.json，对 sequence[] 中每个 segment
    用 ffmpeg 从对应压缩视频中裁剪 [use_timeline] 段。

    输出：剪好的 clip 文件 + 对应 texts JSON + manifest.md。
    """
    plan_path = config.plans_dir / f"{day_label}_plan.json"
    if not plan_path.is_file():
        raise FileNotFoundError(f"规划文件不存在: {plan_path}")

    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    seq = plan.get("sequence", [])
    if not seq:
        print(f"规划文件中没有 sequence 段: {plan_path.name}")
        return []

    out_root = (output_dir or config.paths.output_dir / "cuts" / day_label).resolve()
    out_root.mkdir(parents=True, exist_ok=True)
    ffmpeg = resolve_binary(config.paths.ffmpeg, "ffmpeg")
    ffprobe = resolve_binary(config.paths.ffprobe, "ffprobe")
    comp_dir = config.compressed_dir
    input_dir = config.paths.input_dir

    print(f"[cut] 计划: {plan_path.name} ({len(seq)} 段)")
    print(f"[cut] 输出: {out_root}")
    print(f"[cut] 视频来源: {source} ({comp_dir if source == 'compressed' else input_dir})")

    state = ProcessingState(config.paths.output_dir)

    def _orig_stem_from_path(video_path: Path) -> str:
        stem = video_path.stem
        if "_" in stem:
            stem = stem.split("_", 1)[1]
        m = _SEG_RE.match(stem)
        return m.group(1) if m else stem

    def _resolve_video_path(idx: str) -> Path | None:
        if source == "compressed":
            candidates = sorted(comp_dir.glob(f"{idx}_*"))
            return candidates[0] if candidates else None
        else:
            comp_candidates = sorted(comp_dir.glob(f"{idx}_*"))
            if not comp_candidates:
                return None
            compressed = comp_candidates[0]

            # 优先：读 .vmeta 直接拿原始路径（O(1)，支持任意目录层级）
            meta = VideoMeta.read(compressed)
            if meta is not None:
                src = meta.source_path_obj()
                if src.is_file():
                    return src

            # 降级：regex 反解 + rglob（修复 B-06）
            suffix = compressed.stem.split("_", 1)[1].lower()
            m = _SEG_RE.match(suffix)
            orig_stem = m.group(1) if m else suffix
            for p in find_videos(input_dir, recursive=True):
                if p.stem.lower() == orig_stem:
                    return p
            return None

    clips: list[dict] = []
    completed = 0
    elapsed_total = 0.0

    with timed(f"run_cut_all {day_label}（{len(seq)} 段）"):
        for i, seg in enumerate(seq, start=1):
            if cancel_event and cancel_event.is_set():
                print(f"  [取消] 裁剪阶段被用户终止（第 {i} 段）")
                break
            idx = seg.get("index", "")
            title = seg.get("title", "").strip()
            timeline = (seg.get("use_timeline") or "").strip()
            if not idx or not timeline:
                print(f"  [跳过] 第 {i} 段缺少 index 或 use_timeline")
                continue

            video_path = _resolve_video_path(idx)
            if video_path is None:
                src = "compressed" if source != "original" else "original"
                print(f"  [跳过] 找不到 index={idx} 的视频（{src}）: {seg.get('title', '')}")
                continue

            try:
                start, end = parse_time_range(timeline)
            except ValueError as e:
                print(f"  [跳过] 时间格式错误 '{timeline}': {e}")
                orig_stem = _orig_stem_from_path(video_path) if video_path else ""
                if orig_stem:
                    state.mark(orig_stem, "cut", "skipped")
                continue

            # Apply segment offset for original source with split videos
            offset = 0.0
            if source == "original":
                # Prefer media_identity.segment_offset_sec from analysis JSON
                text_json_paths = sorted(config.texts_dir.glob(f"{idx}_*.json"))
                if text_json_paths:
                    try:
                        data = json.loads(text_json_paths[0].read_text(encoding="utf-8"))
                        identity = load_identity(data)
                        if identity is not None and identity.segment_offset_sec:
                            offset = identity.segment_offset_sec
                    except Exception:
                        pass
                # Fall back to vmeta-based computation for v1 files
                if offset == 0.0:
                    comp_candidates = sorted(comp_dir.glob(f"{idx}_*"))
                    if comp_candidates:
                        stem = comp_candidates[0].stem
                        offset = _compute_segment_offset(stem, comp_dir, video_path, ffprobe)
                if offset:
                    start += offset
                    end += offset

            clip_stem = f"{idx}_{sanitize_name(title, max_len=30)}_seg_{i:03d}"
            clip_path = out_root / f"{clip_stem}.mp4"

            print(_eta_line("裁剪", i, len(seq), clip_stem, completed, elapsed_total))
            t0 = time.monotonic()
            try:
                cut_one(video_path, clip_path, start, end, ffmpeg, reencode=reencode, cancel_event=cancel_event)
                state.mark(_orig_stem_from_path(video_path), "cut", "done")
            except Exception:
                state.mark(_orig_stem_from_path(video_path), "cut", "error")
                raise
            elapsed_total += time.monotonic() - t0
            completed += 1

            # 复制对应的 texts JSON，附加 _cut_info 标明片段来源
            text_json = None
            matching_texts = sorted(config.texts_dir.glob(f"{idx}_*.json"))
            if matching_texts:
                text_path = matching_texts[0]
                data = json.loads(text_path.read_text(encoding="utf-8"))
                data["_cut_info"] = {
                    "seg_index": i,
                    "timeline": timeline,
                    "start_sec": round(start, 2),
                    "end_sec": round(end, 2),
                }
                dst = out_root / f"{clip_stem}.json"
                write_json_atomic(dst, data)
                text_json = dst.name
                print(f"  -> texts: {dst.name}")

            clips.append(
                {
                    "seg_index": i,
                    "video_index": idx,
                    "title": title,
                    "timeline": timeline,
                    "start_sec": round(start, 2),
                    "end_sec": round(end, 2),
                    "duration_sec": round(end - start, 2),
                    "output_file": clip_path.name,
                    "text_file": text_json or "",
                }
            )

    manifest_path = out_root / "manifest.md"
    lines = [
        f"# {plan.get('day_title', day_label)} — 剪辑片段",
        "",
        f"**主题**: {plan.get('theme', '')}",
        f"**预估总时长**: {plan.get('total_estimated_sec', '')} 秒",
        f"**实际输出**: {out_root}",
        "",
        "| # | 视频 | 标题 | 时间范围 | 时长 | 输出文件 | texts |",
        "|---|------|------|---------|------|---------|-------|",
    ]
    for c in clips:
        lines.append(
            f"| {c['seg_index']} | {c['video_index']} | {c['title']} "
            f"| {c['timeline']} | {format_duration(c['duration_sec'])} "
            f"| {c['output_file']} | {c['text_file'] or '-'} |"
        )
    write_text_atomic(manifest_path, "\n".join(lines) + "\n")
    print(f"  -> manifest: {manifest_path.name}")
    print(f"完成！共裁剪 {len(clips)} 段，输出目录: {out_root}")
    return clips
