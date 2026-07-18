"""Tests for clio/ui/routes/deps.py."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from clio.ui.routes.deps import handle_get_deps_ffmpeg


def _handler(tmp_path: Path) -> MagicMock:
    h = MagicMock()
    proj = tmp_path / "proj"
    proj.mkdir()
    h._resolve_project_dir.return_value = proj
    h._get_config.return_value = SimpleNamespace(paths=SimpleNamespace(ffmpeg="", ffprobe=""))
    h._send_json = MagicMock()
    return h


class TestHandleGetDepsFfmpeg:
    def test_returns_probe_payload(self, tmp_path: Path):
        h = _handler(tmp_path)
        payload = {
            "ok": False,
            "ffmpeg": None,
            "ffprobe": None,
            "missing": ["ffmpeg", "ffprobe"],
            "detail": "未找到 ffmpeg、ffprobe。…",
        }
        with patch("clio.ui.routes.deps.probe_ffmpeg_deps", return_value=payload) as probe:
            handle_get_deps_ffmpeg(h, {})
        probe.assert_called_once_with("", "")
        h._send_json.assert_called_once_with(payload)

    def test_uses_config_paths(self, tmp_path: Path):
        h = _handler(tmp_path)
        ff = tmp_path / "ffmpeg.exe"
        fp = tmp_path / "ffprobe.exe"
        ff.write_bytes(b"x")
        fp.write_bytes(b"x")
        h._get_config.return_value = SimpleNamespace(paths=SimpleNamespace(ffmpeg=str(ff), ffprobe=str(fp)))
        with patch("clio.ui.routes.deps.probe_ffmpeg_deps") as probe:
            probe.return_value = {
                "ok": True,
                "ffmpeg": str(ff),
                "ffprobe": str(fp),
                "missing": [],
                "detail": "",
            }
            handle_get_deps_ffmpeg(h, {})
        probe.assert_called_once_with(str(ff), str(fp))
