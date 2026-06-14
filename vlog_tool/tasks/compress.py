"""Compression task — compress source videos (with optional auto-split)."""

from __future__ import annotations

import time
from pathlib import Path

from vlog_tool.compress import compress_video
from vlog_tool.config import AppConfig
from vlog_tool.log import timed
from vlog_tool.progress import ProgressTracker
from vlog_tool.split import split_video
from vlog_tool.tasks._helpers import ClipRecord, _eta_line, _next_index
from vlog_tool.utils import find_videos, format_index, resolve_binary


def run_compress_all(
    config: AppConfig, tracker: ProgressTracker | None = None, single_file: Path | None = None
) -> list[ClipRecord]:
    ffmpeg = resolve_binary(config.paths.ffmpeg, "ffmpeg")
    ffprobe = resolve_binary(config.paths.ffprobe, "ffprobe")

    if single_file:
        videos = [single_file]
    else:
        videos = find_videos(config.paths.input_dir, recursive=config.paths.recursive)
    config.compressed_dir.mkdir(parents=True, exist_ok=True)

    # Phase 1: resolve items to compress — split long videos if needed
    items: list[tuple[Path, Path]] = []  # (original_path, path_to_compress)
    for video in videos:
        max_min = config.compress.split_max_min
        if max_min > 0:
            splits_dir = config.paths.output_dir / config.compress.splits_subdir
            segments = split_video(video, splits_dir, max_min, ffmpeg, ffprobe)
            for seg in segments:
                items.append((video, seg))
        else:
            items.append((video, video))

    # Phase 2: assign indices and compress each
    next_idx = _next_index(config.compressed_dir, config.naming.index_width)
    records: list[ClipRecord] = []
    comp_label = f"run_compress_all（{len(items)} 个）"
    with timed(comp_label):
        completed = 0
        elapsed_total = 0.0
        for i, (original, source) in enumerate(items, start=1):
            use_idx = next_idx + i - 1
            use_out = config.compressed_dir / f"{format_index(use_idx, config.naming.index_width)}_{source.stem}.mp4"
            if tracker:
                tracker.update(phase="compress", current=i, total=len(items), message=f"压缩 {source.name}...")

            label_name = source.name if source == original else f"{original.name} → {source.name}"
            if config.analyze.skip_existing and use_out.exists():
                print(f"[跳过压缩] {label_name} (已存在: {use_out.name})")
            else:
                print(_eta_line("压缩", i, len(items), label_name, completed, elapsed_total))
                t0 = time.monotonic()
                if tracker:

                    def _on_progress(_sec: float, total_dur: float):
                        pct = int(_sec / total_dur * 100) if total_dur > 0 else 0
                        tracker.update(
                            phase="compress", current=i, total=len(items), message=f"压缩 {source.name} ({pct}%)"
                        )

                    compress_video(source, use_out, config, progress_callback=_on_progress)
                else:
                    compress_video(source, use_out, config)
                elapsed_total += time.monotonic() - t0
                completed += 1
            records.append(ClipRecord(index=use_idx, stem=use_out.stem, source_path=original, compressed_path=use_out))
    return records
