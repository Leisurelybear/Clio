"""Tests for vlog_tool/ui/routes/transcripts.py and whisper_routes.py."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from vlog_tool.ui.routes.transcripts import handle_get_transcripts, handle_put_transcripts
from vlog_tool.ui.routes.whisper_routes import handle_get_whisper_check


class TestHandleGetTranscripts:
    def test_no_video_param(self):
        handler = MagicMock()
        handler._send_json = MagicMock()
        handle_get_transcripts(handler, {})
        handler._send_json.assert_called_once_with({"ok": False, "error": "missing video param"}, 400)

    def test_present(self, tmp_path: Path):
        handler = MagicMock()
        handler.config_path = str(tmp_path / "config.yaml")
        handler._get_project_output.return_value = tmp_path
        (tmp_path / "transcripts").mkdir()
        transcript = {
            "source_stem": "GL010683",
            "segments": [{"start": 0.0, "end": 2.0, "text": "hello"}],
        }
        (tmp_path / "transcripts" / "GL010683_transcript.json").write_text(json.dumps(transcript), encoding="utf-8")

        with patch("vlog_tool.ui.routes.transcripts.load_config") as mock_lc:
            mock_cfg = MagicMock()
            mock_cfg.whisper.transcripts_subdir = "transcripts"
            mock_lc.return_value = mock_cfg

            handler._send_json = MagicMock()
            handle_get_transcripts(handler, {"video": ["001_GL010683.mp4"]})
            handler._send_json.assert_called_once()
            args = handler._send_json.call_args
            assert args[0][0]["ok"] is True
            assert args[0][0]["source_stem"] == "GL010683"

    def test_not_found(self, tmp_path: Path):
        handler = MagicMock()
        handler.config_path = str(tmp_path / "config.yaml")
        handler._get_project_output.return_value = tmp_path
        (tmp_path / "transcripts").mkdir()

        with patch("vlog_tool.ui.routes.transcripts.load_config") as mock_lc:
            mock_cfg = MagicMock()
            mock_cfg.whisper.transcripts_subdir = "transcripts"
            mock_lc.return_value = mock_cfg

            handler._send_json = MagicMock()
            handle_get_transcripts(handler, {"video": ["nonexistent.mp4"]})
            handler._send_json.assert_called_once_with({"ok": False}, 404)


class TestHandlePutTranscripts:
    def test_update_segment(self, tmp_path: Path):
        handler = MagicMock()
        handler.config_path = str(tmp_path / "config.yaml")
        handler._get_project_output.return_value = tmp_path
        (tmp_path / "transcripts").mkdir()
        transcript = {
            "source_stem": "GL010683",
            "segments": [{"start": 0.0, "end": 2.0, "text": "old text"}],
        }
        tf = tmp_path / "transcripts" / "GL010683_transcript.json"
        tf.write_text(json.dumps(transcript), encoding="utf-8")

        with patch("vlog_tool.ui.routes.transcripts.load_config") as mock_lc:
            mock_cfg = MagicMock()
            mock_cfg.whisper.transcripts_subdir = "transcripts"
            mock_lc.return_value = mock_cfg

            handler._send_json = MagicMock()
            handle_put_transcripts(
                handler,
                {"video": ["001_GL010683.mp4"]},
                {
                    "segment_index": 0,
                    "text": "new text",
                },
            )
            handler._send_json.assert_called_once_with({"ok": True})
            updated = json.loads(tf.read_text(encoding="utf-8"))
            assert updated["segments"][0]["text"] == "new text"

    def test_invalid_index(self, tmp_path: Path):
        handler = MagicMock()
        handler._send_json = MagicMock()
        handle_put_transcripts(
            handler,
            {"video": ["001_GL010683.mp4"]},
            {
                "segment_index": "not_an_int",
                "text": "new text",
            },
        )
        handler._send_json.assert_called_once()
        args = handler._send_json.call_args
        assert args[0][0]["ok"] is False


class TestHandleGetWhisperCheck:
    def test_okay(self):
        handler = MagicMock()
        handler._send_json = MagicMock()

        with (
            patch("vlog_tool.ui.routes.whisper_routes.check_whisper", return_value=True),
            patch("ctranslate2.get_cuda_device_count", return_value=1),
        ):
            handle_get_whisper_check(handler)
            handler._send_json.assert_called_once()
            args = handler._send_json.call_args
            assert args[0][0]["installed"] is True
            assert args[0][0]["cuda"] is True

    def test_not_installed(self):
        handler = MagicMock()
        handler._send_json = MagicMock()

        with patch("vlog_tool.ui.routes.whisper_routes.check_whisper", return_value=False):
            handle_get_whisper_check(handler)
            args = handler._send_json.call_args
            assert args[0][0]["installed"] is False
