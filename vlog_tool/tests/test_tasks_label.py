from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from vlog_tool.config import AppConfig


@pytest.fixture
def cfg(tmp_path) -> AppConfig:
    texts = tmp_path / "texts"
    compressed = tmp_path / "compressed"
    texts.mkdir()
    compressed.mkdir()
    analyze = MagicMock(skip_existing=True, texts_subdir="texts", compressed_subdir="compressed")
    script = MagicMock(scripts_subdir="scripts")
    plan = MagicMock(plans_subdir="plans")
    return AppConfig(
        paths=MagicMock(
            input_dir=tmp_path / "videos",
            output_dir=tmp_path,
            ffmpeg="ffmpeg_path",
            ffprobe="",
        ),
        analyze=analyze,
        naming=MagicMock(index_width=3),
        script=script,
        plan=plan,
    )


class TestRunLabelVideos:
    @patch("vlog_tool.tasks.label.run_ffmpeg")
    @patch("vlog_tool.tasks.label.resolve_binary")
    def test_skips_if_no_compressed_file(self, mock_resolve, mock_ffmpeg, cfg):
        (cfg.texts_dir / "001_test.json").write_text('{"index": 1}')
        mock_resolve.return_value = "ffmpeg"

        from vlog_tool.tasks.label import run_label_videos

        run_label_videos(cfg)
        mock_ffmpeg.assert_not_called()

    @patch("vlog_tool.tasks.label.run_ffmpeg")
    @patch("vlog_tool.tasks.label.resolve_binary")
    def test_labels_video(self, mock_resolve, mock_ffmpeg, cfg):
        (cfg.texts_dir / "001_test.json").write_text('{"index": 1}')
        compressed = cfg.compressed_dir / "001_original.mp4"
        compressed.write_bytes(b"\x00")
        mock_resolve.return_value = "ffmpeg"

        from vlog_tool.tasks.label import run_label_videos

        run_label_videos(cfg)
        labeled_dir = cfg.paths.output_dir / "labeled"
        out = labeled_dir / "001_test_labeled.mp4"
        assert out.name == "001_test_labeled.mp4"
        mock_ffmpeg.assert_called_once()

    @patch("vlog_tool.tasks.label.run_ffmpeg")
    @patch("vlog_tool.tasks.label.resolve_binary")
    def test_skip_existing(self, mock_resolve, mock_ffmpeg, cfg):
        (cfg.texts_dir / "001.json").write_text('{"index": 1}')
        compressed = cfg.compressed_dir / "001_original.mp4"
        compressed.write_bytes(b"\x00")
        labeled_dir = cfg.paths.output_dir / "labeled"
        labeled_dir.mkdir()
        out = labeled_dir / "001_labeled.mp4"
        out.write_bytes(b"\x00")
        mock_resolve.return_value = "ffmpeg"

        from vlog_tool.tasks.label import run_label_videos

        run_label_videos(cfg)
        mock_ffmpeg.assert_not_called()

    @patch("vlog_tool.tasks.label.run_ffmpeg")
    @patch("vlog_tool.tasks.label.resolve_binary")
    def test_uses_index_from_data(self, mock_resolve, mock_ffmpeg, cfg):
        (cfg.texts_dir / "001_test.json").write_text('{"index": 42}')
        compressed = cfg.compressed_dir / "042_src.mp4"
        compressed.write_bytes(b"\x00")
        mock_resolve.return_value = "ffmpeg"

        from vlog_tool.tasks.label import run_label_videos

        run_label_videos(cfg)
        labeled_dir = cfg.paths.output_dir / "labeled"
        out = labeled_dir / "001_test_labeled.mp4"
        assert out.name == "001_test_labeled.mp4"
        args = mock_ffmpeg.call_args.args[0]
        assert any("042_src.mp4" in str(a) for a in args)

    @patch("vlog_tool.tasks.label.run_ffmpeg")
    @patch("vlog_tool.tasks.label.resolve_binary")
    def test_passes_drawtext_filter(self, mock_resolve, mock_ffmpeg, cfg):
        (cfg.texts_dir / "001_test.json").write_text('{"index": 1}')
        compressed = cfg.compressed_dir / "001_src.mp4"
        compressed.write_bytes(b"\x00")
        mock_resolve.return_value = "ffmpeg"

        from vlog_tool.tasks.label import run_label_videos

        run_label_videos(cfg)
        args = mock_ffmpeg.call_args.args[0]
        vf_idx = args.index("-vf") + 1 if "-vf" in args else -1
        assert vf_idx > 0
        assert "drawtext" in args[vf_idx]
        assert "001" in args[vf_idx]

    @patch("vlog_tool.tasks.label.run_ffmpeg")
    @patch("vlog_tool.tasks.label.resolve_binary")
    def test_tracker_next_called(self, mock_resolve, mock_ffmpeg, cfg):
        (cfg.texts_dir / "001.json").write_text('{"index": 1}')
        compressed = cfg.compressed_dir / "001_src.mp4"
        compressed.write_bytes(b"\x00")
        mock_resolve.return_value = "ffmpeg"
        tracker = MagicMock()

        from vlog_tool.tasks.label import run_label_videos

        run_label_videos(cfg, tracker=tracker)
        tracker.update.assert_called_once()
        tracker.next.assert_called_once()
        tracker.log.assert_called_once()
