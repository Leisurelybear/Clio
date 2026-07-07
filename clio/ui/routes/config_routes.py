"""Route handlers: /api/config, /api/config/raw, /api/config/global,
/api/config/project, /api/config/init"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import unquote

import yaml

from clio.config import CONFIG_DESCRIPTIONS, deep_merge, load_config, load_global_config
from clio.config.parsers import _infer_provider_capabilities
from clio.ui.services.file_service import (
    _coerce_config_types,
    _create_project_yaml,
    _find_texts_dirs,
    _save_atomic,
)
from clio.ui.services.project_service import _project_output_dir

if TYPE_CHECKING:
    from clio.ui.handler_protocol import HandlerProtocol

_PROVIDER_TYPES = {"gemini", "openai", "openai_compat"}


def _provider_name_error(name: str) -> str | None:
    if not name or not all(c.isalnum() or c in "_-" for c in name):
        return "provider name must contain only letters, numbers, '_' or '-'"
    return None


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
    split_sections = set(_SPLIT_GLOBAL.keys()) & set(_SPLIT_PROJECT.keys())

    if layer == "global":
        foreign = _PROJECT_SECTIONS | set(_SPLIT_PROJECT.keys())
    else:
        foreign = _GLOBAL_SECTIONS | set(_SPLIT_GLOBAL.keys())

    # Skip section-level check for split sections (checked at field level below)
    for section in foreign - split_sections:
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
        elif section in _SPLIT_GLOBAL:
            kept = {k: v for k, v in val.items() if k in _SPLIT_GLOBAL.get(section, set())}
            if kept:
                result[section] = kept
        elif _is_global_section(section):
            result[section] = val
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
        if section in _SPLIT_PROJECT:
            kept = {k: v for k, v in val.items() if k in _SPLIT_PROJECT.get(section, set())}
            if kept:
                result[section] = kept
        elif _is_project_section(section):
            result[section] = val
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


# ---------------------------------------------------------------------------
# /api/providers — focused CRUD API for global AI provider registry
# ---------------------------------------------------------------------------


def _read_global_config_raw(config_path: Path | None) -> tuple[dict[str, Any] | None, str | None]:
    if not config_path or not config_path.is_file():
        return None, "config file not available"
    try:
        with open(config_path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    except Exception as e:
        return None, f"cannot read current config: {e}"
    if not isinstance(raw, dict):
        return None, "config root must be a mapping"
    return raw, None


def _provider_error(name: str, provider: dict[str, Any]) -> str | None:
    if error := _provider_name_error(name):
        return error
    provider_type = provider.get("type", "gemini")
    if provider_type not in _PROVIDER_TYPES:
        return f"unsupported provider type: {provider_type}"
    models = provider.get("models", [])
    if not isinstance(models, list) or any(not isinstance(m, str) for m in models):
        return "models must be a list of strings"
    capabilities = provider.get("capabilities")
    if capabilities is not None and (
        not isinstance(capabilities, list) or any(not isinstance(c, str) for c in capabilities)
    ):
        return "capabilities must be a list of strings"
    return None


def _normalize_provider(name: str, obj: dict[str, Any]) -> dict[str, Any]:
    provider_type = obj.get("type", "gemini")
    data = {
        "type": provider_type,
        "api_key_env": obj.get("api_key_env", ""),
        "api_key": obj.get("api_key", ""),
        "base_url": obj.get("base_url", ""),
        "poll_interval_sec": obj.get("poll_interval_sec", 5),
        "retry_attempts": obj.get("retry_attempts", 2),
        "requests_per_minute": obj.get("requests_per_minute", 0),
        "timeout_sec": obj.get("timeout_sec", 120.0),
        "max_tokens": obj.get("max_tokens", 4096),
        "models": obj.get("models", []),
        "capabilities": obj.get("capabilities") or _infer_provider_capabilities(provider_type),
    }
    if obj.get("name"):
        data["name"] = name
    return data


def _write_global_config_raw(handler: HandlerProtocol, raw: dict[str, Any]) -> tuple[bool, str | None]:
    config_path = handler.config_path
    if not config_path:
        return False, "config_path not available"
    try:
        yml = yaml.dump(raw, allow_unicode=True, default_flow_style=False, sort_keys=False, indent=2)
    except Exception as e:
        return False, f"YAML serialization failed: {e}"
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".yaml", delete=False, dir=str(config_path.parent)) as tmp:
            tmp.write(yml.encode("utf-8"))
            tmp_path = Path(tmp.name)
        load_global_config(tmp_path)
    except Exception as e:
        if tmp_path and tmp_path.exists():
            tmp_path.unlink()
        return False, f"config validation failed: {e}"
    _save_atomic(config_path, yml.encode("utf-8"))
    if tmp_path and tmp_path.exists():
        tmp_path.unlink()
    handler.__class__._config_cache.invalidate_all()
    return True, None


def handle_get_providers(handler: HandlerProtocol, qs: dict[str, Any]) -> None:
    raw, error = _read_global_config_raw(handler.config_path)
    if error:
        return handler._send_json({"ok": False, "error": error}, 500)
    providers = raw.get("ai", {}).get("providers", {}) if raw else {}
    return handler._send_json({"ok": True, "providers": providers})


def handle_post_provider(handler: HandlerProtocol, qs: dict[str, Any], obj: dict[str, Any]) -> None:
    name = (obj.get("name") or "").strip()
    if not name:
        return handler._send_json({"ok": False, "error": "provider name is required"}, 400)
    raw, error = _read_global_config_raw(handler.config_path)
    if error:
        return handler._send_json({"ok": False, "error": error}, 500)
    assert raw is not None
    providers = raw.setdefault("ai", {}).setdefault("providers", {})
    if name in providers:
        return handler._send_json({"ok": False, "error": f"provider already exists: {name}"}, 409)
    provider = _normalize_provider(name, obj)
    error = _provider_error(name, provider)
    if error:
        return handler._send_json({"ok": False, "error": error}, 400)
    providers[name] = provider
    ok, error = _write_global_config_raw(handler, raw)
    if not ok:
        return handler._send_json({"ok": False, "error": error}, 400)
    return handler._send_json({"ok": True, "name": name, "provider": provider})


def handle_put_provider(handler: HandlerProtocol, qs: dict[str, Any], obj: dict[str, Any], name: str) -> None:
    name = unquote(name).strip()
    raw, error = _read_global_config_raw(handler.config_path)
    if error:
        return handler._send_json({"ok": False, "error": error}, 500)
    assert raw is not None
    provider = _normalize_provider(name, obj)
    error = _provider_error(name, provider)
    if error:
        return handler._send_json({"ok": False, "error": error}, 400)
    providers = raw.setdefault("ai", {}).setdefault("providers", {})
    providers[name] = provider
    ok, error = _write_global_config_raw(handler, raw)
    if not ok:
        return handler._send_json({"ok": False, "error": error}, 400)
    return handler._send_json({"ok": True, "name": name, "provider": provider})


def handle_delete_provider(handler: HandlerProtocol, qs: dict[str, Any], name: str) -> None:
    name = unquote(name).strip()
    if error := _provider_name_error(name):
        return handler._send_json({"ok": False, "error": error}, 400)
    raw, error = _read_global_config_raw(handler.config_path)
    if error:
        return handler._send_json({"ok": False, "error": error}, 500)
    assert raw is not None
    providers = raw.setdefault("ai", {}).setdefault("providers", {})
    if name not in providers:
        return handler._send_json({"ok": False, "error": f"provider not found: {name}"}, 404)
    del providers[name]
    ok, error = _write_global_config_raw(handler, raw)
    if not ok:
        return handler._send_json({"ok": False, "error": error}, 400)
    return handler._send_json({"ok": True, "name": name})
