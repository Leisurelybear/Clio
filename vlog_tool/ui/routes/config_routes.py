"""Route handlers: /api/config, /api/config/raw, /api/config/init"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from vlog_tool.config import deep_merge, load_config
from vlog_tool.ui.services.file_service import (
    _coerce_config_types,
    _create_project_yaml,
    _find_texts_dirs,
    _save_atomic,
)
from vlog_tool.ui.services.project_service import _project_output_dir

if TYPE_CHECKING:
    from http.server import BaseHTTPRequestHandler


def handle_get_config(handler: BaseHTTPRequestHandler, qs: dict) -> None:
    """Handle GET /api/config."""
    proj_input = handler._resolve_project_input(qs)
    proj_out = handler._get_project_output(proj_input)
    comp = proj_out / "compressed"
    texts = _find_texts_dirs(proj_out)
    handler._send_json(
        {
            "input_dir": str(proj_input),
            "output_dir": str(proj_out),
            "compressed_dir": str(comp),
            "texts_dirs": [str(d) for d in texts],
            "scripts_dir": str(proj_out / "scripts"),
            "plans_dir": str(proj_out / "plans"),
        }
    )


def handle_get_config_raw(handler: BaseHTTPRequestHandler, qs: dict) -> None:
    """Handle GET /api/config/raw."""

    config_path = (
        handler.server.config_path if hasattr(handler.server, "config_path") else getattr(handler, "config_path", None)
    )
    input_dir = handler.server.input_dir if hasattr(handler.server, "input_dir") else handler.input_dir

    if not config_path or not config_path.is_file():
        return handler._send_json({"error": "config file not available"}, 500)
    proj_input = handler._resolve_project_input(qs)
    # Always try to load project.yaml if it exists (proj_input may equal default dir)
    proj_yaml = proj_input / "project.yaml"
    if not proj_yaml.is_file():
        # Non-default project without project.yaml => needs init
        if proj_input != input_dir:
            return handler._send_json({"needs_init": True})
        proj_yaml = None
    # Return the merged effective config
    with open(config_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    if proj_yaml:
        with open(proj_yaml, encoding="utf-8") as f:
            project_raw = yaml.safe_load(f) or {}
        raw = deep_merge(raw, project_raw)
        raw["_config_source"] = "project"
    else:
        raw["_config_source"] = "global_fallback"
    handler._send_json(raw)


def handle_put_config_raw(handler: BaseHTTPRequestHandler, qs: dict, obj: dict) -> None:
    """Handle PUT /api/config/raw."""
    config_path = (
        handler.server.config_path if hasattr(handler.server, "config_path") else getattr(handler, "config_path", None)
    )
    input_dir = handler.server.input_dir if hasattr(handler.server, "input_dir") else handler.input_dir

    if not config_path:
        return handler._send_json({"ok": False, "error": "config_path not available"}, 500)
    # Support ?project=X writing project-specific config
    proj_input = handler._resolve_project_input(qs)
    # 写 project.yaml（如果项目有专属配置、或在非默认目录下）
    proj_yaml = proj_input / "project.yaml"
    if proj_yaml.is_file() or proj_input != input_dir:
        target_path = proj_yaml
        try:
            yml = yaml.dump(obj, allow_unicode=True, default_flow_style=False, sort_keys=False, indent=2)
        except Exception as e:
            return handler._send_json({"ok": False, "error": f"YAML serialization failed: {e}"}, 400)
        orig_backup = target_path.read_bytes() if target_path.is_file() else None
        try:
            _save_atomic(target_path, yml.encode("utf-8"))
            load_config(config_path, project_dir=proj_input)
        except Exception as e:
            if orig_backup is not None:
                target_path.write_bytes(orig_backup)
            else:
                target_path.unlink(missing_ok=True)
            return handler._send_json({"ok": False, "error": f"config validation failed: {e}"}, 400)
        handler.__class__._config_cache.pop(str(proj_input.resolve()), None)
        return handler._send_json({"ok": True, "path": str(target_path)})
    # Global config.yaml write (original logic)
    try:
        with open(config_path, encoding="utf-8") as f:
            ref_raw = yaml.safe_load(f) or {}
    except Exception as e:
        return handler._send_json({"ok": False, "error": f"cannot read current config: {e}"}, 500)
    coerced = _coerce_config_types(obj, ref_raw)
    try:
        yml = yaml.dump(coerced, allow_unicode=True, default_flow_style=False, sort_keys=False, indent=2)
    except Exception as e:
        return handler._send_json({"ok": False, "error": f"YAML serialization failed: {e}"}, 400)
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".yaml", delete=False, dir=str(config_path.parent)) as tmp:
            tmp.write(yml.encode("utf-8"))
            tmp_path = Path(tmp.name)
        load_config(tmp_path)
    except (ValueError, FileNotFoundError, Exception) as e:
        if tmp_path and tmp_path.exists():
            tmp_path.unlink()
        return handler._send_json({"ok": False, "error": f"config validation failed: {e}"}, 400)
    _save_atomic(config_path, yml.encode("utf-8"))
    if tmp_path and tmp_path.exists():
        tmp_path.unlink()
    handler._send_json({"ok": True, "path": str(config_path)})


def handle_post_config_init(handler: BaseHTTPRequestHandler, qs: dict, obj: dict) -> None:
    """Handle POST /api/config/init."""
    config_path = (
        handler.server.config_path if hasattr(handler.server, "config_path") else getattr(handler, "config_path", None)
    )
    input_dir = handler.server.input_dir if hasattr(handler.server, "input_dir") else handler.input_dir

    proj_input = handler._resolve_project_input(qs)
    if proj_input == input_dir:
        return handler._send_json(
            {"ok": False, "error": "default project already has config.yaml, no init needed"}, 400
        )
    proj_out = _project_output_dir(proj_input)
    result = _create_project_yaml(proj_input, config_path, proj_out)
    if result is None:
        return handler._send_json(
            {"ok": False, "error": "failed to create project.yaml (global config.yaml not available)"}, 500
        )
    handler.__class__._config_cache.pop(str(proj_input.resolve()), None)
    handler._send_json({"ok": True, "path": str(result)})
