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
    single_idx_str = None
    single_out = None
    if single_file:
        # 查找是否已有同名压缩文件，有则覆盖（保留原 index）
        existing = sorted(config.compressed_dir.glob(f"*_{single_file.stem}.mp4"))
        if existing:
            single_idx_str = existing[0].stem.split("_", 1)[0]
            single_out = existing[0]
        else:
            # 没有同名文件，用下一个可用 index
            idx_val = _next_index(config.compressed_dir, config.naming.index_width)
            single_idx_str = format_index(idx_val, config.naming.index_width)
            single_out = config.compressed_dir / f"{single_idx_str}_{single_file.stem}.mp4"

    with timed(f"run_compress_all（{len(videos)} 个）"):
        completed = 0
        elapsed_total = 0.0
        for i, video in enumerate(videos, start=1):
            if tracker:
                tracker.update(phase="compress", current=i, total=len(videos), message=f"压缩 {video.name}...")
            if single_file:
                use_idx = int(single_idx_str)
                use_out = single_out
            else:
                use_idx = i + index_offset
                use_out = config.compressed_dir / f"{format_index(use_idx, config.naming.index_width)}_{video.stem}.mp4"
            if config.analyze.skip_existing and use_out.exists():
                print(f"[跳过压缩] {video.name} (已存在: {use_out.name})")
            else:
                print(_eta_line("压缩", i, len(videos), video.name, completed, elapsed_total))
                t0 = time.monotonic()
                compress_video(video, use_out, config)
                elapsed_total += time.monotonic() - t0
                completed += 1
            records.append(ClipRecord(index=use_idx, stem=use_out.stem, source_path=video, compressed_path=use_out))
    return records
