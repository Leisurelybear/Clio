from __future__ import annotations

import json

from vlog_tool.ai.base import TaskName
from vlog_tool.ai.factory import get_task_provider, get_video_provider
from vlog_tool.ai.gemini import extract_json
from vlog_tool.config import AppConfig
from vlog_tool.log import format_size, timed
from vlog_tool.prompts import (
    ANALYZE_PROMPT,
    PLAN_PROMPT,
    REFINE_SCRIPT_FIX_PROMPT,
    REFINE_SCRIPT_PROMPT,
    REFINE_TEXT_FIX_PROMPT,
    REFINE_TEXT_PROMPT,
    SCRIPT_PROMPT,
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


def _call_ai(label: str, provider_id: str, model: str, prompt: str, fn) -> str:
    """统一 AI 调用的日志壳：打印提示词大小、起止时间、响应大小。"""
    prompt_bytes = len(prompt.encode("utf-8"))
    print(f"  AI: {provider_id}/{model}（prompt {format_size(prompt_bytes)}）")
    with timed(f"{label} {provider_id}/{model}"):
        text = fn()
    print(f"  响应: {format_size(len(text.encode('utf-8')))}")
    return text


def analyze_video(video_path: str, config: AppConfig) -> dict:
    provider, model = get_video_provider(config, TaskName.VIDEO_ANALYZE)
    prompt = _wrap_with_context(ANALYZE_PROMPT, config)
    text = _call_ai(
        "AI 视频分析", provider.provider_id, model, prompt,
        lambda: provider.analyze_video(video_path, prompt, model),
    )
    return extract_json(text)


def generate_voiceover(clip_data: dict, template: str, config: AppConfig) -> dict:
    provider, model = get_task_provider(config, TaskName.VOICEOVER)

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
    text = _call_ai(
        "AI 口播", provider.provider_id, model, prompt,
        lambda: provider.generate_text(prompt, model),
    )
    return extract_json(text)


def plan_daily_vlog(clips: list[dict], config: AppConfig, day_label: str = "day1") -> dict:
    provider, model = get_task_provider(config, TaskName.VLOG_PLAN)

    base = PLAN_PROMPT.format(
        clips_json=json.dumps(clips, ensure_ascii=False, indent=2),
        max_clips=config.plan.max_clips_per_day,
        target_duration_sec=config.plan.target_duration_sec,
    )
    prompt = _wrap_with_context(f"日 vlog 标签: {day_label}\n\n{base}", config)
    text = _call_ai(
        "AI 日 vlog 规划", provider.provider_id, model, prompt,
        lambda: provider.generate_text(prompt, model),
    )
    return extract_json(text)


def refine_text(analysis: dict, config: AppConfig, fix: str | None = None) -> dict:
    """审阅并修正现有的素材分析。

    fix 非空时切换为「按用户意见定向修正」模式（仅改用户提到的字段，
    changelog 第一条固定写"按用户意见修改了 XXX"）。
    """
    provider, model = get_task_provider(config, TaskName.REFINE_TEXT)
    if fix:
        base = REFINE_TEXT_FIX_PROMPT.format(
            fix_instruction=fix.strip(),
            existing_json=json.dumps(analysis, ensure_ascii=False, indent=2),
        )
        label = "AI refine (定向)"
    else:
        base = REFINE_TEXT_PROMPT.format(
            existing_json=json.dumps(analysis, ensure_ascii=False, indent=2),
        )
        label = "AI refine 素材"
    prompt = _wrap_with_context(base, config)
    text = _call_ai(
        label, provider.provider_id, model, prompt,
        lambda: provider.generate_text(prompt, model),
    )
    return extract_json(text)


def refine_script(script: dict, analysis: dict | None, config: AppConfig, fix: str | None = None) -> dict:
    """审阅并修正现有的口播文案。

    复用 refine_text 任务的 provider/model 配置 —— texts 和 scripts 审阅
    都是纯文本输入输出，没必要拆两个任务。
    fix 非空时切换为定向修正模式（同 refine_text）。
    """
    provider, model = get_task_provider(config, TaskName.REFINE_TEXT)
    analysis_json = (
        json.dumps(analysis, ensure_ascii=False, indent=2) if analysis else "（无）"
    )
    existing_json = json.dumps(script, ensure_ascii=False, indent=2)
    if fix:
        base = REFINE_SCRIPT_FIX_PROMPT.format(
            fix_instruction=fix.strip(),
            analysis_json=analysis_json,
            existing_json=existing_json,
        )
        label = "AI refine 脚本 (定向)"
    else:
        base = REFINE_SCRIPT_PROMPT.format(
            analysis_json=analysis_json,
            existing_json=existing_json,
        )
        label = "AI refine 脚本"
    prompt = _wrap_with_context(base, config)
    text = _call_ai(
        label, provider.provider_id, model, prompt,
        lambda: provider.generate_text(prompt, model),
    )
    return extract_json(text)
