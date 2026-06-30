# Archived ROADMAP Sections (2026-07-01)

Archived from `ROADMAP.md` to reduce file length. Kept for historical reference.

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
| B-019 | `VIDEO_EXTS` duplicate definition (utils.py includes .avi/.mkv, server.py does not) | Move to `clio/_constants.py` for unified reference | ✅ `4ac5785` |
| B-020 | `_write_csv` `format_index(rec.index, 3)` hardcoded `3` instead of using config | Use `config.naming.index_width` instead | ✅ `4ac5785` |

## Completed (Recent, Reverse Chronological)

| Commit | Description |
| --- | --- |
| `ae56e6d` | test(server): auth tests for sensitive routes (12 cases) |
| `767bc92` | feat(server): add token-based auth for LAN-exposed UI |
| `7ba48aa` | fix(tasks): prefer media_identity offset_sec for cut segment offset |
| `0ce946f` | fix(ui): use media_identity for transcript matching in videos route |
| `cd717a0` | fix(export): use media_identity for source resolution, apply segment offset |
| `943472e` | fix(plan): match transcripts by original_stem from media_identity |
| `5a86c95` | refactor(tasks): add identity field to ClipRecord dataclass |
| `83c6132` | fix(transcribe): write media_identity block in transcript JSON |
| `7179b30` | fix(analyze): write media_identity + _schema_version in analysis JSON |
| `2c95f18` | feat(identity): add MediaIdentity dataclass with resolve/load helpers |
| `fa5fee1` | test: add unit tests for files/overwrite params across all pipeline steps (R-018) |
| `95b539f` | fix(review): address code review - fix label.py shadow, plan.py overwrite gate, add type validation and tests (R-018) |
| `5b0a9c0` | feat(ui): wire selection mode to runner - send files/overwrite params, show badge (R-018d/e) |
| `983f526` | feat(ui): add selection mode with checkboxes and select all/cancel in sidebar (R-018a) |
| `54dc63e` | feat(ui): add selectionMode + selectedFiles to state, clear on source switch (R-018) |
| `58003f8` | feat(tasks): add files filter and overwrite param to all pipeline steps (R-018b) |
| `f9828b8` | feat(run): accept files filter + overwrite flag in API and pipeline (R-018b) |
| `3ace4f4` | docs: add R-018 multi-video selection design doc + .superpowers to gitignore |
| `6efbcc3` | fix(ai): fix return type annotation in OpenAICompatProvider and add type hint to _call_ai fn parameter (code review fix) |
| `27fb86a` | test: update provider tests for AIResponse return type |
| `e875159` | feat(ui): add Tokens sidebar entity with usage statistics panel |
| `b234a1b` | feat(cli): add tokens subcommand for token usage stats |
| `4057373` | feat(ui): add GET /api/token-usage backend route |
| `8a1dfc8` | feat(tasks): inject FileTokenUsageStore into all AI pipeline steps |
| `05ce1b9` | feat(analyze): collect token usage from AIResponse in _call_ai |
| `3fb5e74` | fix(ai): guard against None content in openai_compat AIResponse |
| `4814bc8` | feat(ai): OpenAI compat provider returns AIResponse with token_usage |
| `ff5ac43` | refactor(ai): extract _extract_usage helper in Gemini provider |
| `94769e6` | feat(ai): Gemini provider returns AIResponse with token_usage |
| `e41c58f` | fix(ai): address code review - _merge_stats returns None, use _EMPTY_STATS constant, add lock to get_stats |
| `01317f0` | feat(ai): add TokenUsage, AIResponse types and FileTokenUsageStore |
| `aa9ddcf` | docs(spec): add R-014 token usage design doc |
| `d799f21` | fix(config): restore missing analyze: header in config.example.yaml (codereview); fix(refine): move json.loads into try block |
| `91f1da4` | docs(config): add reencode_split example to config.example.yaml |
| `94f4501` | fix(tasks): move elapsed_total to finally block for accurate ETA (B-004) |
| `cd1da63` | feat(split): add reencode_split option for frame-accurate cuts (B-068) |
| `6c3c231` | fix(compress): add ffprobe integrity check for skip_existing (B-072) |
| `92a6d9e` | feat(config): add ai.debug_print_prompt for prompt debugging (R-018) |
| `a10efb1` | docs: remove ASCII UI art, add new screenshots |
| `a5dd5b0` | docs(readme): replace small image table with full-width screenshot gallery |
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
| `4d146d0` | style: ruff format clio/ui/services/file_service.py and project_service.py |
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

## ✅ Recently Completed (2026-07-01)

| Commit | Description |
| --- | --- |
| `43a922b` | feat(ui): run panel prompt injection (R-019) |
| `05edab2` | fix(ui): segment-specific text/script matching in video list (B-097) |

## ✅ Recently Completed (Verified 2026-06-21 Code Review)

Items found already implemented during code-audit of ROADMAP:

| ID | Description | Key Evidence |
|----|-------------|-------------|
| **U-001a** | `config_cache.py` with LRU + mtime + thread-safe | `clio/ui/services/config_cache.py` (79 lines) |
| **U-001b** | `_resolve_project_input` + `resolve_last_project_config` in `project_service.py` | `project_service.py:resolve_project_input, resolve_last_project_config` |
| **U-001c** | `send_video_range` + `resolve_texts`/`resolve_in` in `file_service.py` | `file_service.py:send_video_range, resolve_texts, resolve_in` |
| **U-001d** | `server.py` reduced to ~360 lines, route dispatch only | `server.py` (363 lines) |
| **U-003** | Config module split: `config/` package with 7 modules | `config/__init__.py`, `loader.py`, `models.py`, `parsers.py`, `validators.py`, `enums.py`, `descriptions.py` |
| **U-004** | `projects.json` path centralized via `_registry_path()` | `project_service.py:_registry_path` — all callers use it |
| **U-005** | `cancel_event` in all pipeline steps + generic propagation | `tasks/{analyze,scripts,plan,label}.py` all have `cancel_event` param; `pipeline.py:108` generic kwargs |
| **U-006** | `acquire()` method in RateLimiter; gemini + openai_compat use it | `ratelimit.py:acquire()` returns wait without lock-sleep; `gemini.py:117`, `openai_compat.py:41` call `acquire()` |
| **U-009** | Low-confidence segments kept with `low_confidence` flag + UI ⚠ icon | `transcribe.py:150-158` always appends; `editor.js:277` renders ⚠; `style.css` warning-color styling |
| **R-009b** | `setup.sh` exists at repo root | `setup.sh` (180 lines, Linux/macOS equivalent of setup.ps1) |
