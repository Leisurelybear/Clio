"""Tests for clio/ui/routes/waveform.py."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from clio.ui.routes.waveform import handle_get_waveform


def _handler(tmp_path: Path) -> MagicMock:
    h = MagicMock()
    proj = tmp_path / "proj"
    out = tmp_path / "out"
    proj.mkdir()
    out.mkdir()
    h._resolve_project_dir.return_value = proj
    h._get_project_output.return_value = out
    h._get_config.return_value = SimpleNamespace(paths=SimpleNamespace(ffmpeg="ffmpeg", ffprobe="ffprobe"))
    h._send_json = MagicMock()
    return h


class TestHandleGetWaveform:
    def test_ready_returns_peaks(self, tmp_path: Path):
        h = _handler(tmp_path)
        out = h._get_project_output.return_value
        comp = out / "compressed"
        comp.mkdir()
        vid = comp / "001_a.mp4"
        vid.write_bytes(b"x")
        payload = {
            "status": "ready",
            "version": 1,
            "peaks": [0.1, 0.2],
            "duration_sec": 1.0,
            "bin_count": 2,
            "audio_source": "compressed",
            "source_path": str(vid),
        }
        with patch("clio.ui.routes.waveform.ensure_waveform", return_value=payload) as en:
            handle_get_waveform(
                h,
                {"file": ["001_a.mp4"], "source": ["compressed"], "is_segment": ["1"]},
            )
        en.assert_called_once()
        h._send_json.assert_called_once()
        args = h._send_json.call_args
        assert args[0][0]["status"] == "ready"
        if len(args[0]) > 1:
            assert args[0][1] == 200

    def test_pending_returns_202(self, tmp_path: Path):
        h = _handler(tmp_path)
        out = h._get_project_output.return_value
        comp = out / "compressed"
        comp.mkdir()
        (comp / "001_a.mp4").write_bytes(b"x")
        with patch(
            "clio.ui.routes.waveform.ensure_waveform",
            return_value={"status": "pending", "started_at": 1.0, "key": "k"},
        ):
            handle_get_waveform(h, {"file": ["001_a.mp4"], "source": ["compressed"], "is_segment": ["1"]})
        args = h._send_json.call_args
        assert args[0][0]["status"] == "pending"
        assert args[0][1] == 202

    def test_no_media_404(self, tmp_path: Path):
        h = _handler(tmp_path)
        handle_get_waveform(h, {"file": ["missing.mp4"], "source": ["compressed"]})
        args = h._send_json.call_args
        assert args[0][1] == 404
