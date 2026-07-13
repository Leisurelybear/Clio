"""Tests for clio/ui/routes/run.py — run status/start/rerun handlers."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from clio.ui.routes.run import (
    _apply_run_input_dir_override,
    handle_get_run_status,
    handle_post_rerun,
    handle_post_run_cancel,
    handle_post_run_preview,
    handle_post_run_start,
)


@pytest.fixture
def _handler():
    """Create a mock handler with _get_state returning a per-project ServerState-like object."""
    from threading import Event, Lock

    class _FakeState:
        def __init__(self):
            self.run_lock = Lock()
            self.run_thread = None
            self.cancel_event = Event()

    handler = MagicMock()
    handler._get_state = lambda key: handler.__class__._fake_state
    handler.__class__._fake_state = _FakeState()
    return handler


@pytest.fixture
def _no_thread(monkeypatch):
    """Prevent background threads from actually starting — avoids copy.deepcopy leaks on CI."""
    monkeypatch.setattr(
        "clio.ui.routes.run.threading.Thread",
        lambda *a, **kw: MagicMock(start=lambda: None),
    )


class TestHandleGetRunStatus:
    def test_idle_when_no_progress_file(self, _handler):
        handler = _handler
        handler._resolve_project_dir.return_value = Path("/nonexistent")
        handler._get_project_output.return_value = Path("/nonexistent")

        handle_get_run_status(handler, {})

        handler._send_json.assert_called_once_with({"status": "idle", "running": False})

    def test_reads_progress_file(self, tmp_path: Path, _handler):
        handler = _handler
        proj_dir = tmp_path / "input"
        proj_out = tmp_path / "output"
        proj_out.mkdir(parents=True)
        progress = proj_out / ".progress.json"
        progress.write_text(json.dumps({"status": "running", "phase": "compress"}), encoding="utf-8")
        handler._resolve_project_dir.return_value = proj_dir
        handler._get_project_output.return_value = proj_out
        handler.__class__._fake_state.run_thread = MagicMock()
        handler.__class__._fake_state.run_thread.is_alive.return_value = True

        handle_get_run_status(handler, {})

        handler._send_json.assert_called_once()
        payload = handler._send_json.call_args[0][0]
        assert payload["status"] == "running"
        assert payload["phase"] == "compress"
        assert payload["running"] is True


class TestApplyRunInputDirOverride:
    def test_none_keeps_config(self, tmp_path: Path):
        cfg = SimpleNamespace(paths=SimpleNamespace(input_dir=tmp_path))

        result, error = _apply_run_input_dir_override(cfg, None)

        assert result is cfg
        assert error is None

    def test_valid_input_dir_returns_config_copy(self, tmp_path: Path):
        cfg = SimpleNamespace(paths=SimpleNamespace(input_dir=tmp_path / "old"))
        new_input = tmp_path / "new"
        new_input.mkdir()

        result, error = _apply_run_input_dir_override(cfg, str(new_input))
        assert getattr(result, "_project_dir", None) == new_input.resolve() or getattr(result, "project_dir", None) in (
            new_input,
            new_input.resolve(),
        )

        assert error is None
        assert result is not cfg
        assert result._project_dir == new_input
        assert not hasattr(cfg, "_project_dir") or cfg._project_dir != new_input

    def test_missing_input_dir_returns_error(self, tmp_path: Path):
        cfg = SimpleNamespace(paths=SimpleNamespace(input_dir=tmp_path))

        result, error = _apply_run_input_dir_override(cfg, str(tmp_path / "missing"))

        assert result is cfg
        assert "project_dir not found" in error or "input_dir not found" in error


class TestHandlePostRunStart:
    def test_already_running(self, _handler):
        handler = _handler
        handler._resolve_project_dir.return_value = Path("/input")
        handler.__class__._fake_state.run_thread = MagicMock()
        handler.__class__._fake_state.run_thread.is_alive.return_value = True

        handle_post_run_start(handler, {}, {})

        handler._send_json.assert_called_once_with({"ok": False, "error": "pipeline is already running"}, 409)

    def test_already_running_does_not_clobber_progress(self, tmp_path, _handler):
        """Duplicate run request must NOT overwrite existing progress file."""
        handler = _handler
        handler._resolve_project_dir.return_value = Path("/input")
        out_dir = tmp_path / "output"
        out_dir.mkdir()
        progress = out_dir / ".progress.json"
        original = {"status": "running", "phase": "analyze", "message": "still running"}
        progress.write_text(json.dumps(original, ensure_ascii=False), encoding="utf-8")
        cfg = MagicMock()
        cfg.paths.output_dir = out_dir
        handler._get_config.return_value = cfg
        handler.__class__._fake_state.run_thread = MagicMock()
        handler.__class__._fake_state.run_thread.is_alive.return_value = True

        handle_post_run_start(handler, {}, {})

        handler._send_json.assert_called_once_with({"ok": False, "error": "pipeline is already running"}, 409)
        assert json.loads(progress.read_text(encoding="utf-8")) == original

    def test_starts_thread(self, tmp_path: Path, _no_thread, _handler):
        handler = _handler
        handler._resolve_project_dir.return_value = tmp_path / "input"
        handler._get_config.return_value = MagicMock()

        handle_post_run_start(handler, {}, {"steps": ["compress", "analyze"]})

        handler._send_json.assert_called_once()
        assert handler._send_json.call_args[0][0]["ok"] is True

    def test_rejects_missing_input_dir_override(self, tmp_path: Path, _handler):
        handler = _handler
        handler._resolve_project_dir.return_value = tmp_path / "input"
        cfg = SimpleNamespace(paths=SimpleNamespace(input_dir=tmp_path / "input", output_dir=tmp_path / "output"))
        handler._get_config.return_value = cfg

        handle_post_run_start(handler, {}, {"input_dir": str(tmp_path / "missing")})

        handler._send_json.assert_called_once()
        assert handler._send_json.call_args.args[1] == 400
        err = handler._send_json.call_args.args[0]["error"]
        assert "project_dir not found" in err or "input_dir not found" in err


class TestHandlePostRunPreview:
    def test_builds_preview_from_request(self, tmp_path: Path, _handler, monkeypatch):
        handler = _handler
        proj_dir = tmp_path / "input"
        cfg = MagicMock()
        handler._resolve_project_dir.return_value = proj_dir
        handler._get_config.return_value = cfg
        expected = {"input": {}, "steps": [], "totals": {}}
        build = MagicMock(return_value=expected)
        monkeypatch.setattr("clio.ui.routes.run.build_run_preview", build)

        handle_post_run_preview(
            handler,
            {},
            {
                "day_label": "day3",
                "steps": ["compress", "analyze"],
                "use_transcripts": False,
                "overwrite": True,
                "files": ["A.mp4"],
            },
        )

        build.assert_called_once_with(
            cfg,
            ["compress", "analyze"],
            force=True,
            use_transcripts=False,
            files=["A.mp4"],
            day_label="day3",
        )
        handler._send_json.assert_called_once_with({"ok": True, "preview": expected})

    def test_rejects_non_list_files(self, tmp_path: Path, _handler):
        handler = _handler
        handler._resolve_project_dir.return_value = tmp_path / "input"
        handler._get_config.return_value = MagicMock()

        handle_post_run_preview(handler, {}, {"files": "A.mp4"})

        handler._send_json.assert_called_once_with({"ok": False, "error": "files must be a list of video names"}, 400)


class TestHandlePostRerun:
    def test_missing_params(self, tmp_path: Path, _handler):
        handler = _handler
        handler._resolve_project_dir.return_value = tmp_path

        handle_post_rerun(handler, {}, {})

        handler._send_json.assert_called_once()
        assert handler._send_json.call_args[0][1] == 400

    def test_invalid_task(self, tmp_path: Path, _handler):
        handler = _handler
        handler._resolve_project_dir.return_value = tmp_path

        handle_post_rerun(handler, {}, {"video": "test.mp4", "task": "invalid"})

        handler._send_json.assert_called_once()
        assert handler._send_json.call_args[0][1] == 400

    def test_transcribe_valid_task(self, tmp_path: Path, _no_thread, _handler):
        """transcribe 应作为有效 task 被接受"""
        handler = _handler
        proj_dir = tmp_path / "input"
        proj_dir.mkdir()
        (proj_dir / "GL010695.MP4").write_bytes(b"")
        handler._resolve_project_dir.return_value = proj_dir

        handle_post_rerun(handler, {}, {"video": "GL010695.MP4", "task": "transcribe", "source": "original"})

        handler._send_json.assert_called_once()
        assert handler._send_json.call_args[0][0]["ok"] is True

    def test_starts_rerun(self, tmp_path: Path, _no_thread, _handler):
        handler = _handler
        proj_dir = tmp_path / "input"
        proj_dir.mkdir()
        (proj_dir / "GL010695.MP4").write_bytes(b"")
        handler._resolve_project_dir.return_value = proj_dir

        handle_post_rerun(handler, {}, {"video": "001_GL010695.mp4", "task": "compress"})

        handler._send_json.assert_called_once()
        assert handler._send_json.call_args[0][0]["ok"] is True

    def test_rerun_with_external_original_returns_ok(self, tmp_path: Path, _handler):
        """Rerun with compressed source: verify original_video captured by the rerun
        thread closure is the correct external path (from .vmeta.source_path)."""
        import json as _json

        handler = _handler
        proj_dir = tmp_path / "input"
        proj_dir.mkdir()
        proj_out = tmp_path / "output"
        comp_dir = proj_out / "compressed"
        comp_dir.mkdir(parents=True)

        # External original (outside proj_dir)
        ext_root = tmp_path / "external"
        ext_root.mkdir()
        original = ext_root / "GL010695.MP4"
        original.write_bytes(b"original data")

        # Compressed file with .vmeta pointing to external original
        compressed = comp_dir / "001_GL010695.mp4"
        compressed.write_bytes(b"compressed")
        from clio.vmeta import VideoMeta

        meta = VideoMeta.build(
            source=original,
            target=compressed,
            source_duration=10.0,
            target_duration=5.0,
        )
        meta.write(compressed)

        # videos.json with external path
        (proj_dir / "videos.json").write_text(_json.dumps([str(original.resolve())]))

        handler._resolve_project_dir.return_value = proj_dir
        cfg = MagicMock()
        cfg.compressed_dir = comp_dir
        cfg.paths = SimpleNamespace(ffprobe="", output_dir=proj_out, input_dir=proj_dir)
        cfg.analyze = SimpleNamespace(skip_existing=True)
        cfg.compress = SimpleNamespace(split_max_min=0)
        handler._get_config.return_value = cfg

        # Capture the thread target's default arguments
        # _no_thread can't be used here because we need to inspect the Thread call
        captured_thread_args = {}

        def _fake_thread(*a, **kw):
            captured_thread_args["target"] = kw.get("target")
            return MagicMock(start=lambda: None)

        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr("clio.ui.routes.run.threading.Thread", _fake_thread)

        handle_post_rerun(handler, {}, {"video": "001_GL010695.mp4", "task": "compress"})

        handler._send_json.assert_called_once()
        payload = handler._send_json.call_args[0][0]
        assert payload["ok"] is True, f"Expected ok=True, got {payload}"

        target_fn = captured_thread_args.get("target")
        assert target_fn is not None, "Thread was not created"
        # _rerun_worker has defaults: cfg, task, video_basename, original_video, ...
        defaults = target_fn.__defaults__
        assert defaults is not None, "No defaults on _rerun_worker"
        # defaults: (cfg, task, video_basename, original_video, texts_json, proj_out, cancel_event)
        assert len(defaults) >= 4, f"Expected at least 4 defaults, got {len(defaults)}"
        original_video_arg = defaults[3]  # 4th default is original_video
        assert original_video_arg == original.resolve(), (
            f"Wrong original_video: expected {original.resolve()}, got {original_video_arg}"
        )


class TestHandlePostRunCancel:
    def test_cancel_sets_event(self, _handler):
        handler = _handler
        handler._resolve_project_dir.return_value = Path("/input")
        assert not handler.__class__._fake_state.cancel_event.is_set()

        handle_post_run_cancel(handler, {}, {})

        assert handler.__class__._fake_state.cancel_event.is_set()
        handler._send_json.assert_called_once_with({"ok": True, "message": "取消请求已发送"})
