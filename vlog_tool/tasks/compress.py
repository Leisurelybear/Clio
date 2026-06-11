"""Compression task — compress source videos."""

from __future__ import annotations

import time
from pathlib import Path

from vlog_tool.compress import compress_video
from vlog_tool.config import AppConfig
from vlog_tool.log import timed
from vlog_tool.progress import ProgressTracker
from vlog_tool.tasks._helpers import ClipRecord, _eta_line, _next_index
from vlog_tool.utils import find_videos, format_index


def run_compress_all(
    config: AppConfig, tracker: ProgressTracker | None = None, single_file: Path | None = None
) -> list[ClipRecord]:
    if single_file:
        videos = [single_file]
    else:
        videos = find_videos(config.paths.input_dir, recursive=config.paths.recursive)
    config.compressed_dir.mkdir(parents=True, exist_ok=True)
    records: list[ClipRecord] = []

    index_offset = 0
    if single_file:
        index_offset = _next_index(config.compressed_dir, config.naming.index_width) - 1

    with timed(f"run_compress_all（{len(videos)} 个）"):
        completed = 0
        elapsed_total = 0.0
        for i, video in enumerate(videos, start=1):
            if tracker:
                tracker.update(phase="compress", current=i, total=len(videos), message=f"压缩 {video.name}...")
            idx_val = i + index_offset
            idx = format_index(idx_val, config.naming.index_width)
            out = config.compressed_dir / f"{idx}_{video.stem}.mp4"
            if config.analyze.skip_existing and out.exists():
                print(f"[跳过压缩] {video.name} (已存在: {out.name})")
            else:
                print(_eta_line("压缩", i, len(videos), video.name, completed, elapsed_total))
                t0 = time.monotonic()
                compress_video(video, out, config)
                elapsed_total += time.monotonic() - t0
                completed += 1
            records.append(ClipRecord(index=idx_val, stem=out.stem, source_path=video, compressed_path=out))
    return records
