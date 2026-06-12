"""Analysis task — AI analysis of compressed videos."""

from __future__ import annotations

import json
import time
from pathlib import Path

from vlog_tool.analyze import analyze_video
from vlog_tool.config import AppConfig
from vlog_tool.log import timed
from vlog_tool.progress import ProgressTracker
from vlog_tool.tasks._helpers import (
    ClipRecord,
    _build_stem,
    _eta_line,
    _write_csv,
    _write_text_file,
)


def run_analyze_all(
    config: AppConfig, tracker: ProgressTracker | None = None, single_file: Path | None = None
) -> list[ClipRecord]:
    """Analyze already-compressed videos using AI (compress step must precede this).

    Scans compressed_dir for existing *.mp4 files and analyzes each.
    For single_file (an original video), finds the matching compressed file first.
    """
    config.texts_dir.mkdir(parents=True, exist_ok=True)
    records: list[ClipRecord] = []

    if single_file:
        items: list[tuple[Path, Path, str]] = []
        candidates = sorted(config.compressed_dir.glob(f"*_{single_file.stem}.mp4"))
        if not candidates:
            print(f"[错误] 未找到 {single_file.name} 对应的压缩文件，请先运行压缩步骤")
            return []
        compressed = candidates[0]
        idx_str = compressed.stem.split("_", 1)[0]
        items.append((compressed, single_file, idx_str))
    else:
        items = []
        for p in sorted(config.compressed_dir.glob("*.mp4")):
            parts = p.stem.split("_", 1)
            if len(parts) != 2 or not parts[0].isdigit():
                continue
            idx_str, orig_stem = parts
            orig_path = config.paths.input_dir / f"{orig_stem}.mp4"
            if not orig_path.is_file():
                for ext in (".mov", ".mkv", ".avi", ".mts", ".m2ts"):
                    alt = config.paths.input_dir / f"{orig_stem}{ext}"
                    if alt.is_file():
                        orig_path = alt
                        break
                else:
                    print(f"[警告] 找不到 {p.name} 对应的原始视频，跳过")
                    continue
            items.append((p, orig_path, idx_str))

    if not items:
        print(f"[错误] 压缩目录为空或无法匹配: {config.compressed_dir}，请先运行压缩步骤")
        return []

    total = len(items)
    print(f"待分析视频: {total} 个（压缩目录: {config.compressed_dir}）")

    with timed(f"run_analyze_all（{total} 个）"):
        completed = 0
        elapsed_total = 0.0
        for i, (compressed, original, idx_str) in enumerate(items, start=1):
            idx_val = int(idx_str)

            existing = sorted(config.texts_dir.glob(f"{idx_str}_*.json"))
            if config.analyze.skip_existing and existing:
                json_path = existing[0]
                text_path = json_path.with_suffix(".txt")
                analysis = json.loads(json_path.read_text(encoding="utf-8"))
                print(f"[跳过分析] {compressed.name} (已存在: {json_path.name})")
                records.append(
                    ClipRecord(
                        index=idx_val,
                        stem=json_path.stem,
                        source_path=original,
                        compressed_path=compressed,
                        text_path=text_path,
                        analysis=analysis,
                    )
                )
                continue

            print(_eta_line("分析", i, total, compressed.name, completed, elapsed_total))
            if tracker:
                tracker.update(phase="analyze", current=i, message=f"分析 {compressed.name}...")
            t0 = time.monotonic()
            try:
                analysis = analyze_video(str(compressed), config)
            except Exception as e:
                print(f"  [错误] 分析 {compressed.name} 失败: {e}")
                if tracker:
                    tracker.log(f"分析 {compressed.name} 失败: {e}")
                continue
            elapsed_total += time.monotonic() - t0
            completed += 1
            analysis["index"] = idx_val
            analysis["source_file"] = original.name

            stem = _build_stem(idx_val, analysis.get("title", original.stem), config)
            final_text = config.texts_dir / f"{stem}.txt"
            json_path = config.texts_dir / f"{stem}.json"

            _write_text_file(final_text, analysis, original, compressed)
            json_path.write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")

            records.append(
                ClipRecord(
                    index=idx_val,
                    stem=stem,
                    source_path=original,
                    compressed_path=compressed,
                    text_path=final_text,
                    analysis=analysis,
                )
            )
            print(f"  -> {final_text.name}")

    _write_csv(config.summary_csv, records, config)
    print(f"\nCSV 已保存: {config.summary_csv}")
    return records
