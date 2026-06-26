"""Analysis task — AI analysis of compressed videos."""

from __future__ import annotations

import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from vlog_tool._constants import VIDEO_EXTS
from vlog_tool.ai.token_usage import FileTokenUsageStore
from vlog_tool.analyze import analyze_video
from vlog_tool.config import AppConfig
from vlog_tool.identity import _identity_to_dict, load_identity, resolve_identity
from vlog_tool.log import format_duration, timed
from vlog_tool.processing_state import ProcessingState
from vlog_tool.progress import ProgressTracker
from vlog_tool.tasks._helpers import (
    ClipRecord,
    _build_stem,
    _write_csv,
    _write_text_file,
)
from vlog_tool.utils import get_duration_sec, resolve_binary, write_json_atomic
from vlog_tool.vmeta import VideoIndex


def _build_stem_to_path(input_dir: Path) -> dict[str, Path]:
    """Build a one-time {stem_lower: path} map from input_dir (recursive)."""
    mapping: dict[str, Path] = {}
    exts = (".mp4", ".mov", ".mkv", ".avi", ".mts", ".m2ts", ".m4v", ".webm", ".lrv")
    for p in input_dir.rglob("*"):
        if p.is_file() and p.suffix.lower() in exts:
            mapping[p.stem.lower()] = p
    return mapping


def _resolve_original(input_dir: Path, compressed_stem: str, stem_cache: dict[str, Path] | None = None) -> Path | None:
    """Resolve original video path from a compressed file stem.

    Handles:
    - Direct match: '001_GL010683' → GL010683.mp4
    - Segment match: '001_GL010683_seg01' → strip _segXX → GL010683.mp4
    - Recursive search: scans subdirectories for all above cases.
    - No index prefix: 'GL010683' → GL010683.mp4

    stem_cache: pre-built {stem_lower: path} map for O(1) lookup.
    """
    if "_" not in compressed_stem:
        orig_stem = compressed_stem
    else:
        _, orig_stem = compressed_stem.split("_", 1)

    def _try_find(stem: str) -> Path | None:
        key = stem.lower()
        if stem_cache is not None:
            return stem_cache.get(key)
        for ext in (".mp4", ".mov", ".mkv", ".avi", ".mts", ".m2ts", ".m4v", ".webm", ".lrv"):
            candidate = input_dir / f"{stem}{ext}"
            if candidate.is_file():
                return candidate
        for ext in (".mp4", ".mov", ".mkv", ".avi", ".mts", ".m2ts", ".m4v", ".webm", ".lrv"):
            for candidate in input_dir.rglob(f"{stem}{ext}"):
                if candidate.is_file():
                    return candidate
        return None

    result = _try_find(orig_stem)
    if result is not None:
        return result

    m = re.match(r"^(.+)_seg\d+$", orig_stem)
    if m:
        return _try_find(m.group(1))
    return None


def _process_video_item(
    compressed: Path,
    original: Path,
    idx_str: str,
    config: AppConfig,
    token_store: FileTokenUsageStore,
    overwrite: bool,
    tracker: ProgressTracker | None,
    state: ProcessingState,
    error_count: list[int],
) -> ClipRecord | None:
    idx_val = int(idx_str)

    # Probe compressed file duration once (cheaper than probing original in _write_csv)
    duration_sec = 0.0
    try:
        ffprobe_bin = resolve_binary(config.paths.ffprobe, "ffprobe")
        duration_sec = get_duration_sec(compressed, ffprobe_bin)
    except Exception:
        pass

    existing = sorted(config.texts_dir.glob(f"{idx_str}_*.json"))
    json_path = None
    analysis = None
    if not overwrite and config.analyze.skip_existing and existing:
        candidate = existing[0]
        try:
            existing_data = json.loads(candidate.read_text(encoding="utf-8"))
            if existing_data.get("source_file", "") == original.name:
                json_path = candidate
                analysis = existing_data
            else:
                print(f"  [覆盖] {candidate.name} 的 source_file 不匹配，将重新分析")
                candidate.unlink()
                candidate.with_suffix(".txt").unlink(missing_ok=True)
        except (json.JSONDecodeError, OSError):
            pass
    if json_path:
        text_path = json_path.with_suffix(".txt")
        if tracker:
            tracker.next(message=f"跳过 {compressed.name}...")
            tracker.log(f"跳过 {compressed.name}（已分析）")
        state.mark(original.stem, "analyze", "skipped")
        print(f"[跳过分析] {compressed.name} (已存在: {json_path.name})")
        identity = load_identity(analysis) or resolve_identity(compressed, config.paths.input_dir, idx_str)
        return ClipRecord(
            index=idx_val,
            stem=json_path.stem,
            source_path=original,
            compressed_path=compressed,
            text_path=text_path,
            analysis=analysis,
            duration_sec=duration_sec,
            identity=identity,
        )

    max_min = config.analyze.max_analyze_duration_min
    if max_min > 0 and duration_sec > max_min * 60:
        print(f"  [跳过] {compressed.name} 时长 {format_duration(duration_sec)} 超过限制 {max_min} 分钟")
        if tracker:
            tracker.next(message=f"跳过 {compressed.name}（超长）")
            tracker.log(f"跳过 {compressed.name}（超长 {format_duration(duration_sec)}）")
        state.mark(original.stem, "analyze", "skipped")
        return None

    print(f"  [{compressed.name}] 分析中...")
    t0 = time.monotonic()
    try:
        analysis = analyze_video(str(compressed), config, progress_callback=lambda msg: None, token_store=token_store)
    except Exception as e:
        elapsed_total = time.monotonic() - t0
        print(f"  [错误] 分析 {compressed.name} 失败: {e}（耗时 {format_duration(elapsed_total)}）")
        state.mark(original.stem, "analyze", "error")
        error_count[0] += 1
        if tracker:
            tracker.next(message=f"失败 {compressed.name}")
            tracker.log(f"分析 {compressed.name} 失败: {e}")
        return None

    analysis["index"] = idx_val
    analysis["source_file"] = original.name
    identity = resolve_identity(compressed, config.paths.input_dir, idx_str)
    analysis["_schema_version"] = 2
    analysis["media_identity"] = _identity_to_dict(identity)

    stem = _build_stem(idx_val, analysis.get("title", original.stem), config)
    final_text = config.texts_dir / f"{stem}.txt"
    json_path = config.texts_dir / f"{stem}.json"
    _write_text_file(final_text, analysis, original, compressed)
    write_json_atomic(json_path, analysis)

    state.mark(original.stem, "analyze", "done")
    if tracker:
        tracker.next(message=f"完成 {compressed.name}")
        tracker.log(f"分析 {original.stem} ✓")
    print(f"  -> {final_text.name}")
    return ClipRecord(
        index=idx_val,
        stem=stem,
        source_path=original,
        compressed_path=compressed,
        text_path=final_text,
        analysis=analysis,
        duration_sec=duration_sec,
        identity=identity,
    )


def run_analyze_all(
    config: AppConfig,
    tracker: ProgressTracker | None = None,
    single_file: Path | None = None,
    cancel_event: threading.Event | None = None,
    files: list[str] | None = None,
    overwrite: bool = False,
) -> list[ClipRecord]:
    """Analyze already-compressed videos using AI (compress step must precede this).

    Scans compressed_dir for existing *.mp4 files and analyzes each.
    For single_file (an original video), finds the matching compressed file first.
    """
    config.texts_dir.mkdir(parents=True, exist_ok=True)
    token_store = FileTokenUsageStore(str(config.paths.output_dir))
    records: list[ClipRecord] = []

    # Build one-time stem→path cache to avoid per-video rglob
    stem_cache = _build_stem_to_path(config.paths.input_dir)

    def _list_compressed(d: Path) -> list[Path]:
        return sorted(p for p in d.iterdir() if p.suffix.lower() in VIDEO_EXTS and p.is_file())

    if single_file:
        items: list[tuple[Path, Path, str]] = []

        # 优先读 .vindex（O(1)，含所有分段）
        vindex = VideoIndex.read(single_file.stem, config.compressed_dir)
        if vindex is not None:
            comp_paths = vindex.compressed_paths(config.compressed_dir)
            if not comp_paths:
                print(f"[错误] .vindex 存在但压缩文件缺失: {single_file.name}，请重新压缩")
                return []
            for comp in comp_paths:
                idx_str = comp.stem.split("_", 1)[0]
                items.append((comp, single_file, idx_str))
        else:
            # 降级：原有 stem 匹配，修复只取 candidates[0] 的 bug
            candidates = [
                p for p in _list_compressed(config.compressed_dir) if single_file.stem.lower() in p.stem.lower()
            ]
            if not candidates:
                print(f"[错误] 未找到 {single_file.name} 对应的压缩文件，请先运行压缩步骤")
                return []
            for comp in candidates:
                idx_str = comp.stem.split("_", 1)[0]
                items.append((comp, single_file, idx_str))
    else:
        items = []
        for p in _list_compressed(config.compressed_dir):
            parts = p.stem.split("_", 1)
            if len(parts) != 2 or not parts[0].isdigit():
                continue
            orig_path = _resolve_original(config.paths.input_dir, p.stem, stem_cache)
            if orig_path is None:
                print(f"[警告] 找不到 {p.name} 对应的原始视频，跳过")
                continue
            idx_str = parts[0]
            items.append((p, orig_path, idx_str))

    if files is not None:
        allowed = {Path(f).stem.lower() for f in files}
        items = [it for it in items if it[0].stem.lower() in allowed]

    if not items:
        print(f"[错误] 压缩目录为空或无法匹配: {config.compressed_dir}，请先运行压缩步骤")
        return []

    total = len(items)
    print(f"待分析视频: {total} 个（压缩目录: {config.compressed_dir}）")
    state = ProcessingState(config.paths.output_dir)

    with timed(f"run_analyze_all（{total} 个）"):
        error_count: list[int] = [0]
        max_workers = config.analyze.max_workers

        if tracker:
            tracker.update(phase="analyze", total=total, current=0)

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = []
            for compressed, original, idx_str in items:
                if cancel_event and cancel_event.is_set():
                    print("[取消] analyze 步骤被用户终止")
                    break
                f = pool.submit(
                    _process_video_item,
                    compressed,
                    original,
                    idx_str,
                    config,
                    token_store,
                    overwrite,
                    tracker,
                    state,
                    error_count,
                )
                futures.append(f)
            for future in as_completed(futures):
                result = future.result()
                if result is not None:
                    records.append(result)

    records.sort(key=lambda r: r.index)

    _write_csv(config.summary_csv, records, config)
    print(f"\nCSV 已保存: {config.summary_csv}")

    completed = len(records)
    failed = error_count[0]
    if completed == 0 and failed > 0:
        raise RuntimeError(f"AI 分析全部失败（{failed} 个失败），请检查 API Key 和网络连接")
    return records
