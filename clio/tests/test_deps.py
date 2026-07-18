"""Tests for probe_ffmpeg_deps."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from clio.utils import probe_ffmpeg_deps


class TestProbeFfmpegDeps:
    def test_both_found(self, tmp_path: Path):
        ff = tmp_path / "ffmpeg.exe"
        fp = tmp_path / "ffprobe.exe"
        ff.write_bytes(b"x")
        fp.write_bytes(b"x")
        out = probe_ffmpeg_deps(str(ff), str(fp))
        assert out["ok"] is True
        assert out["ffmpeg"] == str(ff)
        assert out["ffprobe"] == str(fp)
        assert out["missing"] == []
        assert out["detail"] == ""

    def test_neither_found_empty_config(self):
        with patch("clio.utils.discover_ffmpeg_bin", return_value=None):
            out = probe_ffmpeg_deps("", "")
        assert out["ok"] is False
        assert set(out["missing"]) == {"ffmpeg", "ffprobe"}
        assert out["ffmpeg"] is None and out["ffprobe"] is None
        assert "ffmpeg" in out["detail"] and "ffprobe" in out["detail"]

    def test_only_ffmpeg_found(self, tmp_path: Path):
        ff = tmp_path / "ffmpeg.exe"
        ff.write_bytes(b"x")

        def fake_resolve(configured, fallback):
            if fallback == "ffmpeg":
                return str(ff)
            raise FileNotFoundError(fallback)

        with patch("clio.utils.resolve_binary", side_effect=fake_resolve):
            out = probe_ffmpeg_deps("", "")
        assert out["ok"] is False
        assert out["missing"] == ["ffprobe"]
        assert out["ffmpeg"] == str(ff)
        assert "ffprobe" in out["detail"]

    def test_bad_configured_path(self, tmp_path: Path):
        out = probe_ffmpeg_deps(str(tmp_path / "nope.exe"), str(tmp_path / "nope2.exe"))
        assert out["ok"] is False
        assert "ffmpeg" in out["missing"]
        assert "ffprobe" in out["missing"]

    def test_empty_not_coerced_to_bare_name(self):
        calls = []

        def fake_resolve(configured, fallback):
            calls.append((configured, fallback))
            raise FileNotFoundError(fallback)

        with patch("clio.utils.resolve_binary", side_effect=fake_resolve):
            probe_ffmpeg_deps("", "")
        assert calls == [("", "ffmpeg"), ("", "ffprobe")]
