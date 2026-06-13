"""Tests for vlog_tool/ui/routes/projects.py — project CRUD handlers."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from vlog_tool.ui.routes.projects import (
    handle_get_project,
    handle_get_projects,
    handle_post_project_add,
    handle_post_project_create,
    handle_put_project,
)


class TestHandleGetProject:
    def test_returns_defaults_when_no_project_json(self):
        handler = MagicMock()
        handler._resolve_project_input.return_value = Path("/nonexistent")
        handler.DEFAULT_PROJECT = {"name": "Unnamed", "currentDay": "day1", "source": "compressed"}
        handler._send_json = MagicMock()

        handle_get_project(handler, {})

        handler._send_json.assert_called_once()
        payload = handler._send_json.call_args[0][0]
        assert payload["name"] == "Unnamed"
        assert "steps" in payload

    def test_reads_project_json(self, tmp_path: Path):
        handler = MagicMock()
        proj_input = tmp_path / "project"
        proj_input.mkdir()
        (proj_input / "project.json").write_text(json.dumps({"name": "Tokyo", "currentDay": "day3"}), encoding="utf-8")
        handler._resolve_project_input.return_value = proj_input
        handler.DEFAULT_PROJECT = {"name": "Unnamed", "currentDay": "day1", "source": "compressed"}
        handler._send_json = MagicMock()

        handle_get_project(handler, {})
        payload = handler._send_json.call_args[0][0]
        assert payload["name"] == "Tokyo"
        assert payload["currentDay"] == "day3"


class TestHandleGetProjects:
    def test_empty(self, tmp_path: Path):
        handler = MagicMock()
        handler.server.config_path = tmp_path / "config.yaml"
        handler.server.input_dir = tmp_path / "input"
        handler._send_json = MagicMock()

        handle_get_projects(handler, {})

        payload = handler._send_json.call_args[0][0]
        assert "projects" in payload
        assert "last_project" in payload


class TestHandlePutProject:
    def test_updates_project_json(self, tmp_path: Path):
        handler = MagicMock()
        proj_input = tmp_path / "project"
        proj_input.mkdir()
        cfg = tmp_path / "config.yaml"
        cfg.write_bytes(b"")
        handler._resolve_project_input.return_value = proj_input
        handler.server.config_path = cfg
        handler.DEFAULT_PROJECT = {"name": "Unnamed", "currentDay": "day1", "source": "compressed"}
        handler._send_json = MagicMock()

        handle_put_project(handler, {}, {"name": "Updated", "currentDay": "day2"})

        handler._send_json.assert_called_once_with({"ok": True})
        proj_file = proj_input / "project.json"
        assert proj_file.is_file()
        data = json.loads(proj_file.read_text(encoding="utf-8"))
        assert data["name"] == "Updated"
        assert data["currentDay"] == "day2"
        assert "updatedAt" in data


class TestHandlePostProjectCreate:
    def test_missing_name(self):
        handler = MagicMock()
        handler._send_json = MagicMock()

        handle_post_project_create(handler, {})

        assert handler._send_json.call_args[0][1] == 400

    def test_missing_input_dir(self):
        handler = MagicMock()
        handler._send_json = MagicMock()

        handle_post_project_create(handler, {"name": "Test"})

        assert handler._send_json.call_args[0][1] == 400

    def test_nonexistent_input_dir(self):
        handler = MagicMock()
        handler._send_json = MagicMock()

        handle_post_project_create(handler, {"name": "Test", "input_dir": "/nonexistent"})

        assert handler._send_json.call_args[0][1] == 400

    def test_creates_project(self, tmp_path: Path):
        handler = MagicMock()
        proj_input = tmp_path / "new_project"
        proj_input.mkdir()
        handler.server.config_path = tmp_path / "config.yaml"
        handler.__class__._config_cache = {}
        handler._send_json = MagicMock()

        handle_post_project_create(handler, {"name": "Paris", "input_dir": str(proj_input)})

        assert handler._send_json.call_args[0][0]["ok"] is True
        proj_file = proj_input / "project.json"
        assert proj_file.is_file()
        data = json.loads(proj_file.read_text(encoding="utf-8"))
        assert data["name"] == "Paris"
        assert data["currentDay"] == "day1"


class TestHandlePostProjectAdd:
    def test_missing_input_dir(self):
        handler = MagicMock()
        handler._send_json = MagicMock()

        handle_post_project_add(handler, {})

        assert handler._send_json.call_args[0][1] == 400

    def test_adds_existing_project(self, tmp_path: Path):
        handler = MagicMock()
        proj_input = tmp_path / "existing"
        proj_input.mkdir()
        (proj_input / "project.json").write_text(json.dumps({"name": "Existing Project"}), encoding="utf-8")
        handler.server.config_path = tmp_path / "config.yaml"
        handler._send_json = MagicMock()

        handle_post_project_add(handler, {"input_dir": str(proj_input)})

        assert handler._send_json.call_args[0][0]["ok"] is True

    def test_auto_creates_project_json(self, tmp_path: Path):
        """Adding a dir without project.json should auto-create it."""
        handler = MagicMock()
        proj_input = tmp_path / "new_dir"
        proj_input.mkdir()
        handler.server.config_path = tmp_path / "config.yaml"
        handler.__class__._config_cache = {}
        handler._send_json = MagicMock()

        handle_post_project_add(handler, {"input_dir": str(proj_input)})

        assert handler._send_json.call_args[0][0]["ok"] is True
        proj_file = proj_input / "project.json"
        assert proj_file.is_file()
