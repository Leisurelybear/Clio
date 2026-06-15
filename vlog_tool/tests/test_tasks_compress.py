"""Tests for vlog_tool/tasks/compress.py — run_compress_all."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from vlog_tool.tasks.compress import run_compress_all


def _cfg(tmp_path: Path, **overrides) -> SimpleNamespace:
    cfg = SimpleNamespace(
        paths=SimpleNamespace(
            input_dir=tmp_path / "input",
            output_dir=tmp_path / "output",
            ffmpeg="ffmpeg",
            ffprobe="ffprobe",
            recursive=False,
        ),
        compressed_dir=tmp_path / "output" / "compressed",
        compress=SimpleNamespace(
            split_max_min=0,
            splits_subdir="splits",
            target_size_mb=5,
            max_width=640,
            fps=15,
            codec="libx264",
            remove_audio=True,
            crf=23,
        ),
        analyze=SimpleNamespace(skip_existing=False),
        naming=SimpleNamespace(index_width=3),
    )
    cfg.paths.input_dir.mkdir(parents=True, exist_ok=True)
    cfg.compressed_dir.mkdir(parents=True, exist_ok=True)
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


class TestRunCompressAll:
    def test_compress_single_file(self, monkeypatch, tmp_path: Path):
        cfg = _cfg(tmp_path)
        src = cfg.paths.input_dir / "test.mp4"
        src.write_bytes(b"\x00" * 1000)

        monkeypatch.setattr("vlog_tool.tasks.compress.resolve_binary", lambda *a: "ffmpeg")
        monkeypatch.setattr("vlog_tool.tasks.compress.find_videos", lambda *a, **kw: [src])

        def _mock_compress(inp, outp, cfg):
            outp.write_bytes(b"\x00" * 100)
            return outp

        monkeypatch.setattr("vlog_tool.tasks.compress.compress_video", _mock_compress)
        monkeypatch.setattr("vlog_tool.tasks.compress.split_video", lambda *a, **kw: [a[0]])

        records = run_compress_all(cfg)
        assert len(records) == 1
        assert records[0].stem == "001_test"
        assert records[0].compressed_path == cfg.compressed_dir / "001_test.mp4"

    def test_skip_existing(self, monkeypatch, tmp_path: Path):
        """Compress once, then verify second call skips the existing file."""
        cfg = _cfg(tmp_path)
        src = cfg.paths.input_dir / "test.mp4"
        src.write_bytes(b"\x00" * 1000)

        monkeypatch.setattr("vlog_tool.tasks.compress.resolve_binary", lambda *a: "ffmpeg")
        monkeypatch.setattr("vlog_tool.tasks.compress.find_videos", lambda *a, **kw: [src])

        call_count = 0

        def _mock_compress(inp, outp, c):
            nonlocal call_count
            call_count += 1
            outp.write_bytes(b"\x00" * 300)
            return outp

        monkeypatch.setattr("vlog_tool.tasks.compress.compress_video", _mock_compress)

        # First call — compresses
        cfg.analyze.skip_existing = False
        records1 = run_compress_all(cfg)
        assert len(records1) == 1
        assert call_count == 1

        # Second call — should skip since output exists
        cfg.analyze.skip_existing = True
        monkeypatch.setattr("vlog_tool.tasks.compress._next_index", lambda *a: 1)
        records2 = run_compress_all(cfg)
        assert len(records2) == 1
        assert call_count == 1  # still 1 — no new compress calls

    def test_single_file_param(self, monkeypatch, tmp_path: Path):
        cfg = _cfg(tmp_path)
        src = cfg.paths.input_dir / "custom.mp4"
        src.write_bytes(b"\x00" * 1000)

        monkeypatch.setattr("vlog_tool.tasks.compress.resolve_binary", lambda *a: "ffmpeg")

        def _mock_compress(inp, outp, c):
            outp.write_bytes(b"\x00" * 300)
            return outp

        monkeypatch.setattr("vlog_tool.tasks.compress.compress_video", _mock_compress)

        records = run_compress_all(cfg, single_file=src)
        assert len(records) == 1
        assert records[0].stem == "001_custom"
