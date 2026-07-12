"""Compression task — compress source videos (with optional auto-split)."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

from clio._constants import VIDEO_EXTS
from clio.compress import compress_video
from clio.config import AppConfig
from clio.log import timed
from clio.processing_state import ProcessingState
from clio.progress import ProgressTracker
from clio.split import split_video
from clio.tasks._helpers import ClipRecord, _eta_line, _matches_selected_stem, _next_index, _selected_stems
from clio.utils import format_index, get_duration_sec, resolve_binary
from clio.vmeta import SegmentEntry, SplitInfo, VideoIndex, VideoMeta


def _build_split_info(source: Path, original: Path, config: AppConfig) -> SplitInfo | None:
    """从 split_manifest.json 读取本分段的 offset_sec 和段号信息。"""
    if source is original:
        return None
    manifest_path = config.compressed_dir / f"{original.stem}_split_manifest.json"
    if not manifest_path.is_file():
        return None
    try:
        import json

        entries = json.loads(manifest_path.read_text(encoding="utf-8"))
        total = len(entries)
        for e in entries:
            if e.get("filename") == source.name or Path(e.get("filename", "")).stem == source.stem:
                return SplitInfo(
                    original_stem=original.stem,
                    segment_index=e["segment_index"],
                    total_segments=total,
                    offset_sec=e["offset_sec"],
                    segment_duration_sec=e["actual_duration_sec"],
                )
    except Exception:
        pass
    return None


def _safe_duration(path: Path, ffprobe: str) -> float:
    try:
        return get_duration_sec(path, ffprobe)
    except Exception:
        return 0.0


def _write_vindex(records: list[ClipRecord], config: AppConfig, ffprobe: str) -> None:
    from collections import defaultdict

    compressed_dir = config.compressed_dir
    groups: dict[Path, list[ClipRecord]] = defaultdict(list)
    for rec in records:
        if rec.compressed_path is not None:
            groups[rec.source_path].append(rec)

    for original, recs in groups.items():
        seg_entries: list[SegmentEntry] = []
        source_dur = 0.0
        for rec in recs:
            if rec.meta is None or rec.compressed_path is None:
                continue
            source_dur = rec.meta.source_duration_sec
            si = rec.meta.split_info
            seg_entries.append(
                SegmentEntry(
                    index=format_index(rec.index, config.naming.index_width),
                    filename=rec.compressed_path.name,
                    offset_sec=si.offset_sec if si else 0.0,
                    duration_sec=rec.meta.target_duration_sec,
                    segment_number=si.segment_index if si else 1,
                    total_segments=si.total_segments if si else 1,
                )
            )

        if not seg_entries:
            continue

        vindex = VideoIndex.build(
            source=original,
            source_duration=source_dur,
            segments=sorted(seg_entries, key=lambda s: s.segment_number),
        )
        vindex.write(compressed_dir)


def run_compress_all(
    config: AppConfig,
    tracker: ProgressTracker | None = None,
    single_file: Path | None = None,
    cancel_event: threading.Event | None = None,
    files: list[str] | None = None,
    overwrite: bool = False,
    **kwargs: Any,
) -> list[ClipRecord]:
    ffmpeg = resolve_binary(config.paths.ffmpeg, "ffmpeg")
    ffprobe = resolve_binary(config.paths.ffprobe, "ffprobe")

    if single_file:
        videos = [single_file]
    else:
        from clio.tasks._video_loader import source_videos

        videos = source_videos(config)
    if files is not None:
        selected = _selected_stems(files)
        videos = [v for v in videos if _matches_selected_stem(v, selected)]
    config.compressed_dir.mkdir(parents=True, exist_ok=True)

    # Phase 1: resolve items to compress — split long videos if needed
    items: list[tuple[Path, Path]] = []  # (original_path, path_to_compress)
    split_staging_dir = config.paths.output_dir / config.compress.splits_subdir
    for video in videos:
        max_min = config.compress.split_max_min
        if max_min > 0:
            segments = split_video(
                video,
                split_staging_dir,
                max_min,
                ffmpeg,
                ffprobe,
                reencode=config.compress.reencode_split,
                manifest_dir=config.compressed_dir,
                cancel_event=cancel_event,
            )
            for seg in segments:
                items.append((video, seg))
        else:
            items.append((video, video))

    # Phase 2: build existing lookup (source_stem -> (index, Path))
    # Only include files >= 50KB to skip partially-written files from interrupted runs.
    MIN_VALID_SIZE = 50 * 1024
    existing_map: dict[str, tuple[int, Path]] = {}
    if not overwrite and config.analyze.skip_existing and config.compressed_dir.is_dir():
        for f in config.compressed_dir.iterdir():
            if not f.is_file() or f.suffix.lower() not in VIDEO_EXTS:
                continue
            if f.stat().st_size < MIN_VALID_SIZE:
                continue
            try:
                dur = get_duration_sec(f, ffprobe)
                if dur <= 0:
                    raise ValueError("zero duration")
            except Exception:
                print(f"[清理] {f.name} 已损坏（ffprobe 无法读取），重新压缩")
                f.unlink(missing_ok=True)
                continue
            if "_" in f.stem:
                prefix, stem_part = f.stem.split("_", 1)
                if prefix.isdigit():
                    existing_map[stem_part] = (int(prefix), f)

    # Also build lookup by original stem for split videos (strip _segNN suffix).
    # Handles the case where split_video fails on re-run (e.g. ffprobe returns 0)
    # but segments were already compressed before.
    def _orig_stem_for(stem_part: str) -> str:
        import re

        m = re.match(r"^(.+?)_seg\d+$", stem_part)
        return m.group(1) if m else stem_part

    orig_to_compressed: dict[str, set[str]] = {}
    if not overwrite and config.analyze.skip_existing:
        for stem_part in existing_map:
            orig_stem = _orig_stem_for(stem_part)
            orig_to_compressed.setdefault(orig_stem, set()).add(stem_part)

    # Phase 3: assign indices and compress each
    next_idx = _next_index(config.compressed_dir, config.naming.index_width)
    records: list[ClipRecord] = []
    state = ProcessingState(config.paths.output_dir)
    comp_label = f"run_compress_all（{len(items)} 个）"
    with timed(comp_label):
        completed = 0
        elapsed_total = 0.0
        for i, (original, source) in enumerate(items, start=1):
            label_name = source.name if source == original else f"{original.name} → {source.name}"

            # Reuse existing compressed file if skip_existing matches by stem
            if source.stem in existing_map:
                use_idx, use_out = existing_map[source.stem]
                if tracker:
                    tracker.update(phase="compress", current=i, total=len(items), message=f"压缩 {source.name}...")
                    tracker.log(f"⏭️ 跳过 {label_name}（已存在 {use_out.name}）")
                state.mark(original.stem, "compress", "skipped")
                print(f"[跳过压缩] {label_name} (已存在: {use_out.name})")
                records.append(
                    ClipRecord(index=use_idx, stem=use_out.stem, source_path=original, compressed_path=use_out)
                )
                continue

            # Fallback: source == original (no split) but compressed files with _segNN exist.
            # This happens when split_video failed/is inconsistent on re-run.
            if (
                not overwrite
                and config.analyze.skip_existing
                and source is original
                and original.stem in orig_to_compressed
            ):
                seg_stems = orig_to_compressed[original.stem]
                print(f"[跳过压缩] {label_name}: 已存在分割压缩片段 {', '.join(sorted(seg_stems))}")
                if tracker:
                    tracker.log(f"⏭️ 跳过 {label_name}（已存在分割文件）")
                state.mark(original.stem, "compress", "skipped")
                records.append(ClipRecord(index=0, stem=original.stem, source_path=original, compressed_path=None))
                continue

            use_idx = next_idx + completed
            use_out = config.compressed_dir / f"{format_index(use_idx, config.naming.index_width)}_{source.stem}.mp4"
            if tracker:
                tracker.update(phase="compress", current=i, total=len(items), message=f"压缩 {source.name}...")
                tracker.log(f"▶ 压缩 {label_name}")
            print(_eta_line("压缩", i, len(items), label_name, completed, elapsed_total))
            t0 = time.monotonic()
            if tracker:

                def _on_progress(_sec: float, total_dur: float, _i: int = i, _name: str = label_name):
                    pct = int(_sec / total_dur * 100) if total_dur > 0 else 0
                    tracker.update(phase="compress", current=_i, total=len(items), message=f"压缩 {_name} ({pct}%)")

                compress_video(source, use_out, config, progress_callback=_on_progress, cancel_event=cancel_event)
            else:
                compress_video(source, use_out, config, cancel_event=cancel_event)
            state.mark(original.stem, "compress", "done")
            elapsed_total += time.monotonic() - t0
            completed += 1

            # 写 .vmeta
            split_info = _build_split_info(source, original, config)
            src_dur = _safe_duration(original, ffprobe)
            tgt_dur = _safe_duration(use_out, ffprobe)
            meta = VideoMeta.build(
                source=original,
                target=use_out,
                source_duration=src_dur,
                target_duration=tgt_dur,
                compress_settings={
                    "max_width": config.compress.max_width,
                    "fps": config.compress.fps,
                    "target_size_mb": config.compress.target_size_mb,
                },
                split_info=split_info,
            )
            meta.write(use_out)

            records.append(
                ClipRecord(
                    index=use_idx,
                    stem=use_out.stem,
                    source_path=original,
                    compressed_path=use_out,
                    meta=meta,
                )
            )

    # 写 .vindex（每个原始文件一个，汇总所有分段）
    _write_vindex(records, config, ffprobe)
    return records
