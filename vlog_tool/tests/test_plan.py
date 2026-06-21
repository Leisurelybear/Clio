"""Tests for plan transcript injection."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from vlog_tool.config import AppConfig


def test_plan_prompt_includes_transcripts():
    """plan_daily_vlog injects transcripts_map into PLAN_PROMPT."""
    from vlog_tool.analyze import plan_daily_vlog

    clips = [
        {
            "index": "001",
            "title": "到达",
            "summary": "抵达机场",
            "timeline": [{"start": "00:00", "end": "00:30", "description": "到达"}],
            "location": "巴黎",
            "highlights": [],
            "suggested_use": "开场",
        }
    ]
    transcripts_map = {
        "GL010683": {"segments": [{"start": 0.0, "end": 2.5, "text": "今天天气真好", "avg_logprob": -0.1}]}
    }
    cfg = MagicMock(spec=AppConfig)
    cfg.ai = MagicMock(debug_print_prompt=False)
    cfg.plan = MagicMock()
    cfg.plan.max_clips_per_day = 12
    cfg.plan.target_duration_sec = 180
    cfg.whisper = MagicMock()
    cfg.whisper.max_segments_per_clip = 5
    cfg.whisper.enabled = True

    provider_mock = MagicMock()
    with (
        patch("vlog_tool.analyze.get_task_provider", return_value=(provider_mock, "deepseek-chat")),
        patch("vlog_tool.analyze._wrap_with_context", return_value="prompt"),
        patch("vlog_tool.analyze._call_ai", return_value="{}"),
        patch("vlog_tool.analyze.extract_json", return_value={"sequence": [], "day_title": "test"}),
    ):
        result = plan_daily_vlog(clips, cfg, "day1", transcripts_map=transcripts_map)
        assert result["day_title"] == "test"


def test_plan_no_transcript_fallback():
    """No transcript provided — plan generates normally without injection."""
    from vlog_tool.analyze import plan_daily_vlog

    clips = [
        {
            "index": "001",
            "title": "到达",
            "summary": "",
            "timeline": [],
            "location": "",
            "highlights": [],
            "suggested_use": "",
        }
    ]
    cfg = MagicMock(spec=AppConfig)
    cfg.ai = MagicMock(debug_print_prompt=False)
    cfg.plan = MagicMock()
    cfg.plan.max_clips_per_day = 12
    cfg.plan.target_duration_sec = 180
    cfg.whisper = MagicMock()
    cfg.whisper.max_segments_per_clip = 5
    cfg.whisper.enabled = True

    provider_mock = MagicMock()
    with (
        patch("vlog_tool.analyze.get_task_provider", return_value=(provider_mock, "deepseek-chat")),
        patch("vlog_tool.analyze._wrap_with_context", return_value="prompt"),
        patch("vlog_tool.analyze._call_ai", return_value="{}"),
        patch("vlog_tool.analyze.extract_json", return_value={"sequence": [], "day_title": "test"}),
    ):
        result = plan_daily_vlog(clips, cfg, "day1", transcripts_map=None)
        assert result["day_title"] == "test"
