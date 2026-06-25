"""Shared helper functions and classes for pipeline tasks."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from vlog_tool.config import AppConfig
from vlog_tool.log import format_duration
from vlog_tool.utils import format_index, probe_video_info, resolve_binary, sanitize_name, write_text_atomic
from vlog_tool.vmeta import VideoMeta


@dataclass
class ClipRecord:
    index: int
    stem: str
    source_path: Path
    compressed_path: Path | None = None
    text_path: Path | None = None
    analysis: dict | None = None
    duration_sec: float = 0.0
    meta: VideoMeta | None = None


def _build_stem(index: int, title: str, config: AppConfig) -> str:
    idx = format_index(index, config.naming.index_width)
    return f"{idx}_{sanitize_name(title)}"


def _next_index(scan_dir: Path, index_width: int = 3) -> int:
    """Scan scan_dir for {index}_* prefixed files and return next available index."""
    if not scan_dir.is_dir():
        return 1
    max_idx = 0
    for p in sorted(scan_dir.iterdir()):
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
    return f"[{label} {i}/{total}] {name}"


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

    write_text_atomic(path, "\n".join(lines))


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
    write_text_atomic(path, "\n".join(lines))


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
    write_text_atomic(path, md)


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
            if not rec.duration_sec and rec.source_path.exists():
                info = probe_video_info(rec.source_path, ffprobe)
                duration_sec = info.get("duration_sec", "")
                source_size_mb = info.get("size_mb", "")
            else:
                duration_sec = rec.duration_sec
                source_size_mb = ""
            writer.writerow(
                {
                    "index": format_index(rec.index, config.naming.index_width),
                    "stem": rec.stem,
                    "title": a.get("title", ""),
                    "summary": a.get("summary", ""),
                    "location": a.get("location", ""),
                    "mood": a.get("mood", ""),
                    "suggested_use": a.get("suggested_use", ""),
                    "source_file": str(rec.source_path),
                    "compressed_file": str(rec.compressed_path) if rec.compressed_path else "",
                    "text_file": str(rec.text_path) if rec.text_path else "",
                    "duration_sec": duration_sec,
                    "source_size_mb": source_size_mb,
                }
            )
