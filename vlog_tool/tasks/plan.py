"""Planning task — generate daily vlog editing plan."""

from __future__ import annotations

import json
import threading
from pathlib import Path

from vlog_tool.ai.token_usage import FileTokenUsageStore
from vlog_tool.analyze import plan_daily_vlog
from vlog_tool.config import AppConfig
from vlog_tool.log import timed
from vlog_tool.processing_state import ProcessingState
from vlog_tool.progress import ProgressTracker
from vlog_tool.utils import format_index, write_json_atomic, write_text_atomic


def run_plan_vlog(
    config: AppConfig,
    day_label: str = "day1",
    tracker: ProgressTracker | None = None,
    cancel_event: threading.Event | None = None,
    files: list[str] | None = None,
    overwrite: bool = False,
) -> None:
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
            return

    clips = []
    for json_file in sorted(config.texts_dir.glob("*.json")):
        if cancel_event and cancel_event.is_set():
            print("[取消] plan 步骤被用户终止")
            return
        data = json.loads(json_file.read_text(encoding="utf-8"))
        raw_idx = data.get("index")
        if raw_idx is None:
            raw_idx = json_file.stem[:3]  # fallback: 从文件名取前缀 "001"
        try:
            idx = int(raw_idx)
        except (ValueError, TypeError):
            print(f"  [跳过] 无效 index '{raw_idx}' 在 {json_file.name}")
            continue
        source_stem = Path(data.get("source_file", "")).stem
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
        return

    # 加载 transcript 数据
    transcripts_map: dict[str, dict] = {}
    trans_dir = config.paths.output_dir / config.whisper.transcripts_subdir
    if trans_dir.is_dir() and config.whisper.enabled and config.plan.use_transcripts:
        for tf in sorted(trans_dir.glob("*_transcript.json")):
            try:
                data = json.loads(tf.read_text(encoding="utf-8"))
                stem = data.get("source_stem", "")
                if stem:
                    transcripts_map[stem] = data
            except (json.JSONDecodeError, KeyError):
                continue

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
        )
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
