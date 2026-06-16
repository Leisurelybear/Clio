"""Tests for vlog_tool/tasks/transcribe.py — run_transcribe_all."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from vlog_tool.config import WhisperConfig
from vlog_tool.progress import ProgressTracker


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
    @patch("vlog_tool.tasks.transcribe.resolve_binary", return_value="ffmpeg")
    def test_dedup(self, mock_resolve, mock_transcribe, mock_extract, cfg, tmp_path):
        """同一原始视频只转录一次（有 split 段时）"""
        from vlog_tool.tasks.transcribe import run_transcribe_all

        output = tmp_path / "output"
        compressed = output / "compressed"
        compressed.mkdir(parents=True)
        inp = tmp_path / "input"
        inp.mkdir()
        (inp / "GL010683.mp4").touch()
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

    @patch("vlog_tool.tasks.transcribe.check_whisper", return_value=False)
    def test_tracker_error_when_whisper_missing(self, mock_check, cfg, tmp_path):
        """当 faster-whisper 未安装时 tracker.error 被调用"""
        from vlog_tool.tasks.transcribe import run_transcribe_all

        tracker = MagicMock(spec=ProgressTracker)
        run_transcribe_all(cfg, tracker)
        tracker.error.assert_called_once()
        args = tracker.error.call_args[0][0]
        assert "faster-whisper" in args
        assert "whisper install" in args

    @patch("vlog_tool.tasks.transcribe._extract_audio")
    @patch("vlog_tool.tasks.transcribe.transcribe_audio")
    @patch("vlog_tool.tasks.transcribe.resolve_binary", return_value="ffmpeg")
    def test_skip_existing(self, mock_resolve, mock_transcribe, mock_extract, cfg, tmp_path):
        """已有 transcript 文件时跳过"""
        from vlog_tool.tasks.transcribe import run_transcribe_all

        output = tmp_path / "output"
        inp = tmp_path / "input"
        inp.mkdir()
        (inp / "GL010683.mp4").touch()
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

    @patch("vlog_tool.tasks.transcribe._extract_audio")
    @patch("vlog_tool.tasks.transcribe.transcribe_audio")
    @patch("vlog_tool.tasks.transcribe.resolve_binary", return_value="ffmpeg")
    def test_audio_extracted(self, mock_resolve, mock_transcribe, mock_extract, cfg, tmp_path):
        """转录会提取音频并调用 Whisper（无 duration 限制）"""
        from vlog_tool.tasks.transcribe import run_transcribe_all

        output = tmp_path / "output"
        inp = tmp_path / "input"
        inp.mkdir()
        (inp / "GL010683.mp4").touch()
        compressed = output / "compressed"
        compressed.mkdir(parents=True)
        (compressed / "001_GL010683.mp4").touch()
        cfg.paths.input_dir = inp
        cfg.paths.output_dir = output

        transcripts = output / "transcripts"
        transcripts.mkdir(parents=True)

        mock_extract.return_value = tmp_path / "fake.wav"
        (tmp_path / "fake.wav").touch()

        tracker = MagicMock()
        run_transcribe_all(cfg, tracker)
        mock_transcribe.assert_called_once()

    @patch("vlog_tool.tasks.transcribe._extract_audio")
    @patch("vlog_tool.tasks.transcribe.transcribe_audio")
    def test_original_not_found(self, mock_transcribe, mock_extract, cfg, tmp_path):
        """压缩文件在 input_dir 中找不到原始视频时跳过"""
        from vlog_tool.tasks.transcribe import run_transcribe_all

        output = tmp_path / "output"
        compressed = output / "compressed"
        compressed.mkdir(parents=True)
        inp = tmp_path / "input"
        inp.mkdir()
        cfg.paths.input_dir = inp
        cfg.paths.output_dir = output

        (compressed / "001_GL010683.mp4").touch()

        transcripts = output / "transcripts"
        transcripts.mkdir(parents=True)

        tracker = MagicMock()
        run_transcribe_all(cfg, tracker)
        mock_transcribe.assert_not_called()

    @patch("vlog_tool.tasks.transcribe._extract_audio")
    @patch("vlog_tool.tasks.transcribe.transcribe_audio")
    @patch("vlog_tool.tasks.transcribe.resolve_binary", return_value="ffmpeg")
    def test_audio_extraction_failure(self, mock_resolve, mock_transcribe, mock_extract, cfg, tmp_path):
        """音频提取失败时跳过"""
        from vlog_tool.tasks.transcribe import run_transcribe_all

        output = tmp_path / "output"
        inp = tmp_path / "input"
        inp.mkdir()
        (inp / "GL010683.mp4").touch()
        compressed = output / "compressed"
        compressed.mkdir(parents=True)
        (compressed / "001_GL010683.mp4").touch()
        cfg.paths.input_dir = inp
        cfg.paths.output_dir = output

        transcripts = output / "transcripts"
        transcripts.mkdir(parents=True)

        mock_extract.return_value = None

        tracker = MagicMock()
        run_transcribe_all(cfg, tracker)
        mock_transcribe.assert_not_called()

    @patch("vlog_tool.tasks.transcribe._extract_audio")
    @patch("vlog_tool.tasks.transcribe.transcribe_audio")
    @patch("vlog_tool.tasks.transcribe.resolve_binary", return_value="ffmpeg")
    def test_transcribe_error(self, mock_resolve, mock_transcribe, mock_extract, cfg, tmp_path):
        """Whisper 转录出错时记录错误状态并继续"""
        from vlog_tool.tasks.transcribe import run_transcribe_all

        output = tmp_path / "output"
        inp = tmp_path / "input"
        inp.mkdir()
        (inp / "GL010683.mp4").touch()
        compressed = output / "compressed"
        compressed.mkdir(parents=True)
        (compressed / "001_GL010683.mp4").touch()
        cfg.paths.input_dir = inp
        cfg.paths.output_dir = output

        transcripts = output / "transcripts"
        transcripts.mkdir(parents=True)

        mock_extract.return_value = tmp_path / "fake.wav"
        (tmp_path / "fake.wav").touch()
        mock_transcribe.side_effect = RuntimeError("whisper崩溃")

        tracker = MagicMock()
        result = run_transcribe_all(cfg, tracker)
        assert result == 0


class TestRunTranscribeOne:
    @patch("vlog_tool.tasks.transcribe.resolve_binary", return_value="ffmpeg")
    def test_success(self, mock_resolve, cfg, tmp_path):
        from vlog_tool.tasks.transcribe import run_transcribe_one

        video = tmp_path / "test.mp4"
        video.write_text("fake video")

        cfg.paths.output_dir = tmp_path / "output"

        with (
            patch("vlog_tool.tasks.transcribe._extract_audio", return_value=tmp_path / "fake.wav"),
            patch(
                "vlog_tool.tasks.transcribe.transcribe_audio", return_value=[{"start": 0.0, "end": 1.0, "text": "test"}]
            ),
        ):
            (tmp_path / "fake.wav").touch()
            result = run_transcribe_one(cfg, video)
            assert "error" not in result
            assert result["source_stem"] == "test"
            assert len(result["segments"]) == 1

    def test_file_not_found(self, cfg, tmp_path):
        from vlog_tool.tasks.transcribe import run_transcribe_one

        video = tmp_path / "nonexistent.mp4"
        result = run_transcribe_one(cfg, video)
        assert "error" in result
        assert "不存在" in result["error"]

    @patch("vlog_tool.tasks.transcribe.resolve_binary", return_value="ffmpeg")
    def test_extraction_failure(self, mock_resolve, cfg, tmp_path):
        from vlog_tool.tasks.transcribe import run_transcribe_one

        video = tmp_path / "test.mp4"
        video.write_text("fake video")

        cfg.paths.output_dir = tmp_path / "output"

        with patch("vlog_tool.tasks.transcribe._extract_audio", return_value=None):
            result = run_transcribe_one(cfg, video)
            assert "error" in result
            assert "音频提取失败" in result["error"]
