# Phase 4: Type and Schema Hardening — Design Spec

**Date**: 2026-06-27  
**Source**: `docs/analysis/2026-06-26-project-review.md` §6 Phase 4  
**Current state**: 243 mypy errors in 39 files (checked 117 source files)

## 1. Strategy: Incremental Strict Mode

Rather than fixing all 243 errors at once, we apply mypy controls **per-module** and progressively expand the strict subset. Each module, once clean, is added to a `strict_modules` list that CI enforces.

```
Phase 4a: Core modules (config, utils, progress, vmeta, identity, export)
Phase 4b: Route handler Protocol
Phase 4c: Artifact schema versions
Phase 4d: CI gate for clean subset
```

### Why incremental?

- Each fix batch is small, reviewable, and independently verifiable
- Avoids introducing regressions from large-scale refactoring
- The 120+ route handler errors are noisy but low-risk; fixing them doesn't improve type safety until the Protocol exists
- Core module errors (config, progress, export) are the real contract risks

## 2. Phase 4a: Core Module Typing

### 2.1 `config/loader.py` + `config/validators.py` (5 errors)

**Problem**: `type.__dataclass_fields__` is unrecognized by mypy because `type` is generic.

**Fix**: Use `getattr(cls, "__dataclass_fields__", None)` with `cast(...)` or guard with `hasattr`. Alternative: `typing.get_type_hints(cls)` for field introspection.

**File**: `vlog_tool/config/loader.py:115`, `vlog_tool/config/validators.py:5`, `vlog_tool/tests/test_config_descriptions.py:40`

### 2.2 `progress.py` (8 errors)

**Problem**: `_data: dict` defaults to `dict[str, object]` in Python 3.11+ with `dict` bare annotation. Arithmetic and method calls on `object` fail mypy checks.

**Fix**: Use `TypedDict` for the progress data shape, or explicitly type `_data: dict[str, Any]` and add assertions before arithmetic operations:

```python
total: int = self._data.get("total", 0)  # type: ignore[assignment]
current: int = self._data.get("current", 0)
eta_sec: float | None = self._data.get("eta_sec")
```

Alternatively, cast in getter methods where the shape is known.

### 2.3 `export/__init__.py` (1 error)

**Problem**: `FORMAT_REGISTRY: dict[str, type]` has value type `type`, but actual values are `Callable[[...], Path]`.

**Fix**: Change type to `dict[str, Callable[..., Path]]` or define a `FormatExporter` Protocol.

### 2.4 `utils.py` / `utils_expanded.py`

**Problem**: `write_json_atomic` typed narrower than usage. Several functions accept `str | Path` but callers pass mixed types.

**Fix**: Widen JSON types — accept `Any` for JSON-serializable data, add proper overloads where needed.

### 2.5 `analyze.py`, `split.py`, `transcribe.py`, `cut.py`, `factory.py`

**Problem**: Various type mismatches — `Path` vs `str`, `int` vs `str` in sets, `None` not callable, variable redefinition.

**Fix**: Scoped per-file fixes:
- `analyze.py:284`: `set[str]` vs `set[int]` — align type
- `split.py:103`: `write_json_atomic` accepts `list[dict]` — widen param type
- `tasks/transcribe.py:250-251,342-343`: variable reuse with incompatible types — use separate variables
- `tasks/cut.py:206-207`: `Path` assigned to `str` variable — fix type annotation
- `tasks/analyze.py:124`: `Optional` vs `dict` — add guard
- `factory.py:60,62,94`: `object` has no `.close()` — cast or Protocol
- `whisper_cli.py:14,89`: incompatible overloads — add `type: ignore` or fix kwargs

### 2.6 Test file fixes (~30 errors)

**Problem**: Tests use `SimpleNamespace` as `AppConfig` mock.

**Fix**: Use `unittest.mock.create_autospec(AppConfig)` or `TestingAppConfig` dataclass. For simple cases, widen the production function signature to accept `Any` for config (since `AppConfig` is already a dataclass with no special methods).

### 2.7 `pipeline.py` (2 errors)

**Problem**: `cancel_event` typed as `callable` (builtins) vs `Callable`.

**Fix**: Change to `Callable` import from `typing`.

## 3. Phase 4b: Route Handler Protocol

### 3.1 Problem

Every route module references methods dynamically attached in `make_handler()`:

```python
# server.py
handler._send_json = lambda data, status=200: ...
handler._resolve_project_input = lambda qs: ...
handler._get_project_output = lambda qs: ...
```

Mypy sees `BaseHTTPRequestHandler` and reports ~120 errors for missing attributes.

### 3.2 Solution: `HandlerProtocol`

Define a `Protocol` in `vlog_tool/ui/handler_protocol.py`:

```python
from typing import Protocol, Any, runtime_checkable
from pathlib import Path
from vlog_tool.config import AppConfig

class HandlerProtocol(Protocol):
    """Typed interface for dynamic handler methods/attrs attached in make_handler()."""
    # Instance methods
    def _send_json(self, data: Any, status: int = 200) -> None: ...
    def _send_bytes(self, data: bytes, content_type: str = "application/octet-stream", status: int = 200) -> None: ...
    def _send_static(self, rel: str) -> None: ...
    def _resolve_project_input(self, qs: dict[str, str]) -> Path | None: ...
    def _get_project_output(self, qs: dict[str, str]) -> Path | None: ...
    def _get_config(self, project_dir: str | None = None) -> AppConfig: ...
    def _get_state(self, project: str | None) -> Any: ...
    def _resolve_texts(self, project_path: Path, qs: dict[str, str]) -> Path | None: ...
    def _resolve_in(self, project_path: Path, subdir: str, qs: dict[str, str]) -> Path | None: ...
    def _send_video_range(self, path: Path, range_header: str | None) -> None: ...

    # Class-level attributes (set via make_handler)
    config_path: Path
    input_dir: Path | None
    output_dir: Path | None
    DEFAULT_PROJECT: str
    _api_token: str | None
    _config_cache: dict  # used via cls._config_cache in some routes
```

### 3.3 Migration

1. Create `vlog_tool/ui/handler_protocol.py`
2. Import `HandlerProtocol` and change function signatures in all route modules
3. In `server.py`, annotate the handler class as conforming to `HandlerProtocol`:
   - Change `class Handler(BaseHTTPRequestHandler):` → `class Handler(BaseHTTPRequestHandler, HandlerProtocol):` (runtime: Protocol has no runtime impact with `@runtime_checkable`, but without the decorator it's purely structural)

**Note on `_config_cache`**: Some routes access it via `type(handler)._config_cache` (class-level). Since it's declared as an instance attribute in `HandlerProtocol`, mypy may still complain. Two options:
- a) Access via `handler._config_cache` instead (works at runtime because class attrs are visible from instances)
- b) Keep `type: ignore[attr-defined]` on class-level accesses and explain why
- Recommended: option (a) — simpler and still correct at runtime

### 3.4 File list to update (~15 files)

All under `vlog_tool/ui/routes/`:
- `config_routes.py`, `env_routes.py`, `export.py`, `fs.py`, `plan.py`
- `processing_state_routes.py`, `projects.py`, `refine.py`, `run.py`
- `static_files.py`, `texts.py`, `videos.py`, `whisper_routes.py`
- `token_routes.py`, `transcript_routes.py`

Plus: `vlog_tool/ui/server.py` (add Protocol conformance annotation), `vlog_tool/pipeline.py` (fix `cancel_event` type)

## 4. Phase 4c: Artifact Schema Versions

### 4.1 Design

- Add `_schema_version: int` to generated JSON artifacts
- Define `ARTIFACT_SCHEMA_VERSION = 1` in a central location (e.g., `vlog_tool/config/models.py` or new `vlog_tool/schema.py`)
- Write version on creation; read and warn on mismatch (no automatic migration)
- Tracked artifacts: analysis JSON, voiceover JSON, plan JSON, transcript JSON, progress JSON, processing state JSON

### 4.2 Implementation

```python
# vlog_tool/schema.py
ARTIFACT_SCHEMA_VERSION = 1

def add_schema_version(data: dict) -> dict:
    data["_schema_version"] = ARTIFACT_SCHEMA_VERSION
    return data

def check_schema_version(data: dict, label: str = "artifact") -> bool:
    v = data.get("_schema_version")
    if v != ARTIFACT_SCHEMA_VERSION:
        logger.warning("%s schema v%s != current v%s", label, v, ARTIFACT_SCHEMA_VERSION)
        return False
    return True
```

### 4.3 Integration points

- `vlog_tool/analyze.py`: after generating analysis JSON → `add_schema_version()` before write
- `vlog_tool/tasks/scripts.py`: after generating voiceover JSON → `add_schema_version()`
- `vlog_tool/tasks/plan.py`: after generating plan JSON → `add_schema_version()`
- `vlog_tool/tasks/transcribe.py`: after generating transcript JSON → `add_schema_version()`
- `vlog_tool/progress.py`: add `_schema_version` to progress dict
- `vlog_tool/processing_state.py`: add `_schema_version`

Reading side: log a warning on version mismatch, but continue processing (backward compatibility).

## 5. Phase 4d: CI Gate

### 5.1 mypy configuration

In `.github/workflows/test.yml`, add a step after the current test run:

```yaml
- name: mypy core modules
  run: python -m mypy vlog_tool/config/ vlog_tool/utils.py vlog_tool/progress.py vlog_tool/schema.py vlog_tool/identity.py vlog_tool/vmeta.py vlog_tool/export/ --check-untyped-defs
```

The module list grows as each module is cleaned. Initially empty (gate only activates when at least one module passes).

**Why `--check-untyped-defs` instead of `--strict`?** `--strict` also enables `disallow_untyped_defs`, `disallow_any_unimported`, etc., which would add errors for every unannotated function. We fix existing errors first, then progressively add annotations. `--check-untyped-defs` checks function bodies of untyped functions — strict enough to catch contract violations, loose enough not to require full annotation coverage immediately.

### 5.2 Local workflow

```bash
# Check cleaned module
python -m mypy vlog_tool/config/ --check-untyped-defs
# Add module when clean
python -m mypy vlog_tool/config/ vlog_tool/utils.py --check-untyped-defs
```

### 5.3 CI integration plan

1. First module clean → add to CI list (with `--check-untyped-defs`)
2. When core is clean → CI fails if core regresses
3. After route Protocol → add route modules
4. After all annotations complete → switch to `--strict` for entire project

## 6. Error Budget Summary

| Module | Current errors | Target | Priority |
|--------|---------------|--------|----------|
| `config/` | 5 | 0 | P0 (Phase 4a) |
| `progress.py` | 8 | 0 | P0 (Phase 4a) |
| `export/` | 1 | 0 | P0 (Phase 4a) |
| `analyze.py` | 1 | 0 | P1 (Phase 4a) |
| `split.py` | 1 | 0 | P1 (Phase 4a) |
| `tasks/transcribe.py` | 5 | 0 | P1 (Phase 4a) |
| `tasks/cut.py` | 2 | 0 | P1 (Phase 4a) |
| `tasks/analyze.py` | 1 | 0 | P1 (Phase 4a) |
| `factory.py` | 3 | 0 | P1 (Phase 4a) |
| `whisper_cli.py` | 3 | 0 | P1 (Phase 4a) |
| `pipeline.py` | 2 | 0 | P1 (Phase 4a) |
| Route handlers (15 files) | ~120 | 0 | P2 (Phase 4b) |
| Tests (multiple files) | ~30 | 0 | P3 (Phase 4a) |
| `server.py` | 5 | 0 | P2 (Phase 4b) |
| `main.py` | 2 | 0 | P3 |

## 7. Verification

After each fix batch:
1. `python -m pytest vlog_tool/tests/ -q` — 901 must pass
2. `ruff check vlog_tool/` — must be clean
3. `python -m mypy <fixed_module> --check-untyped-defs` — 0 errors for fixed modules
4. Overall error count decreases

## 8. Non-goals

- Not fixing P3-level mypy issues in tests (unless they block CI)
- Not refactoring route handlers into class-based views
- Not adding automatic migration for schema version mismatches
- Not adding new features — pure type/schema hardening
