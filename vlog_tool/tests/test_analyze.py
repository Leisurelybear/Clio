"""Tests for vlog_tool/tasks/analyze.py — pure logic only."""

from __future__ import annotations

from pathlib import Path

from vlog_tool.tasks.analyze import _resolve_original


class TestResolveOriginal:
    def test_direct_match_mp4(self, tmp_path: Path):
        (tmp_path / "GL010683.mp4").write_bytes(b"")
        result = _resolve_original(tmp_path, "001_GL010683")
        assert result == tmp_path / "GL010683.mp4"

    def test_direct_match_mov(self, tmp_path: Path):
        (tmp_path / "GL010683.mov").write_bytes(b"")
        result = _resolve_original(tmp_path, "001_GL010683")
        assert result == tmp_path / "GL010683.mov"

    def test_direct_match_mkv(self, tmp_path: Path):
        (tmp_path / "GL010683.mkv").write_bytes(b"")
        result = _resolve_original(tmp_path, "001_GL010683")
        assert result == tmp_path / "GL010683.mkv"

    def test_direct_match_mts(self, tmp_path: Path):
        (tmp_path / "GL010683.MTS").write_bytes(b"")
        result = _resolve_original(tmp_path, "001_GL010683")
        assert result == tmp_path / "GL010683.MTS"

    def test_direct_match_m2ts(self, tmp_path: Path):
        (tmp_path / "GL010683.M2TS").write_bytes(b"")
        result = _resolve_original(tmp_path, "001_GL010683")
        assert result == tmp_path / "GL010683.M2TS"

    def test_no_match(self, tmp_path: Path):
        result = _resolve_original(tmp_path, "001_NOFILE")
        assert result is None

    def test_segment_match(self, tmp_path: Path):
        (tmp_path / "GL010683.mp4").write_bytes(b"")
        result = _resolve_original(tmp_path, "001_GL010683_seg01")
        assert result == tmp_path / "GL010683.mp4"

    def test_segment_match_mov(self, tmp_path: Path):
        (tmp_path / "GL010683.mov").write_bytes(b"")
        result = _resolve_original(tmp_path, "001_GL010683_seg02")
        assert result == tmp_path / "GL010683.mov"

    def test_segment_no_original(self, tmp_path: Path):
        result = _resolve_original(tmp_path, "001_GL010683_seg01")
        assert result is None

    def test_empty_dir(self, tmp_path: Path):
        result = _resolve_original(tmp_path, "001_GL010683")
        assert result is None
