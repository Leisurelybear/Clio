# Roadmap

Feature tracking. Each feature is broken down into minimal executable sub-tasks (per `AGENTS.md` §6.1 "one feature, one commit").
Mark `[ ]` as `[x]` when done, `[~]` for in-progress, `[!]` for blocked.

Design discussions / decision history in `AGENTS.md`, implementation details in git log.

## In Progress

### U-002: ProviderManager (Phase 2 — Short-term)

**Source**: 2026-06-20 code review (`docs/analysis/2026-06-20-REVIEW-part1.md`)

**Background**: Current `_provider_cache` in `factory.py` already has composite key + thread safety (C2/C4 fixed), but no TTL/expiration/hot-reload. Long-running server accumulates HTTP sessions.

**Acceptance Criteria**:
- `ai/manager.py`: `ProviderManager` class replaces module-level `_provider_cache`
- TTL-based expiration (default 30min no-access → auto close)
- `close_all()` for server shutdown cleanup
- `hot_reload()` for config hot-reload (close old, create new)
- Maintain existing thread-safety + composite key + test isolation

**Sub-tasks**:
- [ ] U-002a: Implement `ProviderManager` class with TTL + `close_all` + `hot_reload`
- [ ] U-002b: Integrate into `factory.py` (backward-compatible)
- [ ] U-002c: Call `close_all` on `server.py` shutdown
- [ ] U-002d: Update tests + verify CI

### U-007: Whisper Cancel Safety (Phase 2)

**Source**: 2026-06-21 review part2 (`docs/analysis/2026-06-21-review_part2.md`)

**Background**: `whisper_routes.py` uses `ctypes.pythonapi.PyThreadState_SetAsyncExc` to kill download thread — unsafe (C extensions block injection, resource leaks). Replace with chunked download that checks cancel flag per-chunk.

**Sub-tasks**:
- [ ] U-007a: Replace `hf_hub_download` with chunked `requests.get(stream=True)` + `iter_content`
- [ ] U-007b: Per-chunk `_INSTALL_CANCEL.is_set()` check for clean interrupt
- [ ] U-007c: Remove `ctypes` thread-kill code
- [ ] U-007d: Update tests

### U-010: Server + fs.py Test Coverage (Phase 3 — Testing)

**Source**: 2026-06-21 review part2 (`docs/analysis/2026-06-21-review_part2.md`)

**Background**: `server.py` has 6% coverage, `fs.py` has 12% coverage. These are security-sensitive and critical files with minimal testing.

**Sub-tasks**:
- [ ] U-010a: Add integration tests for `server.py` dispatch logic (do_GET/do_PUT/do_POST routing)
- [ ] U-010b: Add tests for `fs.py` directory browsing (boundary cases, permission errors)
- [ ] U-010c: Add tests for `whisper_routes.py` install/cancel/model management flows

### U-008: fs.py Path Restriction + Auth for LAN Mode (Phase 1 — Security)

**Source**: 2026-06-21 review part2 (`docs/analysis/2026-06-21-review_part2.md`)

**Background**: `/api/fs/dirs` has no path restriction, exposing full filesystem when `--host 0.0.0.0` is used. All write endpoints lack auth. Requires lightweight token-based protection.

**Sub-tasks**:
- [ ] U-008a: Restrict `handle_get_fs_dirs` to user home directory or a configurable root
- [ ] U-008b: Add `UI_TOKEN` env var check — when `--host` is not localhost, require `?token=` on all sensitive endpoints
- [ ] U-008c: Update README.md with explicit security warning for `--host 0.0.0.0`
- [ ] U-008d: Add tests for `fs.py` (currently 12% coverage)

## Staging / WIP

### R-017: Model Registry & Task Binding UI

**Background**: Currently users must manually edit `config.yaml` to change models — typing provider names, model strings, and API keys by hand. This is error-prone and unfriendly. Goal: a visual model registry where users can:

- See all available models in a dropdown per task (instead of typing `deepseek-chat`)
- Each model tagged with compatible task types (e.g. Gemini/OpenAI = video + text, DeepSeek = text only)
- Each task can independently pick any registered model
- Register new models: name, API key, adapter type (OpenAI-compatible / Anthropic / Gemini), base URL, etc.
- New registrations auto-populate the provider list in `config.yaml`

**Acceptance Criteria**:
- UI "Models" tab listing all registered models with adapter type + supported tasks
- Task binding panel: each task (video_analyze, voiceover, refine_text, etc.) shows a dropdown of compatible models
- "Add Model" form: name, api_key, base_url, adapter_type (openai / anthropic / gemini), optional tags
- Auto-validate: video tasks filter out text-only models
- Backend: CRUD API for models, stored in `ai.providers` section of config
- Existing `config.yaml` providers migrate seamlessly

**Sub-tasks**:
- [ ] R-017a: Design model registry data model (adapter type, capability tags, credential storage)
- [ ] R-017b: Backend CRUD API for provider registration
- [ ] R-017c: Backend task-model binding with capability validation
- [ ] R-017d: UI model list + add/edit/remove
- [ ] R-017e: UI task binding dropdowns with filtering
- [ ] R-017f: Migration path for existing config.yaml providers

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
- [x] R-004d: Docs: `vlog_tool/ui/README.md` add "Settings" tab usage

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
- [x] R-005a: `vlog_tool/progress.py` ProgressTracker: writes `output/.progress.json` (phase / current / total / message / started_at / eta / status)  ← `29bcb35`
- [x] R-005b: Integrate into `pipeline.run_analyze_all`: call `tracker.update` at key nodes of compress / analyze / scripts / plan / label  ← `29bcb35`
- [x] R-005c: Backend `POST /api/run/start` (daemon thread + lock to prevent concurrency); `GET /api/run/status` reads `.progress.json`  ← `29bcb35`
- [x] R-005d: UI header "Run" button + progress panel (polls every 2s, renders phase / [i/N] / ETA / status)  ← `29bcb35`
- [x] R-005e: Docs: `vlog_tool/ui/README.md` add run panel  ← `29bcb35`
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
- [x] R-001d: `vlog_tool/ui/README.md` add toggle description + edge case docs  ← `ec83f48`
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
- [x] R-006a: `vlog_tool/ui/static/index.html` + `style.css`: sidebar two-section structure + grayed styles  ← `a648e60`
- [x] R-006b: `vlog_tool/ui/static/app.js`: state.currentEntity + selectPlan + right panel content dispatch; plan content extracted from tab as independent rendering branch  ← `c42d347`
- [x] R-006c: `vlog_tool/ui/README.md`: updated layout diagram + project-level section description  ← `778c44a`
- [!] R-006d: When switching source in plan view, player should auto-switch to the corresponding video in the new source (not clear the player). Current behavior: `setSource` in plan branch only clears the player — user must click the video in the left sidebar or a plan segment to load. Proposed fix: in plan branch, use `state.currentVideo?.index` to find the corresponding file in `state.videos` and call `playVideoSegment`.

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
- Enable sidebar "▶ Run" as the R-008 entry point
- Right panel shows run panel: step selection (compress / analyze / voiceover / plan / all)
- Input directory can be independently selected (not limited to config's `input_dir`, can manually enter path or browse)
- Files within the selected directory can be checked individually (not "run all")
- After clicking execute, panel shows real-time progress + ETA (reuses R-005's `.progress.json` or uses SSE)
- Auto-switch to corresponding view after completion (e.g., after voiceover completes, switch to voiceover tab and refresh)

**Sub-tasks**:
- [ ] R-008a: Backend `/api/run/step` endpoint, accepts `{ step: string, input_dir?: string, files?: string[] }`
- [ ] R-008b: Run panel UI (step selection, progress, result viewing)
- [ ] R-008c: Input directory selection + file checkbox interaction
- [ ] R-008d: Auto-refresh corresponding view after completion
- [ ] R-008e: Documentation + enable sidebar "Run" entry

> **F-001 Suggestion**: External analysis suggests merging R-007 (multi-project switching) and R-008 (single-step execution) into a unified "Project Management + Pipeline" panel, using `projects.json` to persist the project list. Can be implemented together.

## Feature R-009: Engineering Robustness

**Background**: The project has gaps in dependency management, cross-platform compatibility, and code testing. Pin dependency versions + add `setup.sh` + add unit tests for core pure functions.

**Acceptance Criteria**:
- ✅ `requirements.txt` pins all dependency versions (`requirements-locked.txt`)
- ✅ Core pure functions + route handlers + orchestration logic have unit tests (**381 test cases**, GitHub Actions CI)
- [ ] Add Linux/macOS `setup.sh` (equivalent to existing `setup.ps1`) — project primarily targets Windows
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
- [x] R-002a: `vlog_tool/cut.py`: `cut_one(video, start, end, out, *, reencode=False)` wraps ffmpeg
- [x] R-002b: `vlog_tool/cut.py`: `parse_time_range("00:00-00:20")` reuses existing utils logic
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

## Feature R-014: AI Model Token Usage Statistics (Project Level)

**Background**: Currently all AI calls only log prompt size and response size (bytes), with no per-token statistics. Users don't know how many tokens each project consumes, and cannot compare costs across models. Project-level token statistics help optimize model selection and cost control.

**Acceptance Criteria**:
- Record token usage after each AI call (prompt_tokens / completion_tokens / total_tokens), write to `output/.token_usage.json`
- If the model API does not return token counts, use tiktoken for estimation
- Aggregate by project: record cumulative token counts per model under each project
- UI Settings tab or new tab shows token statistics (project overview / per-model breakdown / by time)
- CLI supports `main.py tokens` to view statistics

**Sub-tasks**:
- [ ] R-014a: Backend AI calls unified token recording wrapper (returns token count regardless of provider)
- [ ] R-014b: Write to `output/.token_usage.json`, aggregated by project/model/date
- [ ] R-014c: UI displays token statistics panel
- [ ] R-014d: CLI `tokens` subcommand

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
- [ ] R-018a: Sidebar video list add checkbox + select all/deselect all
- [ ] R-018b: Backend `/api/run/start` supports `files: string[]` filter parameter
- [ ] R-018c: Run panel adjusts progress display based on selected videos (total count / ETA / message)
- [ ] R-018d: Selected video highlight style + count display
- [ ] R-018e: Disable run button + hint text when nothing selected

## Documentation Maintenance (from 2026-06-10 Full Review)

| ID | Issue | Description | Status |
| --- | --- | --- | --- |
| D-001 | AGENTS.md §7 commit list out of date | Last entry is R-007, missing 6 new commits | ✅ Updated |
| D-002 | vlog_tool/ui/README.md run status description outdated | "▶ Run grayed (requires R-005)" — R-005 is complete | ✅ Fixed |
| D-003 | README.md / README.en.md missing per-project config | `project.yaml` layered config not in user docs | ✅ Added |
| D-004 | config.example.yaml model name doesn't match actual usage | Example has `deepseek-chat`, config.yaml uses `deepseek-v4-flash`, should add comment note | ✅ Added comment |

## Architecture Improvements (from review, aligned with design doc Phase 1)

| ID | Issue | Description | Status |
| --- | --- | --- | --- |
| A-001 | server.py → 1261-line single closure | Split into routes/ + services/ (Phase 1c complete, 454 lines) | ✅ |
| A-002 | app.js → 1509-line global functions | Split into src/ ES modules (Phase 1d complete, 8 modules) | ✅ |
| A-003 | pipeline.py → 789-line pile | Split into tasks/ package (Phase 1b complete, 96 lines) | ✅ |
| A-004 | `_write_text_file` / `_rewrite_text_file` 80% duplicate | Extract common function (Phase 1b moved to _helpers.py) | ✅ |
| A-005 | `project.json` vs `project.yaml` out of sync | Two config sources inconsistent, should unify or make mutually aware | 🔴 |
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
| B-004 | ETA estimate too low (successful items include failed items' time) | Move timing to `finally` block, only count successes | |
| B-007 | Cross-platform venv detection only recognizes Windows `Scripts/`, Linux uses `bin/` | Support both `bin/` and `Scripts/` | ✅ `bdcc678` + `f24bdf3` |
| B-015 | `project.yaml` write only validates YAML format, no `_validate_config` | Run full merge validation before `do_PUT /api/config/raw?project=X` | ✅ `9c73903` |
| B-016 | `deepseek-v4-flash` in `config.yaml` may be an invalid model name (AGENTS §8.4) | Confirm actual usable model name, update config or add note | 🆕 |
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
| B-068 | `split.py` `-c copy` cuts by time, non-keyframe segment start has black frames, AI may misjudge | Document this; or provide `--reencode-split` option | 🆕 |
| B-069 | `progress.py` tmp filename fixed, may conflict across processes | Use `os.urandom(4).hex()` random suffix | ✅ `ea2e79c` |
| B-070 | `pipeline.py` unknown step name causes `NoneType` crash | Validate step names before loop and `raise ValueError` early | ✅ `34846df` |
| B-071 | `server.py` Range request `length=0` (when `start=size-1`) unprotected | Add `length <= 0` boundary check | ✅ `e21373e` |

### P3 — Long-term

| ID | Issue | Fix Approach | Status |
| --- | --- | --- | --- |
| B-042 | `gemini.py:41` `_wait_for_file` no timeout, permanently blocks when file processing hangs | Add `timeout` parameter with `time.monotonic()` check | ✅ `a276225` |
| B-043 | `.githooks/pre-commit:21` `git add` may stage workspace changes user didn't intend to commit | Only stage ruff-formatted files: check if ruff changed them before `git add` | 🆕 |
| B-044 | `_helpers.py:51` `_eta_line` always shows `1/total` when `completed=0`, but actual progress may be 3rd, 4th entry | Use `i` instead of hardcoded `1` | ✅ `a276225` |
| B-045 | `sidebar.js:177` video list rendering piles up `{ once: true }` click listeners on `document`, close dropdown logic fails | Use event delegation + persistent handler, or `removeEventListener` before rendering | ✅ `a276225` |
| B-059 | `_parse_providers` doesn't read `requests_per_minute` and `retry_attempts` from YAML | `cfg.get("requests_per_minute", 0)` + `retry_attempts` default unified to 2 | ✅ `a276225` |
| B-060 | Original video view split segment index lost — each original file only uses `comp[0]`, plan referencing `002`/`003` returns 404 | Iterate all matches in `comp`, create independent video entries for each split segment | ✅ `c59880d` |
| B-072 | `tasks/compress.py` corrupted `.mp4` permanently skipped by `skip_existing` without retry | Add file integrity check or fallback retry | 🆕 |
| B-073 | `routes/videos.py` `_parse_segment_info` only recognizes `001_GL010683_seg01` format | Relax naming convention assumptions, support custom naming | 🆕 |
| B-086 | `server.py:524` hardcodes `config_path.parent / "projects.json"` instead of calling `_registry_path()` | Use `_registry_path(config_path)` for consistency | 🆕 |
| B-087 | `serve.ps1`/`serve.sh` hardcodes project directory paths | Remove hardcoded paths, make distributable | 🆕 |
| B-088 | `ROADMAP.md` 656 lines — completed features not archived | Archive completed `[x]` sections to separate file | 🆕 |
| B-089 | `AGENTS.md` §7 commit history 100+ entries too long | Trim to ~30 most recent, archive rest | 🆕 |
| B-090 | `pipeline.py` cancel_event not propagated to analyze/scripts/plan/label | Add `cancel_event` param + loop check to all 4 functions (see U-005) | 🆕 |
| B-091 | `RateLimiter.__enter__` holds lock during `time.sleep()`, blocks parallel AI calls | Split acquire() from sleep (see U-006) | 🆕 |
| B-092 | `whisper_routes.py` ctypes thread kill unsafe (C ext blocks injection, resource leak) | Replace with chunked download (see U-007) | 🆕 |
| B-093 | `transcribe.py` low-confidence segments silently dropped, no record kept | Mark with `low_confidence` flag instead of discard (see U-009) | 🆕 |
| B-094 | `/api/fs/dirs` no path restriction, exposes full filesystem in LAN mode | Add root restriction + token auth (see U-008) | 🆕 |
| B-095 | `server.py` only 6% test coverage, no integration tests for dispatch/error paths | Add HTTP-level tests (see U-010) | 🆕 |
| B-096 | `whisper_routes.py` 48% coverage — new feature, test lagging behind | Add tests for install/cancel/model management flows | 🆕 |
| B-097 | `videos.py:101` `text_sidecars.get(idx)[0]` always picks first text file for all split segments, each segment should map to its own text/script sidecar | Match by segment-specific filename pattern instead of `[0]` | 📝 new |
| B-074 | `analyze.py:_wrap_with_context` reads `trip_context.md` from disk on every AI call | Module-level `_trip_context_cache` | ✅ `fe57a7f` |
| B-075 | `ui/server.py` Range request doesn't support suffix `bytes=-N` | Empty start + non-empty end → suffix calculation | ✅ `d2591a9` |
| B-076 | `utils/discover_ffmpeg_bin` hardcoded `G:/ffmpeg` | Remove, use `FFMPEG_HOME` env var instead | ✅ `74c34f5` |
| B-077 | `tasks/analyze.py` `_resolve_original` ValueError on stem without `_` | Add `if "_" not in stem:` guard | ✅ `e6e7666` |
| B-078 | `main.py` doesn't pass `project_dir` to `load_config`, project.yaml ignored | Infer `project_dir` from `-i` directory or cwd | ✅ `60d765f` |
| B-079 | `log.py` `_TeeWriter.__getattr__` passes through `close`/`writelines`/`truncate` | Intercept and raise AttributeError | ✅ `947a320` |
| B-080 | `openai_compat.py` hardcoded `attempts=3` ignores configured `retry_attempts` | Read from `cfg.retry_attempts` + `+1` conversion | ✅ `ef2311d` |
| B-081 | `gemini.py` `retry_attempts` semantics inconsistent with openai_compat (missing `+1`) | Align to `max(1, cfg.retry_attempts + 1)` | ✅ `ef68308` |
| B-082 | `ai/factory.py` provider cache not thread-safe + no test cleanup mechanism | Add lock + `_clear_provider_cache()` + autouse fixture | ✅ `ef68308` |
| B-083 | `ui/routes/run.py` `obj.get("index")` unsanitized used as glob pattern | `re.sub(r"[^a-zA-Z0-9_-]", "")` filter | ✅ `bebf21f` |
| B-084 | `ui/static/src/editor.js` `save()` data references not captured at call site | Capture `planData/textsData/voiceoverData/configRaw` | ✅ `bebf21f` |
| B-085 | `ui/static/src/editor.js` transcript edit onblur reads from `state.currentVideo` instead of captured value at dblclick | Capture `origV` at dblclick time | ✅ `fe511be` |

## ~~Test Coverage Gaps~~ ✅ All Fixed (163 New Tests, 2026-06-13)

All B-046~B-052 covered by 163 new tests:

| ID | Priority | Original Issue | Fix |
| --- | --- | --- | --- |
| B-046 | High | `with_retry` no tests | `test_utils.py::TestWithRetry` (5 tests) |
| B-047 | High | `cut_one` no tests | `test_cut.py::TestCutOne` (3 tests) |
| B-048 | High | `_TeeWriter` / `setup_logging` no tests | `test_log.py::TestTeeWriter` + `TestSetupLogging` (8 tests) |
| B-049 | Medium | `ProgressTracker.log()` no tests | `test_progress.py::test_log_appends` / `test_log_truncates_at_100` |
| B-050 | Medium | `resolve_binary` no tests | `test_utils.py::TestResolveBinary` (3 tests) |
| B-051 | Medium | ETA tests depend on sleep | Changed to use `mock.patch("time.monotonic")` to inject time |
| B-052 | Medium | ETA assertion doesn't verify None | Changed to `assert data.get("eta_sec") is None` |
| B-009 | AI occasionally outputs non-pure JSON, `extract_json` parsing fails | Trailing comma repair via regex fallback + 6 new tests | ✅ `badb621` |
| B-011 | New users `python main.py check` false failure (unfriendly messages) | Optimize check step messages, platform-agnostic setup script hint | ✅ `bdcc678` |
| B-010 | (Pending further confirmation) | — | |
| B-019 | `VIDEO_EXTS` duplicate definition (utils.py includes .avi/.mkv, server.py does not) | Move to `vlog_tool/_constants.py` for unified reference | ✅ `4ac5785` |
| B-020 | `_write_csv` `format_index(rec.index, 3)` hardcoded `3` instead of using config | Use `config.naming.index_width` instead | ✅ `4ac5785` |

## Performance Optimizations

| ID | Bottleneck | Optimization Plan | Priority |
| --- | --- | --- | --- |
| P-001 | AI analysis (analyze step) is pure serial, each video waits for previous upload+process+generate | `ThreadPoolExecutor(max_workers=3~5)` after RateLimiter refactoring (U-006). See part2 review §P-1 for details | P2 |
| P-002 | Repeated ffprobe calls to read same video's `duration_sec` / `size_mb` | Cache already-read info, reuse results | P3 |
| P-003 | `GET /api/videos` iterates directory every time, high I/O cost | Add directory mtime cache, reuse unchanged scan results | P3 |

## Completed (Recent, Reverse Chronological)

| Commit | Description |
| --- | --- |
| `f24bdf3` | fixup: address review findings - venv detection with sys.prefix, refine route security/proj_input/post-body cleanup |
| `089dc6a` | feat(ui): add refine panel with context textarea and AI trigger button (R-003e) |
| `cae3c9a` | feat(ui): differentiate project vs global config save message (R-015c) |
| `7017ff6` | fix(analyze): deepcopy input in _validate_* to prevent side effects (B-008) |
| `bdcc678` | fix(main): cross-platform venv detection and platform-agnostic check messages (B-007/B-011) |
| `badb621` | fix(utils): handle trailing commas in extract_json with fallback repair (B-009) |
| `fe45f53` | fix: lint F541 f-string and UT assertion after empty-state changes |
| `c1584df` | fix(ui): move all event handlers before try block so they work in empty state |
| `aa720d8` | fix(ui): move modal event binding before init early return; remove duplicate code |
| `fcbccf5` | feat(serve): add quick-launch scripts for web UI |
| `360b91a` | fix(ui): show placeholder instead of 'loading...' when no project loaded |
| `12c314e` | feat(ui): project remove, empty state, no default input_dir |
| `3a5eaed` | fix(setup): improve idempotency, input dir check, and CUDA disk space handling |
| `7f5c0d6` | feat(ui): layout overhaul - resizable panels, dark OLED theme, run step sub-options |
| `5029ba1` | feat(ui): play/pause toggle for preview, stop no longer resets to segment 0 |
| `e4818af` | fix(ui): preview bar blocks start preview when inactive |
| `0d322c2` | fix(ui): two-row preview bar, buttons work without clicking segment first, fix MouseEvent leak |
| `67d8b0d` | feat(ui): preview bar blocks show seg number + tooltip with title and time window |
| `de03cc2` | fix(ui): plan segment click integrates with preview system |
| `298a729` | fix(ui): correct $() calls - use IDs without # prefix |
| `d410c4e` | fix(compress): fix closure late-binding trap in progress callback |
| `129de90` | feat(ai): add structured validation for AI responses (P2-1) |
| `eb93573` | fix(analyze): clean up stale existing files on source_file mismatch (P2-6) |
| `097a6ff` | fix(split): clean up partial segments + atomic manifest (P2-2) |
| `123c84f` | fix(tasks): use atomic writes for scripts/refine output (P0-3) |
| `3ce9ef3` | fix(prompts): TRANSCRIPT_CONTEXT English→Chinese (Q-6) |
| `cdcc873` | fix(ai): include file mtime in trip_context_cache key (P2-3) |
| `6d23de3` | fix(transcribe): use find_videos for recursive scanning (P2-5) |
| `78a0b69` | fix(compress): raise MIN_VALID_SIZE 256→50KB (P2-7) |
| `3660fea` | fix(ai): add max_tokens + temperature to OpenAI API (P1-2) |
| `a29a53c` | fix(plan): record ProcessingState after generating plan (P0-5) |
| `bebf21f` | fix(save): capture data refs at entry; sanitize index_prefix in rerun |
| `ef68308` | fix(review): align Gemini retry_attempts, thread-safe provider cache, test isolation |
| `ef2311d` | fix(ai): use configurable retry_attempts |
| `947a320` | fix(log): block destructive calls on _TeeWriter |
| `60d765f` | fix(cli): pass project_dir to load_config |
| `9288216` | fix(utils): add stdout=DEVNULL to run_ffmpeg Popen |
| `e6e7666` | fix(tasks): handle stem without underscore |
| `74c34f5` | fix(utils): remove hardcoded G:/ffmpeg |
| `b072240` | fix(security): add _is_safe_basename for cut day_label |
| `d2591a9` | fix(ui): handle suffix range bytes=-N |
| `08d815c` | fix(ui): clean up portal close listener |
| `1406e0e` | fix(ui): guard startRun with btn.disabled check |
| `8d3b2f8` | fix(ui): capture state at save() entry |
| `fe511be` | fix(ui): capture video ref at dblclick in transcript edit |
| `71659aa` | fix(ai): cache provider instances |
| `18ccee4` | fix(config): filter unknown YAML fields |
| `dba1cd9` | fix(ai): fail fast on non-retryable 4xx |
| `bce09ce` | fix(ui): replace addEventListener with onloadedmetadata |
| `89614a4` | fix(ui): delegate switchToOriginalThenCompress to setSource |
| `41abe5b` | fix(security): add _is_safe_basename guard to rerun |
| `1b53499` | fix(transcribe): resolve rerun 404, CUDA fallback, UI transcript display |
| `d0d0847` | fix(compress): fallback skip when split segments exist but source is original |
| `6a56eaf` | fix: batch fix 19 review issues from project-wide code audit |
| `fe1a078` | fix(compress): filter partial files (<256B) from existing_map |
| `1c5d681` | fix(cli): lazy imports prevent google-genai loading on whisper install |
| `8412e03` | fix(config): hf_endpoint defaults to empty, only overrides when configured |
| `31abfac` | feat(processing-state): per-file pipeline state matrix with UI table |
| `eff8fce` | feat(ui): per-file compress log in run tab panel |
| `417aa0a` | fix(ui): keep btn enabled when stale progress from interrupted run |
| `c600840` | fix(ui): pollRunStatus shows progress when s.status==='running' even without live thread |
| `11ea035` | fix(compress): skip_existing now matches existing files by stem instead of by path |
| `306f349` | feat(compress): real-time stderr progress with progress_callback for tracker |
| `1d1b46a` | fix(whisper): replace torch with ctranslate2 for CUDA detection |
| `812b520` | fix(whisper): lazy import torch in whisper_cli |
| `c6e01ec` | feat(whisper): reorder pipeline, per-video rerun, plan toggle, UI error handling |
| `34846df` | fix(pipeline): validate step names before execution |
| `ea2e79c` | fix(progress): random suffix for tmp file to avoid name conflicts |
| `34c0d3b` | refactor(ui): remove hasattr(handler.server) patterns, use direct attr access |
| `fe57a7f` | fix(analyze): use project-level trip_context.md with read cache |
| `7f05ee4` | feat(ui): return segment_matches array for multi-segment original videos |
| `51f50d7` | fix(analyze): replace *.mp4 glob with VIDEO_EXTS filtering, move import re to top |
| `e21373e` | fix(config): clear _config_cache on global config write and cap cache at 20 entries |
| `fad1cc8` | feat: add .lrv (GoPro proxy) video format support |
| `cb4d8e9` | fix(ui): delegate browse-btn click handler to cover dynamically created buttons |
| `2cc3451` | fix(cut): resolve original source path and apply segment offset for split videos |
| `86a281d` | fix(ui): add offset_sec to timeline click seek in texts tab |
| `c78622f` | fix(ui): compute segment offset_sec for original view |
| `3fb8263` | fix(ui): update plan preview counter and unique video identity for split segments |
| `e6e068c` | feat(ui): show AI analysis title below filename in sidebar video list |
| `e72ba10` | fix(ui): create per-segment entries in original video view for plan segment playback |
| `c59880d` | feat(analyze): add progress_callback for per-file upload/wait/AI/disk granularity |
| `6c2ab33` | chore: add pre-commit hook to auto-format staged .py files with ruff |
| `4d146d0` | style: ruff format vlog_tool/ui/services/file_service.py and project_service.py |
| `2f1d56c` | docs: add config hot-reload audit spec (R-015) and update ROADMAP |
| `e3f87a1` | feat(config): add migrate-config subcommand to inject provider defaults |
| `a276225` | fix: batch P2/P3 bug fixes (B-005/B-017/B-018/B-042/B-044/B-045/B-059) and config injection |
| `93eb4f1` | fix(ui): wrap _config_cache.pop with _config_cache_lock |
| `dc01300` | fix(run): serialize _run_thread check-and-set under _run_lock |
| `c283bb9` | fix(ui): hoist statusEl/fill/logsEl before early return |
| `8608d14` | fix(analyze): add .m4v and .webm to _resolve_original |
| `18f7358` | fix(ui): serve correct MIME type per video extension |
| `7868a95` | fix(ui): overwrite stale .bak in _save_atomic instead of skip |
| `3b69ff0` | fix(ui): prevent duplicate project in _list_projects |
| `e404042` | docs: add UI screenshots to README preview |
| `4aa5015` | ci: add --cov-branch, README coverage badge + 343 test table |
| `51ac8fc` | fix(tests): cross-platform CI failures (MTS case, PermissionError, thread leak) |
| `68ec476` | docs: UT-progress v2 with run_compress_all + run_analyze_all (163 new, 343 total) |
| `284ead0` | test(tasks): 6 tests for run_analyze_all duration gate + skip existing |
| `ffe0e58` | test(tasks): 3 tests for run_compress_all orchestration |
| `40431c8` | test(routes): 18 tests for run pipeline + project CRUD handlers |
| `3df0705` | test(compress): 6 tests — compress_video bitrate/flags/duration |
| `c62b507` | test(split): 7 tests — split_video segment computation |
| `a11aecd` | test(analyze): 9 tests — _wrap_with_context, plan_daily_vlog filtering |
| `6dafde9` | test(routes): 30 tests for videos/plan/config route handlers |
| `5a54a2b` | test(project_service): 22 tests — output dir, registry, step detection |
| `f9edede` | test(tasks): tests for _helpers.py + _resolve_original |
| `7e7e138` | test(file_service): 60 tests — basename/segment/atomic/config coercion |
| `c197496` | test(ai): 12 tests — factory dispatch + provider instantiation |
| `2f3c86c` | feat(ui): segment group tree in sidebar (Plan B frontend) |
| `0ab6960` | feat(ui): group_key/segment_label/groups in /api/videos (Plan B backend) |
| `539b587` | feat(ui): _segNN matching for compressed-original lookup (Plan A) |
| `fe2134a` | feat(ai): retry Gemini ClientError 429 with should_retry callback |
| `9d69a44` | feat(split): video splitting + long-video duration gate |
| `31c972d` | fix: enable compress step in pipeline runner |
| `464c3d4`~`ba02b86` | Bug fix spree: B-021~B-041 (19 bugs: cut -to→-t, empty dir misdetect, atomic project.json, int guard, detect-steps, temp name, config cache lock, ffprobe N/A, audio bitrate budget, rerun timeout/path, save_atomic race, B-040 path empty, B-039 provider close) |
| `75b2ffd` | feat(plan): add preview playback + speed control (R-011) |
| `1912012` | refactor(ui): improve plan naming, move day selector to plan tab |
| `250a35c` | style(lint): fix all ruff CI lint errors |
| `c474830` | test: with_retry, cut_one, TeeWriter, ProgressTracker.log (B-046~B-052) |
| `b0da41a` | refactor: split app.js into ES modules (Phase 1d) |
| `0918da0` | refactor: split server.py into routes/ and services/ (Phase 1c) |
| `cac4d67` | refactor: split pipeline.py into tasks/ package (Phase 1b) |
| `5e8d376` | refactor: extract global constants to _constants.py (Phase 1a) |
| `b6b84df`..`66613cc` | CI + 118 original tests (config/utils/cut/log/progress) |
| `a8daa63` | feat(ui): pipeline step selection with checkboxes (R-005f) |
| `29bcb35` | feat(ui): pipeline runner with progress tracking (R-005) |
| `a3d2fe0` | feat(ui): multi-project switching with create (R-007) |
| `9c73903` | fix: P0 bugs B-012/B-013/B-015 + lock dependency versions |
| `a93b5f5` | R-004 UI config editing (backend raw config API / recursive nested form / validation + .bak save / docs) |
| `6706dc3`..`2ad23f5` | R-002 CLI + UI cut (cut.py + POST /api/cut + cut tab + manifest.md) |
| `0d52cf6`..`439911c` | Local Web UI (backend / CLI / frontend / docs / plan-seek fix) |
| `88679ee`..`ec83f48` | R-001 UI source toggle (backend dual source / top toggle + match badge) |
| `a648e60`..`778c44a` | R-006 sidebar hierarchy (HTML+CSS / JS state machine / README layout diagram) |
| `d6d62ef` | feat(config): per-project configuration via project.yaml |
| `a9996a9` | fix(ai): clean up Gemini File API uploads + retry (B-001, B-002) |
| `25128d1` | feat(ai): retry transient API failures with exponential backoff |

---

## ✅ Recently Completed (Verified 2026-06-21 Code Review)

Items found already implemented during code-audit of ROADMAP:

| ID | Description | Key Evidence |
|----|-------------|-------------|
| **U-001a** | `config_cache.py` with LRU + mtime + thread-safe | `vlog_tool/ui/services/config_cache.py` (79 lines) |
| **U-001b** | `_resolve_project_input` + `resolve_last_project_config` in `project_service.py` | `project_service.py:resolve_project_input, resolve_last_project_config` |
| **U-001c** | `send_video_range` + `resolve_texts`/`resolve_in` in `file_service.py` | `file_service.py:send_video_range, resolve_texts, resolve_in` |
| **U-001d** | `server.py` reduced to ~360 lines, route dispatch only | `server.py` (363 lines) |
| **U-003** | Config module split: `config/` package with 7 modules | `config/__init__.py`, `loader.py`, `models.py`, `parsers.py`, `validators.py`, `enums.py`, `descriptions.py` |
| **U-004** | `projects.json` path centralized via `_registry_path()` | `project_service.py:_registry_path` — all callers use it |
| **U-005** | `cancel_event` in all pipeline steps + generic propagation | `tasks/{analyze,scripts,plan,label}.py` all have `cancel_event` param; `pipeline.py:108` generic kwargs |
| **U-006** | `acquire()` method in RateLimiter; gemini + openai_compat use it | `ratelimit.py:acquire()` returns wait without lock-sleep; `gemini.py:117`, `openai_compat.py:41` call `acquire()` |
| **U-009** | Low-confidence segments kept with `low_confidence` flag + UI ⚠ icon | `transcribe.py:150-158` always appends; `editor.js:277` renders ⚠; `style.css` warning-color styling |
| **R-009b** | `setup.sh` exists at repo root | `setup.sh` (180 lines, Linux/macOS equivalent of setup.ps1) |
