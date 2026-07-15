# Project-Video Manager Implementation Plan

> **Status (2026-07-15): COMPLETE** on branch `feat/project-video-manager`.
> All 13 tasks landed (data model, pipeline cutover, UI backend rename, migrate CLI, frontend video manager, mkdir/drag-drop/relink, tests). Checkbox steps below are historical; do not re-run.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decouple project directory from `input_dir`, remove the single `input_dir` concept, store selected videos in `videos.json`, add UI file browser for video selection, migrate existing projects.

**Architecture:** New `_video_loader.py` provides `load_selected_videos(project_dir)` / `save_selected_videos(project_dir)` replacing all `find_videos(input_dir)` calls. `AppConfig.project_dir` property gives runtime code a canonical project directory path. UI query params rename `input_dir` → `project_dir`. Registry stores `project_dir` instead of `input_dir`.

**Tech Stack:** Python 3.11+, existing `clio/` package structure, existing UI framework, `json` for `videos.json`.

**Spec:** `docs/superpowers/specs/2026-07-11-project-video-manager-design.md`

---

## File Map

### New Files
| File | Purpose |
|---|---|
| `clio/tasks/_video_loader.py` | `load_selected_videos()` / `save_selected_videos()` — read/write `videos.json` |

### Modified Files (by phase)

**Phase 1 — Data Model Foundation:**
- `clio/config/models.py` — `ProjectPathsConfig` remove `input_dir`/`recursive`; `CombinedPaths` remove `input_dir`/`recursive`; `AppConfig` add `project_dir` property
- `clio/config/loader.py` — `load_project_config()` stop parsing `input_dir`; `apply_run_paths()` remove `input_dir`; pass `project_dir` to `AppConfig`

**Phase 2 — Pipeline Adaptation:**
- `clio/tasks/compress.py` — replace `find_videos(input_dir)` with `load_selected_videos(project_dir)`
- `clio/tasks/analyze.py` — `_build_stem_to_path` uses `load_selected_videos()`
- `clio/tasks/transcribe.py` — `_build_original_stem_map` uses `load_selected_videos()`
- `clio/tasks/cut.py` — `_resolve_video_path` fallback uses `load_selected_videos()`
- `clio/tasks/reindex.py` — `_find_original_for_stem` fallback uses `load_selected_videos()`
- `clio/ui/services/run_preview.py` — return shape: `{"mode": "videos", ...}` instead of `{"mode": "directory", ...}`
- `clio/ui/services/file_service.py` — `_find_original_for_compressed()` uses `load_selected_videos()`

**Phase 3 — UI Backend + Registry:**
- `clio/config/models.py` — `AppConfig.project_dir` property
- `clio/ui/services/project_service.py` — `_list_projects`, `_project_output_dir`, `resolve_last_project_config`, `_save_last_project`, registry format
- `clio/ui/server.py` — `make_handler`, `DEFAULT_PROJECT`, rename `handler.input_dir` → `handler.project_dir`
- `clio/ui/handler_protocol.py` — `input_dir` → `project_dir`
- `clio/ui/routes/projects.py` — create/add: use `project_dir` body field, write to project_dir
- `clio/ui/routes/config_routes.py` — editable paths set `{"output_dir"}` only; GET config response remove `input_dir`
- `clio/ui/routes/videos.py` — `videos_json` instead of directory scan for original
- `clio/ui/routes/export.py` — source resolution from `load_selected_videos()`
- `clio/ui/routes/` — all other routes: rename `proj_input` → `proj_dir`, `input_dir` query param → `project_dir`
- `clio/analyze.py` — `_read_trip_context(str(config.project_dir))`
- `clio/doctor.py` — update diagnosis
- `clio/prompt_overrides.py` — `_project_dir()` return `config.project_dir`
- `clio/main.py` — CLI args: `-p/--project`, `-i/--input` as compat alias

**Phase 4 — Migration Tool:**
- `clio/main.py` — add `migrate` subcommand
- `clio/tasks/migrate.py` — (new) migration logic

**Phase 5 — Frontend UI:**
- `clio/ui/static/src/main.js` — rename `currentProjectInputDir` → `currentProjectDir`, project create/add API calls
- `clio/ui/static/src/api.js` — rename query param
- `clio/ui/static/src/sidebar-data.js` — rename state fields
- `clio/ui/static/src/runner.js` — remove `run-input-dir`, rename fields
- `clio/ui/static/src/runner_feat.js` — same
- `clio/ui/static/src/runner_main.js` — same
- `clio/ui/static/src/main.js` — project card display
- New frontend components for file browser + video management panel

**Phase 6 — Config Examples + Cleanup:**
- `config.example.yaml` — remove `input_dir`/`recursive` from comments
- `docs/project.example.yaml` — remove `input_dir`, update docs
- `clio/tests/test_run_preview.py` — fix `ProjectPathsConfig`
- `clio/tests/test_tasks_cut.py` — fix
- `clio/tests/test_tasks_compress.py` — fix
- `clio/tests/test_tasks_label.py` — fix
- `clio/tests/test_whisper_cli.py` — fix
- Other tests — fix as needed

---

## Tasks

### Task 1: ProjectPathsConfig — remove input_dir/recursive

**Files:**
- Modify: `clio/config/models.py:140-142`
- Modify: `clio/config/models.py:199-225` (CombinedPaths)
- Test: `clio/tests/test_*` (will break, fixed in Phase 6)

- [ ] **Step 1: Edit ProjectPathsConfig**

```python
@dataclass
class ProjectPathsConfig:
    output_dir: Path = Path("./output")
```

- [ ] **Step 2: Edit CombinedPaths — remove input_dir/recursive**

Remove the `input_dir` and `recursive` properties from `CombinedPaths`:

```python
@dataclass
class CombinedPaths:
    _global: GlobalPathsConfig
    _project: ProjectPathsConfig | None

    @property
    def ffmpeg(self) -> str:
        return self._global.ffmpeg

    @property
    def ffprobe(self) -> str:
        return self._global.ffprobe

    @property
    def logs_dir(self) -> Path:
        return self._global.logs_dir

    @property
    def output_dir(self) -> Path:
        return self._project.output_dir if self._project else Path("./output")
```

- [ ] **Step 3: Commit**

```bash
git add clio/config/models.py
git commit -m "refactor(config): remove input_dir and recursive from ProjectPathsConfig"
```

---

### Task 2: Add AppConfig.project_dir property

**Files:**
- Modify: `clio/config/models.py:405-425` (AppConfig.__init__)

- [ ] **Step 1: Edit AppConfig.__init__ to accept and store project_dir**

```python
class AppConfig:
    def __init__(
        self,
        *,
        global_cfg: GlobalConfig,
        project_cfg: ProjectConfig | None = None,
        project_dir: Path | None = None,
    ) -> None:
        self._global_cfg = global_cfg
        self._project_cfg = project_cfg
        self._project_dir = project_dir.resolve() if project_dir else None
        self._paths: CombinedPaths | None = None
        self._ai: CombinedAIConfig | None = None
        self._compress: CombinedCompressConfig | None = None
        self._whisper: CombinedWhisperConfig | None = None

    @property
    def project_dir(self) -> Path | None:
        return self._project_dir
```

- [ ] **Step 2: Commit**

```bash
git add clio/config/models.py
git commit -m "feat(config): add project_dir property to AppConfig"
```

---

### Task 3: Create _video_loader.py

**Files:**
- Create: `clio/tasks/_video_loader.py`
- Test: `clio/tests/test_video_loader.py`

- [ ] **Step 1: Write the failing test**

Create `clio/tests/test_video_loader.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest

from clio.tasks._video_loader import load_selected_videos, save_selected_videos


def test_save_and_load(tmp_path: Path) -> None:
    videos = [Path("D:/GoPro/GH010001.MP4"), Path("E:/phone/video.mp4")]
    save_selected_videos(tmp_path, videos)
    loaded = load_selected_videos(tmp_path)
    assert loaded == videos


def test_load_missing_file(tmp_path: Path) -> None:
    loaded = load_selected_videos(tmp_path)
    assert loaded == []


def test_load_empty_array(tmp_path: Path) -> None:
    (tmp_path / "videos.json").write_text("[]", encoding="utf-8")
    loaded = load_selected_videos(tmp_path)
    assert loaded == []


def test_save_atomicity(tmp_path: Path) -> None:
    v1 = [Path("A.mp4")]
    save_selected_videos(tmp_path, v1)
    content = (tmp_path / "videos.json").read_text(encoding="utf-8")
    assert json.loads(content) == ["A.mp4"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest clio/tests/test_video_loader.py -v`
Expected: ModuleNotFoundError or FunctionNotFoundError

- [ ] **Step 3: Write minimal implementation**

```python
from __future__ import annotations

import json
import os
from pathlib import Path


def load_selected_videos(project_dir: Path) -> list[Path]:
    """从 project_dir/videos.json 读取选中视频列表。"""
    video_file = project_dir / "videos.json"
    if not video_file.is_file():
        return []
    try:
        data = json.loads(video_file.read_text(encoding="utf-8"))
        return [Path(p) for p in data]
    except (json.JSONDecodeError, OSError):
        return []


def save_selected_videos(project_dir: Path, videos: list[Path]) -> None:
    """保存选中视频列表到 project_dir/videos.json（原子写入）。"""
    video_file = project_dir / "videos.json"
    video_file.parent.mkdir(parents=True, exist_ok=True)
    data = [str(p) for p in videos]
    suffix = os.urandom(4).hex()
    tmp = video_file.with_suffix(f".json.tmp.{suffix}")
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        tmp.replace(video_file)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest clio/tests/test_video_loader.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add clio/tasks/_video_loader.py clio/tests/test_video_loader.py
git commit -m "feat(pipeline): add _video_loader for videos.json read/write"
```

---

### Task 4: Update load_config / load_project_config

**Files:**
- Modify: `clio/config/loader.py:472-530`

- [ ] **Step 1: Edit load_project_config — stop parsing input_dir/recursive**

```python
def load_project_config(project_dir: Path, *, config_path: Path | None = None) -> ProjectConfig | None:
    project_yaml = project_dir.resolve() / "project.yaml"
    if not project_yaml.is_file():
        return None

    _upgrade_config_file(project_yaml, section_map=_PROJECT_SECTION_DC_MAP)

    with project_yaml.open(encoding="utf-8") as f:
        raw: dict[str, Any] = yaml.safe_load(f) or {}

    project_base = project_dir.resolve()
    config_base = config_path.parent if config_path is not None else project_base

    paths_raw = raw.get("paths", {})
    ai_raw = raw.get("ai", {})
    context = _load_context(ai_raw, config_base, project_dir=project_dir)

    return ProjectConfig(
        paths=ProjectPathsConfig(
            output_dir=_path(paths_raw.get("output_dir", "./output"), project_base),
        ),
        ai=ProjectAIConfig(
            tasks=_parse_tasks(ai_raw.get("tasks")),
            context=context,
        ),
        compress=...,
        analyze=...,
        script=...,
        plan=...,
        whisper=...,
        export=...,
    )
```

- [ ] **Step 2: Edit load_config — pass project_dir to AppConfig**

```python
def load_config(config_path: str | Path = "config.yaml", project_dir: Path | None = None) -> AppConfig:
    config_file = Path(config_path).resolve()
    global_cfg = load_global_config(config_file)
    effective_project_dir = project_dir
    if effective_project_dir is None and (config_file.parent / "project.yaml").is_file():
        effective_project_dir = config_file.parent
    project_cfg = (
        load_project_config(effective_project_dir, config_path=config_file)
        if effective_project_dir is not None
        else None
    )

    config = AppConfig(global_cfg=global_cfg, project_cfg=project_cfg, project_dir=effective_project_dir)
    _validate_config(config)
    return config
```

- [ ] **Step 3: Edit apply_run_paths — remove input_dir**

```python
def apply_run_paths(
    config: AppConfig,
    output_dir: Path | None = None,
) -> AppConfig:
    config = deepcopy(config)
    if config.project_cfg is None:
        return config
    if output_dir:
        config.project_cfg.paths.output_dir = output_dir.resolve()
    return config
```

- [ ] **Step 4: Commit**

```bash
git add clio/config/loader.py
git commit -m "refactor(config): remove input_dir from load_project_config and apply_run_paths"
```

---

### Task 5: Update pipeline steps — replace find_videos(input_dir)

**Files:**
- Modify: `clio/tasks/compress.py:109`
- Modify: `clio/tasks/analyze.py:36-40, 266`
- Modify: `clio/tasks/transcribe.py:37-38, 167`
- Modify: `clio/tasks/cut.py:93, 129`
- Modify: `clio/tasks/reindex.py:15-21, 120`
- Modify: `clio/ui/services/run_preview.py:37, 98-100`
- Modify: `clio/ui/services/file_service.py:160-186`

Each step is the same pattern: `find_videos(config.paths.input_dir, recursive=...)` → `load_selected_videos(config.project_dir)`.

- [ ] **Step 1: Update compress.py**

Replace line 109:
```python
# Before:
videos = find_videos(config.paths.input_dir, recursive=config.paths.recursive)
# After:
videos = load_selected_videos(config.project_dir)
```

Remove `find_videos` import if no longer used. Add `from clio.tasks._video_loader import load_selected_videos`.

- [ ] **Step 2: Update analyze.py**

Replace `_build_stem_to_path(config.paths.input_dir)` usage (line 266):
```python
# Before:
stem_cache = _build_stem_to_path(config.paths.input_dir)
# After:
selected = load_selected_videos(config.project_dir)
stem_cache = _build_stem_to_path_from_list(selected)
```

Replace `_build_stem_to_path` function with a new helper or add an overload:
```python
def _build_stem_to_path_from_list(videos: list[Path]) -> dict[str, Path]:
    """Build {stem_lower: path} map from a list of video paths."""
    result: dict[str, Path] = {}
    for p in videos:
        result[p.stem.lower()] = p
    return result
```

- [ ] **Step 3: Update transcribe.py**

Replace line 167:
```python
# Before:
original_cache = _build_original_stem_map(config.paths.input_dir)
# After:
selected = load_selected_videos(config.project_dir)
original_cache = {p.stem.lower(): p for p in selected}
```

Delete `_build_original_stem_map` function (lines 37-38) if no longer used elsewhere.

- [ ] **Step 4: Update cut.py**

Replace fallback in `_resolve_video_path` (around line 129):
```python
# Before:
for p in find_videos(input_dir, recursive=True):
    if p.stem.lower() == orig_stem:
        return p
# After:
for p in load_selected_videos(config.project_dir):
    if p.stem.lower() == orig_stem:
        return p
```

- [ ] **Step 5: Update reindex.py**

Replace `_find_original_for_stem` (lines 15-21):
```python
def _find_original_for_stem(stem: str, config: AppConfig) -> Path | None:
    for p in load_selected_videos(config.project_dir):  # Updated
        if p.stem.lower() == stem.lower():
            return p
    return None
```

And update the call site (line 120) to pass `config` instead of `config.paths.input_dir`.

- [ ] **Step 6: Update run_preview.py**

Replace the return value (lines 98-100):
```python
# Before:
input_dir = config.paths.input_dir
videos = _video_files(input_dir, recursive=config.paths.recursive)
return {"mode": "directory", "path": str(input_dir), "count": len(videos)}, videos
# After:
videos = load_selected_videos(config.project_dir)
count = len(videos)
return {"mode": "videos", "count": count}, videos
```

- [ ] **Step 7: Update file_service.py `_find_original_for_compressed`**

Replace the `input_dir` fallback (around line 177):
```python
# Before:
for p in sorted(input_dir.iterdir()):
# After:
for p in load_selected_videos(project_dir):
```

This function receives `input_dir` as parameter; the caller should now pass `project_dir`.

- [ ] **Step 8: Commit**

```bash
git add clio/tasks/compress.py clio/tasks/analyze.py clio/tasks/transcribe.py
git add clio/tasks/cut.py clio/tasks/reindex.py
git add clio/ui/services/run_preview.py clio/ui/services/file_service.py
git commit -m "feat(pipeline): replace find_videos(input_dir) with load_selected_videos(project_dir)"
```

---

### Task 6: UI Backend — rename input_dir → project_dir

**Files:**
- Modify: `clio/ui/handler_protocol.py:41` — rename `input_dir: Path` → `project_dir: Path`
- Modify: `clio/ui/server.py:131-132` — rename `Handler.input_dir` → `Handler.project_dir`, `DEFAULT_PROJECT.name` from `project_dir.name`
- Modify: `clio/ui/services/project_service.py` — rename all `proj_input` → `proj_dir`, `input_dir` → `project_dir`, `_list_projects` return key rename
- Modify: `clio/ui/routes/projects.py` — create/add: use `project_dir` body field, write to project_dir, remove `input_dir` references
- Modify: `clio/ui/routes/config_routes.py:43,187` — GET config: `"project_dir"` instead of `"input_dir"`; editable paths set `{"output_dir"}`
- Modify: `clio/ui/routes/videos.py:64-86, 306-323` — source resolution from `videos.json`
- Modify: `clio/ui/routes/export.py:63` — source from `load_selected_videos()`
- Modify: `clio/ui/routes/` all others — rename `proj_input` → `proj_dir`, `_resolve_project_input` → `_resolve_project_dir`
- Modify: `clio/ui/services/project_service.py` — registry format: `project_dir` instead of `input_dir`

This is a large rename across many files. Pattern:
1. `proj_input` variable rename → `proj_dir`
2. `input_dir` query param rename → `project_dir` in all `qs.get("input_dir")` calls → `qs.get("project_dir")`
3. `_resolve_project_input` rename → `_resolve_project_dir`
4. `_project_output_dir(proj_input)` → `_project_output_dir(proj_dir)` (signature unchanged, param name updated)
5. Registry entries use `"project_dir"` key instead of `"input_dir"`
6. `handler.input_dir` → `handler.project_dir`

- [ ] **Step 1: handler_protocol.py + server.py**

```python
# handler_protocol.py:41
input_dir: Path  →  project_dir: Path

# server.py:131-132
project_dir = config.project_dir or config.paths.input_dir  # transitional: prefer project_dir
DEFAULT_PROJECT = {
    "name": project_dir.name,
    "output_dir": str(output_dir.resolve()),
    ...
}
Handler.project_dir = project_dir  # was Handler.input_dir
```

- [ ] **Step 2: project_service.py** — rename throughout. Key changes:

```python
def _list_projects(config_path, project_dir, ...):
    # return dict keys: "project_dir" instead of "input_dir"
    return {
        "name": name,
        "project_dir": str(p),  # was "input_dir"
        "output_dir": str(proj_out),
        ...
    }

def _save_last_project(name, config_path, project_dir=None):  # param rename
    last_project: dict = {"name": name, "project_dir": project_dir} if project_dir else name

def resolve_last_project_config(config, config_path):
    # read "project_dir" from registry instead of "input_dir"
    project_dir_raw = last_project.get("project_dir")  # was "input_dir"
```

- [ ] **Step 3: config_routes.py:43, 187**

```python
# Line 43 — GET config response:
"project_dir": str(proj_dir),  # was "input_dir"

# Line 187 — editable paths set:
"paths": {"output_dir"},  # removed input_dir, recursive
```

- [ ] **Step 4: projects.py create/add API**

```python
# POST /api/project/create body:
input_dir_raw = (obj.get("input_dir") or "").strip()
→
project_dir_raw = (obj.get("project_dir") or "").strip()
```

- [ ] **Step 5: export.py:63** — source resolution

```python
# Before:
cfg.paths.input_dir,
# After:
load_selected_videos(cfg.project_dir)  # or use project_dir for jianying
```

- [ ] **Step 6: Commit**

```bash
git add clio/ui/handler_protocol.py clio/ui/server.py
git add clio/ui/services/project_service.py clio/ui/routes/projects.py
git add clio/ui/routes/config_routes.py clio/ui/routes/videos.py clio/ui/routes/export.py
git add clio/ui/routes/ clio/ui/services/
git commit -m "refactor(ui): rename input_dir to project_dir across UI backend"
```

---

### Task 7: Update clio/analyze.py, doctor.py, prompt_overrides.py

**Files:**
- Modify: `clio/analyze.py:121` — `_read_trip_context(str(config.project_dir))`
- Modify: `clio/doctor.py:131-136, 177-178` — update diagnosis
- Modify: `clio/prompt_overrides.py` — `_project_dir(config)` return `config.project_dir`

- [ ] **Step 1: clio/analyze.py:121**

```python
# Before:
text = _read_trip_context(str(config.paths.input_dir))
# After:
text = _read_trip_context(str(config.project_dir))
```

- [ ] **Step 2: clio/doctor.py**

```python
# Before:
input_dir = config.paths.input_dir
if input_dir.is_dir():
    videos = find_videos(input_dir, recursive=config.paths.recursive)
    print(f"  [OK] 素材目录 ({len(videos)} 个视频) - {input_dir}")
# After:
project_dir = config.project_dir
if project_dir and project_dir.is_dir():
    videos = load_selected_videos(project_dir)
    print(f"  [OK] 项目 '{project_dir.name}' ({len(videos)} 个视频)" )
else:
    print("  [INFO] 未指定项目，使用 -p/--project 选择项目")
```

- [ ] **Step 3: prompt_overrides.py`_project_dir()**

```python
def _project_dir(config: AppConfig) -> Path | None:
    return config.project_dir
```

- [ ] **Step 4: Commit**

```bash
git add clio/analyze.py clio/doctor.py clio/prompt_overrides.py
git commit -m "refactor: replace input_dir with project_dir in analyze, doctor, prompt_overrides"
```

---

### Task 8: CLI — add -p/--project, keep -i/--input as alias

**Files:**
- Modify: `clio/main.py:22-45`

- [ ] **Step 1: Update _add_io_args**

```python
def _add_io_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "-p", "--project",
        type=Path,
        help="项目目录（包含 project.yaml）",
    )
    parser.add_argument(
        "-i", "--input",
        type=Path,
        help=argparse.SUPPRESS,  # hidden compat alias for -p
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        help="输出目录覆盖",
    )
```

- [ ] **Step 2: Update _prepare_config**

```python
def _prepare_config(config_path: Path, args: argparse.Namespace):
    raw_input = getattr(args, "input", None)
    raw_project = getattr(args, "project", None)
    project_dir = raw_project or raw_input
    if project_dir and project_dir.is_dir():
        project_dir = project_dir
    else:
        project_dir = Path.cwd()
    config = load_config(config_path, project_dir=project_dir)
    output_override = getattr(args, "output", None)
    if output_override:
        config = apply_run_paths(config, output_override)
    return config
```

- [ ] **Step 3: Update serve command (no -p needed)**

No change needed — `serve` already uses `resolve_last_project_config`.

- [ ] **Step 4: Commit**

```bash
git add clio/main.py
git commit -m "feat(cli): add -p/--project flag, keep -i/--input as compat alias"
```

---

### Task 9: Migration tool

**Files:**
- Create: `clio/tasks/migrate.py`
- Modify: `clio/main.py:235-236` — add `migrate` subcommand

- [ ] **Step 1: Create migrate.py**

```python
from __future__ import annotations

import json
import shutil
from pathlib import Path

import yaml

from clio.config.loader import _find_original_for_stem  # or use find_videos
from clio.tasks._video_loader import save_selected_videos
from clio.utils import find_videos


def run_migrate(config_path: Path, from_path: Path | None = None) -> tuple[int, list[str]]:
    """Scan and migrate old projects to new format.
    
    Returns (updated_count, error_messages).
    """
    registry_file = config_path.parent / "projects.json"
    projects_to_migrate: list[Path] = []
    errors: list[str] = []
    
    # 1. From registry
    if registry_file.is_file():
        try:
            reg = json.loads(registry_file.read_text(encoding="utf-8"))
            for p_str in reg.get("projects", []):
                p = Path(p_str)
                if p.is_dir():
                    projects_to_migrate.append(p)
        except Exception:
            pass
    
    # 2. From --from flag
    if from_path:
        if from_path.is_dir() and (from_path / "project.yaml").is_file():
            projects_to_migrate.append(from_path)
    
    # Backup registry
    if registry_file.is_file():
        shutil.copy2(registry_file, registry_file.with_suffix(".json.migrate-bak"))
    
    updated = 0
    for old_dir in projects_to_migrate:
        old_yaml = old_dir / "project.yaml"
        if not old_yaml.is_file():
            continue
        
        # Read old config
        try:
            with old_yaml.open(encoding="utf-8") as f:
                old_raw = yaml.safe_load(f) or {}
        except Exception as e:
            errors.append(f"{old_dir}: 读取 project.yaml 失败: {e}")
            continue
        
        old_input = old_raw.get("paths", {}).get("input_dir", ".")
        old_input_path = (old_dir / old_input).resolve() if old_input != "." else old_dir
        
        # Default new project dir: <config_dir>/projects/<name>/
        name = old_raw.get("name") or old_dir.name
        new_dir = (config_path.parent / "projects" / name).resolve()
        
        print(f"迁移: {old_dir} → {new_dir}")
        new_dir.mkdir(parents=True, exist_ok=True)
        
        # 1. Copy project.yaml (remove input_dir/recursive)
        old_raw.pop("paths", None)
        yaml_data = old_raw
        yaml_data["paths"] = {"output_dir": "./output"}
        try:
            (new_dir / "project.yaml").write_text(
                yaml.dump(yaml_data, default_flow_style=False, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )
        except Exception as e:
            errors.append(f"{old_dir}: 写入 project.yaml 失败: {e}")
            continue
        
        # 2. Copy project.json if exists
        old_json = old_dir / "project.json"
        if old_json.is_file():
            shutil.copy2(old_json, new_dir / "project.json")
        
        # 3. Scan old input_dir for videos → videos.json
        videos = find_videos(old_input_path, recursive=True)
        save_selected_videos(new_dir, videos)
        print(f"  发现 {len(videos)} 个视频")
        
        # 4. Update registry
        new_entry = {
            "project_dir": str(new_dir.resolve()),
            "output_dir": str((new_dir / "output").resolve()),
            "name": name,
        }
        # Read current registry
        reg_entries = []
        if registry_file.is_file():
            try:
                reg = json.loads(registry_file.read_text(encoding="utf-8"))
                reg_entries = [e for e in reg.get("projects", []) if Path(e) != old_dir]
            except Exception:
                reg_entries = []
        reg_entries.append(new_entry)
        registry_file.write_text(
            json.dumps({"projects": reg_entries}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        
        # 5. Backup old project.yaml
        old_yaml.rename(old_dir / "project.yaml.migrate-bak")
        
        updated += 1
    
    return updated, errors
```

- [ ] **Step 2: Add migrate subcommand to main.py**

```python
p_migrate = sub.add_parser("migrate", help="将旧项目迁移到新结构（独立 project_dir + videos.json）")
p_migrate.add_argument("--from", type=Path, default=None, dest="from_path",
                       help="指定要迁移的项目路径（默认扫描注册表）")

# In dispatch:
elif args.command == "migrate":
    from clio.tasks.migrate import run_migrate
    updated, errors = run_migrate(config_path, args.from_path)
    print(f"已迁移 {updated} 个项目")
    for err in errors:
        print(f"  错误: {err}")
    return 0
```

- [ ] **Step 3: Commit**

```bash
git add clio/tasks/migrate.py clio/main.py
git commit -m "feat(cli): add migrate command for old project conversion"
```

---

### Task 10: Frontend — rename state fields + API calls

**Files:**
- Modify: `clio/ui/static/src/api.js:15-22`
- Modify: `clio/ui/static/src/main.js:44-153, 266-267`
- Modify: `clio/ui/static/src/sidebar-data.js:18-38, 314-323`
- Modify: `clio/ui/static/src/runner.js:84, 259, 322`
- Modify: `clio/ui/static/src/runner_feat.js:84, 198, 261`
- Modify: `clio/ui/static/src/runner_main.js:301`

The pattern across all files:
1. `state.currentProjectInputDir` → `state.currentProjectDir`
2. `state.config.input_dir` → `state.config.project_dir`
3. `p.input_dir` → `p.project_dir`
4. `?input_dir=` → `?project_dir=`
5. Delete the `run-input-dir` HTML input field

- [ ] **Step 1: Update api.js**

```javascript
// Line 22:
if (state.currentProjectDir) {
    url += `${sep}project_dir=${encodeURIComponent(state.currentProjectDir)}`;
}
```

- [ ] **Step 2: Update main.js**

```javascript
// Line 47:
const urlProjectDir = urlParams.get('project_dir');
// Line 74:
const body = { name, project_dir: inputDir };
// Line 97:
data-project-dir="${escapeHtml(p.project_dir)}"
// Line 103:
项目目录: ${escapeHtml(p.project_dir)}<br>
// Line 121:
const r2 = await api('POST', '/api/project/remove', { project_dir: card.dataset.projectDir });
// Line 136:
window.location.search = `?project=${encodeURIComponent(name)}&project_dir=${encodeURIComponent(projectDir)}`;
// Line 149:
const r = await api('POST', '/api/project/add', { project_dir: path });
```

- [ ] **Step 3: Update sidebar-data.js**

```javascript
// Line 18:
if (!state.currentProjectDir) state.currentProjectDir = state.currentProject.project_dir;
// Line 35:
state.config = { project_dir: '(加载失败)', output_dir: '' };
// Line 37:
$('proj-name').textContent = state.config.project_dir;
// Line 38:
$('proj-name').title = `project: ${state.config.project_dir}\noutput: ${state.config.output_dir}`;
// Line 314, 323:
素材目录: ${escapeHtml(state.config?.project_dir || '未知')}
```

- [ ] **Step 4: Update runner.js / runner_feat.js**

Remove the `run-input-dir` HTML input (lines ~84):
```javascript
// Delete entire <input id="run-input-dir"> element
```

And related body assignment (line ~259):
```javascript
// Delete: body.input_dir = runInputDir;
```

- [ ] **Step 5: Commit**

```bash
git add clio/ui/static/src/api.js clio/ui/static/src/main.js
git add clio/ui/static/src/sidebar-data.js
git add clio/ui/static/src/runner.js clio/ui/static/src/runner_feat.js
git add clio/ui/static/src/runner_main.js
git commit -m "refactor(ui): rename input_dir to project_dir in frontend state and API calls"
```

---

### Task 11: Frontend — add file browser + video management panel

**Files:**
- New: `clio/ui/static/src/file-browser.js` — file browser component
- New: `clio/ui/static/src/video-manager.js` — video management panel
- Modify: `clio/ui/static/src/main.js` — integrate panels

This task adds:
- A "视频管理" tab in the project view
- File browser that navigates directories and shows video files with checkboxes
- Selected videos display with remove capability
- API calls to POST/DELETE `videos.json` paths

This is a frontend-heavy task. Implementation details depend on the existing UI framework (vanilla ES modules). The engineer should follow existing patterns in `sidebar.js`, `editor-config.js`, etc.

- [ ] **Step 1: Create file-browser.js**

```javascript
// File browser module — directory tree + video file listing with checkboxes
// API: GET /api/fs/videos?path=<dir> returns list of video files
// Events: onSelect(paths: string[]), onLoadDirectory(dir: string)
```

- [ ] **Step 2: Create video-manager.js**

```javascript
// Video management panel — current videos list + file browser integration
// API: GET /api/projects/videos?project_dir=<path> — existing videos
// API: POST /api/projects/videos?project_dir=<path> — add videos
// API: DELETE /api/projects/videos?project_dir=<path> — remove videos
```

- [ ] **Step 3: Integrate into main.js**

Add a "视频管理" tab alongside existing tabs.

- [ ] **Step 4: Add backend API endpoints for video management**

In `clio/ui/routes/videos.py` or new route file:
```python
@handler.route("POST", "/api/projects/videos")
def handle_post_videos(qs, body):
    proj_dir = handler._resolve_project_dir(qs)
    paths = [Path(p) for p in body.get("paths", [])]
    existing = load_selected_videos(proj_dir)
    new_set = set(existing) | set(paths)
    save_selected_videos(proj_dir, list(new_set))
    return {"ok": True, "count": len(new_set)}

@handler.route("DELETE", "/api/projects/videos")
def handle_delete_videos(qs, body):
    proj_dir = handler._resolve_project_dir(qs)
    paths = {Path(p) for p in body.get("paths", [])}
    existing = load_selected_videos(proj_dir)
    remaining = [p for p in existing if p not in paths]
    save_selected_videos(proj_dir, remaining)
    return {"ok": True, "count": len(remaining)}
```

- [ ] **Step 5: Commit**

```bash
git add clio/ui/static/src/file-browser.js clio/ui/static/src/video-manager.js
git add clio/ui/static/src/main.js clio/ui/routes/videos.py
git commit -m "feat(ui): add file browser and video management panel"
```

---

### Task 12: Update config examples

**Files:**
- Modify: `config.example.yaml:15, 93-96`
- Modify: `docs/project.example.yaml:13-15, entire file`

- [ ] **Step 1: Update config.example.yaml**

Line 15: Remove `paths: input_dir, output_dir, recursive` from project-level list.
Line 93-96: No changes needed (global paths section stays same).

- [ ] **Step 2: Update docs/project.example.yaml**

```yaml
# 项目级配置示例（project.yaml）
#
# ...header comments keep same...

paths:
  # 注意：原始视频不再通过 input_dir 配置。
  # 请在 Web UI 中打开项目 → "视频管理" → 内嵌文件浏览器勾选。
  output_dir: "./output"

# ...rest of file stays same...
```

- [ ] **Step 3: Commit**

```bash
git add config.example.yaml docs/project.example.yaml
git commit -m "docs(config): remove input_dir/recursive from example configs"
```

---

### Task 13: Fix existing tests

**Files:**
- Modify: `clio/tests/test_run_preview.py:20-24`
- Modify: `clio/tests/test_tasks_cut.py:36`
- Modify: `clio/tests/test_tasks_compress.py:14`
- Modify: `clio/tests/test_tasks_label.py:28`
- Modify: `clio/tests/test_whisper_cli.py:17`
- Others as found

Pattern: `ProjectPathsConfig(input_dir=tmp_path / "videos", output_dir=... , recursive=False)` → `ProjectPathsConfig(output_dir=...)`.

Then add a `videos.json` fixture for tests that need video discovery:

```python
@pytest.fixture
def config_with_videos(tmp_path):
    out = tmp_path / "output"
    out.mkdir()
    cfg = AppConfig(
        global_cfg=load_global_config(),
        project_cfg=ProjectConfig(
            paths=ProjectPathsConfig(output_dir=out),
        ),
        project_dir=tmp_path,
    )
    # Write videos.json
    vids_dir = tmp_path / "videos"
    vids_dir.mkdir()
    (vids_dir / "A.MP4").write_bytes(b"video")
    (vids_dir / "B.mov").write_bytes(b"video")
    save_selected_videos(tmp_path, [vids_dir / "A.MP4", vids_dir / "B.mov"])
    return cfg
```

- [ ] **Step 1: Run all tests to see what breaks**

Run: `python -m pytest clio/tests/ --tb=short -x`
Expected: Failures in tests that construct `ProjectPathsConfig(input_dir=...)`.

- [ ] **Step 2-11: Fix each broken test file** (one commit per file or batch)

```bash
git add clio/tests/
git commit -m "test: fix tests after removing ProjectPathsConfig.input_dir"
```

---

### Plan Self-Review Checklist

1. **Spec coverage**: Every section in the spec has a corresponding task:
   - §1-3 (Motivation/concepts) → Covered in plan intro
   - §4.1 (models.py) → Task 1
   - §4.2 (loader.py) → Task 4
   - §4.3 (video_loader) → Task 3
   - §4.4 (find_videos replacement) → Task 5
   - §4.5 (sidecar location) → Covered in spec, no code change needed
   - §4.6 (AppConfig.project_dir) → Task 2
   - §4.7 (files parameter) → Already exists, no change needed
   - §4.8 (UI video service) → Task 6
   - §4.9 (cut.py) → Task 5
   - §4.10 (project.json migration) → Task 9
   - §4.11 (prompt_overrides) → Task 7
   - §4.12 (path consistency) → Spec reference, code changes covered in Task 4
   - §4.13 (API style) → Task 6 (routes)
   - §4.14 (other code points) → Task 7 (analyze/doctor/prompt_overrides)
   - §5 (UI) → Tasks 10, 11
   - §6 (project discovery) → Task 6 (registry)
   - §7 (migration) → Task 9
   - §8 (CLI) → Task 8
   - §9 (backward compat) → Task 9
   - §10 (phases) → Tasks 1-13
   - §11 (tests) → Task 13

2. **Placeholder scan**: No TBD/TODO/incomplete sections found.

3. **Type consistency**: `load_selected_videos(project_dir)` and `save_selected_videos(project_dir)` defined in Task 3, used consistently in Tasks 5, 7, 9, 11. `AppConfig.project_dir` defined in Task 2, used in Tasks 5, 7. `_resolve_project_dir` introduced in Task 6. Consistent.

4. **Completeness**: Every file from the File Map has a corresponding task. Every task has explicit code or an explicit pattern description.
