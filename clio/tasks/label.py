"""Label task — burn sequence numbers onto compressed videos."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from clio.config import AppConfig
from clio.log import timed
from clio.processing_state import ProcessingState
from clio.progress import ProgressTracker
from clio.tasks._helpers import _eta_line
from clio.utils import format_index, resolve_binary, run_ffmpeg


def run_label_videos(
    config: AppConfig,
    tracker: ProgressTracker | None = None,
    cancel_event: threading.Event | None = None,
    files: list[str] | None = None,
    overwrite: bool = False,
    **kwargs: Any,
) -> None:
    """用 ffmpeg 在压缩视频上烧录序号（便于剪映对照）。"""
    ffmpeg = resolve_binary(config.paths.ffmpeg, "ffmpeg")
    labeled_dir = config.paths.output_dir / "labeled"
    labeled_dir.mkdir(parents=True, exist_ok=True)
    state = ProcessingState(config.paths.output_dir)

    json_files = sorted(config.texts_dir.glob("*.json"))
    if files is not None:
        allowed = {Path(f).stem.lower() for f in files}
        json_files = [f for f in json_files if f.stem.lower() in allowed]
    if tracker:
        tracker.update(phase="label", total=len(json_files), message=f"烧录序号（{len(json_files)} 个）...")
    with timed(f"run_label_videos（{len(json_files)} 个）"):
        completed = 0
        elapsed_total = 0.0
        for i, json_file in enumerate(json_files, start=1):
            if cancel_event and cancel_event.is_set():
                print("[取消] label 步骤被用户终止")
                break
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
            orig_stem = json_file.stem.split("_", 1)[-1]
            if not compressed or not compressed.exists():
                print(f"[跳过] 找不到压缩文件: {idx}")
                state.mark(orig_stem, "label", "skipped")
                if tracker:
                    tracker.next(message=f"跳过 {idx}（无压缩文件）")
                continue

            out = labeled_dir / f"{json_file.stem}_labeled.mp4"
            if not overwrite and config.analyze.skip_existing and out.exists():
                print(f"[跳过标注] {out.name} (已存在)")
                state.mark(orig_stem, "label", "skipped")
                if tracker:
                    tracker.next(message=f"跳过 {out.name}")
                continue

            print(_eta_line("标注", i, len(json_files), json_file.stem, completed, elapsed_total))
            if tracker:
                tracker.next(message=f"标注 {json_file.stem}")
            t0 = time.monotonic()
            label = idx.replace("'", "")
            vf = f"drawtext=text='{label}':fontsize=36:fontcolor=white:box=1:boxcolor=black@0.5:boxborderw=8:x=20:y=20"
            try:
                run_ffmpeg(["-i", str(compressed), "-vf", vf, "-an", "-y", str(out)], ffmpeg)
                state.mark(orig_stem, "label", "done")
            except Exception:
                state.mark(orig_stem, "label", "error")
                raise
            elapsed_total += time.monotonic() - t0
            completed += 1
            if tracker:
                tracker.log(f"标号 {json_file.stem} ✓")
            print(f"  -> {out.name}")
