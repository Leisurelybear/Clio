from __future__ import annotations

import csv
import json
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
        lines.append(
            f"- [{item.get('start', '?')} - {item.get('end', '?')}] {item.get('description', '')}"
        )
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
        lines.append(
            f"- [{item.get('start', '?')} - {item.get('end', '?')}] {item.get('description', '')}"
        )
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
        "index", "stem", "title", "summary", "location", "mood",
        "suggested_use", "source_file", "compressed_file", "text_file",
        "duration_sec", "source_size_mb",
    ]
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for rec in records:
            a = rec.analysis or {}
            info = probe_video_info(rec.source_path, ffprobe) if rec.source_path.exists() else {}
            writer.writerow({
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
            })


def run_compress_all(config: AppConfig) -> list[ClipRecord]:
    videos = find_videos(config.paths.input_dir, recursive=config.paths.recursive)
    config.compressed_dir.mkdir(parents=True, exist_ok=True)
    records: list[ClipRecord] = []

    for i, video in enumerate(videos, start=1):
        idx = format_index(i, config.naming.index_width)
        out = config.compressed_dir / f"{idx}_{video.stem}.mp4"
        if config.analyze.skip_existing and out.exists():
            print(f"[跳过压缩] {video.name} (已存在: {out.name})")
        else:
            print(f"[压缩] {video.name} -> {out.name}")
            compress_video(video, out, config)
        records.append(ClipRecord(index=i, stem=out.stem, source_path=video, compressed_path=out))
    return records


def run_analyze_all(config: AppConfig) -> list[ClipRecord]:
    videos = find_videos(config.paths.input_dir, recursive=config.paths.recursive)
    config.compressed_dir.mkdir(parents=True, exist_ok=True)
    config.texts_dir.mkdir(parents=True, exist_ok=True)

    print(f"素材目录: {config.paths.input_dir}（{len(videos)} 个视频）")
    records: list[ClipRecord] = []

    for i, video in enumerate(videos, start=1):
        idx = format_index(i, config.naming.index_width)
        compressed = config.compressed_dir / f"{idx}_{video.stem}.mp4"

        if not compressed.exists():
            print(f"[压缩] {video.name}")
            compress_video(video, compressed, config)
        else:
            print(f"[跳过压缩] {video.name} (已存在)")

        existing = sorted(config.texts_dir.glob(f"{idx}_*.json"))
        if config.analyze.skip_existing and existing:
            json_path = existing[0]
            text_path = json_path.with_suffix(".txt")
            analysis = json.loads(json_path.read_text(encoding="utf-8"))
            print(f"[跳过分析] {video.name} (已存在: {json_path.name})")
            records.append(ClipRecord(
                index=i, stem=json_path.stem, source_path=video,
                compressed_path=compressed, text_path=text_path, analysis=analysis,
            ))
            continue

        print(f"[分析] {video.name} (使用压缩版)")
        analysis = analyze_video(str(compressed), config)
        analysis["index"] = idx
        analysis["source_file"] = video.name

        stem = _build_stem(i, analysis.get("title", video.stem), config)
        final_text = config.texts_dir / f"{stem}.txt"
        json_path = config.texts_dir / f"{stem}.json"

        _write_text_file(final_text, analysis, video, compressed)
        json_path.write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")

        records.append(ClipRecord(
            index=i, stem=stem, source_path=video,
            compressed_path=compressed, text_path=final_text, analysis=analysis,
        ))
        print(f"  -> {final_text.name}")

    _write_csv(config.summary_csv, records, config)
    print(f"\nCSV 已保存: {config.summary_csv}")
    return records


def run_label_videos(config: AppConfig) -> None:
    """用 ffmpeg 在压缩视频上烧录序号（便于剪映对照）。"""
    ffmpeg = resolve_binary(config.paths.ffmpeg, "ffmpeg")
    labeled_dir = config.paths.output_dir / "labeled"
    labeled_dir.mkdir(parents=True, exist_ok=True)

    for json_file in sorted(config.texts_dir.glob("*.json")):
        data = json.loads(json_file.read_text(encoding="utf-8"))
        idx = data.get("index", json_file.stem[:3])
        title = data.get("title", json_file.stem)
        source_name = data.get("source_file", "")
        compressed = None
        for f in config.compressed_dir.glob(f"{idx}_*"):
            compressed = f
            break
        if not compressed or not compressed.exists():
            print(f"[跳过] 找不到压缩文件: {idx}")
            continue

        out = labeled_dir / f"{json_file.stem}_labeled.mp4"
        if config.analyze.skip_existing and out.exists():
            print(f"[跳过标注] {out.name} (已存在)")
            continue

        label = idx.replace("'", "")
        vf = (
            f"drawtext=text='{label}':fontsize=36:fontcolor=white:"
            f"box=1:boxcolor=black@0.5:boxborderw=8:x=20:y=20"
        )
        run_ffmpeg(["-i", str(compressed), "-vf", vf, "-an", "-y", str(out)], ffmpeg)
        print(f"[标注] {out.name}")


def run_generate_scripts(config: AppConfig) -> None:
    config.scripts_dir.mkdir(parents=True, exist_ok=True)
    template = config.script.template_file.read_text(encoding="utf-8") if config.script.template_file.exists() else ""

    for json_file in sorted(config.texts_dir.glob("*.json")):
        data = json.loads(json_file.read_text(encoding="utf-8"))
        data["index"] = data.get("index", json_file.stem[:3])
        out = config.scripts_dir / f"{json_file.stem}_voiceover.json"
        if config.analyze.skip_existing and out.exists():
            print(f"[跳过] {out.name}")
            continue

        print(f"[口播] {json_file.stem}")
        script = generate_voiceover(data, template, config)
        out.write_text(json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")

        md_out = config.scripts_dir / f"{json_file.stem}_voiceover.md"
        md_out.write_text(
            f"# {script.get('title', json_file.stem)} 口播\n\n"
            f"{script.get('voiceover', '')}\n\n"
            f"**剪辑建议**: {script.get('edit_tip', '')}\n",
            encoding="utf-8",
        )
        print(f"  -> {md_out.name}")


def run_plan_vlog(config: AppConfig, day_label: str = "day1") -> None:
    config.plans_dir.mkdir(parents=True, exist_ok=True)

    out_json = config.plans_dir / f"{day_label}_plan.json"
    out_md = config.plans_dir / f"{day_label}_plan.md"
    if config.analyze.skip_existing and out_json.exists() and out_md.exists():
        print(f"[跳过] {day_label} 计划 (已存在)")
        return

    clips = []
    for json_file in sorted(config.texts_dir.glob("*.json")):
        data = json.loads(json_file.read_text(encoding="utf-8"))
        clips.append({
            "index": data.get("index", json_file.stem[:3]),
            "title": data.get("title", ""),
            "summary": data.get("summary", ""),
            "location": data.get("location", ""),
            "timeline": data.get("timeline", []),
            "highlights": data.get("highlights", []),
            "suggested_use": data.get("suggested_use", ""),
        })

    if not clips:
        print("没有可用的分析结果，请先运行 analyze")
        return

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
        lines.extend([
            f"### {item.get('index', '?')} {item.get('title', '')}",
            f"- **理由**: {item.get('reason', '')}",
            f"- **使用片段**: {item.get('use_timeline', '')}",
            f"- **口播方向**: {item.get('voiceover_hint', '')}",
            "",
        ])
    lines.extend([
        "## 开场建议", plan.get("opening_tip", ""),
        "", "## 结尾建议", plan.get("ending_tip", ""),
    ])
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


def run_refine_texts(config: AppConfig, path: Path | None = None) -> int:
    """审阅并修正 texts/*.json；同步重写同名 .txt。返回处理条数。"""
    files = _collect_target_files(path, config.texts_dir)
    if not files:
        print(f"未找到 json 文件: {path or config.texts_dir}")
        return 0
    print(f"[refine:texts] 目标 {len(files)} 个文件")
    for json_file in files:
        print(f"[refine] {json_file.name}")
        analysis = json.loads(json_file.read_text(encoding="utf-8"))
        try:
            refined = refine_text(analysis, config)
        except Exception as e:
            print(f"  失败: {e}")
            continue
        json_file.write_text(json.dumps(refined, ensure_ascii=False, indent=2), encoding="utf-8")
        txt_path = json_file.with_suffix(".txt")
        _rewrite_text_file(txt_path, refined)
        changelog = refined.get("_changelog") or []
        if changelog:
            print(f"  改动 ({len(changelog)}): {'; '.join(changelog)[:120]}")
        else:
            print("  无改动")
    return len(files)


def run_refine_scripts(config: AppConfig, path: Path | None = None) -> int:
    """审阅并修正 scripts/*_voiceover.json；同步重写同名 .md。"""
    files = _collect_target_files(path, config.scripts_dir, pattern="*_voiceover.json")
    if not files:
        print(f"未找到 voiceover json 文件: {path or config.scripts_dir}")
        return 0
    print(f"[refine:scripts] 目标 {len(files)} 个文件")
    for json_file in files:
        print(f"[refine] {json_file.name}")
        script = json.loads(json_file.read_text(encoding="utf-8"))
        analysis = _load_analysis_for_script(json_file, config.texts_dir)
        try:
            refined = refine_script(script, analysis, config)
        except Exception as e:
            print(f"  失败: {e}")
            continue
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
    print("=== 1/4 分析素材（含压缩） ===")
    run_analyze_all(config)
    print("\n=== 2/4 生成口播文案 ===")
    run_generate_scripts(config)
    print("\n=== 3/4 日 vlog 剪辑规划 ===")
    run_plan_vlog(config, day_label)
    print("\n=== 4/4 烧录序号标注 ===")
    run_label_videos(config)
    print("\n完成！输出目录:", config.paths.output_dir)
