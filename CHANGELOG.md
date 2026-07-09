# Changelog

## 2026-07-10

### Added (merged from feat/ui-redesign, PR #17/#18)
- R-010b: Confidence scoring (`_confidence` field in AI outputs)
- R-010c: Multi-model comparison CLI (`main.py compare-models`)
- R-010d: Backend prompt management API (`GET/PUT/DELETE /api/prompts`)
- R-010e: UI Prompt Management panel (Settings tab)
- R-016: Draggable UI layout (`layout.js`, localStorage persistence)
- R-019f: context_override propagation tests
- R-020: `main.py verify` sidecar integrity CLI (`clio/tasks/verify.py`)
- R-021: All-days planning (`plan --all-days`)
- R-022: Smart cover frame extraction (`clio/tasks/cover.py`)
- R-023: Transcript/visual timeline alignment (`clio/tasks/transcript_align.py`)
- R-025: Webhook trigger endpoint (`POST /api/webhook/trigger`)
- Provider connection test button + skipped diagnostics panel (CR-008)
- Video counterpart navigation (jump between compressed ↔ original)
- Toast notifications for key actions
- `whisper_cache.py` — Whisper model cache management
- `template/prompts/README.md` — prompt override documentation
- Config semantic validation for provider/task compatibility (CR-002)

### Fixed
- Runner.js and editor-plan.js merge corruption repaired
- Whisper model download completion flow
- Various test alignment with new `resolve_prompt_template` naming
- README restored from clean commit

## 2026-07-03

### Added
- R-017: Model Registry & Task Binding UI (14 commits, be636f2–2a712f7)
- ProviderConfig.models field for model name storage (be636f2)
- Tag input component for model name editing (c1c3ba9)
- Provider list UI with add/edit/delete in Settings Global tab (5d4c8fc)
- Task binding panel with dropdowns in Settings Project tab (87cd821)
- CSS styles for provider cards, task binding cards, modals, tag input (61d50b8)
- 39 unit tests for _renderProviderList and _renderTaskBinding (dd44169)

### Fixed
- Provider edit modal layout, default provider delete button hidden (9b9a7ab)
- Dirty state not triggered by default model population (86c88e7)
- Restore ai.debug_print_prompt/provider_ttl_min/ai.context fields lost during custom AI renderer refactor (fe63fe6)
- Various test assertions for provider card rendering and task binding (21307f5, 2a712f7)
- Video player onloadedmetadata for original source segments (a1e5b32)
- Edit modal hint about empty API key remaining unchanged (d550715)

## 2026-07-02

### Added
- Phase 6: Global vs Project Config Separation — config.yaml now holds only global settings, project.yaml holds per-project overrides
- New config format (V2): `config_version: V2` marker with auto-migration from V1
- `GlobalConfig`/`ProjectConfig` dataclasses with `CombinedX` read-only wrappers for backward compat
- `load_global_config()` / `load_project_config()` — per-layer loading
- V1→V2 migration: auto-split merged config.yaml into global-only + project.yaml on first load
- `/api/config/global` and `/api/config/project` — per-layer GET/PUT endpoints with field ownership validation
- Frontend config tab split (Global / Project / Merged views) in editor-config.js
- 36 new tests for V2 migration, combined wrappers, field validation, apply_run_paths
- `docs/project.example.yaml` — project-level config example

### Fixed
- `handle_put_config_raw` — layer validation now correctly handles split sections (e.g. `compress`) at field level
- V1→V2 migration now creates `project.yaml` for default project (not just projects.json-registered projects)
- V1→V2 migration no longer overwrites existing `project.yaml`
- `test_config.py` / `test_routes_config.py` — migrated 57 tests to new `AppConfig(global_cfg=..., project_cfg=...)` interface
- `test_tasks_cut/label/scripts/refine/transcribe/reindex` — migrated tests to use real dataclass instances instead of MagicMock
- `conftest.py` — `tmp_config` fixture now creates V2-format config.yaml + project.yaml

## 2026-07-01

### Added
- R-019: Run panel prompt injection — context_override textarea and task_prompts in POST /api/run (43a922b)

### Fixed
- B-097: Segment-specific text/script matching in video list — 3-strategy lookup replaces index-based [0] fallback (05edab2)
- B-073: `_parse_segment_info` now supports `_partNN`, `_ptNN`, `_chunkNN` in addition to `_segNN` (f2465cd)
- B-043: Pre-commit hook only re-stages files actually modified by ruff, not all staged files (25fe130)

### Changed
- B-088: ROADMAP archived — commit log, test coverage verification, code review audit moved to docs/archive/2026-07-01-roadmap-archive.md (88d7238)
- R-019f: context_override propagation — non-AI tasks swallow with `**kwargs`, AI tasks pass with explicit `context_override` param

## 2026-06-30

### Fixed
- Auto-highlight next segment when original video crosses segment boundary (viewer.js): playing a split original video now auto-jumps sidebar selection and loads the next segment's texts/voiceover without reloading the player (f0059db)

## 2026-06-26

### Added
- U-010a/b: Unit tests for 13 previously uncovered modules — overall coverage 82% → 89% (864 tests)
- New test files: `test_fs.py`, `test_static_files.py`, `test_token_routes.py`, `test_processing_state_routes.py`,
  `test_server.py`, `test_config_cache.py`, `test_refine_routes.py`, `test_shutdown.py`, `test_session_log.py`,
  `test_token_usage.py`, `test_reindex.py`, `test_export.py`, `test_export_routes.py`

### Changed
- README badge: tests 640+ → 860+

## 2026-06-25

### Added
- F-02 concurrent AI analysis: `ThreadPoolExecutor(max_workers)` for analyze step, per-video progress via `tracker.next()` (34dd5b5)
- U-002 provider cache TTL: `ai.provider_ttl_min` (default 60), expired providers auto-close on access (538064b)
- N-01 JianYing draft export: `vlog_tool/export/` package with FORMAT_REGISTRY dispatch, `draft_content.json` builder for JianYing 5.9 (f010db0, 559921c, 3349038)
- CLI `export` subcommand: `main.py export --format jianying --day day1` (008da7b)
- UI export button: "导出到剪映" in plan view, `POST /api/export` route (8e4be96, 3349038)

### Fixed
- B-02 plan state.mark key: fallback `source_stem` to JSON filename when `source_file` field is empty (bb86872)
- B-05 Whisper download: replace unsafe `PyThreadState_SetAsyncExc` with safe `requests.get(stream=True)` + chunked cancel check (6d452e6)
- B-05: restore detailed error messages via `_download_error_detail()` for HTTP/download failures
- F-02: restore `tracker.update(phase="analyze")` and per-video `tracker.next()` calls lost during refactoring

### Refactored
- A-01 server.py: move `_project_states={}` and `_config_cache=None` from class body to closure assignment (69c3321)

## 2026-06-24

### Fixed
- Transcribe: extract `_extract_orig_stem` helper, remove dead `_resolve_original_video`, fix state key for missing-original case, wire `progress_callback` to `_extract_audio` in rerun (7fc9b18)
- Transcribe: move `error_count` outside tracker guard so errors are always counted (5eabf52)
- Transcribe: from original video, CUDA fallback, centralized model download UX (428e275)

### Added
- Unit tests for files/overwrite params across all pipeline steps (fa5fee1)
- Fix review: label.py shadow, plan.py overwrite gate, type validation and tests (95b539f)

## 2026-06-22

### Added
- R-014 token usage tracking: `TokenUsage`, `AIResponse`, `FileTokenUsageStore`, Gemini/OpenAI provider usage extraction, UI Tokens panel, CLI `tokens` subcommand (01317f0–e875159)
- R-018 multi-video selection + step execution: sidebar checkboxes, `files`/`overwrite` params, pipeline filtering (3ace4f4–5b0a9c0)
- Config auto-upgrade: inject missing dataclass defaults on load (b4bd05b)
- Split reencode option for frame-accurate cuts (cd1da63)
- AI debug print prompt option (92a6d9e)
- Refine panel with context textarea and AI trigger button (089dc6a)

### Fixed
- Provider cache TOCTOU race + Gemini close leak (45e09e3)
- Transcribe thread-safe os.environ save/restore (9ef45e2)
- Config propagate max_tokens to ProviderConfig (dc3ad72)
- Various code review fixes (6efbcc3, 7017ff6, badb621, bdcc678)
- ffprobe integrity check for skip_existing (6c3c231)
- ETA fix: elapsed_total moved to finally block (94f4501)
- Restore missing analyze header in config.example.yaml (d799f21)

## 2026-06-20

### Added
- Whisper model UI download: POST /api/whisper/install with progress, download button in transcript tab (326fe46, e361f7d)
- Project remove + empty state UI (12c314e, 360b91a)
- Quick-launch serve scripts (fcbccf5)
- ENV_FIREWORKS_API_KEY support

### Fixed
- UI event binding order for empty state (aa720d8, c1584df)
- Lint + UT after empty-state changes (fe45f53)

## 2026-06-19

### Fixed
- Setup scripts: idempotency, input dir check, CUDA disk space (3a5eaed)
- Modal event binding before init early return (aa720d8)
- All event handlers before try block for empty state (c1584df)

## 2026-06-18

### Added
- R-012 preview progress bar: two-row layout, play/pause toggle, segment blocks with tooltip (298a729–5029ba1)
- UI layout overhaul: resizable panels, dark OLED theme (7f5c0d6)

### Fixed
- ProcessingState recorded after generating plan (a29a53c)
- max_tokens + temperature in OpenAI API calls (3660fea)
- compress MIN_VALID_SIZE 256→50KB (78a0b69)
- transcribe find_videos for recursive scanning (6d23de3)
- Trip context cache key includes file mtime (cdcc873)
- TRANSCRIPT_CONTEXT English→Chinese (3ce9ef3)
- Atomic writes for scripts/refine output (123c84f)
- Split clean up partial segments + atomic manifest (097a6ff)
- Stale existing files cleanup on source_file mismatch (eb93573)
- Structured validation for AI responses (129de90)
- Closure late-binding trap in progress callback (d410c4e)

## 2026-06-17

### Fixed
- 10 commits covering usability and code quality issues from comprehensive analysis (a29a53c–d410c4e):
  - Plan state recording, atomic writes, max_tokens validation
  - Closure trap fix, transcript Chinese, prompts validation

## 2026-06-16

### Fixed
- Second code review: 5 S0 + 5 S1 + 1 S2 items all fixed:
  - runner.js prog undefined (S0-1)
  - analyze.py transcript bound to source_stem (S0-2)
  - split.py missing manifest (S0-3)
  - Pipeline recovery atomic writes (S0-4)
  - /api/cut project query parameter (S1-1)
  - transcript UI _segNN stripping (S1-2)
  - _extract_audio ffmpeg parameter (S1-3)
  - Whisper batch gated by max_analyze_duration (S1-4)
  - AI provider cache composite key (S1-5)
  - Whisper model cache key device/compute_type (S2-3)

### Added
- Comprehensive code review: 6 Critical + 12 Important + 36 Minor, fixed 6+12+5

## Earlier

See git log for full history. Key milestones:
- Initial scaffold (commit 1)
- ffmpeg compress with comma escaping fix (commit 2)
- Whisper ASR full integration (commits ~98–112)
- Security fixes: _is_safe_basename, non-retryable 4xx (commits 113–118)
- UI fixes: video ref, state capture, btn guard (commits 119–122)
- Provider cache + test isolation (commits 130–131)
- CI fixes for ctranslate2 mock, Linux case, lint (commits 133–136)
- 27 new tests for whisper, processing_state, CLI (commit 137)
