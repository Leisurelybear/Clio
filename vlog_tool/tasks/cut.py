"""Cut task — clip video segments based on plan."""

from __future__ import annotations

import json
import time
from pathlib import Path

from vlog_tool._constants import VIDEO_EXTS
from vlog_tool.config import AppConfig
from vlog_tool.cut import cut_one, parse_time_range
from vlog_tool.log import format_duration, timed
from vlog_tool.tasks._helpers import _eta_line
from vlog_tool.utils import resolve_binary, sanitize_name


def run_cut_all(
    config: AppConfig,
    day_label: str = "day1",
    output_dir: Path | None = None,
    reencode: bool = False,
    source: str = "compressed",
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
    comp_dir = config.compressed_dir
    input_dir = config.paths.input_dir

    print(f"[cut] 计划: {plan_path.name} ({len(seq)} 段)")
    print(f"[cut] 输出: {out_root}")
    print(f"[cut] 视频来源: {source} ({comp_dir if source == 'compressed' else input_dir})")

    def _resolve_video_path(idx: str) -> Path | None:
        if source == "compressed":
            candidates = sorted(comp_dir.glob(f"{idx}_*"))
            return candidates[0] if candidates else None
        else:
            comp_candidates = sorted(comp_dir.glob(f"{idx}_*"))
            if not comp_candidates:
                return None
            suffix = comp_candidates[0].stem.split("_", 1)[1].lower()
            for p in sorted(input_dir.iterdir()):
                if p.is_file() and p.suffix.lower() in VIDEO_EXTS and p.stem.lower() == suffix:
                    return p
            return None

    clips: list[dict] = []
    completed = 0
    elapsed_total = 0.0

    with timed(f"run_cut_all {day_label}（{len(seq)} 段）"):
        for i, seg in enumerate(seq, start=1):
            idx = seg.get("index", "")
            title = seg.get("title", "").strip()
            timeline = (seg.get("use_timeline") or "").strip()
            if not idx or not timeline:
                print(f"  [跳过] 第 {i} 段缺少 index 或 use_timeline")
                continue

            video_path = _resolve_video_path(idx)
            if video_path is None:
                print(
                    f"  [跳过] 找不到 index={idx} 的视频（{'original' if source == 'original' else 'compressed'}）: {seg.get('title', '')}"
                )
                continue

            try:
                start, end = parse_time_range(timeline)
            except ValueError as e:
                print(f"  [跳过] 时间格式错误 '{timeline}': {e}")
                continue

            clip_stem = f"{idx}_{sanitize_name(title, max_len=30)}_seg_{i:03d}"
            clip_path = out_root / f"{clip_stem}.mp4"

            print(_eta_line("裁剪", i, len(seq), clip_stem, completed, elapsed_total))
            t0 = time.monotonic()
            cut_one(video_path, clip_path, start, end, ffmpeg, reencode=reencode)
            elapsed_total += time.monotonic() - t0
            completed += 1

            # 复制对应的 texts JSON，附加 _cut_info 标明片段来源
            text_json = None
            matching_texts = sorted(config.texts_dir.glob(f"{idx}_*.json"))
            if matching_texts:
                src = matching_texts[0]
                data = json.loads(src.read_text(encoding="utf-8"))
                data["_cut_info"] = {
                    "seg_index": i,
                    "timeline": timeline,
                    "start_sec": round(start, 2),
                    "end_sec": round(end, 2),
                }
                dst = out_root / f"{clip_stem}.json"
                dst.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
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
    manifest_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"  -> manifest: {manifest_path.name}")
    print(f"完成！共裁剪 {len(clips)} 段，输出目录: {out_root}")
    return clips
