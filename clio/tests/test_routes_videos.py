"""Tests for clio/ui/routes/videos.py — _parse_segment_info + handler mocks."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from clio.ui.routes.videos import _parse_segment_info, handle_get_video, handle_get_videos


class TestParseSegmentInfo:
    def test_no_underscore(self):
        assert _parse_segment_info("NOUNDERSCORE") == (None, None)

    def test_no_seg_suffix(self):
        """Plain compressed file with no _segNN suffix."""
        assert _parse_segment_info("001_GL010683") == (None, None)

    def test_basic_segment(self):
        gk, sn = _parse_segment_info("001_GL010683_seg01")
        assert gk == "GL010683"
        assert sn == 1

    def test_multi_digit_segment(self):
        gk, sn = _parse_segment_info("001_GL010683_seg12")
        assert gk == "GL010683"
        assert sn == 12

    def test_stem_before_underscore_matches(self):
        gk, sn = _parse_segment_info("002_GX010456_seg07")
        assert gk == "GX010456"
        assert sn == 7

    def test_seg_prefix_not_false_match(self):
        """_seg without digits should not match."""
        assert _parse_segment_info("001_GL010683_segment") == (None, None)

    def test_seg_with_trailing_text(self):
        """_seg01a should not match (non-digit after seg)."""
        assert _parse_segment_info("001_GL010683_seg01a") == (None, None)

    def test_only_seg_prefix(self):
        assert _parse_segment_info("_seg01") == (None, None)  # no underscore prefix → stem split gives "_seg01"

    def test_part_pattern(self):
        gk, sn = _parse_segment_info("001_GX010456_part07")
        assert gk == "GX010456"
        assert sn == 7

    def test_pt_pattern(self):
        gk, sn = _parse_segment_info("001_GX010456_pt03")
        assert gk == "GX010456"
        assert sn == 3

    def test_chunk_pattern_case_insensitive(self):
        gk, sn = _parse_segment_info("001_GX010456_Chunk02")
        assert gk == "GX010456"
        assert sn == 2

    def test_seg_pattern_uppercase(self):
        gk, sn = _parse_segment_info("001_GX010456_SEG05")
        assert gk == "GX010456"
        assert sn == 5

    def test_empty_string(self):
        assert _parse_segment_info("") == (None, None)


class TestHandleGetVideos:
    def test_source_compressed(self, tmp_path: Path):
        handler = MagicMock()
        proj_input = tmp_path / "input"
        proj_input.mkdir()
        proj_out = tmp_path / "output"
        proj_out.mkdir()
        comp_dir = proj_out / "compressed"
        comp_dir.mkdir()
        (comp_dir / "001_GL010695.mp4").write_bytes(b"")

        handler._resolve_project_input.return_value = proj_input
        handler._get_project_output.return_value = proj_out
        handler._send_json = MagicMock()

        handle_get_videos(handler, {"source": ["compressed"]})

        handler._send_json.assert_called_once()
        args = handler._send_json.call_args
        payload = args[0][0]
        assert payload["source"] == "compressed"
        assert len(payload["videos"]) == 1
        assert payload["videos"][0]["file"] == "001_GL010695.mp4"
        assert payload["videos"][0]["index"] == "001"

    def test_source_original(self, tmp_path: Path):
        handler = MagicMock()
        proj_input = tmp_path / "input"
        proj_input.mkdir()
        (proj_input / "GL010695.MP4").write_bytes(b"")
        proj_out = tmp_path / "output"
        proj_out.mkdir()
        comp_dir = proj_out / "compressed"
        comp_dir.mkdir()
        (comp_dir / "001_GL010695.mp4").write_bytes(b"")

        handler._resolve_project_input.return_value = proj_input
        handler._get_project_output.return_value = proj_out
        handler._send_json = MagicMock()

        handle_get_videos(handler, {"source": ["original"]})

        handler._send_json.assert_called_once()
        args = handler._send_json.call_args
        payload = args[0][0]
        assert payload["source"] == "original"
        assert len(payload["videos"]) == 1
        assert payload["videos"][0]["match"]["file"] == "001_GL010695.mp4"

    def test_invalid_source(self, tmp_path: Path):
        handler = MagicMock()
        handler._send_json = MagicMock()

        handle_get_videos(handler, {"source": ["invalid"]})

        handler._send_json.assert_called_once_with({"ok": False, "error": "source must be compressed|original"}, 400)

    def test_groups_populated_for_segments(self, tmp_path: Path):
        handler = MagicMock()
        proj_input = tmp_path / "input"
        proj_input.mkdir()
        (proj_input / "GL010695.MP4").write_bytes(b"")
        proj_out = tmp_path / "output"
        proj_out.mkdir()
        comp_dir = proj_out / "compressed"
        comp_dir.mkdir()
        (comp_dir / "001_GL010695_seg01.mp4").write_bytes(b"")
        (comp_dir / "002_GL010695_seg02.mp4").write_bytes(b"")

        handler._resolve_project_input.return_value = proj_input
        handler._get_project_output.return_value = proj_out
        handler._send_json = MagicMock()

        handle_get_videos(handler, {"source": ["compressed"]})

        handler._send_json.assert_called_once()
        args = handler._send_json.call_args
        payload = args[0][0]
        assert "GL010695" in payload["groups"]
        group = payload["groups"]["GL010695"]
        assert group["total"] == 2
        vid0 = payload["videos"][0]
        vid1 = payload["videos"][1]
        assert vid0["group_key"] == "GL010695"
        assert vid0["segment_label"] == "1/2"
        assert vid1["segment_label"] == "2/2"


class TestHandleGetVideo:
    def test_sends_video(self, tmp_path: Path):
        handler = MagicMock()
        proj_input = tmp_path / "input"
        proj_input.mkdir()
        proj_out = tmp_path / "output"
        proj_out.mkdir()
        comp_dir = proj_out / "compressed"
        comp_dir.mkdir()
        (comp_dir / "001_test.mp4").write_bytes(b"video data")
        handler._resolve_project_input.return_value = proj_input
        handler._get_project_output.return_value = proj_out
        handler._send_video_range = MagicMock()

        handle_get_video(handler, {"file": ["001_test.mp4"], "source": ["compressed"]})

        handler._send_video_range.assert_called_once()

    def test_forbidden_basename(self, tmp_path: Path):
        handler = MagicMock()
        handler.send_error = MagicMock()

        handle_get_video(handler, {"file": ["../secret.txt"], "source": ["compressed"]})

        handler.send_error.assert_called_once()

    def test_not_found(self, tmp_path: Path):
        handler = MagicMock()
        proj_input = tmp_path / "input"
        proj_input.mkdir()
        proj_out = tmp_path / "output"
        proj_out.mkdir()
        (proj_out / "compressed").mkdir()
        handler._resolve_project_input.return_value = proj_input
        handler._get_project_output.return_value = proj_out
        handler.send_error = MagicMock()

        handle_get_video(handler, {"file": ["nonexistent.mp4"], "source": ["compressed"]})

        handler.send_error.assert_called_once()
