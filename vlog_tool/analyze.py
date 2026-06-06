from __future__ import annotations

import json

from vlog_tool.ai.base import TaskName
from vlog_tool.ai.factory import get_task_provider, get_video_provider
from vlog_tool.ai.gemini import extract_json
from vlog_tool.config import AppConfig
from vlog_tool.prompts import ANALYZE_PROMPT, PLAN_PROMPT, REFINE_SCRIPT_PROMPT, REFINE_TEXT_PROMPT, SCRIPT_PROMPT


def _wrap_with_context(prompt: str, config: AppConfig) -> str:
    """如果有 trip 上下文/规范，附加在 prompt 前面。"""
    if not config.ai.context:
        return prompt
    return (
        "## 背景与规范（请严格遵守）\n\n"
        f"{config.ai.context}\n\n"
        "---\n\n"
        f"{prompt}"
    )


def _wrap_with_context(prompt: str, config: AppConfig) -> str:
    """如果有 trip 上下文/规范，附加在 prompt 前面。"""
    if not config.ai.context:
        return prompt
    return (
        "## 背景与规范（请严格遵守）\n\n"
        f"{config.ai.context}\n\n"
        "---\n\n"
        f"{prompt}"
    )


def analyze_video(video_path: str, config: AppConfig) -> dict:
    provider, model = get_video_provider(config, TaskName.VIDEO_ANALYZE)
    task_cfg = config.ai.tasks[TaskName.VIDEO_ANALYZE.value]
    print(f"  AI: {task_cfg.provider}/{model}")
    prompt = _wrap_with_context(ANALYZE_PROMPT, config)
    text = provider.analyze_video(video_path, prompt, model)
    return extract_json(text)


def generate_voiceover(clip_data: dict, template: str, config: AppConfig) -> dict:
    provider, model = get_task_provider(config, TaskName.VOICEOVER)
    task_cfg = config.ai.tasks[TaskName.VOICEOVER.value]
    print(f"  AI: {task_cfg.provider}/{model}")

    timeline_text = "\n".join(
        f"- {t.get('start', '?')}-{t.get('end', '?')}: {t.get('description', '')}"
        for t in clip_data.get("timeline", [])
    )
    base = SCRIPT_PROMPT.format(
        index=clip_data.get("index", ""),
        title=clip_data.get("title", ""),
        summary=clip_data.get("summary", ""),
        location=clip_data.get("location", ""),
        timeline_text=timeline_text or "（无）",
        template=template,
        target_words=config.script.target_words,
    )
    prompt = _wrap_with_context(base, config)
    text = provider.generate_text(prompt, model)
    return extract_json(text)


def plan_daily_vlog(clips: list[dict], config: AppConfig, day_label: str = "day1") -> dict:
    provider, model = get_task_provider(config, TaskName.VLOG_PLAN)
    task_cfg = config.ai.tasks[TaskName.VLOG_PLAN.value]
    print(f"  AI: {task_cfg.provider}/{model}")

    base = PLAN_PROMPT.format(
        clips_json=json.dumps(clips, ensure_ascii=False, indent=2),
        max_clips=config.plan.max_clips_per_day,
        target_duration_sec=config.plan.target_duration_sec,
    )
    prompt = _wrap_with_context(f"日 vlog 标签: {day_label}\n\n{base}", config)
    text = provider.generate_text(prompt, model)
    return extract_json(text)


def refine_text(analysis: dict, config: AppConfig) -> dict:
    """依据 trip 上下文审阅并修正现有的素材分析。"""
    provider, model = get_task_provider(config, TaskName.VIDEO_ANALYZE)
    task_cfg = config.ai.tasks[TaskName.VIDEO_ANALYZE.value]
    print(f"  AI: {task_cfg.provider}/{model}")
    base = REFINE_TEXT_PROMPT.format(
        existing_json=json.dumps(analysis, ensure_ascii=False, indent=2),
    )
    prompt = _wrap_with_context(base, config)
    text = provider.generate_text(prompt, model)
    return extract_json(text)


def refine_script(script: dict, analysis: dict | None, config: AppConfig) -> dict:
    """依据 trip 上下文审阅并修正现有的口播文案。"""
    provider, model = get_task_provider(config, TaskName.VOICEOVER)
    task_cfg = config.ai.tasks[TaskName.VOICEOVER.value]
    print(f"  AI: {task_cfg.provider}/{model}")
    analysis_json = (
        json.dumps(analysis, ensure_ascii=False, indent=2) if analysis else "（无）"
    )
    base = REFINE_SCRIPT_PROMPT.format(
        analysis_json=analysis_json,
        existing_json=json.dumps(script, ensure_ascii=False, indent=2),
    )
    prompt = _wrap_with_context(base, config)
    text = provider.generate_text(prompt, model)
    return extract_json(text)
