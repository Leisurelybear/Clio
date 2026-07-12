"""Project management utilities for the UI server.

Closure functions extracted from server.py's make_handler(), now parameterized:
- _project_output_dir
- _detect_steps
- _registry_path
- _add_to_registry
- _save_last_project
- _list_projects
- resolve_project_input
- resolve_last_project_config

All functions take explicit parameters instead of relying on closure variables.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from clio.config import AppConfig, load_config
from clio.ui.services.file_service import _save_atomic


def _resolve_project_output_path(proj_input_dir: Path, value: str | Path | None) -> Path | None:
    if value is None or str(value).strip() == "":
        return None
    out_path = Path(value)
    if not out_path.is_absolute():
        out_path = (proj_input_dir / out_path).resolve()
    return out_path


def _project_output_dir(proj_input_dir: Path) -> Path:
    """Return the project's output directory.

    project.yaml is authoritative for configuration. project.json output_dir is
    kept as a legacy fallback for projects created before the config split.
    """
    proj_yaml = proj_input_dir / "project.yaml"
    if proj_yaml.is_file():
        try:
            data = yaml.safe_load(proj_yaml.read_text(encoding="utf-8")) or {}
            out = data.get("paths", {}).get("output_dir")
            resolved = _resolve_project_output_path(proj_input_dir, out)
            if resolved is not None:
                return resolved
        except (AttributeError, OSError, yaml.YAMLError):
            pass

    proj_file = proj_input_dir / "project.json"
    if proj_file.is_file():
        try:
            data = json.loads(proj_file.read_text(encoding="utf-8"))
            out = data.get("output_dir") or "output"
        except (json.JSONDecodeError, OSError):
            out = "output"
    else:
        out = "output"
    return _resolve_project_output_path(proj_input_dir, out) or (proj_input_dir / "output").resolve()


def _detect_steps(proj_output_dir: Path) -> dict[str, bool]:
    """Infer which pipeline steps are complete from the filesystem."""
    steps: dict[str, bool] = {}
    if not proj_output_dir.is_dir():
        return {k: False for k in ("compress", "analyze", "scripts", "plan", "label", "cut")}
    comp = proj_output_dir / "compressed"
    try:
        steps["compress"] = comp.is_dir() and any(comp.iterdir())
    except (PermissionError, OSError):
        steps["compress"] = False
    texts = [
        d
        for d in sorted(proj_output_dir.iterdir())
        if d.is_dir() and (d.name == "texts" or d.name.startswith("texts - "))
    ]
    try:
        steps["analyze"] = any(any(True for _ in t.iterdir()) for t in texts)
    except (PermissionError, OSError):
        steps["analyze"] = False
    scripts_dir = proj_output_dir / "scripts"
    try:
        steps["scripts"] = scripts_dir.is_dir() and any(scripts_dir.iterdir())
    except (PermissionError, OSError):
        steps["scripts"] = False
    plans_dir = proj_output_dir / "plans"
    try:
        steps["plan"] = plans_dir.is_dir() and any(plans_dir.iterdir())
    except (PermissionError, OSError):
        steps["plan"] = False
    try:
        steps["label"] = (proj_output_dir / "labeled").is_dir() and any((proj_output_dir / "labeled").iterdir())
    except (PermissionError, OSError):
        steps["label"] = False
    try:
        steps["cut"] = (proj_output_dir / "cuts").is_dir() and any((proj_output_dir / "cuts").iterdir())
    except (PermissionError, OSError):
        steps["cut"] = False
    return steps


def _registry_path(config_path: Path | None) -> Path:
    if config_path:
        return config_path.parent / "projects.json"
    return Path("projects.json")


def _remove_from_registry(dir_path: str, config_path: Path | None) -> None:
    """Remove a project from the registry."""
    registry_file = _registry_path(config_path)
    if not registry_file.is_file():
        return
    try:
        reg = json.loads(registry_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    normalized = str(Path(dir_path).resolve())
    paths = reg.get("projects", [])
    if normalized not in paths:
        return
    paths.remove(normalized)
    data: dict[str, Any] = {"projects": paths}
    last_project = reg.get("last_project")
    if last_project:
        last_name = last_project.get("name") if isinstance(last_project, dict) else last_project
        if last_name in {Path(p).name for p in paths}:
            data["last_project"] = last_project
    _save_atomic(registry_file, json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))


def _add_to_registry(dir_path: str, config_path: Path | None) -> None:
    registry_file = _registry_path(config_path)
    paths: list[str] = []
    last_project = None
    if registry_file.is_file():
        try:
            reg = json.loads(registry_file.read_text(encoding="utf-8"))
            paths = reg.get("projects", [])
            last_project = reg.get("last_project")
        except (json.JSONDecodeError, OSError):
            paths = []
    normalized = str(Path(dir_path).resolve())
    if normalized not in paths:
        paths.append(normalized)
    data: dict[str, Any] = {"projects": paths}
    if last_project:
        data["last_project"] = last_project
    _save_atomic(registry_file, json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))


def _save_last_project(
    name: str, config_path: Path | None, input_dir: str | None = None, project_dir: str | None = None
) -> None:
    """Persist the currently active project for auto-load on next startup.

    Stores both name and project_dir so same-named projects can be disambiguated.
    """
    registry_file = _registry_path(config_path)
    paths: list[str] = []
    if registry_file.is_file():
        try:
            reg = json.loads(registry_file.read_text(encoding="utf-8"))
            paths = reg.get("projects", [])
        except (json.JSONDecodeError, OSError):
            paths = []
    dir_value = project_dir or input_dir
    last_project: str | dict[str, str] = (
        {"name": name, "project_dir": dir_value, "input_dir": dir_value} if dir_value else name
    )
    data: dict[str, Any] = {"projects": paths, "last_project": last_project}
    _save_atomic(registry_file, json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))


def _list_projects(
    config_path: Path | None,
    input_dir: Path,
    current_project_name: str | None = None,
    current_project_input_dir: str | None = None,
) -> list[dict[str, Any]]:
    """List all available projects."""
    projects: list[dict[str, Any]] = []
    seen_dirs: set[str] = set()

    # 1. From the registry file (known projects)
    registry_file = _registry_path(config_path)
    registered_paths: list[str] = []
    if registry_file.is_file():
        try:
            reg = json.loads(registry_file.read_text(encoding="utf-8"))
            registered_paths = reg.get("projects", [])
        except (json.JSONDecodeError, OSError):
            registered_paths = []
    for p_str in registered_paths:
        p = Path(p_str)
        proj_file = p / "project.json"
        if not proj_file.is_file():
            continue
        try:
            data = json.loads(proj_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
        name = data.get("name") or p.name
        version = data.get("version", 1)
        proj_out = _project_output_dir(p)
        seen_dirs.add(str(p.resolve()))
        projects.append(
            {
                "name": name,
                "project_dir": str(p),
                "input_dir": str(p),
                "output_dir": str(proj_out),
                "currentDay": data.get("currentDay", "day1"),
                "source": data.get("source", "compressed"),
                "steps": _detect_steps(proj_out),
                "createdAt": data.get("createdAt"),
                "updatedAt": data.get("updatedAt"),
                "is_current": (
                    str(p.resolve()) == current_project_input_dir
                    if current_project_input_dir
                    else (name == current_project_name if current_project_name else p.resolve() == input_dir.resolve())
                ),
                "legacy": version < 2,
            }
        )

    # 2. Include current input_dir fallback only when an explicit project was requested
    if current_project_name:
        cur_resolved = str(input_dir.resolve())
        if cur_resolved not in seen_dirs:
            proj_file = input_dir / "project.json"
            if proj_file.is_file():
                try:
                    data = json.loads(proj_file.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    data = {}
            else:
                data = {}
            name = data.get("name") or input_dir.name
            proj_out = _project_output_dir(input_dir)
            projects.append(
                {
                    "name": name,
                    "project_dir": str(input_dir),
                    "input_dir": str(input_dir),
                    "output_dir": str(proj_out),
                    "currentDay": data.get("currentDay", "day1"),
                    "source": data.get("source", "compressed"),
                    "steps": _detect_steps(proj_out),
                    "createdAt": data.get("createdAt"),
                    "updatedAt": data.get("updatedAt"),
                    "is_current": (
                        str(input_dir.resolve()) == current_project_input_dir
                        if current_project_input_dir
                        else (name == current_project_name if current_project_name else True)
                    ),
                    "legacy": True,
                }
            )

    return projects


def _read_project_name(p: Path) -> str | None:
    """Read project name from project.json."""
    proj_file = p / "project.json"
    if not proj_file.is_file():
        return None
    try:
        data = json.loads(proj_file.read_text(encoding="utf-8"))
        return data.get("name")
    except (json.JSONDecodeError, OSError):
        return None


def resolve_project_input(qs: dict, input_dir: Path, config_path: Path | None) -> Path:
    """Resolve project directory from query params; default to current project_dir.

    Priority:
      1. project_dir / input_dir query param (direct path, unambiguous)
      2. project name query param (may be ambiguous)
    """
    input_dir_raw = qs.get("project_dir", [None])[0] or qs.get("input_dir", [None])[0]
    if input_dir_raw:
        candidate = Path(input_dir_raw).resolve()
        allowed_paths = {str(input_dir.resolve())}
        registry_file = _registry_path(config_path)
        if registry_file.is_file():
            try:
                reg = json.loads(registry_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                reg = {}
            allowed_paths.update(str(Path(p).resolve()) for p in reg.get("projects", []))
        if candidate.is_dir() and str(candidate) in allowed_paths:
            return candidate

    project_name = qs.get("project", [None])[0]
    if not project_name:
        return input_dir

    candidates: list[Path] = []
    seen: set[str] = set()

    def _score(p: Path) -> int:
        s = 0
        if p.name == project_name:
            s += 10
        if p.resolve() == input_dir.resolve():
            s += 5
        return s

    # 1. Registry first (user-added order)
    registry_file = _registry_path(config_path)
    if registry_file.is_file():
        try:
            reg = json.loads(registry_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            reg = {}
        for p_str in reg.get("projects", []):
            p = Path(p_str)
            resolved = str(p.resolve())
            if resolved in seen:
                continue
            seen.add(resolved)
            name = _read_project_name(p)
            if name == project_name:
                candidates.append(p)

    # 2. Sibling directories (auto-discovery)
    projects_root = input_dir.parent
    if projects_root.is_dir():
        for p in sorted(projects_root.iterdir()):
            if not p.is_dir():
                continue
            resolved = str(p.resolve())
            if resolved in seen:
                continue
            seen.add(resolved)
            name = _read_project_name(p)
            if name == project_name:
                candidates.append(p)

    if not candidates:
        return input_dir
    if len(candidates) == 1:
        return candidates[0]
    candidates.sort(key=_score, reverse=True)
    return candidates[0]


def resolve_last_project_config(config: AppConfig, config_path: Path | None) -> AppConfig:
    """If registry has a last_project, attempt to load its config instead of default.

    Supports both legacy (string name) and new (dict with name+input_dir) formats.
    """
    if not config_path:
        return config
    reg_file = _registry_path(config_path)
    if not reg_file.is_file():
        return config
    try:
        reg = json.loads(reg_file.read_text(encoding="utf-8"))
        last_project = reg.get("last_project")
        if not last_project:
            return config

        # New format: dict with project_dir / input_dir — resolve directly
        if isinstance(last_project, dict):
            input_dir_raw = last_project.get("project_dir") or last_project.get("input_dir")
            if input_dir_raw:
                p = Path(input_dir_raw)
                if p.is_dir():
                    return load_config(config_path, project_dir=p)

        # Legacy format: string name — match by project.json name
        last_name = last_project.get("name") if isinstance(last_project, dict) else last_project
        if not last_name:
            return config
        for p_str in reg.get("projects", []):
            p = Path(p_str)
            proj_file = p / "project.json"
            if not proj_file.is_file():
                continue
            data = json.loads(proj_file.read_text(encoding="utf-8"))
            if data.get("name") == last_name:
                return load_config(config_path, project_dir=p)
        return config
    except Exception:
        return config


def resolve_project_dir(qs: dict, project_dir: Path, config_path: Path | None) -> Path:
    """Alias for resolve_project_input (project_dir naming)."""
    return resolve_project_input(qs, project_dir, config_path)
