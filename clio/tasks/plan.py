"""Planning task - generate daily vlog editing plan."""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import Any

from clio.ai.token_usage import FileTokenUsageStore
from clio.analyze import plan_daily_vlog
from clio.config import AppConfig
from clio.identity import load_identity
from clio.log import timed
from clio.processing_state import ProcessingState
from clio.progress import ProgressTracker
from clio.schema import add_schema_version
from clio.utils import format_index, write_json_atomic, write_text_atomic


def _analysis_day_label(data: dict) -> str:
    raw = data.get("day_label") or data.get("day") or data.get("dayLabel") or "day1"
    label = str(raw).strip()
    return label or "day1"


def _discover_day_labels(config: AppConfig) -> list[str]:
    labels: set[str] = set()
    for json_file in sorted(config.texts_dir.glob("*.json")):
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        labels.add(_analysis_day_label(data))
    return sorted(labels)


def run_plan_vlog(
    config: AppConfig,
    day_label: str = "day1",
    tracker: ProgressTracker | None = None,
    cancel_event: threading.Event | None = None,
    files: list[str] | None = None,
    overwrite: bool = False,
    context_override: str | None = None,
    filter_by_day: bool = False,
    task_prompts: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    config.plans_dir.mkdir(parents=True, exist_ok=True)
    token_store = FileTokenUsageStore(str(config.paths.output_dir))

    if files is not None:
        print("[规划] 使用所有素材生成全局规划（视频筛选仅影响前序步骤）")

    out_json = config.plans_dir / f"{day_label}_plan.json"
    out_md = config.plans_dir / f"{day_label}_plan.md"
    if not overwrite and config.analyze.skip_existing and out_json.exists() and out_md.exists():
        try:
            json.loads(out_json.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            print(f"  [重新规划] {day_label} (已有规划文件损坏)")
        else:
            print(f"[跳过] {day_label} 计划 (已存在)")
            return json.loads(out_json.read_text(encoding="utf-8"))

    clips = []
    for json_file in sorted(config.texts_dir.glob("*.json")):
        if cancel_event and cancel_event.is_set():
            print("[取消] plan 步骤被用户终止")
            return
        data = json.loads(json_file.read_text(encoding="utf-8"))
        if filter_by_day and _analysis_day_label(data) != day_label:
            continue
        raw_idx = data.get("index")
        if raw_idx is None:
            raw_idx = json_file.stem[:3]
        try:
            idx = int(raw_idx)
        except (ValueError, TypeError):
            print(f"  [跳过] 无效 index '{raw_idx}' 在 {json_file.name}")
            continue
        identity = load_identity(data)
        if identity is not None:
            source_stem = identity.original_stem
        else:
            source_stem = Path(data.get("source_file", "")).stem or json_file.stem
        clips.append(
            {
                "index": format_index(idx, config.naming.index_width),
                "title": data.get("title", ""),
                "summary": data.get("summary", ""),
                "location": data.get("location", ""),
                "timeline": data.get("timeline", []),
                "highlights": data.get("highlights", []),
                "suggested_use": data.get("suggested_use", ""),
                "source_stem": source_stem,
            }
        )

    if not clips:
        print("没有可用的分析结果，请先运行 analyze")
        return None

    transcripts_map: dict[str, dict] = {}
    trans_dir = config.transcripts_dir
    if trans_dir.is_dir() and config.whisper.enabled and config.plan.use_transcripts:
        for tf in sorted(trans_dir.glob("*_transcript.json")):
            try:
                data = json.loads(tf.read_text(encoding="utf-8"))
                identity = load_identity(data)
                if identity is not None:
                    stem = identity.original_stem
                else:
                    stem = data.get("source_stem", "")
                    if "_" in stem:
                        stem = stem.split("_", 1)[1]
                    stem = re.sub(r"_seg\d+$", "", stem)
                if stem:
                    transcripts_map[stem.lower()] = data
            except (json.JSONDecodeError, KeyError):
                continue
    if config.plan.use_transcripts and not transcripts_map:
        print("[警告] use_transcripts=true 但未找到任何 transcript 数据，规划将不使用语音信息")
        print("       请先运行 transcript 步骤，或设置 use_transcripts: false 消除此警告")

    if tracker:
        tracker.update(phase="plan", total=1, current=0, message=f"生成 {day_label} 规划...")
    with timed(f"run_plan_vlog {day_label}（{len(clips)} 条）"):
        print(f"[规划] {day_label}，共 {len(clips)} 条素材")
        plan = plan_daily_vlog(
            clips,
            config,
            day_label,
            transcripts_map=transcripts_map,
            use_transcripts=config.plan.use_transcripts,
            token_store=token_store,
            context_override=context_override,
            task_prompts=task_prompts,
        )
        if config.plan.use_transcripts:
            plan["_transcripts_missing"] = not transcripts_map
    add_schema_version(plan)
    write_json_atomic(out_json, plan)
    if tracker:
        tracker.log(f"规划 {day_label} ✓")

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
    write_text_atomic(out_md, "\n".join(lines))
    print(f"  -> {out_md.name}")

    state = ProcessingState(config.paths.output_dir)
    for clip in clips:
        source_stem = clip.get("source_stem", "")
        if source_stem:
            state.mark(source_stem, "plan", "done")
    return plan


def run_plan_all_days(
    config: AppConfig,
    tracker: ProgressTracker | None = None,
    cancel_event: threading.Event | None = None,
    overwrite: bool = False,
    context_override: str | None = None,
    task_prompts: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    labels = _discover_day_labels(config)
    if not labels:
        print("没有可用的分析结果，请先运行 analyze")
        return None

    summary: dict[str, Any] = {"days": []}
    for day_label in labels:
        if cancel_event and cancel_event.is_set():
            print("[取消] all-days plan 被用户终止")
            break
        plan = run_plan_vlog(
            config,
            day_label=day_label,
            tracker=tracker,
            cancel_event=cancel_event,
            overwrite=overwrite,
            context_override=context_override,
            filter_by_day=True,
            task_prompts=task_prompts,
        )
        if plan is None:
            continue
        sequence = plan.get("sequence", [])
        summary["days"].append(
            {
                "day_label": day_label,
                "day_title": plan.get("day_title", day_label),
                "theme": plan.get("theme", ""),
                "clip_count": len(sequence) if isinstance(sequence, list) else 0,
                "total_estimated_sec": plan.get("total_estimated_sec", 0),
                "plan_file": f"{day_label}_plan.json",
            }
        )

    if not summary["days"]:
        return None
    add_schema_version(summary)
    config.plans_dir.mkdir(parents=True, exist_ok=True)
    out_json = config.plans_dir / "trip_plan.json"
    write_json_atomic(out_json, summary)
    print(f"  -> {out_json.name}")
    return summary
