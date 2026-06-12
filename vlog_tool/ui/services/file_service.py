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
    return [d for d in output_dir.iterdir() if d.is_dir() and d.name.startswith("texts")]


def _save_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not path.with_suffix(path.suffix + ".bak").exists():
        shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
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
        yml = yaml.dump(raw, allow_unicode=True, default_flow_style=False, sort_keys=False, indent=2)
        _save_atomic(target, yml.encode("utf-8"))
        return target
    except Exception:
        return None


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
    after the first '_'). Returns the original filename or None if not found.
    """
    if "_" not in stem or not input_dir.is_dir():
        return None
    suffix = stem.split("_", 1)[1].lower()
    for p in input_dir.iterdir():
        if p.is_file() and p.stem.lower() == suffix:
            return p.name
    return None


def _find_compressed_for_original(stem: str, comp_dir: Path) -> tuple[str, str] | None:
    """For an original stem like 'GL010695', find the matching compressed file and
    its index. Returns (compressed_basename, index) or None if not found.
    """
    if not comp_dir.is_dir():
        return None
    needle = stem.lower()
    for p in comp_dir.iterdir():
        if p.suffix.lower() not in VIDEO_EXTS or "_" not in p.stem:
            continue
        idx, rest = p.stem.split("_", 1)
        if rest.lower() == needle:
            return (p.name, idx)
    return None


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
