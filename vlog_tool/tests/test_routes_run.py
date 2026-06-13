"""Tests for vlog_tool/ui/routes/run.py — run status/start/rerun handlers."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from vlog_tool.ui.routes.run import handle_get_run_status, handle_post_rerun, handle_post_run_start


@pytest.fixture
def _no_thread(monkeypatch):
    """Prevent background threads from actually starting — avoids copy.deepcopy leaks on CI."""
    monkeypatch.setattr(
        "vlog_tool.ui.routes.run.threading.Thread",
        lambda *a, **kw: MagicMock(start=lambda: None),
    )


class TestHandleGetRunStatus:
    def test_idle_when_no_progress_file(self):
        handler = MagicMock()
        handler._get_project_output.return_value = Path("/nonexistent")
        handler._run_thread = None
        handler._send_json = MagicMock()

        handle_get_run_status(handler, {})

        handler._send_json.assert_called_once_with({"status": "idle", "running": False})

    def test_reads_progress_file(self, tmp_path: Path):
        handler = MagicMock()
        proj_out = tmp_path / "output"
        proj_out.mkdir(parents=True)
        progress = proj_out / ".progress.json"
        progress.write_text(json.dumps({"status": "running", "phase": "compress"}), encoding="utf-8")
        handler._get_project_output.return_value = proj_out
        handler._run_thread = MagicMock()
        handler._run_thread.is_alive.return_value = True
        handler._send_json = MagicMock()

        handle_get_run_status(handler, {})

        handler._send_json.assert_called_once()
        payload = handler._send_json.call_args[0][0]
        assert payload["status"] == "running"
        assert payload["phase"] == "compress"
        assert payload["running"] is True


class TestHandlePostRunStart:
    def test_already_running(self):
        handler = MagicMock()
        handler._run_thread = MagicMock()
        handler._run_thread.is_alive.return_value = True
        handler._send_json = MagicMock()

        handle_post_run_start(handler, {}, {})

        handler._send_json.assert_called_once_with({"ok": False, "error": "pipeline is already running"}, 409)

    def test_starts_thread(self, tmp_path: Path, _no_thread):
        handler = MagicMock()
        handler._run_thread = None
        handler._resolve_project_input.return_value = tmp_path / "input"
        handler._get_config.return_value = MagicMock()
        handler._send_json = MagicMock()

        handle_post_run_start(handler, {}, {"steps": ["compress", "analyze"]})

        handler._send_json.assert_called_once()
        assert handler._send_json.call_args[0][0]["ok"] is True
        assert handler._run_thread is not None


class TestHandlePostRerun:
    def test_missing_params(self, tmp_path: Path):
        handler = MagicMock()
        handler.send_error = MagicMock()
        handler._resolve_project_input.return_value = tmp_path
        handler._send_json = MagicMock()

        handle_post_rerun(handler, {}, {})

        handler._send_json.assert_called_once()
        assert handler._send_json.call_args[0][1] == 400

    def test_invalid_task(self, tmp_path: Path):
        handler = MagicMock()
        handler._resolve_project_input.return_value = tmp_path
        handler._send_json = MagicMock()

        handle_post_rerun(handler, {}, {"video": "test.mp4", "task": "invalid"})

        handler._send_json.assert_called_once()
        assert handler._send_json.call_args[0][1] == 400

    def test_starts_rerun(self, tmp_path: Path, _no_thread):
        handler = MagicMock()
        handler._run_thread = None
        proj_input = tmp_path / "input"
        proj_input.mkdir()
        (proj_input / "GL010695.MP4").write_bytes(b"")
        handler._resolve_project_input.return_value = proj_input
        handler._send_json = MagicMock()

        handle_post_rerun(handler, {}, {"video": "001_GL010695.mp4", "task": "compress"})

        handler._send_json.assert_called_once()
        assert handler._send_json.call_args[0][0]["ok"] is True
        assert handler._run_thread is not None
