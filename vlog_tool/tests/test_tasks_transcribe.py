"""Tests for vlog_tool/tasks/transcribe.py — run_transcribe_all."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from vlog_tool.config import WhisperConfig


@pytest.fixture(autouse=True)
def _mock_whisper_deps():
    """Patch faster_whisper so import inside run_transcribe_all works."""
    with patch.dict("sys.modules", {"faster_whisper": MagicMock()}):
        yield


@pytest.fixture
def cfg():
    c = MagicMock()
    c.whisper = WhisperConfig(enabled=True, language="zh", model_size="small", device="cpu")
    c.paths.output_dir = Path("/tmp/output")
    c.paths.input_dir = Path("/tmp/input")
    c.analyze.skip_existing = True
    c.analyze.compressed_subdir = "compressed"
    c.analyze.max_analyze_duration_min = 30
    return c


class TestRunTranscribeAll:
    @patch("vlog_tool.tasks.transcribe._extract_audio")
    @patch("vlog_tool.tasks.transcribe.transcribe_audio")
    def test_dedup(self, mock_transcribe, mock_extract, cfg, tmp_path):
        """同一原始视频只转录一次（有 split 段时）"""
        from vlog_tool.tasks.transcribe import run_transcribe_all

        output = tmp_path / "output"
        compressed = output / "compressed"
        compressed.mkdir(parents=True)
        inp = tmp_path / "input"
        inp.mkdir()
        (inp / "GL010683.MP4").touch()
        cfg.paths.input_dir = inp
        cfg.paths.output_dir = output

        (compressed / "001_GL010683.mp4").touch()
        split_dir = compressed / "split"
        split_dir.mkdir()
        (split_dir / "001_GL010683_seg01.mp4").touch()
        (split_dir / "001_GL010683_seg02.mp4").touch()

        transcripts_dir = output / "transcripts"
        transcripts_dir.mkdir(parents=True)

        mock_extract.return_value = tmp_path / "fake.wav"
        (tmp_path / "fake.wav").touch()

        tracker = MagicMock()
        run_transcribe_all(cfg, tracker)

        assert mock_transcribe.call_count == 1

    def test_disabled(self, cfg):
        """whisper.enabled=False 时直接跳过"""
        from vlog_tool.tasks.transcribe import run_transcribe_all

        cfg.whisper.enabled = False
        tracker = MagicMock()
        run_transcribe_all(cfg, tracker)
        tracker.update.assert_not_called()

    @patch("vlog_tool.tasks.transcribe._extract_audio")
    @patch("vlog_tool.tasks.transcribe.transcribe_audio")
    def test_skip_existing(self, mock_transcribe, mock_extract, cfg, tmp_path):
        """已有 transcript 文件时跳过"""
        from vlog_tool.tasks.transcribe import run_transcribe_all

        output = tmp_path / "output"
        inp = tmp_path / "input"
        inp.mkdir()
        (inp / "GL010683.MP4").touch()
        compressed = output / "compressed"
        compressed.mkdir(parents=True)
        (compressed / "001_GL010683.mp4").touch()
        cfg.paths.input_dir = inp
        cfg.paths.output_dir = output

        transcripts = output / "transcripts"
        transcripts.mkdir(parents=True)
        (transcripts / "GL010683_transcript.json").write_text("{}")

        mock_extract.return_value = tmp_path / "fake.wav"
        (tmp_path / "fake.wav").touch()

        tracker = MagicMock()
        run_transcribe_all(cfg, tracker)
        mock_transcribe.assert_not_called()
