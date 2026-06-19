from __future__ import annotations

import json
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from vlog_tool.config import AppConfig


@pytest.fixture
def cfg(tmp_path) -> AppConfig:
    plans = tmp_path / "plans"
    texts = tmp_path / "texts"
    compressed = tmp_path / "compressed"
    videos = tmp_path / "videos"
    for d in [plans, texts, compressed, videos]:
        d.mkdir()
    analyze = MagicMock(skip_existing=True, texts_subdir="texts", compressed_subdir="compressed")
    script = MagicMock(scripts_subdir="scripts")
    plan = MagicMock(plans_subdir="plans")
    return AppConfig(
        paths=MagicMock(
            input_dir=videos,
            output_dir=tmp_path,
            ffmpeg="ffmpeg",
            ffprobe="ffprobe",
        ),
        analyze=analyze,
        naming=MagicMock(index_width=3),
        script=script,
        plan=plan,
    )


def _write_plan(cfg: AppConfig, day_label: str = "day1", seq: list | None = None):
    if seq is None:
        seq = [
            {"index": "001", "title": "Intro", "use_timeline": "00:00-00:30"},
            {"index": "002", "title": "Main", "use_timeline": "01:00-02:00"},
        ]
    plan = {"day_title": "Day 1", "theme": "Paris", "total_estimated_sec": 120, "sequence": seq}
    plan_path = cfg.plans_dir / f"{day_label}_plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")


class TestComputeSegmentOffset:
    def test_no_seg_suffix_returns_zero(self, cfg):
        from vlog_tool.tasks.cut import _compute_segment_offset

        result = _compute_segment_offset("001_src", cfg.compressed_dir, Path("/dummy.mp4"), "ffprobe")
        assert result == 0.0

    def test_only_one_segment_returns_zero(self, cfg):
        (cfg.compressed_dir / "001_src_seg1.mp4").write_bytes(b"\x00")
        from vlog_tool.tasks.cut import _compute_segment_offset

        result = _compute_segment_offset("001_src_seg1", cfg.compressed_dir, Path("/dummy.mp4"), "ffprobe")
        assert result == 0.0

    def test_computes_offset_for_seg2(self, cfg):
        for s in ["001_src_seg1.mp4", "001_src_seg2.mp4"]:
            (cfg.compressed_dir / s).write_bytes(b"\x00")
        with patch("vlog_tool.tasks.cut.get_duration_sec", return_value=120.0):
            from vlog_tool.tasks.cut import _compute_segment_offset

            result = _compute_segment_offset("001_src_seg2", cfg.compressed_dir, Path("/dummy.mp4"), "ffprobe")
            assert result == 60.0


class TestRunCutAll:
    def test_plan_not_found(self, cfg):
        from vlog_tool.tasks.cut import run_cut_all

        with pytest.raises(FileNotFoundError, match="规划文件不存在"):
            run_cut_all(cfg, "day1")

    def test_empty_sequence(self, cfg):
        _write_plan(cfg, seq=[])
        from vlog_tool.tasks.cut import run_cut_all

        result = run_cut_all(cfg, "day1")
        assert result == []

    @patch("vlog_tool.tasks.cut.resolve_binary")
    def test_skips_segment_without_timeline(self, mock_resolve, cfg):
        _write_plan(cfg, seq=[{"index": "001", "title": "Intro", "use_timeline": ""}])
        mock_resolve.return_value = "ffmpeg"
        from vlog_tool.tasks.cut import run_cut_all

        result = run_cut_all(cfg, "day1")
        assert result == []

    @patch("vlog_tool.tasks.cut.resolve_binary")
    def test_skips_segment_without_index(self, mock_resolve, cfg):
        _write_plan(cfg, seq=[{"title": "Intro", "use_timeline": "00:00-00:30"}])
        mock_resolve.return_value = "ffmpeg"
        from vlog_tool.tasks.cut import run_cut_all

        result = run_cut_all(cfg, "day1")
        assert result == []

    @patch("vlog_tool.tasks.cut.cut_one")
    @patch("vlog_tool.tasks.cut.resolve_binary")
    def test_cuts_compressed_source(self, mock_resolve, mock_cut, cfg):
        _write_plan(cfg)
        (cfg.compressed_dir / "001_src.mp4").write_bytes(b"\x00")
        (cfg.compressed_dir / "002_src.mp4").write_bytes(b"\x00")
        mock_resolve.return_value = "ffmpeg"

        from vlog_tool.tasks.cut import run_cut_all

        result = run_cut_all(cfg, "day1")
        assert len(result) == 2
        assert result[0]["video_index"] == "001"
        assert mock_cut.call_count == 2

    @patch("vlog_tool.tasks.cut.cut_one")
    @patch("vlog_tool.tasks.cut.resolve_binary")
    def test_skips_missing_video(self, mock_resolve, mock_cut, cfg):
        _write_plan(cfg)
        mock_resolve.return_value = "ffmpeg"

        from vlog_tool.tasks.cut import run_cut_all

        result = run_cut_all(cfg, "day1")
        assert result == []
        mock_cut.assert_not_called()

    @patch("vlog_tool.tasks.cut.cut_one")
    @patch("vlog_tool.tasks.cut.resolve_binary")
    def test_skips_invalid_timeline(self, mock_resolve, mock_cut, cfg):
        _write_plan(cfg, seq=[{"index": "001", "title": "X", "use_timeline": "invalid"}])
        (cfg.compressed_dir / "001_src.mp4").write_bytes(b"\x00")
        mock_resolve.return_value = "ffmpeg"

        from vlog_tool.tasks.cut import run_cut_all

        result = run_cut_all(cfg, "day1")
        assert result == []
        mock_cut.assert_not_called()

    @patch("vlog_tool.tasks.cut.cut_one")
    @patch("vlog_tool.tasks.cut.resolve_binary")
    def test_cancel_event_stops_processing(self, mock_resolve, mock_cut, cfg):
        _write_plan(
            cfg,
            seq=[
                {"index": "001", "title": "A", "use_timeline": "00:00-00:10"},
                {"index": "002", "title": "B", "use_timeline": "00:00-00:10"},
            ],
        )
        (cfg.compressed_dir / "001_src.mp4").write_bytes(b"\x00")
        (cfg.compressed_dir / "002_src.mp4").write_bytes(b"\x00")
        mock_resolve.return_value = "ffmpeg"
        cancel = threading.Event()

        def _cancel_after_first(*_, **__):
            cancel.set()

        mock_cut.side_effect = _cancel_after_first

        from vlog_tool.tasks.cut import run_cut_all

        result = run_cut_all(cfg, "day1", cancel_event=cancel)
        assert len(result) == 1

    @patch("vlog_tool.tasks.cut.cut_one")
    @patch("vlog_tool.tasks.cut.resolve_binary")
    def test_creates_manifest(self, mock_resolve, mock_cut, cfg):
        _write_plan(cfg)
        (cfg.compressed_dir / "001_src.mp4").write_bytes(b"\x00")
        (cfg.compressed_dir / "002_src.mp4").write_bytes(b"\x00")
        mock_resolve.return_value = "ffmpeg"

        from vlog_tool.tasks.cut import run_cut_all

        out_dir = cfg.paths.output_dir / "cuts" / "day1"
        run_cut_all(cfg, "day1")
        manifest = out_dir / "manifest.md"
        assert manifest.exists()
        content = manifest.read_text(encoding="utf-8")
        assert "Day 1" in content
        assert "Paris" in content

    @patch("vlog_tool.tasks.cut.cut_one")
    @patch("vlog_tool.tasks.cut.resolve_binary")
    def test_copies_text_json(self, mock_resolve, mock_cut, cfg):
        _write_plan(cfg)
        (cfg.compressed_dir / "001_src.mp4").write_bytes(b"\x00")
        (cfg.compressed_dir / "002_src.mp4").write_bytes(b"\x00")
        (cfg.texts_dir / "001_test.json").write_text('{"title": "Intro clip"}')
        mock_resolve.return_value = "ffmpeg"

        from vlog_tool.tasks.cut import run_cut_all

        result = run_cut_all(cfg, "day1")
        assert result[0]["text_file"] != ""
        clip_texts = cfg.paths.output_dir / "cuts" / "day1" / result[0]["text_file"]
        assert clip_texts.exists()
        data = json.loads(clip_texts.read_text(encoding="utf-8"))
        assert "_cut_info" in data
        assert data["title"] == "Intro clip"

    @patch("vlog_tool.tasks.cut.cut_one")
    @patch("vlog_tool.tasks.cut.resolve_binary")
    def test_original_source_applies_offset(self, mock_resolve, mock_cut, cfg):
        seq = [{"index": "001", "title": "A", "use_timeline": "00:00-00:10"}]
        _write_plan(cfg, seq=seq)
        (cfg.compressed_dir / "001_src_seg1.mp4").write_bytes(b"\x00")
        (cfg.compressed_dir / "001_src_seg2.mp4").write_bytes(b"\x00")
        (cfg.paths.input_dir / "src.mp4").write_bytes(b"\x00")
        mock_resolve.return_value = "ffmpeg"
        with patch("vlog_tool.tasks.cut.get_duration_sec", return_value=120.0):
            from vlog_tool.tasks.cut import run_cut_all

            result = run_cut_all(cfg, "day1", source="original")
            assert len(result) == 1
