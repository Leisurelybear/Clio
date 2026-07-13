"""Tests for clio/tasks/analyze.py — pure logic only."""

from __future__ import annotations

from pathlib import Path

from clio.tasks.analyze import _resolve_original


class TestResolveOriginal:
    def test_direct_match_mp4(self, tmp_path: Path):
        video = tmp_path / "GL010683.mp4"
        video.write_bytes(b"")
        result = _resolve_original("001_GL010683", stem_cache={"gl010683": video})
        assert result == video

    def test_direct_match_mov(self, tmp_path: Path):
        video = tmp_path / "GL010683.mov"
        video.write_bytes(b"")
        result = _resolve_original("001_GL010683", stem_cache={"gl010683": video})
        assert result == video

    def test_direct_match_mkv(self, tmp_path: Path):
        video = tmp_path / "GL010683.mkv"
        video.write_bytes(b"")
        result = _resolve_original("001_GL010683", stem_cache={"gl010683": video})
        assert result == video

    def test_direct_match_mts(self, tmp_path: Path):
        video = tmp_path / "GL010683.mts"
        video.write_bytes(b"")
        result = _resolve_original("001_GL010683", stem_cache={"gl010683": video})
        assert result == video

    def test_direct_match_m2ts(self, tmp_path: Path):
        video = tmp_path / "GL010683.m2ts"
        video.write_bytes(b"")
        result = _resolve_original("001_GL010683", stem_cache={"gl010683": video})
        assert result == video

    def test_no_match(self, tmp_path: Path):
        result = _resolve_original("001_NOFILE", stem_cache={})
        assert result is None

    def test_segment_match(self, tmp_path: Path):
        video = tmp_path / "GL010683.mp4"
        video.write_bytes(b"")
        result = _resolve_original("001_GL010683_seg01", stem_cache={"gl010683": video})
        assert result == video

    def test_segment_match_mov(self, tmp_path: Path):
        video = tmp_path / "GL010683.mov"
        video.write_bytes(b"")
        result = _resolve_original("001_GL010683_seg02", stem_cache={"gl010683": video})
        assert result == video

    def test_segment_no_original(self, tmp_path: Path):
        result = _resolve_original("001_GL010683_seg01", stem_cache={})
        assert result is None

    def test_empty_dir(self, tmp_path: Path):
        result = _resolve_original("001_GL010683", stem_cache={})
        assert result is None
