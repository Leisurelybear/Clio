"""Tests for clio/ui/routes/whisper_routes.py — project query and model persistence."""

from __future__ import annotations

import json
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

from clio.ui.routes.whisper_download import (
    _install_progress_path,
    _run_install,
    handle_post_whisper_install_cancel,
)
from clio.ui.routes.whisper_models import _get_cache_dir
from clio.ui.routes.whisper_routes import (
    handle_get_whisper_check,
    handle_get_whisper_models,
    handle_put_whisper_model,
)


class _FakePopen:
    """Minimal stand-in for subprocess.Popen used by _pip_install_streaming."""

    def __init__(self, cmd, **kwargs):
        import io

        self.cmd = cmd
        self.stdout = io.StringIO("Downloading package...\nInstalling...\n")
        self.returncode = 0

    def wait(self) -> int:
        return self.returncode


def _make_handler(proj_input: Path, proj_output: Path) -> MagicMock:
    """Build a mock handler that resolves project input/output correctly."""
    handler = MagicMock()

    def _resolve_qs(qs: dict) -> Path:
        # If qs has "project", return a subdirectory; otherwise return proj_input
        return proj_input

    handler._resolve_project_input.side_effect = _resolve_qs
    handler._get_project_output.return_value = proj_output

    cfg = MagicMock()
    cfg.whisper.model_size = "small"
    cfg.whisper.hf_endpoint = ""
    cfg.whisper.cache_dir = ""
    cfg.proxy.enabled = False
    cfg.proxy.url = ""
    handler._get_config.return_value = cfg

    handler._send_json = MagicMock()
    handler.__class__._config_cache = MagicMock()
    return handler


class TestProjectQueryConsistency:
    """Verify that Whisper routes respect the qs project parameter."""

    def test_get_whisper_check_uses_qs(self, tmp_path: Path) -> None:
        """handle_get_whisper_check should pass qs to _resolve_project_input."""
        proj_input = tmp_path / "project_a"
        proj_input.mkdir()
        proj_output = tmp_path / "output_a"
        proj_output.mkdir()
        handler = _make_handler(proj_input, proj_output)
        qs = {"project": "project_a"}

        with patch("clio.ui.routes.whisper_check.check_whisper", return_value=False):
            handle_get_whisper_check(handler, qs)

        handler._resolve_project_input.assert_called_with(qs)
        handler._get_config.assert_called_once_with(proj_input)

    def test_get_whisper_models_uses_qs(self, tmp_path: Path) -> None:
        """handle_get_whisper_models should pass qs to _resolve_project_input."""
        proj_input = tmp_path / "project_b"
        proj_input.mkdir()
        proj_output = tmp_path / "output_b"
        proj_output.mkdir()
        handler = _make_handler(proj_input, proj_output)
        qs = {"project": "project_b"}

        handle_get_whisper_models(handler, qs)

        # _resolve_project_input should be called with qs (at least once, possibly twice)
        call_args_list = handler._resolve_project_input.call_args_list
        assert all(call.args[0] is qs for call in call_args_list), (
            f"Expected all calls with qs={qs}, got: {call_args_list}"
        )

    def test_install_progress_path_uses_qs(self, tmp_path: Path) -> None:
        """_install_progress_path should resolve output from qs, not from empty dict."""
        proj_input = tmp_path / "project_c"
        proj_input.mkdir()
        proj_output = tmp_path / "output_c"
        proj_output.mkdir()
        handler = _make_handler(proj_input, proj_output)
        qs = {"project": "project_c"}

        path = _install_progress_path(handler, qs)

        handler._get_project_output.assert_called_with(qs)
        assert path == proj_output / ".whisper_install.json"

    def test_get_cache_dir_uses_qs(self, tmp_path: Path) -> None:
        """_get_cache_dir should pass qs to _resolve_project_input."""
        proj_input = tmp_path / "project_d"
        proj_input.mkdir()
        proj_output = tmp_path / "output_d"
        proj_output.mkdir()
        handler = _make_handler(proj_input, proj_output)
        qs = {"project": "project_d"}

        _get_cache_dir(handler, qs)

        handler._resolve_project_input.assert_called_with(qs)


class TestPutWhisperModelPersistence:
    """Verify handle_put_whisper_model correctly writes project.yaml."""

    def test_creates_project_yaml_when_missing(self, tmp_path: Path) -> None:
        """If project.yaml doesn't exist, it should be created with whisper config."""
        proj_input = tmp_path / "input"
        proj_input.mkdir()
        proj_output = tmp_path / "output"
        proj_output.mkdir()
        handler = _make_handler(proj_input, proj_output)
        qs = {"project": "test"}

        assert not (proj_input / "project.yaml").exists()

        handle_put_whisper_model(handler, qs, {"model_size": "medium"})

        # project.yaml should now exist with the model_size
        proj_yaml = proj_input / "project.yaml"
        assert proj_yaml.is_file()
        raw = yaml.safe_load(proj_yaml.read_text(encoding="utf-8"))
        assert raw["whisper"]["model_size"] == "medium"
        handler.__class__._config_cache.invalidate_key.assert_called_with(str(proj_input.resolve()))

    def test_updates_existing_project_yaml(self, tmp_path: Path) -> None:
        """If project.yaml exists, it should be updated with the new model_size."""
        proj_input = tmp_path / "input"
        proj_input.mkdir()
        proj_output = tmp_path / "output"
        proj_output.mkdir()

        # Create existing project.yaml with other config
        proj_yaml = proj_input / "project.yaml"
        proj_yaml.write_text(
            yaml.dump({"whisper": {"model_size": "small", "language": "en"}, "other": "data"}),
            encoding="utf-8",
        )

        handler = _make_handler(proj_input, proj_output)
        qs = {"project": "test"}

        handle_put_whisper_model(handler, qs, {"model_size": "medium"})

        raw = yaml.safe_load(proj_yaml.read_text(encoding="utf-8"))
        assert raw["whisper"]["model_size"] == "medium"
        assert raw["whisper"]["language"] == "en"  # preserved
        assert raw["other"] == "data"  # preserved

    def test_rejects_invalid_model_size(self, tmp_path: Path) -> None:
        """Invalid model_size should return 400 error."""
        proj_input = tmp_path / "input"
        proj_input.mkdir()
        proj_output = tmp_path / "output"
        proj_output.mkdir()
        handler = _make_handler(proj_input, proj_output)
        qs = {"project": "test"}

        handle_put_whisper_model(handler, qs, {"model_size": "gigantic"})

        handler._send_json.assert_called_once()
        args = handler._send_json.call_args
        assert args[0][1] == 400  # status code
        assert "invalid" in args[0][0]["error"]

    def test_rejects_empty_model_size(self, tmp_path: Path) -> None:
        """Empty model_size should return 400 error."""
        proj_input = tmp_path / "input"
        proj_input.mkdir()
        proj_output = tmp_path / "output"
        proj_output.mkdir()
        handler = _make_handler(proj_input, proj_output)
        qs = {"project": "test"}

        handle_put_whisper_model(handler, qs, {"model_size": ""})

        handler._send_json.assert_called_once()
        args = handler._send_json.call_args
        assert args[0][1] == 400

    def test_does_not_create_file_on_validation_failure(self, tmp_path: Path) -> None:
        """project.yaml should not be created if validation fails."""
        proj_input = tmp_path / "input"
        proj_input.mkdir()
        proj_output = tmp_path / "output"
        proj_output.mkdir()
        handler = _make_handler(proj_input, proj_output)
        qs = {"project": "test"}

        handle_put_whisper_model(handler, qs, {"model_size": "invalid"})

        assert not (proj_input / "project.yaml").exists()


class TestHandlePostWhisperInstallCancel:
    """Verify handle_post_whisper_install_cancel."""

    def test_cancel_updates_progress_file(self, tmp_path: Path) -> None:
        """Cancel should reset progress file status to idle."""
        proj_input = tmp_path / "input"
        proj_input.mkdir()
        proj_output = tmp_path / "output"
        proj_output.mkdir()
        handler = _make_handler(proj_input, proj_output)
        qs = {"project": "test"}

        progress_file = _install_progress_path(handler, qs)
        progress_file.parent.mkdir(parents=True, exist_ok=True)
        progress_file.write_text('{"status": "downloading", "progress_pct": 42}', encoding="utf-8")

        handle_post_whisper_install_cancel(handler, qs)

        data = json.loads(progress_file.read_text(encoding="utf-8"))
        assert data["status"] == "idle"
        assert data["progress_pct"] == 0
        assert "取消" in data["message"]
        handler._send_json.assert_called_once_with({"ok": True, "message": "cancel requested"})

    def test_cancel_without_progress_file(self, tmp_path: Path) -> None:
        """Cancel should succeed even if no progress file exists."""
        proj_input = tmp_path / "input"
        proj_input.mkdir()
        proj_output = tmp_path / "output"
        proj_output.mkdir()
        handler = _make_handler(proj_input, proj_output)
        qs = {"project": "test"}

        handle_post_whisper_install_cancel(handler, qs)

        handler._send_json.assert_called_once_with({"ok": True, "message": "cancel requested"})


class TestRunWhisperInstall:
    def test_downloads_required_snapshot_files(self, tmp_path: Path) -> None:
        proj_input = tmp_path / "input"
        proj_input.mkdir()
        proj_output = tmp_path / "output"
        proj_output.mkdir()
        handler = _make_handler(proj_input, proj_output)
        cache_dir = tmp_path / "models"
        handler._get_config.return_value.whisper.cache_dir = str(cache_dir)
        handler._get_config.return_value.whisper.model_size = "small"
        qs = {"project": "test"}
        progress_file = _install_progress_path(handler, qs)

        fake_hub = types.SimpleNamespace(hf_hub_url=lambda repo_id, filename: f"https://example.test/{filename}")

        class Response:
            headers = {"Content-Length": "4"}

            def raise_for_status(self) -> None:
                return None

            def iter_content(self, chunk_size: int):
                yield b"data"

        with (
            patch.dict("sys.modules", {"huggingface_hub": fake_hub}),
            patch("clio.ui.routes.whisper_download._get_model_download_size", return_value=16),
            patch("clio.ui.routes.whisper_download._req.get", return_value=Response()) as mock_get,
            patch("clio.ui.routes.whisper_download.subprocess.Popen", _FakePopen),
        ):
            _run_install(handler, qs, progress_file)

        snap = cache_dir / "models--Systran--faster-whisper-small" / "snapshots" / "downloaded"
        assert (snap / "config.json").read_bytes() == b"data"
        assert (snap / "model.bin").read_bytes() == b"data"
        assert (snap / "tokenizer.json").read_bytes() == b"data"
        assert (snap / "vocabulary.txt").read_bytes() == b"data"
        assert (cache_dir / "models--Systran--faster-whisper-small" / "refs" / "main").read_text(
            encoding="utf-8"
        ) == "downloaded"
        assert mock_get.call_count == 4
        status = json.loads(progress_file.read_text(encoding="utf-8"))
        assert status["status"] == "done"
        assert status["progress_pct"] == 100

    def test_download_cancel_removes_tmp_file(self, tmp_path: Path) -> None:
        from clio.ui.routes import whisper_download

        proj_input = tmp_path / "input"
        proj_input.mkdir()
        proj_output = tmp_path / "output"
        proj_output.mkdir()
        handler = _make_handler(proj_input, proj_output)
        cache_dir = tmp_path / "models"
        handler._get_config.return_value.whisper.cache_dir = str(cache_dir)
        handler._get_config.return_value.whisper.model_size = "small"
        qs = {"project": "test"}
        progress_file = _install_progress_path(handler, qs)

        fake_hub = types.SimpleNamespace(hf_hub_url=lambda repo_id, filename: f"https://example.test/{filename}")

        class Response:
            headers = {"Content-Length": "8"}

            def raise_for_status(self) -> None:
                return None

            def iter_content(self, chunk_size: int):
                yield b"data"
                whisper_download._INSTALL_CANCEL.set()
                yield b"more"

        whisper_download._INSTALL_CANCEL.clear()
        with (
            patch.dict("sys.modules", {"huggingface_hub": fake_hub}),
            patch("clio.ui.routes.whisper_download._get_model_download_size", return_value=8),
            patch("clio.ui.routes.whisper_download._req.get", return_value=Response()),
            patch("clio.ui.routes.whisper_download.subprocess.Popen", _FakePopen),
        ):
            _run_install(handler, qs, progress_file)

        status = json.loads(progress_file.read_text(encoding="utf-8"))
        assert status["status"] == "idle"
        assert "取消" in status["message"]
        assert list(cache_dir.rglob("*.tmp")) == []
        assert not (
            cache_dir / "models--Systran--faster-whisper-small" / "snapshots" / "downloaded" / "config.json"
        ).exists()
        whisper_download._INSTALL_CANCEL.clear()

    def test_cancel_with_corrupted_progress_file(self, tmp_path: Path) -> None:
        """Cancel should not crash on corrupted progress file."""
        proj_input = tmp_path / "input"
        proj_input.mkdir()
        proj_output = tmp_path / "output"
        proj_output.mkdir()
        handler = _make_handler(proj_input, proj_output)
        qs = {"project": "test"}

        progress_file = _install_progress_path(handler, qs)
        progress_file.parent.mkdir(parents=True, exist_ok=True)
        progress_file.write_text("not valid json", encoding="utf-8")

        handle_post_whisper_install_cancel(handler, qs)

        handler._send_json.assert_called_once_with({"ok": True, "message": "cancel requested"})
