"""Tests for vlog_tool/pipeline.py — run_pipeline_steps cancel propagation."""

from __future__ import annotations

from pathlib import Path
from threading import Event
from unittest.mock import MagicMock, patch

from vlog_tool.pipeline import run_pipeline_steps


def _mock_config(tmp_path: Path):
    """Create a minimal AppConfig-like object."""
    cfg = MagicMock()
    cfg.paths.output_dir = tmp_path
    cfg.paths.input_dir = tmp_path
    cfg.analyze.skip_existing = False
    cfg.ai.providers = {}
    cfg.ai.tasks = {}
    cfg.compress.target_size_mb = 5
    cfg.compress.max_width = 640
    cfg.compress.fps = 15
    cfg.compress.codec = "libx264"
    cfg.compress.remove_audio = True
    cfg.compress.crf = 23
    cfg.compress.split_max_min = 0
    cfg.compress.splits_subdir = "splits"
    cfg.whisper.enabled = False
    return cfg


class TestRunPipelineStepsCancel:
    def test_cancel_stops_after_current_step(self):
        """cancel_event 设置后 pipeline 在步骤间退出"""
        config = _mock_config(Path(""))
        cancel_event = Event()
        calls: list[str] = []

        def _fake_compress(*a, **kw):
            calls.append("compress")
            cancel_event.set()
            return None

        def _fake_analyze(*a, **kw):
            calls.append("analyze")
            return None

        fake_funcs = {"compress": _fake_compress, "analyze": _fake_analyze}
        with (
            patch("vlog_tool.pipeline._STEP_FUNCS", fake_funcs),
            patch("builtins.print"),
            patch(
                "vlog_tool.pipeline.timed", lambda msg: MagicMock(__enter__=lambda s: None, __exit__=lambda *a: None)
            ),
        ):
            run_pipeline_steps(config, steps=["compress", "analyze"], cancel_event=cancel_event)

        # After compress sets cancel_event, analyze should NOT run
        assert "compress" in calls
        assert "analyze" not in calls, f"analyze should not run after cancel, got calls: {calls}"

    def test_cancel_event_passed_to_compress(self):
        """cancel_event 应传递给 compress step"""
        config = _mock_config(Path(""))
        cancel_event = Event()
        compress_kwargs: dict = {}

        def _compress_mock(*a, **kw):
            compress_kwargs.update(kw)
            return None

        fake_funcs = {"compress": _compress_mock}
        with (
            patch("vlog_tool.pipeline._STEP_FUNCS", fake_funcs),
            patch("builtins.print"),
            patch(
                "vlog_tool.pipeline.timed", lambda msg: MagicMock(__enter__=lambda s: None, __exit__=lambda *a: None)
            ),
        ):
            run_pipeline_steps(config, steps=["compress"], cancel_event=cancel_event)

        assert compress_kwargs.get("cancel_event") is cancel_event, (
            f"Expected cancel_event to be passed, got kwargs: {compress_kwargs}"
        )

    def test_cancel_event_passed_to_transcribe(self):
        """cancel_event 应传递给 transcribe step"""
        config = _mock_config(Path(""))
        config.whisper.enabled = True
        cancel_event = Event()
        transcribe_kwargs: dict = {}

        def _transcribe_mock(*a, **kw):
            transcribe_kwargs.update(kw)
            return 0

        fake_funcs = {"transcribe": _transcribe_mock}
        with (
            patch("vlog_tool.pipeline._STEP_FUNCS", fake_funcs),
            patch("builtins.print"),
            patch(
                "vlog_tool.pipeline.timed", lambda msg: MagicMock(__enter__=lambda s: None, __exit__=lambda *a: None)
            ),
        ):
            run_pipeline_steps(config, steps=["transcribe"], cancel_event=cancel_event)

        assert transcribe_kwargs.get("cancel_event") is cancel_event, (
            f"Expected cancel_event to be passed, got kwargs: {transcribe_kwargs}"
        )

    def test_cancel_event_not_passed_to_analyze(self):
        """cancel_event 不应传递给 analyze（不支持 cancel 的 step）"""
        config = _mock_config(Path(""))
        cancel_event = Event()
        analyze_kwargs: dict = {}

        def _analyze_mock(*a, **kw):
            analyze_kwargs.update(kw)
            return None

        fake_funcs = {"analyze": _analyze_mock}
        with (
            patch("vlog_tool.pipeline._STEP_FUNCS", fake_funcs),
            patch("builtins.print"),
            patch(
                "vlog_tool.pipeline.timed", lambda msg: MagicMock(__enter__=lambda s: None, __exit__=lambda *a: None)
            ),
        ):
            run_pipeline_steps(config, steps=["analyze"], cancel_event=cancel_event)

        assert "cancel_event" not in analyze_kwargs, (
            f"cancel_event should NOT be passed to analyze, got kwargs: {analyze_kwargs}"
        )
