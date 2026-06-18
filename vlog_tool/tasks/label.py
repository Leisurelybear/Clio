"""Label task — burn sequence numbers onto compressed videos."""

from __future__ import annotations

import json
import time

from vlog_tool.config import AppConfig
from vlog_tool.log import timed
from vlog_tool.progress import ProgressTracker
from vlog_tool.tasks._helpers import _eta_line
from vlog_tool.utils import format_index, resolve_binary, run_ffmpeg


def run_label_videos(config: AppConfig, tracker: ProgressTracker | None = None) -> None:
    """用 ffmpeg 在压缩视频上烧录序号（便于剪映对照）。"""
    ffmpeg = resolve_binary(config.paths.ffmpeg, "ffmpeg")
    labeled_dir = config.paths.output_dir / "labeled"
    labeled_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(config.texts_dir.glob("*.json"))
    if tracker:
        tracker.update(phase="label", total=len(files), message=f"烧录序号（{len(files)} 个）...")
    with timed(f"run_label_videos（{len(files)} 个）"):
        completed = 0
        elapsed_total = 0.0
        for i, json_file in enumerate(files, start=1):
            data = json.loads(json_file.read_text(encoding="utf-8"))
            raw_idx = data.get("index")
            try:
                idx = (
                    format_index(int(raw_idx), config.naming.index_width) if raw_idx is not None else json_file.stem[:3]
                )
            except (ValueError, TypeError):
                idx = json_file.stem[:3]
            compressed = None
            for f in config.compressed_dir.glob(f"{idx}_*"):
                compressed = f
                break
            if not compressed or not compressed.exists():
                print(f"[跳过] 找不到压缩文件: {idx}")
                if tracker:
                    tracker.next(message=f"跳过 {idx}（无压缩文件）")
                continue

            out = labeled_dir / f"{json_file.stem}_labeled.mp4"
            if config.analyze.skip_existing and out.exists():
                print(f"[跳过标注] {out.name} (已存在)")
                if tracker:
                    tracker.next(message=f"跳过 {out.name}")
                continue

            print(_eta_line("标注", i, len(files), json_file.stem, completed, elapsed_total))
            if tracker:
                tracker.next(message=f"标注 {json_file.stem}")
            t0 = time.monotonic()
            label = idx.replace("'", "")
            vf = f"drawtext=text='{label}':fontsize=36:fontcolor=white:box=1:boxcolor=black@0.5:boxborderw=8:x=20:y=20"
            run_ffmpeg(["-i", str(compressed), "-vf", vf, "-an", "-y", str(out)], ffmpeg)
            elapsed_total += time.monotonic() - t0
            completed += 1
            if tracker:
                tracker.log(f"标号 {json_file.stem} ✓")
            print(f"  -> {out.name}")
