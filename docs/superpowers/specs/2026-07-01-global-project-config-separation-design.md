# Global vs Project Config Separation

> **Phase 6** of the Project Review Remediation Plan (ROADMAP.md).
> Design approved 2026-07-01 via brainstorming session.

## 1. Problem Statement

Current `config.yaml` and `project.yaml` share the same schema (`AppConfig`) and merge at load time via `deep_merge`. This makes it impossible to:

- Distinguish "app-wide defaults" from "project-specific overrides"
- Prevent API keys from leaking into `project.yaml`
- Verify UI settings belong to the correct layer
- Support future V3 config changes without schema ambiguity

Confirmed real-world bug: `clio/ui/static/src/editor-plan.js:194` sends the full
merged `state.configRaw` (including `ai.providers` with API keys) via
`PUT /api/config/raw`. `handle_put_config_raw` writes it verbatim to `project.yaml`
for non-default projects — API keys leak to disk in project files.

## 2. Schema Boundary

Two independent dataclasses: `GlobalConfig` and `ProjectConfig`. No field overlap.

4 split sections (`paths`, `ai`, `compress`, `whisper`) have fields in both layers.
`export` stays entirely in ProjectConfig (export feature still evolving).

### GlobalConfig (`config.yaml`)

| Section | Fields | Rationale |
|---|---|---|
| `proxy` | `enabled`, `url` | System network layer |
| `server` | `api_token` | Server security |
| `naming` | `index_width` | Global naming convention |
| `paths` | `ffmpeg`, `ffprobe`, `logs_dir` | Tool paths, globally consistent |
| `ai` | `providers` (API keys, base URLs), `debug_print_prompt`, `provider_ttl_min` | Credentials + dev mode live in global |
| `compress` | `codec`, `fps`, `remove_audio`, `crf` | Encoding format defaults |
| `whisper` | `cache_dir`, `hf_endpoint` | System-wide download paths |

### ProjectConfig (`project.yaml`)

| Section | Fields | Rationale |
|---|---|---|
| `paths` | `input_dir`, `output_dir`, `recursive` | Each project has different media |
| `ai` | `tasks` (provider/task binding), `context`, `context_file` | Trip context + model selection per project |
| `compress` | `target_size_mb`, `max_width`, `split_max_min`, `splits_subdir`, `reencode_split` | Quality parameters per project |
| `analyze` | `compressed_subdir`, `texts_subdir`, `skip_existing`, `max_analyze_duration_min`, `max_workers` | Analysis strategy |
| `script` | `scripts_subdir`, `template_file`, `target_words` | Script generation |
| `plan` | `plans_subdir`, `max_clips_per_day`, `target_duration_sec`, `use_transcripts` | Plan generation |
| `whisper` | `enabled`, `model_size`, `language`, `device`, `max_segments_per_clip`, `transcripts_subdir` | Project-specific ASR config |
| `export` | `canvas_ratio`, `output_subdir`, `jianying_draft_dir`, `auto_copy_draft` | Entirely project-level (export feature still evolving) |

**Key rule**: `compress.*` split — encoding format in global, quality params in project.
`ai.*` split — providers in global, tasks/context in project.
`whisper.*` split — download cache in global, ASR config in project.
`export.*` stays in project (deferred decision).

## 3. Versioning & Migration

### 3.1 Version marker

`config.yaml` root gets a `config_version` field:

```yaml
config_version: "V1"  # Legacy: merged config.yaml
config_version: "V2"  # New: global config.yaml + per-project project.yaml
```

No `config_version` field is interpreted as `V1`.

### 3.2 Migration: V1 → V2

```python
# Sections entirely project-only (no split needed)
_PROJECT_ONLY_SECTIONS = {"analyze", "script", "plan", "export"}

# Sections entirely global-only (no split needed)
_GLOBAL_ONLY_SECTIONS = {"proxy", "server", "naming"}

# Split sections: keys that belong to project
_SPLIT_PROJECT_ONLY_KEYS = {
    "paths": {"input_dir", "output_dir", "recursive"},
    "compress": {"target_size_mb", "max_width", "split_max_min", "splits_subdir", "reencode_split"},
    "ai": {"tasks", "context", "context_file"},
    "whisper": {"enabled", "model_size", "language", "device", "max_segments_per_clip", "transcripts_subdir"},
}

# Split sections: keys that belong to global
_SPLIT_GLOBAL_ONLY_KEYS = {
    "paths": {"ffmpeg", "ffprobe", "logs_dir"},
    "ai": {"providers", "debug_print_prompt", "provider_ttl_min"},
    "compress": {"codec", "fps", "remove_audio", "crf"},
    "whisper": {"cache_dir", "hf_endpoint"},
}
```

Flow:
1. Read `config.yaml` — if `config_version` is not `V1`, skip
2. Back up `config.yaml` → `config.yaml.bak`
3. Strip project-only fields → write back as V2 `config.yaml` with `config_version: V2`
4. Iterate all known projects (from `projects.json`):
   a. Read existing `project.yaml` (if any)
   b. Keep only project-only fields
   c. Strip global-only fields
   d. Write back `project.yaml`
5. Mark migration complete

Run once, triggered at top of `load_config()`.

### 3.3 Validation

- Writing to global `config.yaml`: reject project-only fields
- Writing to `project.yaml`: reject global-only fields (especially `ai.providers` — API keys)

## 4. Backend Architecture

### 4.1 New dataclasses

```python
@dataclass
class GlobalConfig:
    proxy: ProxyConfig = field(default_factory=ProxyConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    naming: NamingConfig = field(default_factory=NamingConfig)
    paths: GlobalPathsConfig   # ffmpeg, ffprobe, logs_dir
    ai: GlobalAIConfig         # providers, debug_print_prompt, provider_ttl_min
    compress: GlobalCompressConfig   # codec, fps, remove_audio, crf
    whisper: GlobalWhisperConfig     # cache_dir, hf_endpoint

@dataclass
class ProjectConfig:
    paths: ProjectPathsConfig       # input_dir, output_dir, recursive
    ai: ProjectAIConfig             # tasks, context
    compress: ProjectCompressConfig # target_size_mb, max_width, etc.
    analyze: AnalyzeConfig          # fully project-only (unchanged)
    script: ScriptConfig            # fully project-only (unchanged)
    plan: PlanConfig                # fully project-only (unchanged)
    whisper: ProjectWhisperConfig   # enabled, model_size, etc.
    export: ExportConfig            # entirely project-level (unchanged)
```

### 4.2 AppConfig wrapper (read-only combined view)

`AppConfig` is retained as a **read-only runtime merged view** for backward
compatibility. Combined classes expose fields from both layers via explicit
properties. They do NOT support mutation — code that needs to write config must
go through `config.global_cfg` or `config.project_cfg` directly.

```python
@dataclass
class AppConfig:
    global_cfg: GlobalConfig
    project_cfg: ProjectConfig | None  # None when no project context

    # Read-only combined views (4 split sections)
    @property
    def paths(self) -> CombinedPaths: ...
    @property
    def ai(self) -> CombinedAIConfig: ...
    @property
    def compress(self) -> CombinedCompressConfig: ...
    @property
    def whisper(self) -> CombinedWhisperConfig: ...

    # Non-split sections accessed directly:
    # config.proxy, config.server, config.naming → from global_cfg
    # config.analyze, config.script, config.plan, config.export → from project_cfg
```

Combined classes expose every field from both Global* and Project* sub-configs:

```python
@dataclass
class CombinedPaths:
    """Read-only union of GlobalPathsConfig + ProjectPathsConfig fields."""
    _global: GlobalPathsConfig
    _project: ProjectPathsConfig | None

    @property
    def ffmpeg(self) -> str: return self._global.ffmpeg
    @property
    def ffprobe(self) -> str: return self._global.ffprobe
    @property
    def logs_dir(self) -> Path: return self._global.logs_dir
    @property
    def input_dir(self) -> Path:
        return self._project.input_dir if self._project else Path()
    @property
    def output_dir(self) -> Path:
        return self._project.output_dir if self._project else Path("./output")
    @property
    def recursive(self) -> bool:
        return self._project.recursive if self._project else False
```

**This is read-only**. Attempting `config.paths.input_dir = X` raises
`AttributeError` (no setter). Code that needs to mutate config:

```python
# CLI override: apply_run_paths mutates project_cfg directly
config.project_cfg.paths.input_dir = input_dir.resolve()

# Global settings mutation goes through global_cfg
config.global_cfg.paths.ffmpeg = new_ffmpeg
```

`apply_run_paths()` is updated to mutate `config.project_cfg.paths` directly
instead of going through the combined view (3 call sites in `main.py`).

A regression test asserts that every field accessible on the old flat
`AppConfig.paths` / `AppConfig.compress` / `AppConfig.ai` / `AppConfig.whisper`
still resolves through the combined wrapper.

### 4.3 Loading changes

```
load_config(config_path, project_dir=None) → AppConfig
  ├─ _load_dotenv(base)
  ├─ _migrate_if_needed(config_file)          # V1→V2 auto-migration
  ├─ _upgrade_config_file(config_file)
  ├─ global = load_global_config(config_file)  # pure GlobalConfig
  ├─ if project_dir:
  │    project = load_project_config(project_dir)  # pure ProjectConfig
  │    validate_project_only(raw)                  # reject global fields
  └─ return AppConfig(global, project)
```

`load_global_config()` and `load_project_config()` are the new public API.
`load_config()` is a backward-compat wrapper that composes both.

### 4.4 Cache changes

**Decision**: keep single `ConfigCache` instance. Refactor its internal
`load_config` call to use separate `load_global_config` + `load_project_config`.
This preserves correct mtime invalidation (current `ConfigCache` already tracks
both `config.yaml` and `project.yaml` mtimes per key) and avoids unnecessary
global re-parsing, while keeping route handler cache-invalidation calls mostly
unchanged.

**Route coupling**: `config_routes.py` calls
`handler.__class__._config_cache.invalidate_key(...)` at 3 sites (lines 102,
128, 148). These need minor updating — `.invalidate_key()` must clear both
global and project layer caches. A helper `_invalidate_config(project_key)` is
added to `ConfigCache` that handles this atomically.

### 4.5 API changes

| Endpoint | Current | New Behavior |
|---|---|---|
| `GET /api/config/raw` | Returns merged dict | Returns merged dict (keep for backward compat) |
| `GET /api/config/global` | — | Returns global-only YAML dict |
| `GET /api/config/project` | — | Returns project-only YAML dict |
| `PUT /api/config/global` | — | Writes to config.yaml, rejects project fields |
| `PUT /api/config/project` | (use raw) | Writes to project.yaml, rejects global fields |
| `GET /api/config` | Returns paths | Unchanged |

`PUT /api/config/raw` retained but deprecated — write per-layer endpoints
instead.

## 5. UI Design

### 5.1 Settings tab split

Current single settings form → three sub-tabs:

```
Settings
├─ [Global]  系统配置 (proxy, server, providers, ...)
├─ [Project] 项目配置 (tasks, context, pipeline params, ...)
└─ [Merged]  当前合并视图 (debug view)
```

### 5.2 Global tab

Renders from `GET /api/config/global`:
- `proxy` section (enabled checkbox + url)
- `server.api_token` (password field)
- `paths.ffmpeg`, `paths.ffprobe`, `paths.logs_dir`
- `ai.providers` — provider list with api_key (password), base_url, model configs
- `ai.debug_print_prompt`, `ai.provider_ttl_min`
- `naming.index_width`
- `compress.codec`, `compress.fps`, `compress.remove_audio`, `compress.crf`
- `whisper.cache_dir`, `whisper.hf_endpoint`
- `.env` editor (stays here — env vars are system-level)

### 5.3 Project tab

Renders from `GET /api/config/project`:
- `paths.input_dir` (read-only path display), `paths.output_dir`, `paths.recursive`
- `ai.tasks` — each task shows dropdown of registered providers + model selector
- `ai.context` — textarea
- `compress.target_size_mb`, `compress.max_width`, etc.
- `analyze`, `script`, `plan` — all fields
- `whisper.enabled`, `whisper.model_size`, etc.
- `export` — all fields

### 5.4 Merged tab (debug)

Renders the current `GET /api/config/raw` merged view, with each field annotated
by source (`[global]` or `[project]` badge). Read-only.

### 5.5 Prohibited field defense

- Backend `PUT /api/config/global`: validates no project-only fields → 400
- Backend `PUT /api/config/project`: validates no global-only fields → 400
- Frontend: renders each tab with only its allowed fields (never sends merged)

## 6. Backward Compatibility

- `load_config(config_path, project_dir)` still works → internally calls
  `load_global_config` + `load_project_config` + compose `AppConfig`
- All existing code (pipeline, CLI, routes) that uses `AppConfig` continues to
  work via `AppConfig` wrapper read-only properties
- `deep_merge` is **removed** — no more merge conflicts
- Config initialization (`POST /api/config/init`) creates a proper V2
  `project.yaml` from global config template

## 7. Implementation Plan

```
┌──────────────────────────────────────────────────────────────────┐
│ Plan: 2026-07-01-config-split.md (9 sub-tasks)                  │
├──────────────────────────────────────────────────────────────────┤
│ Sub-task 1: Dataclass definitions                               │
│   - GlobalConfig + Global*Config sub-dataclasses (5 new types)  │
│   - ProjectConfig + Project*Config sub-dataclasses (5 new types)│
│   - CombinedPaths / CombinedAIConfig / CombinedCompressConfig   │
│     CombinedWhisperConfig (read-only)                           │
│   - AppConfig wrapper with read-only combined properties        │
│   - apply_run_paths updated to mutate project_cfg directly      │
│   - Regression test: every old field still resolves              │
├──────────────────────────────────────────────────────────────────┤
│ Sub-task 2: V1→V2 migration logic                               │
│   - config_version: V1|V2 marker                                │
│   - _migrate_v1_to_v2(): strip fields, backup, write            │
│   - _migrate_if_needed() at top of load_config()                │
├──────────────────────────────────────────────────────────────────┤
│ Sub-task 3: loader.py split                                     │
│   - load_global_config(config_path) → GlobalConfig              │
│   - load_project_config(project_dir) → ProjectConfig            │
│   - load_config() → composition of both                         │
│   - Remove deep_merge                                           │
│   - Update _upgrade_config_file for two schemas                 │
├──────────────────────────────────────────────────────────────────┤
│ Sub-task 4: Cache + route coupling                              │
│   - ConfigCache internal refactor to call separate loaders      │
│   - _invalidate_config(key) atomically clears both layers       │
│   - Update 3 call sites in config_routes.py                     │
├──────────────────────────────────────────────────────────────────┤
│ Sub-task 5: API endpoints                                        │
│   - GET /api/config/global → GlobalConfig dict                  │
│   - GET /api/config/project → ProjectConfig dict                │
│   - PUT /api/config/global → writes config.yaml                 │
│   - PUT /api/config/project → writes project.yaml               │
│   - Validation: reject cross-layer fields                       │
├──────────────────────────────────────────────────────────────────┤
│ Sub-task 6: Frontend tab split                                  │
│   - Settings tab split into [Global] [Project] [Merged]         │
│   - Global tab: providers, proxy, server, etc.                  │
│   - Project tab: tasks, context, pipeline params                │
│   - Merged tab: read-only with [global]/[project] badges        │
├──────────────────────────────────────────────────────────────────┤
│ Sub-task 7a: Tests (migrate existing)                            │
│   - test_config.py (383 lines) → update AppConfig construction  │
│   - test_config_cache.py (295 lines) → adapt to loader split    │
│   - test_routes_config.py (262 lines) → update PUT payloads     │
│   - test_config_descriptions.py (105 lines)                     │
├──────────────────────────────────────────────────────────────────┤
│ Sub-task 7b: Tests (new)                                         │
│   - V1→V2 migration: merged config → split → verify fields      │
│   - Prohibited field rejection: PUT cross-layer → 400           │
│   - Combined wrapper regression: every field accessible          │
│   - apply_run_paths mutation through project_cfg                │
├──────────────────────────────────────────────────────────────────┤
│ Sub-task 8: Docs update                                          │
│   - README.md / README.en.md: two-file config structure          │
│   - config.example.yaml: V2 format (global-only)                 │
│   - ROADMAP.md: Phase 6 → [x]                                   │
│   - CHANGELOG.md                                                 │
└──────────────────────────────────────────────────────────────────┘
```
