# Phase 4: Type and Schema Hardening — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish explicit type contracts across stable core modules, introduce route handler Protocol, add artifact schema versions, and progressively enforce via CI.

**Architecture:** Incremental per-module fixes at increasing strictness levels (default → `--check-untyped-defs` → eventual `--strict`). Phase 4a fixes core module mypy errors; Phase 4b introduces a typed Protocol for route handlers; Phase 4c adds `_schema_version` to artifacts; Phase 4d enables CI gate.

**Tech Stack:** Python 3.11, mypy, pytest, ruff

**Implementation principles:**
- Smallest change necessary; preserve runtime behavior
- Prefer `TypedDict`/`JsonValue` over `Any`; `type: ignore` only as last resort with rationale comment
- One module per commit; each step independently verifiable
- Success = stronger contracts, not zero errors

---

## File Structure Map

### New files
- `vlog_tool/ui/handler_protocol.py` — typed Protocol for route handler capabilities
- `vlog_tool/schema.py` — `ARTIFACT_SCHEMA_VERSION`, `add_schema_version()`, `check_schema_version()`

### Modified files (Phase 4a — core modules)
- `vlog_tool/config/loader.py` — fix `__dataclass_fields__` access
- `vlog_tool/config/validators.py` — same fix
- `vlog_tool/progress.py` — add `ProgressData` TypedDict
- `vlog_tool/export/__init__.py` — fix `FORMAT_REGISTRY` type
- `vlog_tool/utils.py` — add `JsonValue` type alias, widen `write_json_atomic` param
- `vlog_tool/analyze.py` — fix heterogeneous `set`
- `vlog_tool/split.py` — fix `write_json_atomic` call with list
- `vlog_tool/tasks/transcribe.py` — fix variable reuse
- `vlog_tool/tasks/cut.py` — fix `Path` vs `str`
- `vlog_tool/tasks/analyze.py` — fix `Optional` vs `dict`
- `vlog_tool/ai/factory.py` — fix `object.close()`
- `vlog_tool/whisper_cli.py` — fix overloaded `snapshot_download`
- `vlog_tool/pipeline.py` — fix `_STEP_FUNCS` typing
- `vlog_tool/ui/server.py` — add class-level type annotations
- `main.py` — fix variable reuse

### Modified files (Phase 4b — route handlers)
All `vlog_tool/ui/routes/*.py` — import `HandlerProtocol`, type `handler` param

### Modified files (Phase 4c — schema versions)
- `vlog_tool/analyze.py` — add `_schema_version`
- `vlog_tool/tasks/scripts.py` — add `_schema_version`
- `vlog_tool/tasks/plan.py` — add `_schema_version`
- `vlog_tool/tasks/transcribe.py` — add `_schema_version`
- `vlog_tool/progress.py` — add `_schema_version`
- `vlog_tool/processing_state.py` — add `_schema_version`

### Modified files (Phase 4d — CI)
- `.github/workflows/test.yml` — add mypy step

---

## Task 1: Add `JsonValue` type alias and widen `write_json_atomic`

**Files:**
- Modify: `vlog_tool/utils.py`

- [ ] **Step 1: Add `JsonValue` type alias and update `write_json_atomic`**

In `vlog_tool/utils.py`, add the import and type alias near the top:

```python
from typing import TypeVar, TypeAlias  # TypeAlias is new

JsonValue: TypeAlias = "str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]"
```

Change `write_json_atomic` signature:

```diff
- def write_json_atomic(path: Path, data: dict, *, ensure_ascii: bool = False, indent: int = 2) -> None:
+ def write_json_atomic(path: Path, data: JsonValue, *, ensure_ascii: bool = False, indent: int = 2) -> None:
```

- [ ] **Step 2: Run verification**

```powershell
& ".venv\Scripts\python.exe" -m pytest vlog_tool/tests/ -q
& ".venv\Scripts\python.exe" -m ruff check vlog_tool/
& ".venv\Scripts\python.exe" -m mypy vlog_tool/utils.py --check-untyped-defs
```

- [ ] **Step 3: Commit**

```powershell
git add vlog_tool/utils.py
git commit -m "feat(types): add JsonValue type alias, widen write_json_atomic param"
```

---

## Task 2: Fix `FORMAT_REGISTRY` type

**Files:**
- Modify: `vlog_tool/export/__init__.py`

- [ ] **Step 1: Add import and fix type**

```diff
+from collections.abc import Callable
 from pathlib import Path

- FORMAT_REGISTRY: dict[str, type] = {"jianying": export_plan_to_jianying}
+ FORMAT_REGISTRY: dict[str, Callable[..., Path]] = {"jianying": export_plan_to_jianying}
```

- [ ] **Step 2: Verification**

- [ ] **Step 3: Commit**

```powershell
git add vlog_tool/export/
git commit -m "fix(types): correct FORMAT_REGISTRY value type to Callable"
```

---

## Task 3: Fix `__dataclass_fields__` in config/loader.py and config/validators.py

**Files:**
- Modify: `vlog_tool/config/loader.py:115`
- Modify: `vlog_tool/config/validators.py:5`

- [ ] **Step 1: Fix `loader.py`**

Replace:
```python
for fd in dc_type.__dataclass_fields__.values():
```

With:
```python
for fd in getattr(dc_type, "__dataclass_fields__", {}).values():
```

- [ ] **Step 2: Fix `validators.py`**

Replace:
```python
fields = {f.name for f in dc.__dataclass_fields__.values()}
```

With:
```python
fields = {f.name for f in getattr(dc, "__dataclass_fields__", {}).values()}
```

- [ ] **Step 3: Verification**

```powershell
& ".venv\Scripts\python.exe" -m mypy vlog_tool/config/ --check-untyped-defs
```

- [ ] **Step 4: Commit**

```powershell
git add vlog_tool/config/
git commit -m "fix(types): use getattr for __dataclass_fields__ to satisfy mypy"
```

---

## Task 4: Fix `progress.py` with `ProgressData` TypedDict

**Files:**
- Modify: `vlog_tool/progress.py`

- [ ] **Step 1: Add TypedDict and annotate `_data`**

Add import:
```python
from typing import TypedDict
```

Add before the `ProgressTracker` class:
```python
class ProgressData(TypedDict):
    phase: str
    current: int
    total: int
    message: str
    status: str
    started_at: str
    eta_sec: float | None
    rerun: bool
    rerun_video: str | None
    logs: list[str]
```

Change `_data` declaration:
```diff
-         self._data = {
+         self._data: ProgressData = {
```

The existing code already assigns `self._data["phase"]` etc. with proper types, so mypy should be satisfied. The arithmetic at lines 74-78 uses `self._data["total"]` and `self._data["current"]` which are `int` fields in the TypedDict, so the `+`, `-`, `/`, `<` operations will type-check correctly.

- [ ] **Step 2: Verification**

```powershell
& ".venv\Scripts\python.exe" -m mypy vlog_tool/progress.py --check-untyped-defs
```

- [ ] **Step 3: Commit**

```powershell
git add vlog_tool/progress.py
git commit -m "fix(types): add ProgressData TypedDict for type-safe progress tracking"
```

---

## Task 5: Fix `pipeline.py` — type `_STEP_FUNCS`

- [ ] **Step 1: Check `_STEP_FUNCS` definition**

Read its definition in `vlog_tool/pipeline.py`:

```python
_STEP_FUNCS: dict[str, Callable[..., Any]] = {
    ...
}
```

If it lacks a type annotation, add one. The values are functions with varying signatures (some take `(config, day_label, tracker, **kwargs)`, others take `(config, tracker, **kwargs)`). Use `Callable[..., Any]` because the signatures are genuinely heterogeneous.

- [ ] **Step 2: Verification**

```powershell
& ".venv\Scripts\python.exe" -m mypy vlog_tool/pipeline.py --check-untyped-defs
```

- [ ] **Step 3: Commit**

```powershell
git add vlog_tool/pipeline.py
git commit -m "fix(types): type _STEP_FUNCS as dict[str, Callable[..., Any]]"
```

---

## Task 6: Fix per-file type mismatches (analyze.py, split.py, tasks/*.py, factory.py, whisper_cli.py)

**Files:**
- Modify: `vlog_tool/analyze.py:284`
- Modify: `vlog_tool/split.py:103`
- Modify: `vlog_tool/tasks/transcribe.py`
- Modify: `vlog_tool/tasks/cut.py:206-207`
- Modify: `vlog_tool/tasks/analyze.py:124`
- Modify: `vlog_tool/ai/factory.py:60,62,94`
- Modify: `vlog_tool/whisper_cli.py:14,89`

- [ ] **Step 1: Fix `analyze.py:284` — heterogeneous set**

Change:
```python
valid_ints = set()
```
To:
```python
valid_ints: set[int | str] = set()
```

- [ ] **Step 2: Fix `split.py:103` — `write_json_atomic` with list**

The param type was already widened to `JsonValue` in Task 1, so the call `write_json_atomic(manifest_path, manifest)` where `manifest` is `list[dict]` should now type-check. Verify by running mypy.

- [ ] **Step 3: Fix `tasks/transcribe.py` — run mypy to get current errors, then fix**

The line numbers may have shifted since the initial scan. First run:
```powershell
& ".venv\Scripts\python.exe" -m mypy vlog_tool/tasks/transcribe.py --check-untyped-defs
```

Common fixes needed:
- Variable `segments` reused with incompatible types → rename shadowing variables
- `progress_callback(None)` guard already exists (line 328), but if mypy still sees `None` not callable, add cast: `cast(Callable, progress_callback)(10)`
- `idx` variable conflict if used before assignment or with mismatched types

- [ ] **Step 4: Fix `tasks/cut.py:206-207` — `Path` vs `str`**

```python
src = matching_texts[0]  # Path
data = json.loads(src.read_text(encoding="utf-8"))  # src is Path, .read_text() exists
```

The error says `Path` assigned to `str` and `str` has no `read_text`. This means `matching_texts` is typed as `list[str]` somewhere. The `glob()` method on `Path` returns `list[Path]`, but maybe `config.texts_dir` is typed as `str` instead of `Path`.

**Fix**: `src: Path = matching_texts[0]` if it's already correct at runtime, or cast.

- [ ] **Step 5: Fix `tasks/analyze.py:124` — `Optional` vs `dict`**

```python
identity = load_identity(analysis) or resolve_identity(...)
```

Here `analysis` is passed to `load_identity` which expects `dict`. `analysis` could be `None` if it was loaded from a missing/failed file.

**Fix**: Guard before calling:
```python
identity = load_identity(analysis) if analysis is not None else None
if identity is None:
    identity = resolve_identity(compressed, config.paths.input_dir, idx_str)
```

- [ ] **Step 6: Fix `factory.py:60,62,94` — `object` has no `close()`**

The `_build_provider` function returns a provider whose return type is `object` or untyped. Need to check the actual function and give it a proper return type annotation.

**Fix**: Either cast the result:
```python
provider = cast(TextAIProvider, _build_provider(...))
```
Or properly annotate `_build_provider`'s return type as `TextAIProvider | VideoAIProvider`.

- [ ] **Step 7: Fix `whisper_cli.py` — `snapshot_download` overloads**

The `_snapshot_download = None` assignment (line 14) causes mypy to infer the type as `None`, conflicting with the overloaded function type from `huggingface_hub`.

**Fix**: 
```python
_snapshot_download: Any
```
Since the type is truly dynamic here (import may fail). Add a comment: `# type narrowing via guard below`.

- [ ] **Step 8: Run verification after each file fix**

```powershell
& ".venv\Scripts\python.exe" -m pytest vlog_tool/tests/ -q
& ".venv\Scripts\python.exe" -m ruff check vlog_tool/
```

- [ ] **Step 9: Commit each file separately**

Example:
```powershell
git add vlog_tool/analyze.py
git commit -m "fix(types): annotate heterogeneous set[int | str] in analyze.py"
```

---

## Task 7: Fix test file typing errors

**Files:** Multiple test files (~30 errors total)

- [ ] **Step 1: Fix tests that pass `SimpleNamespace` as `AppConfig`**

Replace `SimpleNamespace(...)` with `unittest.mock.MagicMock(spec=AppConfig)` or a test helper `make_config(...)`.

For the most common pattern:
```python
# Before:
config = SimpleNamespace(paths=SimpleNamespace(...), ...)
# After:
from unittest.mock import MagicMock
config = MagicMock(spec=AppConfig)
config.paths.output_dir = Path(tmp_path)
```

- [ ] **Step 2: Fix typed test files individually** (`test_config_descriptions.py`, `test_tasks_compress.py`, `test_tasks_analyze.py`, `test_helpers.py`, `test_compress.py`, `test_pipeline.py`, `test_export.py`, `test_file_service.py`, `test_ai_openai_compat.py`, `test_ai_gemini.py`, `test_routes_transcripts.py`)

- [ ] **Step 3: Verification**

```powershell
& ".venv\Scripts\python.exe" -m pytest vlog_tool/tests/ -q
```

- [ ] **Step 4: Commit**

```powershell
git add vlog_tool/tests/
git commit -m "fix(types): replace SimpleNamespace with MagicMock(spec=...) in tests"
```

---

## Task 8: Fix `server.py` class-level attribute annotations

**Files:**
- Modify: `vlog_tool/ui/server.py`

- [ ] **Step 1: Add missing class attribute annotations inside `Handler` class**

Add inside the `Handler` class body:
```python
class Handler(BaseHTTPRequestHandler):
    _project_states: dict[str, _ServerState]
    _config_cache: ConfigCache
    DEFAULT_PROJECT: dict = {}
    _api_token: str | None = None
    input_dir: Path | None = None
    output_dir: Path | None = None
    config_path: Path | None = None
    server: BaseHTTPRequestHandler
```

The dynamically-set attributes (`_api_token`, `input_dir`, `output_dir`, `config_path`) now have class-level declarations, so mypy won't complain about `Handler._api_token` etc.

Also fix line 141:
```diff
-         server: BaseHTTPRequestHandler
+         server: BaseHTTPRequestHandler  # type: ignore[assignment]  # base class defines as BaseServer
```

- [ ] **Step 2: Verification**

```powershell
& ".venv\Scripts\python.exe" -m mypy vlog_tool/ui/server.py --check-untyped-defs
```

- [ ] **Step 3: Commit**

```powershell
git add vlog_tool/ui/server.py
git commit -m "fix(types): add class-level annotations for dynamic Handler attributes"
```

---

## Task 9: Fix `main.py` — variable reuse

**Files:**
- Modify: `main.py:376-377`

- [ ] **Step 1: Fix `except: block` variable reuse**

The error says `Assignment to variable "e" outside except: block` and `Trying to read deleted variable "e"`. This means `e` is used both inside and outside the `except Exception as e:` block.

**Fix**: Separate the variable — use `exc` inside the except block:
```python
except Exception as exc:
    ...
    e = exc  # e is now defined outside except
```

- [ ] **Step 2: Verification**

```powershell
& ".venv\Scripts\python.exe" -m mypy main.py --check-untyped-defs
```

- [ ] **Step 3: Commit**

```powershell
git add main.py
git commit -m "fix(types): avoid variable reuse across except boundary in main.py"
```

---

## Task 10: Create HandlerProtocol

**Files:**
- Create: `vlog_tool/ui/handler_protocol.py`

- [ ] **Step 1: Create `handler_protocol.py`**

```python
"""Typed Protocol for dynamic handler methods attached in server.py's make_handler()."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from vlog_tool.config import AppConfig


class HandlerProtocol(Protocol):
    """Minimal typed interface for stable cross-route handler capabilities.

    Route-specific helpers (_get_state, _resolve_texts, _resolve_in, etc.)
    remain dynamically typed until they stabilize — mark with
    `# type: ignore[attr-defined]  # TODO(phase4): add to Protocol when stable`.
    """

    def _send_json(self, data: Any, status: int = 200) -> None: ...
    def _send_bytes(self, data: bytes, content_type: str = "application/octet-stream", status: int = 200) -> None: ...
    def _send_static(self, rel: str) -> None: ...
    def _resolve_project_input(self, qs: dict[str, str]) -> Path | None: ...
    def _get_project_output(self, qs: dict[str, str]) -> Path | None: ...
    def _get_config(self, project_dir: str | None = None) -> AppConfig: ...
    def _send_video_range(self, path: Path, range_header: str | None) -> None: ...

    # Stable class-level attributes (set via make_handler)
    config_path: Path
    input_dir: Path | None
    output_dir: Path | None
    _api_token: str | None
    _config_cache: Any
```

- [ ] **Step 2: Verification — mypy passes without usage sites yet**

```powershell
& ".venv\Scripts\python.exe" -m mypy vlog_tool/ui/handler_protocol.py --check-untyped-defs
```

- [ ] **Step 3: Commit**

```powershell
git add vlog_tool/ui/handler_protocol.py
git commit -m "feat(types): add HandlerProtocol for route handler type contracts"
```

---

## Task 11-25: Update each route handler module to use HandlerProtocol

**For each route file, same pattern:**

1. Add import: `from vlog_tool.ui.handler_protocol import HandlerProtocol`
2. Change function signature: `def handle_xxx(handler: BaseHTTPRequestHandler, ...)` → `def handle_xxx(handler: HandlerProtocol, ...)`
3. For helpers not in Protocol (`_get_state`, `_resolve_texts`, etc.), add `# type: ignore[attr-defined]  # TODO(phase4): add to Protocol when stable`
4. Run `mypy` on the file
5. Commit per-file

Route files to update (one commit per file):
- `vlog_tool/ui/routes/config_routes.py`
- `vlog_tool/ui/routes/env_routes.py`
- `vlog_tool/ui/routes/export.py`
- `vlog_tool/ui/routes/fs.py`
- `vlog_tool/ui/routes/plan.py`
- `vlog_tool/ui/routes/processing_state_routes.py`
- `vlog_tool/ui/routes/projects.py`
- `vlog_tool/ui/routes/refine.py`
- `vlog_tool/ui/routes/run.py`
- `vlog_tool/ui/routes/static_files.py`
- `vlog_tool/ui/routes/texts.py`
- `vlog_tool/ui/routes/videos.py`
- `vlog_tool/ui/routes/whisper_routes.py`
- `vlog_tool/ui/routes/token_routes.py`
- `vlog_tool/ui/routes/transcript_routes.py`

- [ ] **Step for each file** — see detailed example for `config_routes.py`:

```python
# At top of config_routes.py:
from vlog_tool.ui.handler_protocol import HandlerProtocol
```

Change function signatures from:
```python
def handle_get_config(handler: BaseHTTPRequestHandler, qs: dict) -> None:
```
to:
```python
def handle_get_config(handler: HandlerProtocol, qs: dict[str, str]) -> None:
```

For helpers not in Protocol:
```python
project_dir = handler._resolve_project_input(qs)  # type: ignore[attr-defined]  # TODO(phase4): add to Protocol when stable
```

Run verification after each:
```powershell
& ".venv\Scripts\python.exe" -m pytest vlog_tool/tests/ -q
git add vlog_tool/ui/routes/<file>.py
git commit -m "fix(types): use HandlerProtocol in <file>.py"
```

---

## Task 26: Create `vlog_tool/schema.py` for artifact versioning

**Files:**
- Create: `vlog_tool/schema.py`
- Modify: `vlog_tool/analyze.py`, `vlog_tool/tasks/scripts.py`, `vlog_tool/tasks/plan.py`, `vlog_tool/tasks/transcribe.py`, `vlog_tool/progress.py`, `vlog_tool/processing_state.py`

- [ ] **Step 1: Create `schema.py`**

```python
"""Lightweight schema versioning for generated JSON artifacts."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

ARTIFACT_SCHEMA_VERSION = 1


def add_schema_version(data: dict) -> dict:
    """Add current schema version to a data dict in-place. Returns the same dict."""
    data["_schema_version"] = ARTIFACT_SCHEMA_VERSION
    return data


def check_schema_version(data: dict, label: str = "artifact") -> bool:
    """Check schema version. Logs warning on mismatch. Returns True if matching."""
    v = data.get("_schema_version")
    if v != ARTIFACT_SCHEMA_VERSION:
        logger.warning("%s schema v%s != current v%s — may cause unexpected behavior", label, v, ARTIFACT_SCHEMA_VERSION)
        return False
    return True
```

- [ ] **Step 2: Integrate into `analyze.py`**

After building the analysis dict, before `write_json_atomic`:
```python
from vlog_tool.schema import add_schema_version
...
result = add_schema_version(result)
```

- [ ] **Step 3: Integrate into `tasks/scripts.py`**

After building voiceover dict:
```python
from vlog_tool.schema import add_schema_version
...
data = add_schema_version(data)
```

- [ ] **Step 4: Integrate into `tasks/plan.py`**

After building plan dict:
```python
from vlog_tool.schema import add_schema_version
...
result = add_schema_version(result)
```

- [ ] **Step 5: Integrate into `tasks/transcribe.py`**

After building transcript dict:
```python
from vlog_tool.schema import add_schema_version
...
transcript = add_schema_version(transcript)
```

- [ ] **Step 6: Integrate into `progress.py`**

In `__init__`, add to `_data`:
```python
self._data: ProgressData = {
    ...
    "_schema_version": 1,
}
```
And add `_schema_version` to `ProgressData` TypedDict:
```python
class ProgressData(TypedDict):
    ...
    _schema_version: int
```

- [ ] **Step 7: Integrate into `processing_state.py`**

After building state dict:
```python
from vlog_tool.schema import add_schema_version
...
state = add_schema_version(state)
```

- [ ] **Step 8: Verification**

```powershell
& ".venv\Scripts\python.exe" -m pytest vlog_tool/tests/ -q
```

- [ ] **Step 9: Commit**

```powershell
git add vlog_tool/schema.py vlog_tool/analyze.py vlog_tool/tasks/ vlog_tool/progress.py vlog_tool/processing_state.py
git commit -m "feat(schema): add artifact schema versioning with _schema_version field"
```

---

## Task 27: Enable CI gate for strict modules

**Files:**
- Modify: `.github/workflows/test.yml`

- [ ] **Step 1: Add mypy step to CI**

After the existing test step:
```yaml
- name: mypy core modules
  if: always()
  run: python -m mypy vlog_tool/config/ vlog_tool/utils.py vlog_tool/progress.py vlog_tool/schema.py vlog_tool/export/ --check-untyped-defs
```

Start with only the modules that are clean. Add more as they're fixed.

- [ ] **Step 2: Commit**

```powershell
git add .github/workflows/test.yml
git commit -m "ci(mypy): add --check-untyped-defs gate for cleaned core modules"
```

---

## Verification Summary

After every task, run:
```powershell
& ".venv\Scripts\python.exe" -m pytest vlog_tool/tests/ -q
& ".venv\Scripts\python.exe" -m ruff check vlog_tool/
& ".venv\Scripts\python.exe" -m mypy <fixed_module> --check-untyped-defs
```
