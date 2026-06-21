"""Tests for vlog_tool/split.py — split_video."""

from __future__ import annotations

from pathlib import Path

import pytest

from vlog_tool.split import split_video


class TestSplitVideo:
    def test_no_split_when_under_max(self, monkeypatch, tmp_path: Path):
        monkeypatch.setattr("vlog_tool.split.get_duration_sec", lambda *a, **kw: 60.0)
        monkeypatch.setattr("vlog_tool.split.run_ffmpeg", lambda *a, **kw: None)
        result = split_video(tmp_path / "video.mp4", tmp_path / "splits", 15, "ffmpeg", "ffprobe")
        assert result == [tmp_path / "video.mp4"]

    def test_no_split_at_exact_max(self, monkeypatch, tmp_path: Path):
        monkeypatch.setattr("vlog_tool.split.get_duration_sec", lambda *a, **kw: 900.0)  # 15 min
        monkeypatch.setattr("vlog_tool.split.run_ffmpeg", lambda *a, **kw: None)
        result = split_video(tmp_path / "video.mp4", tmp_path / "splits", 15, "ffmpeg", "ffprobe")
        assert result == [tmp_path / "video.mp4"]

    def test_splits_into_two(self, monkeypatch, tmp_path: Path):
        monkeypatch.setattr("vlog_tool.split.get_duration_sec", lambda *a, **kw: 1200.0)  # 20 min
        ffmpeg_calls = []
        monkeypatch.setattr("vlog_tool.split.run_ffmpeg", lambda args, ff: ffmpeg_calls.append(args))

        result = split_video(tmp_path / "video.mp4", tmp_path / "splits", 15, "ffmpeg", "ffprobe")
        assert len(result) == 2
        assert result[0] == tmp_path / "splits" / "video_seg01.mp4"
        assert result[1] == tmp_path / "splits" / "video_seg02.mp4"
        assert len(ffmpeg_calls) == 2
        # Each call should have -ss, -i, -t, -c copy etc.
        assert "-ss" in ffmpeg_calls[0]
        assert "-c" in ffmpeg_calls[0]
        assert "copy" in ffmpeg_calls[0]

    def test_splits_with_exact_multiple(self, monkeypatch, tmp_path: Path):
        """30 min with 15 min max → exactly 2 segments."""
        monkeypatch.setattr("vlog_tool.split.get_duration_sec", lambda *a, **kw: 1800.0)
        ffmpeg_calls = []
        monkeypatch.setattr("vlog_tool.split.run_ffmpeg", lambda args, ff: ffmpeg_calls.append(args))

        result = split_video(tmp_path / "video.mp4", tmp_path / "splits", 15, "ffmpeg", "ffprobe")
        assert len(result) == 2
        # Segments should be 900s each
        assert ffmpeg_calls[0][ffmpeg_calls[0].index("-t") + 1] == "900.0"

    def test_creates_output_dir(self, monkeypatch, tmp_path: Path):
        monkeypatch.setattr("vlog_tool.split.get_duration_sec", lambda *a, **kw: 1800.0)
        monkeypatch.setattr("vlog_tool.split.run_ffmpeg", lambda *a, **kw: None)
        out = tmp_path / "splits"
        assert not out.exists()
        split_video(tmp_path / "video.mp4", out, 10, "ffmpeg", "ffprobe")
        assert out.is_dir()

    def test_segments_have_correct_format(self, monkeypatch, tmp_path: Path):
        monkeypatch.setattr("vlog_tool.split.get_duration_sec", lambda *a, **kw: 3600.0)
        monkeypatch.setattr("vlog_tool.split.run_ffmpeg", lambda *a, **kw: None)
        result = split_video(tmp_path / "test_video.MOV", tmp_path / "splits", 10, "ffmpeg", "ffprobe")
        expected_count = 6  # 3600 / 600 = 6
        assert len(result) == expected_count
        assert result[0].name == "test_video_seg01.MOV"
        assert result[-1].name == "test_video_seg06.MOV"

    def test_last_segment_takes_remainder(self, monkeypatch, tmp_path: Path):
        """1350s with 600s max → 3 equal segments of ~450s."""
        monkeypatch.setattr("vlog_tool.split.get_duration_sec", lambda *a, **kw: 1350.0)
        ffmpeg_calls = []
        monkeypatch.setattr("vlog_tool.split.run_ffmpeg", lambda args, ff: ffmpeg_calls.append(args))

        result = split_video(tmp_path / "video.mp4", tmp_path / "splits", 10, "ffmpeg", "ffprobe")
        assert len(result) == 3
        # All segments are equal length since the code divides evenly
        last_dur = ffmpeg_calls[-1][ffmpeg_calls[-1].index("-t") + 1]
        assert float(last_dur) == pytest.approx(450.0, rel=0.01)

    def test_reencode_uses_video_codec(self, monkeypatch, tmp_path: Path):
        """When reencode=True, uses libx264 instead of -c copy."""
        monkeypatch.setattr("vlog_tool.split.get_duration_sec", lambda *a, **kw: 1200.0)
        ffmpeg_calls = []
        monkeypatch.setattr("vlog_tool.split.run_ffmpeg", lambda args, ff: ffmpeg_calls.append(args))

        split_video(tmp_path / "video.mp4", tmp_path / "splits", 10, "ffmpeg", "ffprobe", reencode=True)
        assert len(ffmpeg_calls) == 2
        assert "-c:v" in ffmpeg_calls[0]
        assert "libx264" in ffmpeg_calls[0]
        assert "-c:a" in ffmpeg_calls[0]
        assert "aac" in ffmpeg_calls[0]
        assert "-c" not in ffmpeg_calls[0] or ffmpeg_calls[0].index("-c") != ffmpeg_calls[0].index("-c:v")  # no bare -c
