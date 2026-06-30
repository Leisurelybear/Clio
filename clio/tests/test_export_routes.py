"""Tests for clio.ui.routes.export."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from clio.ui.routes.export import handle_post_export


@pytest.fixture
def handler(tmp_path: Path) -> MagicMock:
    h = MagicMock()
    cfg = MagicMock()
    cfg.plans_dir = tmp_path
    cfg.paths.output_dir = tmp_path / "output"
    cfg.paths.input_dir = tmp_path / "input"
    cfg.paths.ffprobe = "ffprobe"
    cfg.texts_dir = tmp_path / "texts"
    h._resolve_project_input.return_value = "default"
    h._get_config.return_value = cfg
    return h


class TestHandlePostExport:
    def test_missing_plan_returns_404(self, handler: MagicMock) -> None:
        handle_post_export(handler, {}, {"day": "day1", "format": "jianying"})

        handler._send_json.assert_called_once()
        args, kwargs = handler._send_json.call_args
        assert args[1] == 404 or kwargs.get("status") == 404
        assert not args[0].get("ok", True)

    def test_file_not_found_error_returns_400(self, handler: MagicMock) -> None:
        plan_path = handler._get_config.return_value.plans_dir / "day1_plan.json"
        plan_path.write_text("{}", encoding="utf-8")

        with patch("clio.ui.routes.export.export_plan") as mock_export:
            mock_export.side_effect = FileNotFoundError("file not found")

            handle_post_export(handler, {}, {"day": "day1", "format": "jianying"})

        handler._send_json.assert_called_once_with({"ok": False, "error": "file not found"}, 400)

    def test_value_error_returns_400(self, handler: MagicMock) -> None:
        plan_path = handler._get_config.return_value.plans_dir / "day1_plan.json"
        plan_path.write_text("{}", encoding="utf-8")

        with patch("clio.ui.routes.export.export_plan") as mock_export:
            mock_export.side_effect = ValueError("bad format")

            handle_post_export(handler, {}, {"day": "day1", "format": "jianying"})

        handler._send_json.assert_called_once_with({"ok": False, "error": "bad format"}, 400)

    def test_success_returns_ok_path(self, handler: MagicMock) -> None:
        plan_path = handler._get_config.return_value.plans_dir / "day1_plan.json"
        plan_path.write_text("{}", encoding="utf-8")

        result_path = Path("/output/export/day1_jianying")

        with patch("clio.ui.routes.export.export_plan") as mock_export:
            mock_export.return_value = result_path

            handle_post_export(handler, {}, {"day": "day1", "format": "jianying"})

        handler._send_json.assert_called_once_with({"ok": True, "path": str(result_path)})
