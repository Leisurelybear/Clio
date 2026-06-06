from __future__ import annotations

import json

from vlog_tool.ai.base import TaskName
from vlog_tool.ai.factory import get_task_provider, get_video_provider
from vlog_tool.ai.gemini import extract_json
from vlog_tool.config import AppConfig
from vlog_tool.prompts import ANALYZE_PROMPT, PLAN_PROMPT, SCRIPT_PROMPT


def analyze_video(video_path: str, config: AppConfig) -> dict:
    provider, model = get_video_provider(config, TaskName.VIDEO_ANALYZE)
    task_cfg = config.ai.tasks[TaskName.VIDEO_ANALYZE.value]
    print(f"  AI: {task_cfg.provider}/{model}")
    text = provider.analyze_video(video_path, ANALYZE_PROMPT, model)
    return extract_json(text)


def generate_voiceover(clip_data: dict, template: str, config: AppConfig) -> dict:
    provider, model = get_task_provider(config, TaskName.VOICEOVER)
    task_cfg = config.ai.tasks[TaskName.VOICEOVER.value]
    print(f"  AI: {task_cfg.provider}/{model}")

    timeline_text = "\n".join(
        f"- {t.get('start', '?')}-{t.get('end', '?')}: {t.get('description', '')}"
        for t in clip_data.get("timeline", [])
    )
    prompt = SCRIPT_PROMPT.format(
        index=clip_data.get("index", ""),
        title=clip_data.get("title", ""),
        summary=clip_data.get("summary", ""),
        location=clip_data.get("location", ""),
        timeline_text=timeline_text or "（无）",
        template=template,
        target_words=config.script.target_words,
    )
    text = provider.generate_text(prompt, model)
    return extract_json(text)


def plan_daily_vlog(clips: list[dict], config: AppConfig, day_label: str = "day1") -> dict:
    provider, model = get_task_provider(config, TaskName.VLOG_PLAN)
    task_cfg = config.ai.tasks[TaskName.VLOG_PLAN.value]
    print(f"  AI: {task_cfg.provider}/{model}")

    prompt = PLAN_PROMPT.format(
        clips_json=json.dumps(clips, ensure_ascii=False, indent=2),
        max_clips=config.plan.max_clips_per_day,
        target_duration_sec=config.plan.target_duration_sec,
    )
    text = provider.generate_text(f"日 vlog 标签: {day_label}\n\n{prompt}", model)
    return extract_json(text)
