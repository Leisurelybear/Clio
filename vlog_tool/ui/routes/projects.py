"""Route handlers: /api/projects, /api/project, /api/project/create, /api/project/add"""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import TYPE_CHECKING

from vlog_tool.ui.services.file_service import _create_project_yaml, _save_atomic
from vlog_tool.ui.services.project_service import (
    _add_to_registry,
    _detect_steps,
    _list_projects,
    _project_output_dir,
    _registry_path,
    _save_last_project,
)

if TYPE_CHECKING:
    from http.server import BaseHTTPRequestHandler


def handle_get_project(handler: BaseHTTPRequestHandler, qs: dict) -> None:
    """Handle GET /api/project."""
    proj_input = handler._resolve_project_input(qs)
    proj_file = proj_input / "project.json"
    data = {}
    if proj_file.is_file():
        try:
            data = json.loads(proj_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
    # Record this as the most recently used project
    qs_project = qs.get("project", [None])[0]
    config_path = handler.server.config_path if hasattr(handler.server, "config_path") else None
    if qs_project:
        _save_last_project(qs_project, config_path)
    merged = {**handler.DEFAULT_PROJECT, **data}
    proj_out = _project_output_dir(proj_input)
    merged["steps"] = _detect_steps(proj_out)
    handler._send_json(merged)


def handle_get_projects(handler: BaseHTTPRequestHandler, qs: dict) -> None:
    """Handle GET /api/projects."""
    req_project = qs.get("project", [None])[0]
    config_path = handler.server.config_path if hasattr(handler.server, "config_path") else None
    input_dir = handler.server.input_dir if hasattr(handler.server, "input_dir") else handler.input_dir
    reg_file = _registry_path(config_path)
    last_project = None
    if reg_file.is_file():
        try:
            reg = json.loads(reg_file.read_text(encoding="utf-8"))
            last_project = reg.get("last_project")
        except (json.JSONDecodeError, OSError):
            pass
    handler._send_json({"projects": _list_projects(config_path, input_dir, req_project), "last_project": last_project})


def handle_put_project(handler: BaseHTTPRequestHandler, qs: dict, obj: dict) -> None:
    """Handle PUT /api/project."""
    proj_input = handler._resolve_project_input(qs)
    proj_file = proj_input / "project.json"
    data = {}
    if proj_file.is_file():
        try:
            data = json.loads(proj_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
    merged = {**handler.DEFAULT_PROJECT, **data, **obj}
    merged["updatedAt"] = datetime.datetime.now().isoformat(timespec="seconds")
    if not proj_file.is_file():
        merged["createdAt"] = merged["updatedAt"]
    proj_input.mkdir(parents=True, exist_ok=True)
    _save_atomic(proj_file, json.dumps(merged, ensure_ascii=False, indent=2).encode("utf-8"))
    config_path = handler.server.config_path if hasattr(handler.server, "config_path") else None
    _save_last_project(merged.get("name") or proj_input.name, config_path)
    handler._send_json({"ok": True})


def handle_post_project_create(handler: BaseHTTPRequestHandler, obj: dict) -> None:
    """Handle POST /api/project/create."""
    config_path = handler.server.config_path if hasattr(handler.server, "config_path") else None

    name = (obj.get("name") or "").strip()
    input_dir_raw = (obj.get("input_dir") or "").strip()
    output_dir_raw = (obj.get("output_dir") or "").strip()
    if not name:
        return handler._send_json({"ok": False, "error": "name is required"}, 400)
    if not input_dir_raw:
        return handler._send_json({"ok": False, "error": "input_dir is required"}, 400)
    input_path = Path(input_dir_raw)
    if not input_path.is_dir():
        return handler._send_json({"ok": False, "error": f"input_dir not found: {input_dir_raw}"}, 400)
    if output_dir_raw:
        proj_out = Path(output_dir_raw)
    else:
        proj_out = input_path / "output"
    now = datetime.datetime.now().isoformat(timespec="seconds")
    proj_data = {
        "name": name,
        "output_dir": str(proj_out),
        "currentDay": "day1",
        "source": "compressed",
        "lastEntity": None,
        "lastVideo": None,
        "createdAt": now,
        "updatedAt": now,
    }
    proj_file = input_path / "project.json"
    _save_atomic(proj_file, json.dumps(proj_data, ensure_ascii=False, indent=2).encode("utf-8"))
    # Auto-create project.yaml (silent failure is fine)
    _create_project_yaml(input_path, config_path, proj_out)
    handler.__class__._config_cache.pop(str(input_path.resolve()), None)
    _add_to_registry(str(input_path), config_path)
    handler._send_json(
        {"ok": True, "project": {"name": name, "input_dir": str(input_path), "output_dir": str(proj_out)}}
    )


def handle_post_project_add(handler: BaseHTTPRequestHandler, obj: dict) -> None:
    """Handle POST /api/project/add."""
    config_path = handler.server.config_path if hasattr(handler.server, "config_path") else None

    input_dir_raw = (obj.get("input_dir") or "").strip()
    if not input_dir_raw:
        return handler._send_json({"ok": False, "error": "input_dir is required"}, 400)
    input_path = Path(input_dir_raw)
    if not input_path.is_dir():
        return handler._send_json({"ok": False, "error": f"目录不存在: {input_dir_raw}"}, 400)
    proj_file = input_path / "project.json"
    if not proj_file.is_file():
        # Auto-create project.json + project.yaml (similar to create project)
        proj_out = input_path / "output"
        now = datetime.datetime.now().isoformat(timespec="seconds")
        proj_data = {
            "name": input_path.name,
            "output_dir": str(proj_out),
            "currentDay": "day1",
            "source": "compressed",
            "lastEntity": None,
            "lastVideo": None,
            "createdAt": now,
            "updatedAt": now,
        }
        _save_atomic(proj_file, json.dumps(proj_data, ensure_ascii=False, indent=2).encode("utf-8"))
        _create_project_yaml(input_path, config_path, proj_out)
        handler.__class__._config_cache.pop(str(input_path.resolve()), None)
        name = input_path.name
    else:
        try:
            data = json.loads(proj_file.read_text(encoding="utf-8"))
            name = data.get("name") or input_path.name
        except (json.JSONDecodeError, OSError) as e:
            return handler._send_json({"ok": False, "error": f"无法读取 project.json: {e}"}, 400)
    _add_to_registry(str(input_path), config_path)
    handler._send_json({"ok": True, "project": {"name": name, "input_dir": str(input_path)}})
