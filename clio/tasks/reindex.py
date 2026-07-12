"""Reindex task — rebuild .vindex and .vmeta sidecar files from existing compressed videos."""

from __future__ import annotations

import time as _time
from collections import defaultdict
from pathlib import Path

from clio._constants import VIDEO_EXTS
from clio.config import AppConfig
from clio.utils import get_duration_sec, resolve_binary
from clio.vmeta import SegmentEntry, VideoIndex, VideoMeta


def _find_original_for_stem(stem: str, input_dir: Path, project_dir: Path | None = None) -> Path | None:
    """Try to find original video by stem (without index prefix)."""
    if project_dir:
        from clio.tasks._video_loader import load_selected_videos

        for p in load_selected_videos(project_dir):
            if p.stem.lower() == stem.lower() and p.suffix.lower() in VIDEO_EXTS:
                return p
        return None
    for ext in VIDEO_EXTS:
        candidate = input_dir / f"{stem}{ext}"
        if candidate.is_file():
            return candidate
    for p in input_dir.rglob("*"):
        if p.is_file() and p.suffix.lower() in VIDEO_EXTS and p.stem.lower() == stem.lower():
            return p
    return None


def auto_reindex_if_needed(config: AppConfig, ffprobe: str | None = None) -> bool:
    """检测 compressed_dir 是否有压缩视频缺少 .vindex，自动补全。

    返回 True 表示执行了 reindex，False 表示不需要或无法补全。
    """
    compressed_dir = config.compressed_dir
    if not compressed_dir.is_dir():
        return False

    import re as _re

    # 找所有带数字前缀的压缩视频
    groups: dict[str, list[Path]] = {}
    for p in sorted(compressed_dir.iterdir()):
        if not p.is_file() or p.suffix.lower() not in VIDEO_EXTS:
            continue
        if "_" not in p.stem:
            continue
        prefix, stem_part = p.stem.split("_", 1)
        if not prefix.isdigit():
            continue
        m = _re.match(r"^(.+)_seg\d+$", stem_part)
        orig_stem = m.group(1) if m else stem_part
        groups.setdefault(orig_stem, []).append(p)

    # 检查哪些没有 .vindex
    missing = [s for s in groups if not VideoIndex.read(s, compressed_dir)]
    if not missing:
        return False

    # 显示重建提示（不清屏，避免在服务/CI 场景丢失日志）
    _W = 60
    print()
    print("=" * _W)
    print("  视频索引重建中...".center(_W))
    print(f"  检测到 {len(missing)}/{len(groups)} 个原视频缺少索引文件".center(_W))
    print("  请勿中断操作".center(_W))
    print("=" * _W)
    print()
    run_reindex(config, ffprobe)
    print()
    print("=" * _W)
    print("  ✅ 索引重建完成，继续执行...".center(_W))
    print("=" * _W)
    _time.sleep(1.5)
    return True


def run_reindex(config: AppConfig, ffprobe: str | None = None) -> int:
    """Scan compressed_dir and rebuild .vindex files.

    Also writes .vmeta for any compressed file missing it.
    Returns count of .vindex files written.
    """
    if ffprobe is None:
        ffprobe = resolve_binary(config.paths.ffprobe, "ffprobe")

    compressed_dir = config.compressed_dir
    if not compressed_dir.is_dir():
        print(f"[reindex] compressed_dir 不存在: {compressed_dir}")
        return 0

    # Group compressed files by original stem (strip _segNN suffix)
    groups: dict[str, list[Path]] = defaultdict(list)

    for p in sorted(compressed_dir.iterdir()):
        if not p.is_file() or p.suffix.lower() not in VIDEO_EXTS:
            continue
        if "_" not in p.stem:
            continue
        prefix, stem_part = p.stem.split("_", 1)
        if not prefix.isdigit():
            continue
        import re

        m = re.match(r"^(.+)_seg\d+$", stem_part)
        orig_stem = m.group(1) if m else stem_part
        groups[orig_stem].append(p)

    written_index = 0

    for orig_stem, comp_files in groups.items():
        # Try to find original source path
        source_path = None
        for p in comp_files:
            meta = VideoMeta.read(p)
            if meta is not None:
                src = meta.source_path_obj()
                if src.is_file():
                    source_path = src
                    break

        if source_path is None:
            source_path = _find_original_for_stem(orig_stem, config.paths.input_dir, config.project_dir)

        if source_path is None:
            print(f"  [跳过] {orig_stem}: 找不到原始视频")
            continue

        # Sort compressed files by prefix index
        comp_files.sort(key=lambda p: int(p.stem.split("_", 1)[0]))

        seg_entries: list[SegmentEntry] = []
        source_dur = 0.0
        try:
            source_dur = get_duration_sec(source_path, ffprobe)
        except Exception:
            pass

        for i, cp in enumerate(comp_files):
            idx_str = cp.stem.split("_", 1)[0]
            si = None
            tgt_dur = 0.0
            meta = VideoMeta.read(cp)
            if meta is not None:
                tgt_dur = meta.target_duration_sec
                if meta.split_info:
                    si = meta.split_info
            else:
                try:
                    tgt_dur = get_duration_sec(cp, ffprobe)
                except Exception:
                    pass
                # Write missing .vmeta
                meta = VideoMeta.build(
                    source=source_path,
                    target=cp,
                    source_duration=source_dur,
                    target_duration=tgt_dur,
                )
                meta.write(cp)

            seg_entries.append(
                SegmentEntry(
                    index=idx_str,
                    filename=cp.name,
                    offset_sec=si.offset_sec
                    if si
                    else round(i * (source_dur / len(comp_files)), 3)
                    if source_dur > 0 and len(comp_files) > 1
                    else 0.0,
                    duration_sec=tgt_dur,
                    segment_number=si.segment_index if si else i + 1,
                    total_segments=si.total_segments if si else len(comp_files),
                )
            )

        vindex = VideoIndex.build(
            source=source_path,
            source_duration=source_dur,
            segments=seg_entries,
        )
        vindex.write(compressed_dir)
        written_index += 1
        print(f"  [OK] {orig_stem}: {len(comp_files)} 个分段 → .vindex")

    print(f"\n[reindex] 完成: 写入 {written_index} 个 .vindex 文件")
    return written_index
