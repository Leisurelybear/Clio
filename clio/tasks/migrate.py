"""Migrate legacy projects (input_dir-based) to project_dir + videos.json."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import yaml

from clio.tasks._video_loader import save_selected_videos
from clio.utils import find_videos


def run_migrate(config_path: Path, from_path: Path | None = None) -> tuple[int, list[str]]:
    """Scan and migrate old projects to the new project_dir + videos.json layout.

    Returns (updated_count, error_messages).
    """
    registry_file = config_path.parent / "projects.json"
    projects_to_migrate: list[Path] = []
    errors: list[str] = []

    # 1. From registry
    if registry_file.is_file():
        try:
            reg = json.loads(registry_file.read_text(encoding="utf-8"))
            for entry in reg.get("projects", []):
                if isinstance(entry, dict):
                    p_str = entry.get("project_dir") or entry.get("input_dir") or ""
                else:
                    p_str = str(entry)
                if not p_str:
                    continue
                p = Path(p_str)
                if p.is_dir() and (p / "project.yaml").is_file():
                    projects_to_migrate.append(p.resolve())
        except Exception as e:
            errors.append(f"读取注册表失败: {e}")

    # 2. From --from flag
    if from_path:
        if from_path.is_dir() and (from_path / "project.yaml").is_file():
            projects_to_migrate.append(from_path.resolve())
        else:
            errors.append(f"--from 路径无效或不含 project.yaml: {from_path}")

    # Dedup while preserving order
    seen: set[Path] = set()
    unique: list[Path] = []
    for p in projects_to_migrate:
        if p not in seen:
            seen.add(p)
            unique.append(p)
    projects_to_migrate = unique

    if not projects_to_migrate:
        return 0, errors or ["未发现可迁移项目"]

    # Backup registry once
    if registry_file.is_file():
        bak = registry_file.with_suffix(".json.migrate-bak")
        try:
            shutil.copy2(registry_file, bak)
        except OSError as e:
            errors.append(f"备份 projects.json 失败: {e}")

    updated = 0
    for old_dir in projects_to_migrate:
        try:
            ok, msg = _migrate_one(old_dir, config_path, registry_file)
            if ok:
                updated += 1
                print(msg)
            else:
                errors.append(msg)
        except Exception as e:
            errors.append(f"{old_dir}: 迁移异常: {e}")

    return updated, errors


def _migrate_one(old_dir: Path, config_path: Path, registry_file: Path) -> tuple[bool, str]:
    """Migrate a single project directory. Returns (ok, message)."""
    old_yaml = old_dir / "project.yaml"
    if not old_yaml.is_file():
        return False, f"{old_dir}: 无 project.yaml"

    # Skip if already migrated (has videos.json and no paths.input_dir)
    videos_json = old_dir / "videos.json"
    try:
        with old_yaml.open(encoding="utf-8") as f:
            old_raw: dict[str, Any] = yaml.safe_load(f) or {}
    except Exception as e:
        return False, f"{old_dir}: 读取 project.yaml 失败: {e}"

    paths_raw = old_raw.get("paths") or {}
    has_input = bool(paths_raw.get("input_dir"))
    if videos_json.is_file() and not has_input:
        return False, f"{old_dir}: 已是新结构，跳过"

    # Resolve old input_dir for video discovery
    old_input_raw = paths_raw.get("input_dir", ".")
    if old_input_raw in (None, "", "."):
        old_input_path = old_dir
    else:
        candidate = Path(str(old_input_raw))
        old_input_path = candidate if candidate.is_absolute() else (old_dir / candidate).resolve()

    name = old_raw.get("name") or old_dir.name
    # In-place migration when project already lives at old_dir and videos are there;
    # otherwise create <config_dir>/projects/<name>/.
    if old_input_path.resolve() == old_dir.resolve() or videos_json.is_file():
        new_dir = old_dir
        in_place = True
    else:
        new_dir = (config_path.parent / "projects" / name).resolve()
        in_place = False

    print(f"迁移: {old_dir} → {new_dir}" + (" (原地)" if in_place else ""))
    new_dir.mkdir(parents=True, exist_ok=True)

    # 1. Backup old yaml
    bak_yaml = old_dir / "project.yaml.migrate-bak"
    if not bak_yaml.is_file():
        try:
            shutil.copy2(old_yaml, bak_yaml)
        except OSError as e:
            return False, f"{old_dir}: 备份 project.yaml 失败: {e}"

    # 2. Write new project.yaml without input_dir/recursive
    new_raw = dict(old_raw)
    new_paths = dict(paths_raw)
    new_paths.pop("input_dir", None)
    new_paths.pop("recursive", None)
    # Keep output_dir; default to ./output if missing
    if "output_dir" not in new_paths or not new_paths["output_dir"]:
        new_paths["output_dir"] = "./output"
    new_raw["paths"] = new_paths
    try:
        (new_dir / "project.yaml").write_text(
            yaml.dump(new_raw, default_flow_style=False, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
    except Exception as e:
        return False, f"{old_dir}: 写入 project.yaml 失败: {e}"

    # 3. Copy project.json if present and different location
    old_json = old_dir / "project.json"
    new_json = new_dir / "project.json"
    if old_json.is_file() and old_json.resolve() != new_json.resolve():
        try:
            data = json.loads(old_json.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
        data["version"] = 2
        if "name" not in data:
            data["name"] = name
        try:
            new_json.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as e:
            return False, f"{old_dir}: 写入 project.json 失败: {e}"
    elif old_json.is_file() and in_place:
        try:
            data = json.loads(old_json.read_text(encoding="utf-8"))
            data["version"] = 2
            old_json.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except (json.JSONDecodeError, OSError):
            pass
    elif not new_json.is_file():
        # Minimal project.json
        try:
            new_json.write_text(
                json.dumps(
                    {
                        "name": name,
                        "version": 2,
                        "output_dir": str((new_dir / "output").resolve()),
                        "currentDay": "day1",
                        "source": "compressed",
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except OSError as e:
            return False, f"{old_dir}: 创建 project.json 失败: {e}"

    # 4. Scan old input for videos → videos.json
    if old_input_path.is_dir():
        videos = find_videos(old_input_path, recursive=True)
    else:
        videos = []
    save_selected_videos(new_dir, videos)
    print(f"  发现 {len(videos)} 个视频")

    # 5. Update registry: replace old path with new
    _update_registry(registry_file, old_dir, new_dir, name)

    # 6. For non-in-place migration, leave a bak marker at old location
    if not in_place and old_yaml.is_file() and old_yaml.resolve() != (new_dir / "project.yaml").resolve():
        try:
            if not bak_yaml.is_file():
                old_yaml.rename(bak_yaml)
            else:
                old_yaml.unlink(missing_ok=True)
        except OSError:
            pass

    return True, f"已迁移 {name}: {new_dir} ({len(videos)} 视频)"


def _update_registry(registry_file: Path, old_dir: Path, new_dir: Path, name: str) -> None:
    reg: dict[str, Any] = {"projects": []}
    if registry_file.is_file():
        try:
            reg = json.loads(registry_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            reg = {"projects": []}

    old_s = str(old_dir.resolve())
    new_s = str(new_dir.resolve())

    def _resolve_entry(entry: Any) -> str:
        if isinstance(entry, dict):
            p = entry.get("project_dir") or entry.get("input_dir") or ""
        else:
            p = str(entry) if entry else ""
        if not p:
            return ""
        try:
            return str(Path(p).resolve())
        except Exception:
            return p

    projects: list[str] = []
    for entry in reg.get("projects", []):
        resolved = _resolve_entry(entry)
        if not resolved or resolved in (old_s, new_s):
            continue
        # Keep plain path strings in registry
        if isinstance(entry, dict):
            projects.append(entry.get("project_dir") or entry.get("input_dir") or resolved)
        else:
            projects.append(str(entry))

    if new_s not in {_resolve_entry(p) for p in projects}:
        projects.append(new_s)

    projects = [p for p in projects if p]

    last = reg.get("last_project")
    if isinstance(last, dict):
        last_dir = last.get("project_dir") or last.get("input_dir")
        if last_dir and str(Path(last_dir).resolve()) == old_s:
            last = {"name": name, "project_dir": new_s, "input_dir": new_s}
    elif isinstance(last, str) and last == name:
        last = {"name": name, "project_dir": new_s, "input_dir": new_s}

    out = {"projects": projects}
    if last:
        out["last_project"] = last
    registry_file.parent.mkdir(parents=True, exist_ok=True)
    registry_file.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
