"""Tests for clio/ui/routes/videos.py — _parse_segment_info + handler mocks."""

from __future__ import annotations

from http import HTTPStatus
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from clio.ui.routes.videos import _VIDEOS_CACHE, _parse_segment_info, handle_get_video, handle_get_videos


def _clear_videos_cache() -> None:
    _VIDEOS_CACHE.clear()


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
    def setup_method(self):
        _clear_videos_cache()

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
        import json

        handler = MagicMock()
        proj_input = tmp_path / "input"
        proj_input.mkdir()
        original = proj_input / "GL010695.MP4"
        original.write_bytes(b"")
        (proj_input / "videos.json").write_text(json.dumps([str(original.resolve())]), encoding="utf-8")
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

    def test_source_original_uses_videos_json_for_nested(self, tmp_path: Path):
        import json

        handler = MagicMock()
        proj_input = tmp_path / "input"
        nested = proj_input / "day1"
        nested.mkdir(parents=True)
        original = nested / "GL010695.MP4"
        original.write_bytes(b"")
        (proj_input / "videos.json").write_text(json.dumps([str(original.resolve())]), encoding="utf-8")
        proj_out = tmp_path / "output"
        proj_out.mkdir()
        (proj_out / "compressed").mkdir()

        handler._resolve_project_input.return_value = proj_input
        handler._get_project_output.return_value = proj_out
        handler._get_config.return_value = SimpleNamespace(
            paths=SimpleNamespace(ffprobe=""),
            whisper=SimpleNamespace(transcripts_subdir="transcripts"),
        )
        handler._send_json = MagicMock()

        handle_get_videos(handler, {"source": ["original"]})

        payload = handler._send_json.call_args[0][0]
        assert len(payload["videos"]) == 1
        assert payload["videos"][0]["file"] in {"day1/GL010695.MP4", "GL010695.MP4"}
        assert payload["videos"][0]["match"] is None

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

    def test_repeated_request_uses_cache(self, tmp_path: Path):
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

        with patch(
            "clio.ui.routes.videos._build_videos_payload",
            wraps=__import__("clio.ui.routes.videos", fromlist=["_build_videos_payload"])._build_videos_payload,
        ) as mock_build:
            handle_get_videos(handler, {"source": ["compressed"]})
            handle_get_videos(handler, {"source": ["compressed"]})

        assert mock_build.call_count == 1
        assert handler._send_json.call_count == 2

    def test_selected_set_includes_video_with_vmeta(self, tmp_path: Path):
        """Compressed view + selected_set: include video whose .vmeta.source_path
        matches a path in videos.json (original outside proj_input)."""
        handler = MagicMock()
        proj_input = tmp_path / "input"
        proj_input.mkdir()
        proj_out = tmp_path / "output"
        proj_out.mkdir()
        comp_dir = proj_out / "compressed"
        comp_dir.mkdir()

        # Original video at a path OUTSIDE proj_input (simulates videos.json)
        orig_root = tmp_path / "external"
        orig_root.mkdir()
        orig_video = orig_root / "GL010695.MP4"
        orig_video.write_bytes(b"original data")

        # Create compressed video + .vmeta pointing to the external original
        compressed = comp_dir / "001_GL010695.mp4"
        compressed.write_bytes(b"compressed data")
        from clio.vmeta import VideoMeta

        meta = VideoMeta.build(
            source=orig_video,
            target=compressed,
            source_duration=10.0,
            target_duration=5.0,
        )
        meta.write(compressed)

        # videos.json with the external path
        import json

        (proj_input / "videos.json").write_text(json.dumps([str(orig_video.resolve())]))

        handler._resolve_project_input.return_value = proj_input
        handler._get_project_output.return_value = proj_out
        handler._get_config.return_value = SimpleNamespace(
            paths=SimpleNamespace(ffprobe=""),
            whisper=SimpleNamespace(transcripts_subdir="transcripts"),
        )
        handler._send_json = MagicMock()

        handle_get_videos(handler, {"source": ["compressed"]})

        handler._send_json.assert_called_once()
        payload = handler._send_json.call_args[0][0]
        assert payload["source"] == "compressed"
        assert len(payload["videos"]) == 1
        assert payload["videos"][0]["file"] == "001_GL010695.mp4"

    def test_selected_set_excludes_unmatched_video(self, tmp_path: Path):
        """Compressed view + selected_set: exclude video whose .vmeta.source_path
        is NOT in selected_set."""
        handler = MagicMock()
        proj_input = tmp_path / "input"
        proj_input.mkdir()
        proj_out = tmp_path / "output"
        proj_out.mkdir()
        comp_dir = proj_out / "compressed"
        comp_dir.mkdir()

        # External original — this one IS selected
        orig_root = tmp_path / "external"
        orig_root.mkdir()
        selected_orig = orig_root / "GL010695.MP4"
        selected_orig.write_bytes(b"original data")

        # Another external original — this one is NOT selected
        non_selected_orig = orig_root / "GX010456.MP4"
        non_selected_orig.write_bytes(b"other original")

        # Compressed video with vmeta pointing to NON-selected original
        compressed = comp_dir / "001_GX010456.mp4"
        compressed.write_bytes(b"compressed data")
        from clio.vmeta import VideoMeta

        meta = VideoMeta.build(
            source=non_selected_orig,
            target=compressed,
            source_duration=10.0,
            target_duration=5.0,
        )
        meta.write(compressed)

        # videos.json only contains selected_orig
        import json

        (proj_input / "videos.json").write_text(json.dumps([str(selected_orig.resolve())]))

        handler._resolve_project_input.return_value = proj_input
        handler._get_project_output.return_value = proj_out
        handler._get_config.return_value = SimpleNamespace(
            paths=SimpleNamespace(ffprobe=""),
            whisper=SimpleNamespace(transcripts_subdir="transcripts"),
        )
        handler._send_json = MagicMock()

        handle_get_videos(handler, {"source": ["compressed"]})

        handler._send_json.assert_called_once()
        payload = handler._send_json.call_args[0][0]
        assert len(payload["videos"]) == 0

    def test_sidecar_change_invalidates_cache(self, tmp_path: Path):
        handler = MagicMock()
        proj_input = tmp_path / "input"
        proj_input.mkdir()
        proj_out = tmp_path / "output"
        proj_out.mkdir()
        comp_dir = proj_out / "compressed"
        comp_dir.mkdir()
        texts_dir = proj_out / "texts"
        texts_dir.mkdir()
        (comp_dir / "001_GL010695.mp4").write_bytes(b"")

        handler._resolve_project_input.return_value = proj_input
        handler._get_project_output.return_value = proj_out
        handler._send_json = MagicMock()

        import clio.ui.routes.videos as videos_route

        with patch(
            "clio.ui.routes.videos._build_videos_payload", wraps=videos_route._build_videos_payload
        ) as mock_build:
            handle_get_videos(handler, {"source": ["compressed"]})
            (texts_dir / "001_GL010695.json").write_text('{"title":"新标题","index":"001"}', encoding="utf-8")
            handle_get_videos(handler, {"source": ["compressed"]})

        assert mock_build.call_count == 2
        payload = handler._send_json.call_args[0][0]
        assert payload["videos"][0]["title"] == "新标题"


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

    def test_sends_nested_original_video(self, tmp_path: Path):
        handler = MagicMock()
        proj_input = tmp_path / "input"
        nested = proj_input / "day1"
        nested.mkdir(parents=True)
        video = nested / "clip.mp4"
        video.write_bytes(b"video data")
        proj_out = tmp_path / "output"
        proj_out.mkdir()
        handler._resolve_project_input.return_value = proj_input
        handler._get_project_output.return_value = proj_out
        handler._send_video_range = MagicMock()

        handle_get_video(handler, {"file": ["day1/clip.mp4"], "source": ["original"]})

        handler._send_video_range.assert_called_once_with(video)

    def test_forbidden_basename(self, tmp_path: Path):
        handler = MagicMock()
        handler.send_error = MagicMock()

        handle_get_video(handler, {"file": ["../secret.txt"], "source": ["compressed"]})

        handler.send_error.assert_called_once()

    def test_forbidden_original_relative_traversal(self, tmp_path: Path):
        handler = MagicMock()
        proj_input = tmp_path / "input"
        proj_input.mkdir()
        proj_out = tmp_path / "output"
        proj_out.mkdir()
        handler._resolve_project_input.return_value = proj_input
        handler._get_project_output.return_value = proj_out
        handler.send_error = MagicMock()

        handle_get_video(handler, {"file": ["../secret.mp4"], "source": ["original"]})

        handler.send_error.assert_called_once_with(HTTPStatus.FORBIDDEN)

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

    def test_abspath_not_in_selected_set_returns_forbidden(self, tmp_path: Path):
        handler = MagicMock()
        proj_input = tmp_path / "input"
        proj_input.mkdir()
        proj_out = tmp_path / "output"
        proj_out.mkdir()
        handler._resolve_project_input.return_value = proj_input
        handler._get_project_output.return_value = proj_out
        handler.send_error = MagicMock()

        video = tmp_path / "secret.mp4"
        video.write_bytes(b"secret")
        handle_get_video(handler, {"file": [""], "source": ["original"], "abspath": [str(video)]})
        handler.send_error.assert_called_once_with(HTTPStatus.FORBIDDEN)

    def test_abspath_in_selected_set_sends_video(self, tmp_path: Path):
        import json

        handler = MagicMock()
        proj_input = tmp_path / "input"
        proj_input.mkdir()
        proj_out = tmp_path / "output"
        proj_out.mkdir()
        handler._resolve_project_input.return_value = proj_input
        handler._get_project_output.return_value = proj_out
        handler._send_video_range = MagicMock()

        video = tmp_path / "external" / "GL010695.MP4"
        video.parent.mkdir()
        video.write_bytes(b"video data")
        (proj_input / "videos.json").write_text(json.dumps([str(video.resolve())]), encoding="utf-8")

        handle_get_video(handler, {"file": ["GL010695.MP4"], "source": ["original"], "abspath": [str(video)]})
        handler._send_video_range.assert_called_once_with(video)

    def test_abspath_nonexistent_returns_not_found(self, tmp_path: Path):
        handler = MagicMock()
        proj_input = tmp_path / "input"
        proj_input.mkdir()
        proj_out = tmp_path / "output"
        proj_out.mkdir()
        handler._resolve_project_input.return_value = proj_input
        handler._get_project_output.return_value = proj_out
        handler.send_error = MagicMock()

        handle_get_video(handler, {"file": [""], "source": ["original"], "abspath": [str(tmp_path / "missing.mp4")]})
        handler.send_error.assert_called_once_with(HTTPStatus.NOT_FOUND)
