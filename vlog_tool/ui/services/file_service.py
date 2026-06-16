"""File-system utilities for the UI server.

Module-level helpers extracted from server.py:
- basename safety checks
- directory scanning (texts dirs, drives)
- atomic file writes
- config type coercion
- video matching (compressed <-> original)
"""

from __future__ import annotations

import os
import re
import shutil
import string
import sys
from pathlib import Path
from typing import Any

import yaml

from vlog_tool._constants import VIDEO_EXTS


def _is_safe_basename(name: str) -> bool:
    if not name or len(name) > 200:
        return False
    if "/" in name or "\\" in name or ".." in name:
        return False
    if any(ord(c) < 0x20 or ord(c) == 0x7F for c in name):
        return False
    return True


def _find_texts_dirs(output_dir: Path) -> list[Path]:
    """Return all texts* subdirectories (texts, texts - Paris, ...)."""
    if not output_dir or not output_dir.is_dir():
        return []
    return [
        d for d in sorted(output_dir.iterdir()) if d.is_dir() and (d.name == "texts" or d.name.startswith("texts - "))
    ]


def _save_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    bak = path.with_suffix(path.suffix + ".bak")
    if path.exists():
        shutil.copy2(path, bak)
    elif bak.exists():
        bak.unlink()
    tmp = path.with_suffix(path.suffix + f".tmp.{os.urandom(4).hex()}")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _create_project_yaml(proj_input: Path, config_path: Path | None, proj_out: Path) -> Path | None:
    """Create project.yaml from global config template, with paths adjusted to the project.

    Returns the project.yaml path, or None if no global config is available.
    """
    if not config_path or not config_path.is_file():
        return None
    target = proj_input / "project.yaml"
    if target.is_file():
        return target  # already exists
    try:
        with open(config_path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        paths = raw.get("paths", {})
        paths["input_dir"] = str(proj_input.resolve())
        paths["output_dir"] = str(proj_out.resolve())
        raw["paths"] = paths
        raw.setdefault("ai", {})
        raw["ai"].setdefault("context", "")
        _inject_provider_defaults(raw)
        _inject_whisper_defaults(raw)
        yml = yaml.dump(raw, allow_unicode=True, default_flow_style=False, sort_keys=False, indent=2)
        _save_atomic(target, yml.encode("utf-8"))
        return target
    except Exception:
        return None


def _inject_provider_defaults(raw: dict) -> None:
    """Inject default provider fields (requests_per_minute, retry_attempts) into
    the ai.providers section of a config dict. Only touches provider blocks."""
    providers = raw.get("ai", {}).get("providers", {})
    for pname, pcfg in providers.items():
        if isinstance(pcfg, dict):
            pcfg.setdefault("requests_per_minute", 0)
            pcfg.setdefault("retry_attempts", 2)


def _inject_whisper_defaults(raw: dict) -> None:
    """Inject default whisper fields into a config dict."""
    whisper = raw.setdefault("whisper", {})
    if isinstance(whisper, dict):
        whisper.setdefault("enabled", False)
        whisper.setdefault("model_size", "medium")
        whisper.setdefault("language", "zh")
        whisper.setdefault("device", "auto")
        whisper.setdefault("max_segments_per_clip", 5)
        whisper.setdefault("transcripts_subdir", "transcripts")


def _migrate_project_configs(projects_root: Path) -> tuple[int, list[str]]:
    """Scan for project.yaml files and inject missing provider defaults.
    Returns (count_updated, list of errors)."""
    updated = 0
    errors: list[str] = []
    if not projects_root.is_dir():
        return updated, errors
    for proj_dir in sorted(projects_root.iterdir()):
        if not proj_dir.is_dir():
            continue
        proj_yaml = proj_dir / "project.yaml"
        if not proj_yaml.is_file():
            continue
        try:
            with open(proj_yaml, encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}
            before = yaml.dump(raw, allow_unicode=True, sort_keys=False)
            _inject_provider_defaults(raw)
            _inject_whisper_defaults(raw)
            after = yaml.dump(raw, allow_unicode=True, sort_keys=False)
            if before != after:
                yml = yaml.dump(raw, allow_unicode=True, default_flow_style=False, sort_keys=False, indent=2)
                _save_atomic(proj_yaml, yml.encode("utf-8"))
                updated += 1
        except Exception as e:
            errors.append(f"{proj_dir.name}: {e}")
    return updated, errors


def _list_drives() -> list[str]:
    """Quickly list available Windows drive letters (avoid Path.is_dir() timeout on network drives)."""
    if sys.platform != "win32":
        return []
    try:
        import ctypes

        bitmask = ctypes.windll.kernel32.GetLogicalDrives()
        return [f"{d}:\\" for d in string.ascii_uppercase if bitmask & (1 << (ord(d) - ord("A")))]
    except Exception:
        # fallback: traditional approach
        return [f"{d}:\\" for d in string.ascii_uppercase if Path(f"{d}:\\").is_dir()]


def _find_original_for_compressed(stem: str, input_dir: Path) -> str | None:
    """For a compressed stem like '001_GL010695', find the matching original basename
    in input_dir. Match is case-insensitive on the GoPro-style suffix (everything
    after the first '_'). Falls back to stripping '_segNN' suffix for split videos.
    Returns the original filename or None if not found.
    """
    if "_" not in stem or not input_dir.is_dir():
        return None
    suffix = stem.split("_", 1)[1].lower()
    for p in sorted(input_dir.iterdir()):
        if p.is_file() and p.stem.lower() == suffix:
            return p.name
    m = re.match(r"^(.+)_seg\d+$", suffix)
    if m:
        base = m.group(1)
        for p in sorted(input_dir.iterdir()):
            if p.is_file() and p.stem.lower() == base:
                return p.name
    return None


def _find_compressed_for_original(stem: str, comp_dir: Path) -> list[tuple[str, str]] | None:
    """For an original stem like 'GL010695', find matching compressed file(s) and
    their indices. Returns a sorted list of (compressed_basename, index) tuples,
    or None if not found. For split videos, returns all segments sorted by index.
    """
    if not comp_dir.is_dir():
        return None
    needle = stem.lower()
    matches: list[tuple[str, str]] = []
    for p in sorted(comp_dir.iterdir()):
        if p.suffix.lower() not in VIDEO_EXTS or "_" not in p.stem:
            continue
        idx, rest = p.stem.split("_", 1)
        if rest.lower() == needle:
            return [(p.name, idx)]
        seg_prefix = needle + "_seg"
        if rest.lower().startswith(seg_prefix) and rest.lower()[len(seg_prefix) :].isdigit():
            matches.append((p.name, idx))
    if not matches:
        return None
    matches.sort(key=lambda m: m[1])
    return matches


def _coerce_config_types(new_val: Any, ref_val: Any) -> Any:
    if ref_val is None:
        return new_val
    if isinstance(ref_val, bool):
        if isinstance(new_val, str):
            return new_val.lower() in ("true", "1", "yes")
        return bool(new_val)
    if isinstance(ref_val, int):
        if new_val is None:
            return None
        try:
            return int(new_val)
        except (ValueError, TypeError):
            return new_val
    if isinstance(ref_val, float):
        if new_val is None:
            return None
        try:
            return float(new_val)
        except (ValueError, TypeError):
            return new_val
    if isinstance(ref_val, str):
        return str(new_val) if not isinstance(new_val, str) else new_val
    if isinstance(ref_val, list) and isinstance(new_val, list):
        if ref_val and new_val:
            return [_coerce_config_types(n, ref_val[0]) for n in new_val]
        return new_val
    if isinstance(ref_val, dict) and isinstance(new_val, dict):
        result = {}
        for k in ref_val:
            if k in new_val:
                result[k] = _coerce_config_types(new_val[k], ref_val[k])
        for k in new_val:
            if k not in result:
                result[k] = new_val[k]
        return result
    return new_val
