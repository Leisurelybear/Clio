from __future__ import annotations

import csv
import json
import time
from dataclasses import dataclass
from pathlib import Path

from vlog_tool.analyze import (
    analyze_video,
    generate_voiceover,
    plan_daily_vlog,
    refine_script,
    refine_text,
)
from vlog_tool.compress import compress_video
from vlog_tool.config import AppConfig
from vlog_tool.cut import cut_one, parse_time_range
from vlog_tool.log import format_duration, timed
from vlog_tool.progress import ProgressTracker
from vlog_tool.utils import (
    find_videos,
    format_index,
    probe_video_info,
    resolve_binary,
    run_ffmpeg,
    sanitize_name,
)


@dataclass
class ClipRecord:
    index: int
    stem: str
    source_path: Path
    compressed_path: Path | None = None
    text_path: Path | None = None
    analysis: dict | None = None


def _build_stem(index: int, title: str, config: AppConfig) -> str:
    idx = format_index(index, config.naming.index_width)
    return f"{idx}_{sanitize_name(title)}"


def _next_index(scan_dir: Path, index_width: int = 3) -> int:
    """Scan scan_dir for {index}_* prefixed files and return next available index."""
    if not scan_dir.is_dir():
        return 1
    max_idx = 0
    for p in scan_dir.iterdir():
        stem = p.stem
        if "_" in stem:
            prefix = stem.split("_", 1)[0]
            if prefix.isdigit():
                idx = int(prefix)
                if idx > max_idx:
                    max_idx = idx
    return max_idx + 1


def _eta_line(label: str, i: int, total: int, name: str, completed: int, elapsed_total: float) -> str:
    """生成 `[label i/total] name（平均 X，剩余 ~Y）` 形式的进度行。"""
    if completed > 0:
        avg = elapsed_total / completed
        remaining = avg * (total - i)
        return f"[{label} {i}/{total}] {name}（平均 {format_duration(avg)}，剩余 ~{format_duration(remaining)}）"
    return f"[{label} 1/{total}] {name}"


def _write_text_file(path: Path, analysis: dict, source: Path, compressed: Path) -> None:
    lines = [
        f"# {analysis.get('title', '未命名')}",
        "",
        f"**源文件**: {source.name}",
        f"**压缩文件**: {compressed.name}",
        "",
        "## 简介",
        analysis.get("summary", ""),
        "",
        f"**地点**: {analysis.get('location', '未知')}",
        f"**氛围**: {analysis.get('mood', '')}",
        f"**建议使用**: {analysis.get('suggested_use', '')}",
        "",
        "## 时间轴",
    ]
    for item in analysis.get("timeline", []):
        lines.append(f"- [{item.get('start', '?')} - {item.get('end', '?')}] {item.get('description', '')}")
    lines.extend(["", "## 亮点"])
    for h in analysis.get("highlights", []):
        lines.append(f"- {h}")

    path.write_text("\n".join(lines), encoding="utf-8")


def _rewrite_text_file(path: Path, analysis: dict) -> None:
    """根据已存在的 analysis 重写 .txt（不需要源文件/压缩文件路径）。"""
    source_name = analysis.get("source_file", "?")
    lines = [
        f"# {analysis.get('title', '未命名')}",
        "",
        f"**源文件**: {source_name}",
        "",
        "## 简介",
        analysis.get("summary", ""),
        "",
        f"**地点**: {analysis.get('location', '未知')}",
        f"**氛围**: {analysis.get('mood', '')}",
        f"**建议使用**: {analysis.get('suggested_use', '')}",
        "",
        "## 时间轴",
    ]
    for item in analysis.get("timeline", []):
        lines.append(f"- [{item.get('start', '?')} - {item.get('end', '?')}] {item.get('description', '')}")
    lines.extend(["", "## 亮点"])
    for h in analysis.get("highlights", []):
        lines.append(f"- {h}")
    if analysis.get("_changelog"):
        lines.extend(["", "## 本次 refine 改动"])
        for item in analysis["_changelog"]:
            lines.append(f"- {item}")
    path.write_text("\n".join(lines), encoding="utf-8")


def _rewrite_script_md(path: Path, script: dict) -> None:
    md = (
        f"# {script.get('title', path.stem)} 口播\n\n"
        f"{script.get('voiceover', '')}\n\n"
        f"**剪辑建议**: {script.get('edit_tip', '')}\n"
    )
    if script.get("_changelog"):
        md += "\n## 本次 refine 改动\n"
        for item in script["_changelog"]:
            md += f"- {item}\n"
    path.write_text(md, encoding="utf-8")


def _write_csv(path: Path, records: list[ClipRecord], config: AppConfig) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ffprobe = resolve_binary(config.paths.ffprobe, "ffprobe")
    fieldnames = [
        "index",
        "stem",
        "title",
        "summary",
        "location",
        "mood",
        "suggested_use",
        "source_file",
        "compressed_file",
        "text_file",
        "duration_sec",
        "source_size_mb",
    ]
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for rec in records:
            a = rec.analysis or {}
            info = probe_video_info(rec.source_path, ffprobe) if rec.source_path.exists() else {}
            writer.writerow(
                {
                    "index": format_index(rec.index, 3),
                    "stem": rec.stem,
                    "title": a.get("title", ""),
                    "summary": a.get("summary", ""),
                    "location": a.get("location", ""),
                    "mood": a.get("mood", ""),
                    "suggested_use": a.get("suggested_use", ""),
                    "source_file": str(rec.source_path),
                    "compressed_file": str(rec.compressed_path) if rec.compressed_path else "",
                    "text_file": str(rec.text_path) if rec.text_path else "",
                    "duration_sec": info.get("duration_sec", ""),
                    "source_size_mb": info.get("size_mb", ""),
                }
            )


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
            analysis = analyze_video(str(compressed), config)
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
            idx = data.get("index", json_file.stem[:3])
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
            print(f"  -> {out.name}")


def run_generate_scripts(
    config: AppConfig, tracker: ProgressTracker | None = None, single_file: Path | None = None
) -> None:
    config.scripts_dir.mkdir(parents=True, exist_ok=True)
    template = config.script.template_file.read_text(encoding="utf-8") if config.script.template_file.exists() else ""

    if single_file:
        files = [single_file]
    else:
        files = sorted(config.texts_dir.glob("*.json"))
    if tracker:
        tracker.update(phase="voiceover", total=len(files), message=f"生成口播文案（{len(files)} 条）...")
    with timed(f"run_generate_scripts（{len(files)} 个）"):
        completed = 0
        elapsed_total = 0.0
        for i, json_file in enumerate(files, start=1):
            data = json.loads(json_file.read_text(encoding="utf-8"))
            data["index"] = data.get("index", json_file.stem[:3])
            out = config.scripts_dir / f"{json_file.stem}_voiceover.json"
            if config.analyze.skip_existing and out.exists():
                print(f"[跳过] {out.name}")
                if tracker:
                    tracker.next(message=f"跳过 {json_file.stem}")
                continue

            print(_eta_line("口播", i, len(files), json_file.stem, completed, elapsed_total))
            if tracker:
                tracker.next(message=f"生成口播 {json_file.stem}")
            t0 = time.monotonic()
            script = generate_voiceover(data, template, config)
            elapsed_total += time.monotonic() - t0
            completed += 1
            out.write_text(json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")

            md_out = config.scripts_dir / f"{json_file.stem}_voiceover.md"
            md_out.write_text(
                f"# {script.get('title', json_file.stem)} 口播\n\n"
                f"{script.get('voiceover', '')}\n\n"
                f"**剪辑建议**: {script.get('edit_tip', '')}\n",
                encoding="utf-8",
            )
            print(f"  -> {md_out.name}")


def run_plan_vlog(config: AppConfig, day_label: str = "day1", tracker: ProgressTracker | None = None) -> None:
    config.plans_dir.mkdir(parents=True, exist_ok=True)

    out_json = config.plans_dir / f"{day_label}_plan.json"
    out_md = config.plans_dir / f"{day_label}_plan.md"
    if config.analyze.skip_existing and out_json.exists() and out_md.exists():
        print(f"[跳过] {day_label} 计划 (已存在)")
        return

    clips = []
    for json_file in sorted(config.texts_dir.glob("*.json")):
        data = json.loads(json_file.read_text(encoding="utf-8"))
        raw_idx = data.get("index")
        if raw_idx is None:
            raw_idx = json_file.stem[:3]  # fallback: 从文件名取前缀 "001"
        clips.append(
            {
                "index": format_index(int(raw_idx), config.naming.index_width),
                "title": data.get("title", ""),
                "summary": data.get("summary", ""),
                "location": data.get("location", ""),
                "timeline": data.get("timeline", []),
                "highlights": data.get("highlights", []),
                "suggested_use": data.get("suggested_use", ""),
            }
        )

    if not clips:
        print("没有可用的分析结果，请先运行 analyze")
        return

    if tracker:
        tracker.update(phase="plan", total=1, current=0, message=f"生成 {day_label} 规划...")
    with timed(f"run_plan_vlog {day_label}（{len(clips)} 条）"):
        print(f"[规划] {day_label}，共 {len(clips)} 条素材")
        plan = plan_daily_vlog(clips, config, day_label)
    out_json.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        f"# {plan.get('day_title', day_label)}",
        "",
        f"**主题**: {plan.get('theme', '')}",
        f"**预估总时长**: {plan.get('total_estimated_sec', '')} 秒",
        "",
        "## 推荐剪辑顺序",
    ]
    for item in plan.get("sequence", []):
        lines.extend(
            [
                f"### {item.get('index', '?')} {item.get('title', '')}",
                f"- **理由**: {item.get('reason', '')}",
                f"- **使用片段**: {item.get('use_timeline', '')}",
                f"- **口播方向**: {item.get('voiceover_hint', '')}",
                "",
            ]
        )
    lines.extend(
        [
            "## 开场建议",
            plan.get("opening_tip", ""),
            "",
            "## 结尾建议",
            plan.get("ending_tip", ""),
        ]
    )
    out_md.write_text("\n".join(lines), encoding="utf-8")
    print(f"  -> {out_md.name}")


def _collect_target_files(path: Path | None, default_dir: Path, pattern: str = "*.json") -> list[Path]:
    """把 -i 参数或默认目录解析为要处理的文件列表。"""
    target = path or default_dir
    if not target.exists():
        raise FileNotFoundError(f"路径不存在: {target}")
    if target.is_file():
        if target.suffix.lower() != ".json":
            raise ValueError(f"仅支持 .json 文件: {target}")
        return [target]
    return sorted(target.glob(pattern))


def _load_analysis_for_script(script_path: Path, texts_dir: Path) -> dict | None:
    """根据口播文件名反查对应的素材分析（001_xxx_voiceover.json → 001_xxx.json）。"""
    stem = script_path.stem
    if stem.endswith("_voiceover"):
        analysis_stem = stem[: -len("_voiceover")]
    else:
        analysis_stem = stem
    candidate = texts_dir / f"{analysis_stem}.json"
    if candidate.is_file():
        return json.loads(candidate.read_text(encoding="utf-8"))
    return None


def run_refine_texts(
    config: AppConfig, path: Path | None = None, fix: str | None = None, context_override: str | None = None
) -> int:
    """审阅并修正 texts/*.json；同步重写同名 .txt。返回处理条数。

    fix 非空时：仅处理 -i 指定的单文件，prompt 切换为「按用户意见定向修正」。
    """
    if fix and (path is None or path.is_dir()):
        raise ValueError("--fix 必须配合 -i 指定单个 json 文件，不能用于目录")
    files = _collect_target_files(path, config.texts_dir)
    if not files:
        print(f"未找到 json 文件: {path or config.texts_dir}")
        return 0
    label = "refine:fix:texts" if fix else "refine:texts"
    print(f"[{label}] 目标 {len(files)} 个文件")
    if fix:
        print(f"  修改意见: {fix}")
    completed = 0
    elapsed_total = 0.0
    with timed(f"{label}（{len(files)} 个）"):
        for i, json_file in enumerate(files, start=1):
            print(_eta_line("refine", i, len(files), json_file.name, completed, elapsed_total))
            t0 = time.monotonic()
            analysis = json.loads(json_file.read_text(encoding="utf-8"))
            try:
                refined = refine_text(analysis, config, fix=fix, context_override=context_override)
            except Exception as e:
                print(f"  失败: {e}")
                continue
            elapsed_total += time.monotonic() - t0
            completed += 1
            json_file.write_text(json.dumps(refined, ensure_ascii=False, indent=2), encoding="utf-8")
            txt_path = json_file.with_suffix(".txt")
            _rewrite_text_file(txt_path, refined)
            changelog = refined.get("_changelog") or []
            if changelog:
                print(f"  改动 ({len(changelog)}): {'; '.join(changelog)[:120]}")
            else:
                print("  无改动")
    return len(files)


def run_refine_scripts(
    config: AppConfig, path: Path | None = None, fix: str | None = None, context_override: str | None = None
) -> int:
    """审阅并修正 scripts/*_voiceover.json；同步重写同名 .md。

    fix 非空时：仅处理 -i 指定的单文件。
    """
    if fix and (path is None or path.is_dir()):
        raise ValueError("--fix 必须配合 -i 指定单个 json 文件，不能用于目录")
    files = _collect_target_files(path, config.scripts_dir, pattern="*_voiceover.json")
    if not files:
        print(f"未找到 voiceover json 文件: {path or config.scripts_dir}")
        return 0
    label = "refine:fix:scripts" if fix else "refine:scripts"
    print(f"[{label}] 目标 {len(files)} 个文件")
    if fix:
        print(f"  修改意见: {fix}")
    completed = 0
    elapsed_total = 0.0
    with timed(f"{label}（{len(files)} 个）"):
        for i, json_file in enumerate(files, start=1):
            print(_eta_line("refine", i, len(files), json_file.name, completed, elapsed_total))
            t0 = time.monotonic()
            script = json.loads(json_file.read_text(encoding="utf-8"))
            analysis = _load_analysis_for_script(json_file, config.texts_dir)
            try:
                refined = refine_script(script, analysis, config, fix=fix, context_override=context_override)
            except Exception as e:
                print(f"  失败: {e}")
                continue
            elapsed_total += time.monotonic() - t0
            completed += 1
            json_file.write_text(json.dumps(refined, ensure_ascii=False, indent=2), encoding="utf-8")
            md_path = json_file.with_name(json_file.stem + ".md")
            _rewrite_script_md(md_path, refined)
            changelog = refined.get("_changelog") or []
            if changelog:
                print(f"  改动 ({len(changelog)}): {'; '.join(changelog)[:120]}")
            else:
                print("  无改动")
    return len(files)


def run_full_pipeline(config: AppConfig, day_label: str = "day1") -> None:
    config.paths.output_dir.mkdir(parents=True, exist_ok=True)
    with timed("=== 1/5 压缩原视频 ==="):
        run_compress_all(config)
    with timed("=== 2/5 AI 分析素材 ==="):
        run_analyze_all(config)
    with timed("=== 3/5 生成口播文案 ==="):
        run_generate_scripts(config)
    with timed("=== 4/5 日 vlog 剪辑规划 ==="):
        run_plan_vlog(config, day_label)
    with timed("=== 5/5 烧录序号标注 ==="):
        run_label_videos(config)
    print("\n完成！输出目录:", config.paths.output_dir)


_STEP_LABELS = {
    "compress": "压缩原视频",
    "analyze": "AI 分析素材",
    "voiceover": "生成口播文案",
    "plan": "日 vlog 剪辑规划",
    "label": "烧录序号标注",
}

_STEP_FUNCS = {
    "compress": run_compress_all,
    "analyze": run_analyze_all,
    "voiceover": run_generate_scripts,
    "plan": run_plan_vlog,
    "label": run_label_videos,
}

_STEP_DAY_ARG = {"plan"}


def run_pipeline_steps(
    config: AppConfig,
    day_label: str = "day1",
    steps: list[str] | None = None,
    tracker: ProgressTracker | None = None,
) -> None:
    """运行指定步骤列表（可选的进度跟踪）。

    steps 取值: analyze, voiceover, plan, label（默认全部）。
    """
    config.paths.output_dir.mkdir(parents=True, exist_ok=True)
    if not steps:
        steps = list(_STEP_FUNCS.keys())

    if tracker is None:
        tracker = ProgressTracker(config.paths.output_dir)

    try:
        for step in steps:
            label = _STEP_LABELS.get(step, step)
            if tracker:
                tracker.update(phase=step, current=0, total=1, message=f"{label}...")
            with timed(f"=== {label} ==="):
                fn = _STEP_FUNCS[step]
                if step in _STEP_DAY_ARG:
                    fn(config, day_label, tracker)
                else:
                    fn(config, tracker)
        tracker.done(f"完成！输出目录: {config.paths.output_dir}")
    except Exception as e:
        tracker.error(str(e))
        raise


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
    VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".webm"}

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
            for p in input_dir.iterdir():
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
                    f"  [跳过] 找不到 index={idx} 的视频（{'compressed' if source == 'original' else 'video_dir'}）: {seg.get('title', '')}"
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
