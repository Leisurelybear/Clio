"""Route handlers: /api/config, /api/config/raw, /api/config/global,
/api/config/project, /api/config/init"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from clio.config import CONFIG_DESCRIPTIONS, deep_merge, load_config, load_global_config
from clio.ui.services.file_service import (
    _coerce_config_types,
    _create_project_yaml,
    _find_texts_dirs,
    _save_atomic,
)
from clio.ui.services.project_service import _project_output_dir

if TYPE_CHECKING:
    from clio.ui.handler_protocol import HandlerProtocol


def handle_get_config(handler: HandlerProtocol, qs: dict[str, Any]) -> None:
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


def handle_get_config_raw(handler: HandlerProtocol, qs: dict[str, Any]) -> None:
    """Handle GET /api/config/raw."""

    config_path = handler.config_path
    input_dir = handler.input_dir

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
    # 确保 ai.context 始终存在（前端需要该字段渲染编辑框）
    raw.setdefault("ai", {})
    raw["ai"].setdefault("context", "")
    raw["_descriptions"] = CONFIG_DESCRIPTIONS
    handler._send_json(raw)


def handle_put_config_raw(handler: HandlerProtocol, qs: dict[str, Any], obj: dict) -> None:
    """Handle PUT /api/config/raw."""
    config_path = handler.config_path
    input_dir = handler.input_dir

    if not config_path:
        return handler._send_json({"ok": False, "error": "config_path not available"}, 500)
    # Support ?project=X writing project-specific config
    proj_input = handler._resolve_project_input(qs)
    # Determine target: project.yaml or config.yaml
    proj_yaml = proj_input / "project.yaml"
    is_project_target = proj_yaml.is_file() or proj_input != input_dir

    # Layer validation: prevent API key leak
    if is_project_target:
        err = _validate_no_foreign_fields(obj, "project")
    else:
        err = _validate_no_foreign_fields(obj, "global")
    if err:
        return handler._send_json({"ok": False, "error": err}, 400)

    if is_project_target:
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
        handler.__class__._config_cache.invalidate_key(str(proj_input.resolve()))
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
    handler.__class__._config_cache.invalidate_all()
    handler._send_json({"ok": True, "path": str(config_path)})


def handle_post_config_init(handler: HandlerProtocol, qs: dict[str, Any], obj: dict) -> None:
    """Handle POST /api/config/init."""
    config_path = handler.config_path
    input_dir = handler.input_dir

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
    handler.__class__._config_cache.invalidate_key(str(proj_input.resolve()))
    handler._send_json({"ok": True, "path": str(result)})


# ---------------------------------------------------------------------------
# /api/config/global and /api/config/project — per-layer endpoints
# ---------------------------------------------------------------------------

# Layer field ownership (mirrors loader.py constants)
_GLOBAL_SECTIONS = {"proxy", "server", "naming"}
_PROJECT_SECTIONS = {"analyze", "script", "plan", "export"}
_SPLIT_GLOBAL: dict[str, set[str]] = {
    "paths": {"ffmpeg", "ffprobe", "logs_dir"},
    "ai": {"providers", "debug_print_prompt", "provider_ttl_min"},
    "compress": {"codec", "fps", "remove_audio", "crf"},
    "whisper": {"cache_dir", "hf_endpoint"},
}
_SPLIT_PROJECT: dict[str, set[str]] = {
    "paths": {"input_dir", "output_dir", "recursive"},
    "compress": {"target_size_mb", "max_width", "split_max_min", "splits_subdir", "reencode_split"},
    "ai": {"tasks", "context", "context_file"},
    "whisper": {"enabled", "model_size", "language", "device", "max_segments_per_clip", "transcripts_subdir"},
}


def _is_global_section(section: str) -> bool:
    return section in _GLOBAL_SECTIONS or section in _SPLIT_GLOBAL


def _is_project_section(section: str) -> bool:
    return section in _PROJECT_SECTIONS or section in _SPLIT_PROJECT


def _validate_no_foreign_fields(obj: dict, layer: str) -> str | None:
    """Check obj has no fields belonging to the other layer.
    Returns error string or None."""
    if layer == "global":
        foreign = _PROJECT_SECTIONS | set(_SPLIT_PROJECT.keys())
    else:
        foreign = _GLOBAL_SECTIONS | set(_SPLIT_GLOBAL.keys())

    for section in foreign:
        if section in obj:
            if layer == "global":
                return f"'{section}' 属于项目配置，不能写入全局 config.yaml"
            else:
                return f"'{section}' 属于全局配置，不能写入 project.yaml"

    # Check split-section field-level violations
    split_table = _SPLIT_PROJECT if layer == "global" else _SPLIT_GLOBAL
    split_label = "项目" if layer == "global" else "全局"
    for section, fields in split_table.items():
        val = obj.get(section)
        if isinstance(val, dict):
            for k in val:
                if k in fields:
                    return f"'{section}.{k}' 属于{split_label}配置，不能写入该文件"

    return None


def handle_get_config_global(handler: HandlerProtocol, qs: dict[str, Any]) -> None:
    """Handle GET /api/config/global."""
    config_path = handler.config_path
    if not config_path or not config_path.is_file():
        return handler._send_json({"error": "config file not available"}, 500)
    with open(config_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    # Strip project-only fields
    result: dict = {}
    for section, val in raw.items():
        if not isinstance(val, dict):
            result[section] = val
        elif _is_global_section(section):
            result[section] = val
        elif section in _SPLIT_GLOBAL:
            kept = {k: v for k, v in val.items() if k not in _SPLIT_PROJECT.get(section, set())}
            if kept:
                result[section] = kept
    result.setdefault("ai", {})
    result["ai"].setdefault("context", "")
    result["_descriptions"] = CONFIG_DESCRIPTIONS
    handler._send_json(result)


def handle_get_config_project(handler: HandlerProtocol, qs: dict[str, Any]) -> None:
    """Handle GET /api/config/project."""
    config_path = handler.config_path
    input_dir = handler.input_dir
    if not config_path:
        return handler._send_json({"error": "config file not available"}, 500)
    proj_input = handler._resolve_project_input(qs)
    proj_yaml = proj_input / "project.yaml"
    if not proj_yaml.is_file():
        if proj_input != input_dir:
            return handler._send_json({"needs_init": True})
        return handler._send_json({})

    try:
        with open(proj_yaml, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    except Exception as e:
        return handler._send_json({"error": f"cannot read project.yaml: {e}"}, 500)

    result: dict = {}
    for section, val in raw.items():
        if not isinstance(val, dict):
            continue
        if _is_project_section(section):
            result[section] = val
        elif section in _SPLIT_PROJECT:
            kept = {k: v for k, v in val.items() if k not in _SPLIT_GLOBAL.get(section, set())}
            if kept:
                result[section] = kept
    result.setdefault("ai", {})
    result["ai"].setdefault("context", "")
    result["_descriptions"] = CONFIG_DESCRIPTIONS
    handler._send_json(result)


def handle_put_config_global(handler: HandlerProtocol, qs: dict[str, Any], obj: dict) -> None:
    """Handle PUT /api/config/global."""
    config_path = handler.config_path
    if not config_path:
        return handler._send_json({"ok": False, "error": "config_path not available"}, 500)

    err = _validate_no_foreign_fields(obj, "global")
    if err:
        return handler._send_json({"ok": False, "error": err}, 400)

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
        load_global_config(tmp_path)
    except Exception as e:
        if tmp_path and tmp_path.exists():
            tmp_path.unlink()
        return handler._send_json({"ok": False, "error": f"config validation failed: {e}"}, 400)
    _save_atomic(config_path, yml.encode("utf-8"))
    if tmp_path and tmp_path.exists():
        tmp_path.unlink()
    handler.__class__._config_cache.invalidate_all()
    handler._send_json({"ok": True, "path": str(config_path)})


def handle_put_config_project(handler: HandlerProtocol, qs: dict[str, Any], obj: dict) -> None:
    """Handle PUT /api/config/project."""
    config_path = handler.config_path
    if not config_path:
        return handler._send_json({"ok": False, "error": "config_path not available"}, 500)
    proj_input = handler._resolve_project_input(qs)
    proj_yaml = proj_input / "project.yaml"

    err = _validate_no_foreign_fields(obj, "project")
    if err:
        return handler._send_json({"ok": False, "error": err}, 400)

    try:
        yml = yaml.dump(obj, allow_unicode=True, default_flow_style=False, sort_keys=False, indent=2)
    except Exception as e:
        return handler._send_json({"ok": False, "error": f"YAML serialization failed: {e}"}, 400)
    orig_backup = proj_yaml.read_bytes() if proj_yaml.is_file() else None
    try:
        _save_atomic(proj_yaml, yml.encode("utf-8"))
        load_config(config_path, project_dir=proj_input)
    except Exception as e:
        if orig_backup is not None:
            proj_yaml.write_bytes(orig_backup)
        else:
            proj_yaml.unlink()
        return handler._send_json({"ok": False, "error": f"config validation failed: {e}"}, 400)
    handler.__class__._config_cache.invalidate_key(str(proj_input.resolve()))
    handler._send_json({"ok": True, "path": str(proj_yaml)})
