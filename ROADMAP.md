# Roadmap

Feature tracking. Each feature is broken down into minimal executable sub-tasks (per `AGENTS.md` §6.1 "one feature, one commit").
Mark `[ ]` as `[x]` when done, `[~]` for in-progress, `[!]` for blocked.

Design discussions / decision history in `AGENTS.md`, implementation details in git log.

## Project Review Remediation Plan (2026-06-26)

**Source**: `docs/analysis/2026-06-26-project-review.md` §6

### Phase 1: High-confidence bug fixes ✅
- [x] 1. Parse `ai.provider_ttl_min` — commit `538064b`
- [x] 2. Fix `.env` hot reload (`_load_dotenv` override=True) — commit `e717ab4`
- [x] 3. Fix duplicate run progress clobbering — commit `c54fc17`
- [x] 4. Fix Whisper route project query + model save — commit `f4b84e0`

### Phase 2: Canonical media identity ✅
- [x] 1. `MediaIdentity` dataclass + `identity.py` — commit `2c95f18`
- [x] 2. Analysis JSON writes `media_identity` — commit `7179b30`
- [x] 3. Transcript JSON writes `media_identity` — commit `83c6132`
- [x] 4. `ClipRecord.identity` field — commit `5a86c95`
- [x] 5. Plan transcript injection fix — commit `943472e`
- [x] 6. JianYing export identity + offset — commit `cd717a0`
- [x] 7. UI videos route transcript matching — commit `0ce946f`
- [x] 8. cut.py prefers `media_identity` offset — commit `7ba48aa`
- [x] 9. Full regression (889→901 passed) — commit `ae56e6d`

### Phase 3: Security hardening ✅
- [x] 1. Backend auth — `ServerConfig`, `--token` CLI, `_require_auth()`, auto-generate on non-localhost — commit `767bc92`
- [x] 2. Frontend auth — `api.js` Bearer header + 401 modal, video `?token=` URL, auto-capture from URL — commit `767bc92`
- [x] 3. Auth tests (12 test cases) — commit `ae56e6d`
- [x] 4. Update README/UI docs with safe hosting guidance — this docs update

### Phase 4: Type and schema hardening ✅
- [x] 1. Fix type contracts in config, utils, progress, vmeta, export
- [x] 2. Introduce route handler protocols
- [x] 3. Add artifact schema versions and validators
- [x] 4. Make mypy fail CI for the cleaned subset

### Phase 5: Maintainability cleanup ✅
- [x] 1. Split large frontend modules — sidebar.js → 4 modules (sidebar-data, sidebar-rerun, sidebar-browse, sidebar)
- [x] 2. Split Whisper route module — whisper_routes.py → 3 modules (whisper_check, whisper_download, whisper_models)
- [x] 3. Replace normal-mode debug prints with structured logging — no leftover debug prints found; all remaining print() calls are intentional CLI output
- [x] 4. Add golden tests for export formats — 26 export tests pass

### Phase 6: Global vs Project Config Separation ✅

**Background**: Previously global `config.yaml` and per-project `project.yaml` shared the same schema and merged at load time, making it impossible to distinguish app-wide defaults from project-specific overrides.

**Design goals**:
- Global config (`config.yaml`): defines providers, Whisper model paths, UI listen address, default paths
- Project config (`project.yaml`): selects provider/task binding, sets AI context, configures pipeline steps
- No schema overlap: each setting lives in exactly one layer
- UI explicitly shows which layer each setting comes from (Global / Project / Merged sub-tabs)
- Provider configuration is exclusively global — API keys never in project.yaml

**Sub-tasks**:
- [x] Design spec (`docs/superpowers/specs/2026-07-01-global-project-config-separation-design.md`)
- [x] Backend: `load_global_config` + `load_project_config` + `GlobalConfig`/`ProjectConfig` dataclasses
- [x] Backend: `/api/config/global` and `/api/config/project` REST endpoints with field ownership validation
- [x] UI: Settings tab split into Global / Project / Merged sub-tabs (editor-config.js)
- [x] Migration: V1→V2 auto-migration on first load, creates `project.yaml` from V1 project fields
- [x] Provider config is exclusively global (API keys validated against leak to project.yaml)
- [x] 36 new tests + 918 existing tests migrated (954 total, all pass)

**Key design decisions**:
- `CombinedX` classes are read-only properties on `AppConfig`; mutation goes through `global_cfg`/`project_cfg` accessors
- V1→V2 migration backs up original config as `config.yaml.bak`
- `handle_put_config_raw` validates field ownership to prevent API key cross-layer leaks
- `_SECTION_DC_MAP` in `_upgrade_config_file` still uses old merged types (pending clean-up in future phase)

---

## Current Review Iteration (2026-07-04)

**Source**: `docs/analysis/2026-07-04-current-project-review.md`

### Completed Iterations
- [x] Config validation now rejects invalid numeric ranges for runtime-sensitive settings such as `analyze.max_workers`, compression dimensions, provider TTL/rate/retry values, and `max_tokens` - this update
- [x] UI original video browsing now honors `paths.recursive`, returns nested originals as safe relative paths, and serves them through bounded `/api/video` resolution - this update
- [x] Split staging no longer writes raw intermediate segments into `compressed/`; `run_compress_all()` now stages split inputs under `output/<splits_subdir>/` while keeping the manifest in `compressed/` for existing metadata lookup — this update
- [x] Example config and README drift reduced: DeepSeek defaults now include official model names used by `project.example.yaml`, Web UI `server.api_token` is documented in `config.example.yaml`, and README test-count badges now say 970+ — this update
- [x] Prompt debug logging now defaults off in config models, loader fallback, and examples to avoid writing full prompts/context/transcripts to logs unless explicitly enabled — this update
- [x] Token mode now requires auth for every `/api/*` GET route, including `/api/config`, while keeping the UI shell and static assets public — this update
- [x] `input_dir` query switching now only accepts the default project directory or directories registered in `projects.json`, preventing arbitrary existing directories from being treated as projects — this update

---

### Remaining Review Items

**Source**: `docs/analysis/2026-07-04-current-project-review.md`

High-value open items that are not already covered by completed fixes:

- [x] CR-001: Selected-video runs now filter later artifacts by canonical identity, not only filename stems.
  - Current risk: selected `002_GL010684.mp4` can miss `texts/002_<AI title>.json`, so `voiceover`, `label`, or `refine` may process zero files.
  - Proposed fix: add a shared artifact-selection helper that reads `media_identity.compressed_stem`, `media_identity.original_stem`, `compressed_file`, and index fallbacks.
  - Required verification: realistic selected filename plus AI-generated analysis JSON title.
- [x] CR-002: Config semantic validation now covers provider/task compatibility.
  - Validate provider `type` against supported adapters.
  - Validate `video_analyze` provider compatibility (`gemini`-type only).
  - Reject when a task model is not listed in its provider `models` if the provider declares a model list.
- [ ] CR-003: Make artifact identity a reusable project-level index service.
  - Build a single lookup layer for original -> compressed segments -> texts -> scripts -> transcripts -> plan usage.
  - Use it in `/api/videos`, selected-run filtering, rerun, label, cut, and export.
- [ ] CR-004: Move UI route authorization toward policy metadata.
  - Define route metadata for method/path/handler/auth policy.
  - Default `/api/*` to auth-required in token mode.
  - Add route-matrix tests so new endpoints cannot bypass token checks accidentally.
- [ ] CR-005: Revisit config auto-upgrade write behavior.
  - Current risk: PyYAML default injection can strip user comments and formatting.
  - Proposed direction: keep auto-upgrade for critical migrations; move optional default injection to explicit `migrate-config` or UI prompt.
- [ ] CR-006: Reduce frontend `innerHTML` interpolation risk.
  - Prefer DOM creation plus `textContent` for filenames, provider names, model names, project names, logs, and AI titles.
  - Add focused XSS regression tests around those values when frontend test runtime is upgraded.
- [ ] CR-007: Developer experience follow-ups.
  - Add local Node version check in setup scripts or docs; local Node 16 cannot run current Vitest/Vite, CI uses Node 22.
  - Document recommended lint command as `ruff check clio main.py` or exclude local assistant/generated directories from repo-wide lint.
  - Consider `python main.py doctor` for env, ffmpeg, API keys, config, model cache, and write-permission checks.
- [ ] CR-008: UX/observability follow-ups.
  - Add pre-run summary showing selected videos, resolved artifact count per step, expected skips, and warnings.
  - Add provider/model test connection button.
  - Add visible warnings when `debug_print_prompt=true` or LAN host mode is active.
  - Add "why skipped" panel based on `.processing.json`.

---

## In Progress

### U-002: ProviderManager (Phase 2 — Short-term)

**Source**: 2026-06-20 code review (`docs/analysis/2026-06-20-REVIEW-part1.md`)

**Background**: Current `_provider_cache` in `factory.py` already has composite key + thread safety (C2/C4 fixed), but no TTL/expiration/hot-reload. Long-running server accumulates HTTP sessions.

**Status**: ✅ **Done** (simple TTL added to `_build_provider`, no separate class — `538064b`)

**Acceptance Criteria**:
- ~`ai/manager.py`: `ProviderManager` class replaces module-level `_provider_cache`~ _inline in factory.py_
- ✅ TTL-based expiration (default 60min, `ai.provider_ttl_min`)
- ✅ `close_all()` via existing `_clear_provider_cache()` (called from `shutdown.py`)
- ❌ `hot_reload()` — not implemented (future work if needed)
- ✅ Maintain existing thread-safety + composite key + test isolation

### U-007: Whisper Cancel Safety (Phase 2)

**Source**: 2026-06-21 review part2 (`docs/analysis/2026-06-21-review_part2.md`)

**Background**: `whisper_routes.py` uses `ctypes.pythonapi.PyThreadState_SetAsyncExc` to kill download thread — unsafe (C extensions block injection, resource leaks). Replace with chunked download that checks cancel flag per-chunk.

**Status**: ✅ **Done** (`6d452e6`)

**Sub-tasks**:
- [x] U-007a: Replace `hf_hub_download` with chunked `requests.get(stream=True)` + `iter_content`
- [x] U-007b: Per-chunk `_INSTALL_CANCEL.is_set()` check for clean interrupt
- [x] U-007c: Remove `ctypes` thread-kill code
- [ ] U-007d: Update tests _(no existing tests for this code path — new tests deferred)_

### U-010: Server + fs.py Test Coverage (Phase 3 — Testing)

**Source**: 2026-06-21 review part2 (`docs/analysis/2026-06-21-review_part2.md`)

**Background**: `server.py` has 6% coverage, `fs.py` has 12% coverage. These are security-sensitive and critical files with minimal testing.

**Status**: ✅ **Done** (`c0e88fc`)

**Sub-tasks**:
- [x] U-010a: Add tests for `server.py` dispatch logic (do_GET/do_PUT/do_POST routing) — 90% coverage
- [x] U-010b: Add tests for `fs.py` directory browsing (boundary cases, permission errors) — 96% coverage
- [x] U-010c: Add tests for `whisper_routes.py` install/cancel/model management flows — 12 tests (project query, model persistence, cancel handler)

### U-008: fs.py Path Restriction + Auth for LAN Mode (Phase 1 — Security)

**Source**: 2026-06-21 review part2 (`docs/analysis/2026-06-21-review_part2.md`)

**Background**: `/api/fs/dirs` has no path restriction, exposing full filesystem when `--host 0.0.0.0` is used. All write endpoints lack auth. Requires lightweight token-based protection.

**Status**: ✅ **Done** (`b071758`, `767bc92`)

**Sub-tasks**:
- [x] U-008a: Restrict `handle_get_fs_dirs` to user home directory and Windows drive roots — `b071758`
- [x] U-008b: Add token auth — when `--host` is not localhost, require `?token=` or Bearer token on sensitive endpoints — `767bc92`
- [x] U-008c: Update UI README with explicit security warning for `--host 0.0.0.0` — this docs update
- [x] U-008d: Add tests for `fs.py` — `c0e88fc`

## Staging / WIP

### R-017: Model Registry & Task Binding UI ✅

**Background**: Currently users must manually edit `config.yaml` to change models — typing provider names, model strings, and API keys by hand. This is error-prone and unfriendly. Goal: a visual model registry where users can:

- See all available models in a dropdown per task (instead of typing `deepseek-chat`)
- Each model tagged with compatible task types (e.g. Gemini/OpenAI = video + text, DeepSeek = text only)
- Each task can independently pick any registered model
- Register new models: name, API key, adapter type (OpenAI-compatible / Anthropic / Gemini), base URL, etc.
- New registrations auto-populate the provider list in `config.yaml`

**Acceptance Criteria** (all ✅):
- ✅ Provider list in Settings Global tab with add/edit/delete
- ✅ Task binding panel in Settings Project tab with dropdowns and capability filtering
- ✅ Add/edit Provider modal: name, type, API key (stored in .env), base_url, model tag list
- ✅ Auto-validate: video_analyze filters to gemini-type providers only
- ✅ Backend: `ProviderConfig.models` field, frontend-only CRUD via existing PUT endpoints
- ✅ Existing `config.yaml` providers migrate seamlessly (models field optional, defaults to empty)

**Sub-tasks**:
- [x] R-017a: Design model registry data model (adapter type, capability tags, credential storage)
- [x] R-017b: Backend CRUD API for provider registration (reuses PUT /api/config/global, no new endpoints)
- [x] R-017c: Backend task-model binding with capability validation (frontend filters, backend runtime check)
- [x] R-017d: UI model list + add/edit/remove
- [x] R-017e: UI task binding dropdowns with filtering
- [x] R-017f: Migration path for existing config.yaml providers

### R-018: AI Prompt Debug Print

**Background**: When AI returns unexpected results, users currently have no way to see what prompt was actually sent. Adding a config toggle to print the full prompt (after context injection, before API call) helps developers debug without modifying code.

**Acceptance Criteria**:
- Config option: `ai.debug_print_prompt: true` (default false)
- When enabled, prints the final prompt (with trip context, user context_override, etc.) to stderr/log before calling the AI provider
- Works for all AI call sites: analyze, voiceover, plan, refine, scripts
- Clear delimiter markers in output so prompt boundaries are visible
- Does not print API keys or other secrets (keys are already masked by `mask_if_looks_like_key`)

**Sub-tasks**:
- [x] R-018a: Add `debug_print_prompt` field to AI config
- [x] R-018b: Inject print logic in `_call_ai()` or provider `generate_text()` — log prompt before API call
- [x] R-018c: Ensure secrets are masked in debug output

## Feature R-004: UI Config Read and Edit

**Background**: Currently the UI only reads paths (output_dir / compressed_dir / texts_dirs / scripts_dir / plans_dir / input_dir) for file location. To change config, users must manually open `config.yaml`, edit, and restart the service. Switching AI provider / context / tasks from the UI saves a restart round-trip.

**Acceptance Criteria**:
- Add a "Settings" tab in the UI (alongside texts/voiceover/plan)
- Display full config tree: paths / ai.providers / ai.tasks / ai.context[_file] / compress / analyze and all other sections
- Form fields are editable (dict nesting → nested form)
- Save writes back to `config.yaml` (with .bak backup first) → show "Service restart required" prompt
- Validation: check paths exist, provider names are registered, tasks.provider references registered providers
- Validation failure → red text in form, no file written

**Sub-tasks**:
- [x] R-004a: Backend `GET /api/config/raw` returns config raw dict; `PUT /api/config/raw` validates and writes back (with .bak backup)
- [x] R-004b: UI adds "Settings" tab; renders full config as nested form (dict / list / scalar)
- [x] R-004c: UI form editing + save (confirm dialog → PUT → restart prompt + validation error red text)
- [x] R-004d: Docs: `clio/ui/README.md` add "Settings" tab usage

## Feature R-005: UI Pipeline Runner

**Background**: Currently `main.py analyze` is CLI-only (compress → analyze → voiceover → plan). Running the full pipeline requires opening a terminal. UI-izing it allows going from "put videos in" to "edit AI output" entirely in the browser with a few clicks.

**Acceptance Criteria**:
- "Run" button in the UI header + progress panel (modal / drawer / new tab — tentatively header button + bottom status bar)
- Clicking the button triggers the full pipeline (default behavior matches `main.py analyze`)
- Real-time `[i/N]` + ETA display for each task × each video
- Toast notification on completion / error
- Does not block editing in texts/voiceover/plan tabs (can be open simultaneously)
- Progress data stored in `output/.progress.json`; UI polls every 2s
- Runs in a background thread; UI must not freeze due to analyze

**Sub-tasks**:
- [x] R-005a: `clio/progress.py` ProgressTracker: writes `output/.progress.json` (phase / current / total / message / started_at / eta / status)  ← `29bcb35`
- [x] R-005b: Integrate into `pipeline.run_analyze_all`: call `tracker.update` at key nodes of compress / analyze / scripts / plan / label  ← `29bcb35`
- [x] R-005c: Backend `POST /api/run/start` (daemon thread + lock to prevent concurrency); `GET /api/run/status` reads `.progress.json`  ← `29bcb35`
- [x] R-005d: UI header "Run" button + progress panel (polls every 2s, renders phase / [i/N] / ETA / status)  ← `29bcb35`
- [x] R-005e: Docs: `clio/ui/README.md` add run panel  ← `29bcb35`
- [x] R-005f: Run panel uses checkboxes to select steps, only runs selected steps  ← `a8daa63`
- [x] R-005g: Fix ProgressTracker.done() parameter passing bug  ← `a8daa63`

## Feature R-001: UI Toggle Original vs Compressed Video

**Background**: The UI currently only displays 640p videos from `output/compressed/`. There is no way to view GoPro 4K originals without opening the file manager — add a toggle to switch to originals.

**Acceptance Criteria**:
- Top toggle: "Compressed (640p)" / "Original (4K)"
- When switching to original, video list shows `input_dir/*.mp4` (sorted by mtime)
- Player can seek / play original videos normally (Range reuses existing implementation)
- Compressed ↔ Original should match by basename where possible, show correspondence in the list

**Sub-tasks**:
- [x] R-001a: Backend `/api/videos?source=compressed|original` supports dual sources  ← `88679ee`
- [x] R-001b: Backend `/api/video?source=original` serves from `input_dir`  ← `88679ee`
- [x] R-001c: UI adds source toggle in header, refetches list on switch  ← `f1d09ac`
- [x] R-001d: `clio/ui/README.md` add toggle description + edge case docs  ← `ec83f48`
- [x] R-001e: Edge case: originals have no `001_` index prefix; UI matches by basename, marks matched/unmatched in list  ← split into `88679ee` (backend helper) + `f1d09ac` (UI match-badge)

## Feature R-006: Sidebar Hierarchy (Project-level vs Video-level)

**Background**: Currently the right panel has three tabs (texts / voiceover / plan) all at the same level, but plan is cross-video (references `sequence[].index`) while texts/voiceover are per-video. The hierarchy is wrong: plan is a project-level artifact, texts/voiceover are video-level artifacts. Making the sidebar two-tier navigation gives R-004 (settings) and R-005 (run) a natural home.

**Acceptance Criteria**:
- Sidebar split into two sections: top "Project" section, bottom "Video" section
- Project section has three entries: `📋 Plan (day1)` / `⚙ Settings` (R-004, not done → grayed with tooltip) / `▶ Run` (R-005, not done → grayed with tooltip)
- Video section stays as-is (match badge + count)
- Select video → right panel shows texts/voiceover tabs (plan tab removed)
- Select plan → right panel hides tab bar, renders plan panel full-width + save button
- When plan is selected, player keeps the previously selected video; clicking a plan segment jumps to the corresponding video + time
- Grayed entries: `opacity: 0.4; cursor: not-allowed;` + `title="Requires R-004 / R-005"`

**Sub-tasks**:
- [x] R-006a: `clio/ui/static/index.html` + `style.css`: sidebar two-section structure + grayed styles  ← `a648e60`
- [x] R-006b: `clio/ui/static/app.js`: state.currentEntity + selectPlan + right panel content dispatch; plan content extracted from tab as independent rendering branch  ← `c42d347`
- [x] R-006c: `clio/ui/README.md`: updated layout diagram + project-level section description  ← `778c44a`
- [x] R-006d: When switching source in plan view, player auto-switches to the corresponding video in the new source. The plan branch now keeps the existing `match.file` lookup and falls back to `currentVideo.index` when metadata is incomplete.

## Feature R-007: Multi-Project Switching in UI

**Background**: The current UI is anchored to a single `output_dir`. To view a different vlog project, users must modify `config.yaml` and restart the service. Users expect to switch projects from the page and directly view other projects' video lists and AI analysis results.

**Acceptance Criteria**:
- UI header/sidebar shows current project name, clickable to switch
- Switching refreshes video list + editor content (texts / scripts / plan all switch to the new project's files)
- No service restart required
- New projects can be created in the UI: enter project name + media directory → auto-creates project directory, generates project.json → refreshes and switches
- Empty project guidance: empty video list shows empty state + media directory path hint

**Sub-tasks**:
- [x] R-007a: Backend `/api/projects` lists all directories containing `project.json` (with step detection)  ← `c91dc6d`
- [x] R-007b: Backend `/api/project/create` creates new project (sanitized directory name + project.json init)  ← `c91dc6d`
- [x] R-007c: Sidebar project selector (dropdown) + new project modal  ← `c88549e`
- [x] R-007d: URL `?project=name` switches project, page reload auto-loads new project data  ← `c88549e`
- [x] R-007e: Empty video list empty state guidance (shows media directory path)  ← `c88549e`

## Feature R-008: UI Single-Step Execution + Folder/File Selection

**Background**: The current UI can only view existing artifacts. To re-run a step (compress / analyze / voiceover / plan), users must open a terminal. Users expect to select a folder → select videos → click a button → see results, without switching to the command line.

**Acceptance Criteria**:
- ✅ Enable sidebar "▶ Run" as the R-008 entry point
- ✅ Right panel shows run panel: step selection (compress / analyze / voiceover / plan / all)
- ❌ Input directory can be independently selected (not limited to config's `input_dir`, can manually enter path or browse)
- ✅ Files within the selected directory can be checked individually (not "run all") — multi-select via "选择视频" button
- ✅ After clicking execute, panel shows real-time progress + ETA (SSE via `/api/run/stream`)
- ⚠️ Auto-switch to corresponding view after completion — video/plan/steps reloaded, but no per-step smart view switch

**Sub-tasks**:
- [ ] R-008a: Backend `/api/run/step` endpoint (dedicated endpoint with `input_dir`) — **not started**. Existing `/api/run/start` + `/api/rerun` cover most use cases; missing standalone `input_dir` override.
- [x] R-008b: Run panel UI (step checkboxes → SSE progress → result/done state) — **done**. `runner.js` has 6 steps, ETA, stalled detection, processing state table.
- [~] R-008c: File checkbox interaction: **done** (`sidebar.js` toggle + `sidebar-data.js` checkboxes + `runner.js` badge). Input directory selection/browse in run panel: **not done** (browse modal exists but not wired to run panel).
- [~] R-008d: Auto-refresh after completion: **done** (videos/plans/steps reload). Per-step smart view switch: **not done** (e.g., compress completed → switch to compressed view).
- [~] R-008e: Sidebar "▶ Run" entry: **done** (active, not grayed). README docs: **not done**. ROADMAP status: **now updated**.

## Feature R-009: Engineering Robustness

**Background**: The project has gaps in dependency management, cross-platform compatibility, and code testing. Pin dependency versions + add `setup.sh` + add unit tests for core pure functions.

**Acceptance Criteria**:
- ✅ `requirements.txt` pins all dependency versions (`requirements-locked.txt`)
- ✅ Core pure functions + route handlers + orchestration logic have unit tests (**381 test cases**, GitHub Actions CI)
- [x] Add Linux/macOS `setup.sh` (equivalent to existing `setup.ps1`) — syntax repaired and UTF-8 prompts restored
- [ ] `main.py check` venv detection compatible with both Linux `bin/` and Windows `Scripts/`

**Sub-tasks**:
- [x] R-009a: Pin dependency versions + migration guide
- [x] R-009b: Linux `setup.sh` (low priority, project primarily targets Windows)
- [x] R-009c: Core pure functions + routes + orchestration unit tests (pytest, 381 cases, CI Linux + Windows dual platform)
- [ ] R-009d: Cross-platform venv detection fix (B-007, affects Linux CI)

## Feature R-010: AI Output Quality & Prompt Management

**Background**: AI analysis results are occasionally wrong (mislocated places, inaccurate timeline, missed highlights), and users cannot intervene in prompt details. Support external prompt overrides + confidence scores + multi-model comparison + UI prompt editing.

**Acceptance Criteria**:
- Support external prompt files overriding system defaults (same-named files in `templates/prompts/` directory, no code changes needed)
- Add "Prompt Management" panel in UI Settings tab: lists all system prompts (analyze / voiceover / plan / refine, etc.)
- Each prompt can be edited online, restored to default, saved to project-level `project.yaml` or global override
- After saving, next AI call automatically uses the modified prompt
- Add `_confidence` field to analyze/texts output (AI self-assessed confidence)
- CLI supports analyzing the same video with multiple models and comparing results

**Sub-tasks**:
- [ ] R-010a: External prompt file override mechanism (`templates/prompts/` same-named file takes priority)
- [ ] R-010b: Confidence scoring (modify prompts to make AI output `_confidence`)
- [ ] R-010c: Multi-model comparison CLI
- [ ] R-010d: Backend `GET /api/prompts` returns all available prompts; `PUT /api/prompts/{name}` saves override
- [ ] R-010e: UI Settings tab embeds Prompt Management panel (list + editor + restore default)

## Feature R-002: One-Clip Cut (Extract All Segments from Plan)

**Background**: `plan.json`'s `sequence[]` already provides `use_timeline` ranges. Users currently have to manually cut in JianYing (CapCut) — want one-click ffmpeg extraction to a specified directory with progress.

**Acceptance Criteria**:
- New CLI subcommand `cut`, no UI dependency
- Reads `plans/day<N>_plan.json`
- Extracts each entry in sequence[] with ffmpeg `-ss <start> -to <end>`
  - Default `-c copy` (fast, cuts in seconds); provide `--reencode` for h264 precise cut
- `--output <dir>` to specify save directory (default `output/cuts/<day>/`)
- Output: extracted `.mp4` + corresponding texts JSON copied to same directory
- Progress: `[i/N] cutting 002 (01:00-01:15)...` + remaining ETA
- Generates `manifest.md` on completion: each sequence lists output file / time range / title

**Sub-tasks**:
- [x] R-002a: `clio/cut.py`: `cut_one(video, start, end, out, *, reencode=False)` wraps ffmpeg
- [x] R-002b: `clio/cut.py`: `parse_time_range("00:00-00:20")` reuses existing utils logic
- [x] R-002c: `pipeline.py`: `run_cut_all(config, day, output_dir, reencode=False)` + progress
- [x] R-002d: `main.py`: `cut` subcommand (`--day`, `--output`, `--reencode`)
- [x] R-002e: Copy accompanying texts JSON to `cuts/<day>/` (renamed `001_xxx_seg_03.json`)
- [x] R-002f: Progress uses `timed()` + `[i/N]` + ETA (consistent with existing pipeline)
- [x] R-002g: Generate `manifest.md` (markdown table: # / video / time / output file / title)
- [x] R-002h: Docs: `README.md` add `cut` subcommand

## Feature R-003: Selective Compress / Analyze / Refine

**Background**: Currently, to redo a specific video's voiceover, the entire pipeline must be rerun. Goal:
- Select a single video for compress / analyze / texts / voiceover
- Regenerate a specific segment (e.g., "only redo 002's voiceover")
- Add temporary context to a specific text for targeted polishing (without polluting global `ai.context`)

**Acceptance Criteria**:
- CLI: `analyze -i single.mp4` already exists → audit and fill gaps
- CLI: `voiceover -i single.json` missing → add
- CLI: `refine --context "temp note"` new, temporarily appended to prompt (priority higher than `ai.context`)
- UI: Each video list item has a dropdown "Rerun texts / voiceover / all / mark refine"
- UI: Refine tab adds temporary context textarea

**Sub-tasks**:
- [x] R-003a: Audit existing subcommands' `-i` single file support (`compress` / `analyze` / `scripts` / `plan` / `refine`)
- [x] R-003b: Add `-i` single JSON support for `scripts` + single file support for `compress`/`analyze`
- [x] R-003c: `refine --context "..."` parameter: temporarily appended to prompt, placed after `ai.context`
- [x] R-003d: UI: each video list item has dropdown "Rerun texts / voiceover / all"
- [x] R-003f: Backend `POST /api/rerun` accepts `{video, task, source}`
- [x] R-003e: UI refine tab adds temporary context textarea (deferred to separate task)
- [ ] R-003g: Pipeline `run_rerun_single` (single-file support already exists, no separate function needed)

## ✅ Feature R-011: Plan Panel Preview Playback

**Background**: The current plan panel only shows a segment list; clicking a segment jumps to the corresponding time. There is no way to quickly preview the coherent playback effect of the entire editing plan.

**Acceptance Criteria**:
- Add "▶ Preview Playback" button to the plan panel
- After clicking, iterate through sequence[] and play each segment sequentially
- Each segment jumps to the `use_timeline` start time, automatically advances to the next when reaching the end time
- The currently playing segment is highlighted in the list
- Panel shows playback progress (Segment 3/11)
- Support "■ Stop Preview" at any time
- Preview stops automatically after completion, player stays at the last segment

**Sub-tasks**:
- [x] R-011a: Frontend state adds previewActive / previewIndex / _previewEndTime
- [x] R-011b: renderPlan adds preview button + highlights current segment
- [x] R-011c: startPreview / stopPreview / _playPreviewSegment control logic
- [x] R-011d: player.ontimeupdate + onended integrated into preview auto-advance

## ✅ Feature R-012: Preview Progress Bar & Interactive Controls

**Background**: R-011 implemented automatic segment jump playback, but users cannot see overall progress or manually jump to a specific segment.

**Acceptance Criteria**:
- In preview mode, show a progress bar below the video player (representing the entire sequence), indicating the current segment position
- Progress bar is clickable/draggable to jump to the corresponding segment
- Preview control bar shows: previous step / play-pause / next step / current segment name
- Manually dragging the player progress bar does not trigger auto-advance (prevent accidental segment skip)

**Sub-tasks**:
- [x] R-012a: Preview control bar UI (previous / pause / next + segment name + overall progress bar)
- [x] R-012b: Progress bar click/drag switches to corresponding segment
- [x] R-012c: Manual player progress bar drag does not trigger auto-advance

## ✅ Feature R-013: Offline Speech Recognition (Whisper ASR → Transcription → Voiceover Reference)

**Background**: Currently, voiceover copy is generated entirely from video visual analysis (location, action, timeline), but cannot know what people in the video are saying. Offline Whisper transcription provides speech content as context for the voiceover plan.

**Acceptance Criteria** (all ✅):
- ✅ New pipeline step `transcribe` (compress → analyze → **transcribe** → voiceover → plan)
- ✅ Offline faster-whisper transcription, absolute timeline on original video, split segments converted via `offset_sec`
- ✅ CLI subcommands `transcribe` / `whisper install` / `whisper check`
- ✅ UI transcript tab + delete/edit/seek + per-video rerun + 10% progress
- ✅ CUDA auto-detection + CPU fallback (`cublas64_12.dll` missing handling)
- ✅ Independent dependency `requirements-whisper.txt`, does not pollute main deps, lazy import

**Sub-tasks**:
- [x] R-013a: WhisperConfig dataclass and model enum (Task 1, `f4b84e0`)
- [x] R-013b: Core transcription module (Task 2, `7263367`)
- [x] R-013c: Pipeline step `run_transcribe_all` (Task 3, `90da4b3`)
- [x] R-013d: CLI subcommands `transcribe` / `whisper` (Task 4, `d2e3924`)
- [x] R-013e: Transcript injection into PLAN_PROMPT (Task 5, `ef7b033`)
- [x] R-013f: Deserialize libs.whisper.package config (Task 6, `370516c`)
- [x] R-013g: UI backend transcript/whisper routes (Task 7, `4b1c6e6`)
- [x] R-013h: UI frontend transcripts tab / sidebar badge / run step (Task 8, `bcfbe04`)
- [x] R-013i: CUDA fallback CPU + lazy import + no torch dependency (`1d1b46a`, `1c5d681`)
- [x] R-013j: Comprehensive fixes: rerun 404, UI display/seek/delete, 10% progress, offset_sec conversion (`1b53499`)

## ✅ Feature R-014: AI Model Token Usage Statistics (Project Level)

**Background**: Currently all AI calls only log prompt size and response size (bytes), with no per-token statistics. Users don't know how many tokens each project consumes, and cannot compare costs across models. Project-level token statistics help optimize model selection and cost control.

**Acceptance Criteria**:
- Record token usage after each AI call (prompt_tokens / completion_tokens / total_tokens), write to `output/.token_usage.json`
- If the model API does not return token counts, use tiktoken for estimation (✅ Record API-returned token counts only; no tiktoken fallback — decision made at user request)
- Aggregate by project: record cumulative token counts per model under each project
- UI Settings tab or new tab shows token statistics (✅ New sidebar entity "Tokens" with summary cards, model/task breakdown, history view)
- CLI supports `main.py tokens` to view statistics

**Sub-tasks**:
- [x] R-014a: Add `TokenUsage` + `AIResponse` dataclasses; update `TextAIProvider`/`VideoAIProvider` return types; `FileTokenUsageStore` impl ← `01317f0`
- [x] R-014b: Gemini + OpenAI providers return `AIResponse` with token_counts; `_call_ai()` collects via store ← `94769e6`~`3fb5e74`
- [x] R-014c: All 5 AI functions + 4 pipeline tasks inject `FileTokenUsageStore` ← `05ce1b9`~`8a1dfc8`
- [x] R-014d: Backend `GET /api/token-usage` route ← `4057373`
- [x] R-014e: UI sidebar "Tokens" entity with summary cards + model/task breakdown + history ← `e875159`
- [x] R-014f: CLI `tokens` subcommand ← `b234a1b`

## Feature R-015: Config Hot Reload

**Background**: Currently, after saving `config.yaml` (global config) in the UI, the cache is not invalidated — the service must be restarted. When `project.yaml` is saved, although the cache is evicted, the frontend always shows "Service restart required." External (CLI / text editor) modifications to config files are entirely undetected. Research in `docs/superpowers/specs/2026-06-13-config-hot-reload-audit.md`.

**Acceptance Criteria**:
- Global `config.yaml` save clears `_config_cache`
- Project-level save shows differentiated prompts (no longer always shows "Service restart required")
- `_get_config()` adds mtime check, auto-re-reads when files change
- Set an upper limit on `_config_cache` size

**Sub-tasks**:
- [x] R-015a: `POST /api/config/raw` global save calls `_config_cache.clear()` ← `e21373e`
- [x] R-015b: `_get_config()` adds mtime-based cache invalidation
- [ ] R-015c: Frontend differentiates project-level vs global save prompts
- [x] R-015d: `_config_cache` adds maxsize limit (LRU cap 20) ← `e21373e`

## Staging / WIP

### N-01: JianYing Draft Export (剪映草稿导出)

**Source**: 2026-06-24 code review (`docs/analysis/2026-06-24-claude_review.md`)

**Background**: plan.json → draft_content.json → JianYing Pro directly importable draft. Core pipeline built but video resolution not working for original files (missing source_file to filepath mapping).

**Sub-tasks**:
- [x] N-01a: Design spec (`docs/superpowers/specs/2026-06-25-jianying-export-design.md`)
- [x] N-01b: `clio/export/` package with FORMAT_REGISTRY
- [x] N-01c: `export_plan_to_jianying()` core builder
- [x] N-01d: CLI `export` subcommand
- [x] N-01e: UI `POST /api/export` route + plan view button
- [x] N-01f: Video resolution — `_resolve_video` needs to use source_file from texts/*.json (debugging, see 4c9f7db, 2d23b38) ✅

- (None)

## Feature R-016: Draggable UI Layout

**Background**: The current UI three-column layout (sidebar / player / editor area) has fixed width and height, unable to adapt to different screen sizes or user preferences.

**Acceptance Criteria**:
- Dividers between sidebar, player, and editor areas are draggable to adjust widths
- Player area height is draggable
- Layout state persisted to `project.json` or localStorage

## Feature R-017: Plan Panel Timeline Drag-and-Drop Navigation

**Background**: The current plan panel only shows a segment list; clicking jumps to the video. Users want to drag along a timeline to view corresponding video content for different segments.

**Acceptance Criteria**:
- Plan panel top shows an overall timeline (representing the plan's sequence[])
- Each segment is displayed as a different-colored block on the timeline
- Users can drag a slider on the timeline / click blocks to jump to the corresponding segment
- Timeline sync: during preview playback, the timeline highlight follows the current segment

## Feature R-018: Multi-Video Selection + Step Execution

**Background**: The current run panel allows step selection and running all videos, or rerunning a single video. There is no "select multiple videos → choose steps → run only selected videos" interaction. Users want to select any videos in the sidebar, then click run to process only the selected items.

**Acceptance Criteria**:
- Add checkbox before each item in sidebar video list, supporting multi-select
- Show "Selected N/N" + "Select All/Deselect All" at the top
- Run panel step checkboxes remain unchanged, but the "Run" button links to selected videos
- Run button disabled when no video is selected, shows "Please select videos first"
- Run progress only reflects processing progress of selected videos
- Selected videos are highlighted in the list

**Sub-tasks**:
- [x] R-018a: Sidebar video list add checkbox + select all/deselect all
- [x] R-018b: Backend `/api/run/start` supports `files: string[]` filter + `overwrite` parameter
- [x] R-018c: Run panel adjusts progress display based on selected videos (total count / ETA / message)
- [x] R-018d: Selected video highlight style + count display + selection mode badge
- [x] R-018e: Disable run button + hint text when nothing selected

### R-018 Follow-up: Compact JSON in Debug Prompt Output ✅

**Background**: `debug_print_prompt` prints the full prompt to console, but injected JSON (clips list, transcripts, analysis data) uses `json.dumps(..., indent=2)`, rendering across dozens of lines. This makes the log hard to scroll through and defeats the purpose of a quick debug glance.

**Request**: Before `print(prompt)` in `_call_ai()`, compact all embedded JSON to single-line format. Suggestion: change all `json.dumps(...)` in prompt-formatting paths (`analyze.py:248/278/333/338/374/375`) to `indent=None` — the AI does not need pretty-printed JSON, and it reduces token count slightly.

✅ Done — all `json.dumps(...)` in prompt-formatting paths use `indent=None`.

## Feature R-019: Run Panel Prompt Injection

**Background**: The run panel (▶ Run) currently has no way to inject custom instructions during pipeline execution. To optimize AI output (e.g., "focus on food scenes", "use more dramatic language", "prefer close-up shots"), users must either edit `config.ai.context` (persists to all runs) or use refine's context textarea (post-hoc, per-video). There is no transient, per-run prompt injection that applies context to all AI calls in a single pipeline run.

**Acceptance Criteria**:
- Run panel shows a collapsible "高级提示词 (Advanced Prompt)" section below step checkboxes
- Users write free-form instructions that get injected into ALL AI calls during this pipeline run
- Optionally tag instructions per-step (e.g., `[analyze] focus on landmarks`, `[voiceover] use conversational tone`)
- Backend: `POST /api/run/start` accepts `context_override: string` and optional `task_prompts: dict[str, str]`
- Pipeline propagates `context_override` → `_wrap_with_context()` → all task prompt chains
- Instructions are transient — they do not persist in config.yaml after pipeline completes
- Existing `config.ai.context` (project-level) and `trip_context.md` still apply; injected prompt is the highest-priority layer

**Sub-tasks**:
- [x] R-019a: Backend: extend `handle_post_run_start` to accept `context_override` and `task_prompts` in request body
- [x] R-019b: Backend: pass `context_override` through `run_pipeline_steps` → each task → `_call_ai()` / `_wrap_with_context()`
- [x] R-019c: Frontend: add collapsible prompt section in run panel (runner.js), send values in POST body
- [x] R-019d: Frontend: add per-step tag hint placeholder (e.g. `[voiceover]`, `[plan]`, `[analyze]`)
- [x] R-019e: Ensure existing `debug_print_prompt` (R-018) shows injected prompt in debug output — `_wrap_with_context` already prints context_override in prompt
- [ ] R-019f: Add tests for context_override propagation through pipeline steps (deferred)

## Documentation Maintenance (from 2026-06-10 Full Review)

| ID | Issue | Description | Status |
| --- | --- | --- | --- |
| D-001 | AGENTS.md §7 commit list out of date | Last entry is R-007, missing 6 new commits | ✅ Updated |
| D-002 | clio/ui/README.md run status description outdated | "▶ Run grayed (requires R-005)" — R-005 is complete | ✅ Fixed |
| D-003 | README.md / README.en.md missing per-project config | `project.yaml` layered config not in user docs | ✅ Added |
| D-004 | config.example.yaml model name doesn't match actual usage | Example has `deepseek-chat`, config.yaml uses `deepseek-v4-flash`, should add comment note | ✅ Added comment |

## Architecture Improvements (from review, aligned with design doc Phase 1)

| ID | Issue | Description | Status |
| --- | --- | --- | --- |
| A-001 | server.py → 1261-line single closure | Split into routes/ + services/ (Phase 1c complete, 454 lines) | ✅ |
| A-002 | app.js → 1509-line global functions | Split into src/ ES modules (Phase 1d complete, 8 modules) | ✅ |
| A-003 | pipeline.py → 789-line pile | Split into tasks/ package (Phase 1b complete, 96 lines) | ✅ |
| A-004 | `_write_text_file` / `_rewrite_text_file` 80% duplicate | Extract common function (Phase 1b moved to _helpers.py) | ✅ |
| A-005 | `project.json` vs `project.yaml` out of sync | `project.yaml.paths.output_dir` is now authoritative; `project.json.output_dir` remains a legacy fallback | ✅ |
| A-006 | Frontend ES module dynamic import circular reference | viewer/editor/runner three-way dynamic import, can be refactored long-term | 🟡 |

## Known Issues (Bug Tracker)

Sorted by priority: P0 (immediate) → P1 (near-term) → P2 (mid-term) → P3 (long-term).

### Found by Code Review (2026-06-16, 5 parallel subagents)

| ID | Priority | Issue | Status |
| --- | --- | --- | --- |
| C1 | P0 | POST /api/rerun path traversal — video_basename not validated | ✅ `41abe5b` |
| C2 | P0 | Empty-state buttons don't refresh video list | ✅ `89614a4` |
| C3 | P0 | playVideoSegment addEventListener leak | ✅ `bce09ce` |
| C4 | P0 | OpenAI 4xx silently retried | ✅ `dba1cd9` |
| C5 | P0 | YAML unknown fields → dataclass TypeError crash | ✅ `18ccee4` |
| C6 | P0 | Provider HTTP connection leak | ✅ `71659aa` + `ef68308` |
| I1 | P1 | Transcription edit onblur race condition | ✅ `fe511be` |
| I2 | P1 | save() data reference race condition | ✅ `8d3b2f8` + `bebf21f` |
| I3 | P1 | startRun double-click starts two pipelines | ✅ `1406e0e` |
| I4 | P1 | Portal menu event listener leak | ✅ `08d815c` |
| I5 | P1 | Range request doesn't support bytes=-N suffix | ✅ `d2591a9` |
| I6 | P1 | POST /api/cut day_label path traversal | ✅ `b072240` |
| I7 | P1 | Hardcoded G:/ffmpeg | ✅ `74c34f5` |
| I8 | P1 | _resolve_original ValueError crash for stem without underscore | ✅ `e6e7666` |
| I9 | P1 | run_ffmpeg stdout pipe deadlock | ✅ `9288216` |
| I10 | P1 | CLI doesn't load project.yaml overrides | ✅ `60d765f` |
| I11 | P1 | _TeeWriter.__getattr__ exposes original stdout/stderr's close/writelines | ✅ `947a320` |
| I12 | P1 | openai_compat retry count hardcoded | ✅ `ef2311d` + `ef68308` |
| M1~M36 | P2 | Minor issues — see `docs/review/2026-06-16-feat-whisper-full-audit.md` | 🆕 |

### P0 — Immediate Fix

| ID | Issue | Fix Approach | Status |
| --- | --- | --- | --- |
| B-001 | Gemini Files API uploads not cleaned up, exhausting quota | `try/finally` ensures video deletion is requested after upload | ✅ `a9996a9` |
| B-002 | with_retry re-uploads the same video on retry | Move upload outside retry logic, do not retry upload | ✅ `a9996a9` |
| B-003 | Temp file residue (.tmp files not auto-cleaned on interrupt) | Use `with` statement or `try/finally` for cleanup | ✅ `0533051` |
| B-012 | `_run()` silently swallows exceptions — pipeline failure invisible to UI | `except Exception: pass` → write progress.json error status + log | ✅ `9c73903` |
| B-013 | `apply_run_paths` directly modifies input config object | Return new config or `copy.deepcopy()` before modification | ✅ `9c73903` |
| B-014 | `requirements.txt` no version numbers — breaking change risk | `pip freeze` lock versions, see R-009a | ✅ `requirements-locked.txt` |
| B-021 | `cut.py:51` ffmpeg uses `-to` but should be `-t` (specify duration) | Change `-to duration_sec` → `-t duration_sec` | ✅ `fix/B-021-cut-to-to-t` |
| B-022 | `project_service.py:52` `_detect_steps` uses `any(t.iterdir() for t in texts)` — iterdir() generator is always truthy, empty dirs marked as analyze complete | Change to `any(any(True for _ in t.iterdir()) for t in texts)` | ✅ `fix/B-022-detect-steps-empty-dir` |
| B-023 | `routes/projects.py` creates/writes project.json with `write_text()` bypassing `_save_atomic`, crash leaves corrupted file | Use `_save_atomic` instead | ✅ `fix/B-023-project-json-atomic` |
| B-053 | `sidebar.js:pollRerunStatus` `statusEl`/`fill`/`logsEl` used before declaration in early `return` path, triggering ReferenceError | Hoist variable declarations before `return` | ✅ `c283bb9` |
| B-061 | `config_routes.py` global config save doesn't invalidate `_config_cache`, new config takes effect only after restart | Call `_config_cache.clear()` after writing to disk | ✅ `e21373e` |
| B-062 | `tasks/analyze.py` `glob("*.mp4")` only matches `.mp4`, missing `.mov`/`.m4v` etc. | Replace with `VIDEO_EXTS` filtering | ✅ `51f50d7` |

### P1 — Near-term

| ID | Issue | Fix Approach | Status |
| --- | --- | --- | --- |
| B-004 | ETA estimate too low (successful items include failed items' time) | Move timing to `finally` block, only count successes | ✅ `d799f21` |
| B-007 | Cross-platform venv detection only recognizes Windows `Scripts/`, Linux uses `bin/` | Support both `bin/` and `Scripts/` | ✅ `bdcc678` + `f24bdf3` |
| B-015 | `project.yaml` write only validates YAML format, no `_validate_config` | Run full merge validation before `do_PUT /api/config/raw?project=X` | ✅ `9c73903` |
| B-016 | `deepseek-v4-flash` in `config.yaml` may be an invalid model name (AGENTS §8.4) | Comment added in config.example.yaml explaining variant names (D-004) | ✅ D-004 |
| B-024 | `cut.py:9` `parse_time_range` doesn't validate end > start, AI-generated reverse intervals silently produce bad files with ffmpeg | Add `if end <= start: raise ValueError(...)` after parsing | ✅ `fix/B-024-parse-time-range-validate` |
| B-025 | `tasks/cut.py:80-82` source label in error message when video not found is inverted | Fix ternary operation | ✅ `fix/B-025-cut-source-label` |
| B-026 | `tasks/plan.py:31` `int(raw_idx)` without protection, uncaught ValueError when filename prefix is non-numeric | Add `try/except` guard to skip | ✅ `fix/B-026-plan-int-raw-idx` |
| B-027 | `prompts.py:38-70` `PLAN_PROMPT` uses `str.format()` with JSON containing `{...}` | ⚠️ Tested: `str.format()` does not process curly braces in replacement values, not a real crash | ❌ Not reproducible |
| B-028 | `progress.py:42` `.with_suffix(".progress.tmp")` generates `.progress.progress.tmp` | Use `parent/name + ".tmp"` | ✅ `fix/B-028-progress-tmp-name` |
| B-029 | `log.py:101-146` `_initialized` without lock; `sys.stdout/stderr` unrecoverable | Add lock + save original stream + `teardown_logging()` | ✅ `fix/B-029-log-init-lock` |
| B-030 | `pyproject.toml:3` `build-backend` private API | Use `setuptools.build_meta:__legacy__` | ✅ `fix/B-030-pyproject-backend` |
| B-031 | `server.py:107-109` `_config_cache` multi-thread no lock | Add `_config_cache_lock` | ✅ `fix/B-031-config-cache-lock` |
| B-038 | `server.py:393-395` Phase 1c refactor missed `config_path` class attribute exposure | Add `Handler.config_path = config_path` | ✅ `fix/B-031-config-path-exposure` |
| B-054 | `routes/run.py` `_run_thread` check-and-set not protected by lock, `handle_post_run_start` / `handle_post_rerun` can start two pipelines concurrently | Wrap reads/writes with `handler.__class__._run_lock` | ✅ `dc01300` |
| B-055 | `server.py` `_config_cache.pop` without lock, data race on concurrent PUT config causes cache inconsistency | Wrap `.pop()` with `_config_cache_lock` | ✅ `93eb4f1` |
| B-056 | `analyze.py:_resolve_original` only recognizes `.mp4`/`.mov`/`.mkv`/`.mts`/`.m2ts`, missing `.m4v`/`.webm` | Complete extension list | ✅ `8608d14` |
| B-057 | `server.py` video response hardcoded `Content-Type: video/mp4`, returns wrong MIME for `.mov`/`.webm` etc. | Choose Content-Type based on actual file extension | ✅ `18f7358` |
| B-063 | `routes/videos.py` `segment_matches` field used by frontend but never returned by backend | Return `segment_matches` array | ✅ `7f05ee4` |
| B-064 | `analyze.py` `trip_context.md` path hardcoded to package directory, wrong location in multi-project scenarios | Project-level priority lookup + cache | ✅ `fe57a7f` |
| B-065 | `routes/config.py`+`routes/projects.py` 8 places with `hasattr(handler.server,...)` defensive code | Access directly after `make_handler` binding | ✅ `34c0d3b` |
| B-066 | `server.py` `_config_cache` no upper bound, memory leak on long-running | LRU cap 20 entries, evict oldest on overflow | ✅ `e21373e` |

### P2 — Mid-term

| ID | Issue | Fix Approach | Status |
| --- | --- | --- | --- |
| B-005 | Linux `sorted(Path.iterdir())` order not guaranteed (glob also not ordered) | Explicit `sorted()` before matching | ✅ `a276225` |
| B-008 | Functions silently modify input parameters (e.g., `analyze_video` modifies passed dict fields) | `deepcopy()` input params to avoid side effects | ✅ `7017ff6` |
| B-017 | `_find_texts_dirs` matches `texts*` too broadly — `texts_backup` also matches | Use more precise glob or add exclusion rule | ✅ `a276225` |
| B-018 | `_config_cache` only grows (only pops on PUT config) | Clean stale cache on project list refresh | ✅ `a276225` |
| B-032 | `tasks/label.py:29-31` glob idx may be integer 1 instead of `"001"`, causing file match failure and skipped processing | `format_index(int(idx), config.naming.index_width)` consistent formatting before glob | ✅ |
| B-033 | `tasks/analyze.py:96` batch AI analysis failure immediately aborts entire batch; `run_refine_texts` has try/except/continue tolerance but this doesn't — inconsistent behavior | Add `try/except` + `continue` to `analyze_video()` calls, log failure and continue | ✅ |
| B-034 | `routes/run.py` rerun progress file path taken from `cfg.paths.output_dir`, but `GET /api/run/status` takes from `_project_output_dir()` — two output_dirs may differ causing frontend poll to miss progress | Unify with `proj_out` (from `_project_output_dir`) | ✅ |
| B-035 | `sidebar.js:448` `pollRerunStatus` early returns on `idle/running` state without timeout safety net, progress overlay permanently stuck when task fails | Add polling timeout (120s) + 10s idle detection + `_rerunPollError()` | ✅ |
| B-036 | `compress.py:33-34` target bitrate `8 * 1024 * 1024 * target_size_mb / duration * 0.92` doesn't subtract audio stream, output file exceeds `target_size_mb` when audio present | Subtract 128kbps audio estimate from `target_bits` | ✅ |
| B-037 | `utils.py:139-140` `get_duration_sec` doesn't handle ffprobe output `"N/A"`, ValueError without context on certain video formats | Add `try/except`, attach file path on error | ✅ |
| B-039 | `openai_compat.py:28` `httpx.Client` created in `__init__` without `close()`, connection leak on long service | Add `close()` method | ✅ |
| B-040 | `config.py:119` `_path()` silently returns `.` when value is empty, reads/writes current directory on missing config path | Raise `ValueError` when empty | ✅ |
| B-041 | `file_service.py:46` `_save_atomic` uses fixed `.tmp` filename, two concurrent requests writing same file overwrite each other | Add `os.urandom(4).hex()` random suffix | ✅ |
| B-058 | `file_service.py:_save_atomic` skips existing `.bak` without overwriting, old `.bak` doesn't match latest content, after multiple saves `.bak` reflects earliest version | Overwrite `.bak` on every save | ✅ `7868a95` |
| B-067 | `tasks/analyze.py:43` lazy `import re` in hot path | Move to top of file | ✅ `51f50d7` |
| B-068 | `split.py` `-c copy` cuts by time, non-keyframe segment start has black frames, AI may misjudge | Add `reencode_split` option for frame-accurate cuts | ✅ `cd1da63` |
| B-069 | `progress.py` tmp filename fixed, may conflict across processes | Use `os.urandom(4).hex()` random suffix | ✅ `ea2e79c` |
| B-070 | `pipeline.py` unknown step name causes `NoneType` crash | Validate step names before loop and `raise ValueError` early | ✅ `34846df` |
| B-071 | `server.py` Range request `length=0` (when `start=size-1`) unprotected | Add `length <= 0` boundary check | ✅ `e21373e` |

### P3 — Long-term

| ID | Issue | Fix Approach | Status |
| --- | --- | --- | --- |
| B-042 | `gemini.py:41` `_wait_for_file` no timeout, permanently blocks when file processing hangs | Add `timeout` parameter with `time.monotonic()` check | ✅ `a276225` |
| B-043 | `.githooks/pre-commit:21` `git add` may stage workspace changes user didn't intend to commit | Only stage ruff-formatted files: check if ruff changed them before `git add` | ✅ `25fe130` |
| B-044 | `_helpers.py:51` `_eta_line` always shows `1/total` when `completed=0`, but actual progress may be 3rd, 4th entry | Use `i` instead of hardcoded `1` | ✅ `a276225` |
| B-045 | `sidebar.js:177` video list rendering piles up `{ once: true }` click listeners on `document`, close dropdown logic fails | Use event delegation + persistent handler, or `removeEventListener` before rendering | ✅ `a276225` |
| B-059 | `_parse_providers` doesn't read `requests_per_minute` and `retry_attempts` from YAML | `cfg.get("requests_per_minute", 0)` + `retry_attempts` default unified to 2 | ✅ `a276225` |
| B-060 | Original video view split segment index lost — each original file only uses `comp[0]`, plan referencing `002`/`003` returns 404 | Iterate all matches in `comp`, create independent video entries for each split segment | ✅ `c59880d` |
| B-072 | `tasks/compress.py` corrupted `.mp4` permanently skipped by `skip_existing` without retry | Add ffprobe integrity check before skip | ✅ `6c3c231` |
| B-073 | `routes/videos.py` `_parse_segment_info` only recognizes `001_GL010683_seg01` format | Relax naming convention assumptions, support custom naming | ✅ `f2465cd` |
| B-086 | `server.py:524` hardcodes `config_path.parent / "projects.json"` instead of calling `_registry_path()` | Use `_registry_path(config_path)` for consistency | ✅ U-004 |
| B-087 | `serve.ps1`/`serve.sh` hardcodes project directory paths | Remove hardcoded paths, make distributable | ✅ `fcbccf5` |
| B-088 | `ROADMAP.md` 925 lines — completed features not archived | Archive completed sections to separate file | ✅ `88d7238` |
| B-089 | `AGENTS.md` §7 commit history 100+ entries too long | Trim to ~30 most recent, archive rest | 🆕 |
| B-090 | `pipeline.py` cancel_event not propagated to analyze/scripts/plan/label | Add `cancel_event` param + loop check to all 4 functions (see U-005) | ✅ U-005 |
| B-091 | `RateLimiter.__enter__` holds lock during `time.sleep()`, blocks parallel AI calls | Split acquire() from sleep (see U-006) | ✅ `already in U-006` |
| B-092 | `whisper_routes.py` ctypes thread kill unsafe (C ext blocks injection, resource leak) | Replace with chunked download (see U-007) | 🆕 |
| B-093 | `transcribe.py` low-confidence segments silently dropped, no record kept | Mark with `low_confidence` flag instead of discard (see U-009) | ✅ U-009 |
| B-094 | `/api/fs/dirs` no path restriction, exposes full filesystem in LAN mode | Add root restriction + token auth (see U-008) | ✅ `767bc92` |
| B-095 | `server.py` only 6% test coverage, no integration tests for dispatch/error paths | Add HTTP-level tests (see U-010) | 🆕 |
| B-096 | `whisper_routes.py` 48% coverage — new feature, test lagging behind | Add tests for install/cancel/model management flows | 🆕 |
| B-097 | `videos.py:101` `text_sidecars.get(idx)[0]` always picks first text file for all split segments, each segment should map to its own text/script sidecar | Add compressed_stem map for segment-specific text/script matching | ✅ `05edab2` |
| B-074 | `analyze.py:_wrap_with_context` reads `trip_context.md` from disk on every AI call | Module-level `_trip_context_cache` | ✅ `fe57a7f` |
| B-075 | `ui/server.py` Range request doesn't support suffix `bytes=-N` | Empty start + non-empty end → suffix calculation | ✅ `d2591a9` |
| B-076 | `utils/discover_ffmpeg_bin` hardcoded `G:/ffmpeg` | Remove, use `FFMPEG_HOME` env var instead | ✅ `74c34f5` |
| B-077 | `tasks/analyze.py` `_resolve_original` ValueError on stem without `_` | Add `if "_" not in stem:` guard | ✅ `e6e7666` |
| B-078 | `main.py` doesn't pass `project_dir` to `load_config`, project.yaml ignored | Infer `project_dir` from `-i` directory or cwd | ✅ `60d765f` |
| B-079 | `log.py` `_TeeWriter.__getattr__` passes through `close`/`writelines`/`truncate` | Intercept and raise AttributeError | ✅ `947a320` |
| B-080 | `openai_compat.py` hardcoded `attempts=3` ignores configured `retry_attempts` | Read from `cfg.retry_attempts` + `+1` conversion | ✅ `ef2311d` |
| B-081 | `gemini.py` `retry_attempts` semantics inconsistent with openai_compat (missing `+1`) | Align to `max(1, cfg.retry_attempts + 1)` | ✅ `ef68308` |
| B-098 | `plan.py` stores transcript_map key as `stem.lower()`, `analyze.py` lookup uses original case — every clip misses, `TRANSCRIPT_CONTEXT` never injected | Unify to `.lower()` on lookup side in `analyze.py` | ✅ `cb2174f` |
| B-082 | `ai/factory.py` provider cache not thread-safe + no test cleanup mechanism | Add lock + `_clear_provider_cache()` + autouse fixture | ✅ `ef68308` |
| B-083 | `ui/routes/run.py` `obj.get("index")` unsanitized used as glob pattern | `re.sub(r"[^a-zA-Z0-9_-]", "")` filter | ✅ `bebf21f` |
| B-084 | `ui/static/src/editor.js` `save()` data references not captured at call site | Capture `planData/textsData/voiceoverData/configRaw` | ✅ `bebf21f` |
| B-085 | `ui/static/src/editor.js` transcript edit onblur reads from `state.currentVideo` instead of captured value at dblclick | Capture `origV` at dblclick time | ✅ `fe511be` |

## Performance Optimizations

| ID | Bottleneck | Optimization Plan | Priority |
| --- | --- | --- | --- |
| P-001 | AI analysis (analyze step) is pure serial, each video waits for previous upload+process+generate | `ThreadPoolExecutor(max_workers=3~5)` after RateLimiter refactoring (U-006). See part2 review §P-1 for details | P2 |
| P-002 | Repeated ffprobe calls to read same video's `duration_sec` / `size_mb` | Cache already-read info, reuse results | P3 |
| P-003 | `GET /api/videos` iterates directory every time, high I/O cost | Add directory mtime cache, reuse unchanged scan results | P3 |

---

## ✅ Recently Completed

| Commit | Description | Date |
| --- | --- | --- |
| `be636f2`~`2a712f7` (14 commits) | R-017: Model Registry & Task Binding UI (ProviderConfig.models, tag input, provider cards, task binding, tests, fixes) | 2026-07-02~07-03 |
| `43a922b` | feat(ui): run panel prompt injection (R-019) | 2026-07-01 |
| `05edab2` | fix(ui): segment-specific text/script matching in video list (B-097) | 2026-07-01 |

Older completed sections (commit log, test coverage verification, code review audit) archived to [`docs/archive/2026-07-01-roadmap-archive.md`](docs/archive/2026-07-01-roadmap-archive.md).

### Test count: 954 → 972 (R-017 added UI unit tests + backend model parsing tests)
