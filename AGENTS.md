# AGENTS.md — AI Maintenance Manual & Project Memory

> This document is a quick reference for **future AI assistants taking over maintenance**.
> Contents will evolve with the project; it has a different role from `README.md` (which is end-user facing).
> User preference: Chinese for conversation, **English** for commit messages and this document.

## 1. Project in One Sentence

An **AI preprocessing pipeline**: raw travel vlog footage → ffmpeg compression → Gemini reviews video + DeepSeek writes script → JianYing (CapCut) manual editing.
The end user is a solo vlogger: first compress and feed to AI, then add effects/lip-sync in JianYing (CapCut).

## 2. Tech Stack

- **Python 3.11+** (uses PEP 604 `X | None` and dataclass)
- **ffmpeg / ffprobe** (video processing; GoPro 4K source → 640p 5MB compressed)
- **google-genai** (Gemini 2.5 Flash's video File API)
- **httpx** (DeepSeek / OpenAI compatible calls)
- **PyYAML** (config parsing)
- **pytest** (unit tests, auto-run in CI; currently **612 test cases**)

Dependencies in `requirements.txt`; `setup.ps1` (Windows) / `setup.sh` (Linux/macOS) creates venv + installs ffmpeg + copies `.env` in one click.

## 3. Directory Structure

```
vlog-video-analysis/
├── main.py                    # CLI entry, all subcommands registered here
├── vlog_tool/
│   ├── config.py              # AppConfig dataclass + load_config
│   ├── shutdown.py            # beforeStop hook: atexit + SIGTERM → kill ffmpeg + close provider connections + flush IO
│   ├── pipeline.py            # High-level pipeline functions (run_analyze_all, etc.)
│   ├── analyze.py             # AI interaction (analyze_video, generate_voiceover, plan_daily_vlog, refine_*)
│   ├── compress.py            # ffmpeg wrapper
│   ├── prompts.py             # All prompt templates (constants)
│   ├── transcribe.py          # Whisper ASR transcription core
│   ├── whisper_cli.py         # whisper install/check CLI
│   ├── utils.py               # ffmpeg path discovery, file IO, mask_if_looks_like_key, extract_json
│   ├── log.py                 # Logging: hourly rotating files + _TeeWriter + timed/format_size/format_duration
│   │                           #     + sys.excepthook turns uncaught exceptions into a single ERROR log
│   ├── tasks/                 # Pipeline steps (split from pipeline.py)
│   │   ├── transcribe.py        # Pipeline task: run_transcribe_all
│   │   └── ...
│   ├── ui/                    # Local Web UI (visual editing of AI output; stdlib http.server, zero new deps)
│   │   ├── server.py            #   UIHandler (BaseHTTPRequestHandler) + make_handler + run
│   │   ├── README.md            #   UI usage documentation
│   │   ├── routes/              #   Route handlers
│   │   │   ├── refine.py           #   POST /api/refine (AI refine trigger)
│   │   │   ├── transcripts.py   #   Transcript GET/PUT API
│   │   │   └── whisper_routes.py#   Whisper check API
│   │   └── static/              #   Frontend, no build step, ES modules
│   │       ├── index.html
│   │       ├── style.css
│   │       └── src/
│   │           ├── main.js
│   │           ├── layout.js        #   Draggable panels, collapse, persistence
│   │           ├── sidebar.js
│   │           ├── runner.js
│   │           ├── editor.js
│   │           ├── viewer.js
│   │           ├── api.js
│   │           ├── state.js
│   │           └── utils.js
│   └── ai/
│       ├── base.py            # TaskName enum, Provider Protocol
│       ├── factory.py         # Look up provider by name
│       ├── gemini.py          # Multimodal: File API upload + poll PROCESSING (wrapped with_retry)
│       └── openai_compat.py   # OpenAI compatible: DeepSeek / OpenAI / Tongyi Qianwen (通义) / Moonshot (Kimi) (wrapped with_retry)
├── templates/
│   ├── vlog_template.md       # Voice-over style template (user-customizable)
│   └── trip_context.md        # Trip background & AI rules (auto-injected into all prompts)
├── config.example.yaml        # Config template committed to git
├── .env.example               # Env variable template committed to git
├── config.yaml / .env         # User's local real config, gitignored
├── requirements.txt           # Loose dev dependencies
├── requirements-locked.txt    # Reproducible build with pinned versions
├── .github/workflows/test.yml # GitHub Actions CI (pushes + PRs)
├── vlog_tool/tests/           # Unit tests (pytest, 587 cases)
│   ├── conftest.py            #   Shared fixtures
│   ├── test_ai.py             #   11 tests - factory dispatch / TaskName / provider instantiation
│   ├── test_ai_gemini.py      #   25 tests - Gemini client / retry / upload / wait
│   ├── test_ai_openai_compat.py#  17 tests - OpenAI compat / retry / close
│   ├── test_analyze.py        #   10 tests - _resolve_original file matching
│   ├── test_analyze_funcs.py  #    9 tests - _wrap_with_context / plan filtering
│   ├── test_compress.py       #    7 tests - compress_video bitrate / params / cancel
│   ├── test_config.py         #   34 tests - config loading/merging/validation
│   ├── test_cut.py            #   25 tests - time parsing / filename generation / cutting
│   ├── test_file_service.py   #   60 tests - safe basename / atomic save / segment matching
│   ├── test_helpers.py        #   20 tests - _next_index / _write_csv / _rewrite_text_file
│   ├── test_log.py            #   13 tests - TeeWriter / format_size / format_duration
│   ├── test_main.py           #    7 tests - CLI subcommand dispatch
│   ├── test_pipeline.py       #    4 tests - cancel_event propagation
│   ├── test_plan.py           #    2 tests - plan prompt transcript injection
│   ├── test_processing_state.py#   8 tests - mark / reset / persistence / corruption recovery
│   ├── test_progress.py       #   14 tests - ProgressTracker read/write/ETA/atomic write
│   ├── test_project_service.py#   22 tests - output dir / registry / step detection
│   ├── test_ratelimit.py      #   12 tests - RateLimiter interval/logging
│   ├── test_routes_config.py  #    5 tests - config GET/PUT/INIT routes
│   ├── test_routes_plan.py    #    6 tests - plan GET/PUT/cut routes
│   ├── test_routes_projects.py#    9 tests - project CRUD routes
│   ├── test_routes_run.py     #    8 tests - run start/status/rerun/cancel routes
│   ├── test_routes_texts.py   #    8 tests - texts/voiceover GET/PUT routes
│   ├── test_routes_transcripts.py# 18 tests - transcript/whisper API routes
│   ├── test_routes_videos.py  #    8 tests - videos GET routes
│   ├── test_split.py          #    7 tests - split_video segment calculation
│   ├── test_tasks_analyze.py  #    6 tests - run_analyze_all orchestration/duration gate
│   ├── test_tasks_compress.py #    4 tests - run_compress_all orchestration
│   ├── test_tasks_cut.py      #   11 tests - run_cut_all / offset calculation / cancel
│   ├── test_tasks_label.py    #    6 tests - run_label_videos orchestration
│   ├── test_tasks_refine.py   #   11 tests - run_refine_texts / scripts / fix mode
│   ├── test_tasks_scripts.py  #    8 tests - run_generate_scripts orchestration
│   ├── test_tasks_transcribe.py#  11 tests - run_transcribe_all / one orchestration
│   ├── test_transcribe.py     #   19 tests - transcribe toggle / device / model / CUDA fallback
│   ├── test_utils.py          #   34 tests - extract_json / mask_key / sanitize / find_videos / with_retry
│   ├── test_utils_expanded.py #   20 tests - run_subprocess / discover_ffmpeg / atomic_io / run_ffmpeg
│   └── test_whisper_cli.py    #    6 tests - whisper check/install status
```

## 4. Key Conventions

### 4.1 Commit

- **English** message, **Conventional Commits** style: `type(scope): subject`
- **Each commit as small as possible**, covering a single independent feature/fix module, to facilitate future branching and rollback
- **Do not bundle multiple independent features in one commit**
- Common types: `feat` / `fix` / `refactor` / `docs` / `chore`
- For rebase history rewriting, prefer `git rebase -i --root`; on Windows the interactive editor can hang, use `git filter-branch --msg-filter` with a byte-level Python script (see [§9 Gotchas](#9-gotchas))

### 4.2 Workflow

- **Plan first, then implement**: before any feature change, record the plan in AGENTS.md or ROADMAP.md, confirm the approach, then write code
- **Document new modules**: every new feature module must be documented (README.md for users, AGENTS.md for AI), including purpose, entry point, and key conventions

### 4.3 Code Style

- Do not write comments unless explaining **why** (WHAT is self-evident in code)
- Chinese for user-facing copy (CLI prompts, error messages, Chinese README version)
- Default `skip_existing=True` policy is shared by all steps (just change the `analyze` toggle)
- AI-returned JSON uses `extract_json()` for fault tolerance (first `json.loads`, then regex for `{}`)

### 4.4 Configuration

- Repository commits `config.example.yaml` and `.env.example`; real `config.yaml` and `.env` are in `.gitignore`
- Any field containing **local paths, proxy IPs, API keys** must not go into examples (use placeholders)
- After config file changes, it is recommended to update both the example and README/en

### 4.5 Prompts

- All placed in `vlog_tool/prompts.py`, as constants
- Trip context is uniformly injected via `_wrap_with_context()` before all prompts; **do not** manually write prefixes in each prompt
- Output format must be JSON (not markdown code blocks) so `extract_json()` can parse it

### 4.6 Future Refactoring Directions

- **Module splitting**: currently `server.py` / `app.js` centralize all UI logic; they should be split into separate files/directories, each responsible for an independent function
- **De-localization**: remove all hardcoded local paths, machine names, specific directory structures from the code to make the project general-purpose / open-source ready
- **Two-phase plan finalized**, see `docs/superpowers/specs/2026-06-09-architecture-cleanup-and-r008-design.md`
  - Phase 1: Split server.py into routes/ + services.py, app.js into state/api/viewer, fill .gitignore gaps, de-localize, fix bugs — **completed**
  - Phase 2: R-008 UI single-step execution (select directory → select files → run steps → progress → auto-refresh)
- **FFMPEG_HOME** environment variable replaces hardcoded paths; `discover_ffmpeg_bin` search chain: `shutil.which` → WinGet Packages (Windows only) → `FFMPEG_HOME`
- **Provider cache**: `ai/factory.py` `_provider_cache` by name, `_provider_cache_lock` thread-safe, `_clear_provider_cache()` for test isolation
- **Config unknown fields**: `_filter_dc()` filters unknown YAML fields before passing to dataclass constructors, silently ignores typos
- **Model registry (R-017)**: future feature where users register models (provider+model+apikey+adapter_type) via UI, tag capabilities (video/text), and bind tasks to compatible models via dropdown selectors

## 5. Standard Practices for Adding New Features

> **First record a requirement in `ROADMAP.md`, break it into sub-tasks, then start.**
> Mark the corresponding sub-task as `[x]` when done and write the commit hash in the "Completed" table.
> The commit list in AGENTS.md will be periodically aligned with ROADMAP.

### Adding a New AI Provider

1. `vlog_tool/ai/newprovider.py` implement `TextAIProvider` and/or `VideoAIProvider`
2. `vlog_tool/ai/factory.py:_PROVIDER_TYPES` register
3. `config.example.yaml` add example; `main.py:check` will auto-list it
4. README (CN/EN) add a line about usage

### Adding a New AI Task (e.g. "subtitle translation")

1. `vlog_tool/ai/base.py:TaskName` add enum value
2. `vlog_tool/prompts.py` add prompt constant
3. `vlog_tool/analyze.py` add `task_xxx()` function, reuse `_wrap_with_context()`
4. `vlog_tool/pipeline.py` add `run_xxx_all()`
5. `main.py` register subcommand
6. Update READMEs

### Changing the AI Used for the Refine Stage

`refine_text` defaults to falling back to `video_analyze` (both texts and scripts review share this one)
(Logic in `vlog_tool/config.py:_parse_tasks`). To switch to a cheaper pure-text model,
explicitly add under `ai.tasks`:

```yaml
ai:
  tasks:
    refine_text:
      provider: deepseek
      model: deepseek-chat
```

### Adding Targeted Fix Mode to Refine (`--fix`)

For known specific errors (misspelled place names, wrong numbering, etc.), `refine --fix '...'` is
more reliable than letting AI freely review:

- Must be used with `-i` specifying a **single** json file (to avoid collateral damage)
- Switches prompt to "Targeted fix based on user feedback," AI only changes fields mentioned in the feedback
- `_changelog` first entry is always written as "Modified XXX per user feedback" for auditability
- Implementation: `vlog_tool/prompts.py`'s `REFINE_TEXT_FIX_PROMPT` /
  `REFINE_SCRIPT_FIX_PROMPT`, `analyze.py`'s `refine_text(refine_script)` with an additional `fix` parameter

### Adding a New CLI Subcommand

1. `main.py` add `p_X = sub.add_parser(...)` and dispatch branch
2. Reuse `_add_io_args()` to obtain `-i/-o`
3. Use `config.analyze.skip_existing` to control whether to skip (consistent with other steps)
4. Update READMEs

## 6. User Preferences (Persistent Memory)

- **Language**: conversation in Chinese, commits/PRs/AGENTS.md in **English**
- **Commit granularity**: one feature per commit, **do not batch**
- **History rewriting**: user accepts force-push to change commit messages (rebase / filter-branch)
- **Do not** leave real API keys / proxy IPs / local paths in config files
- **Do not** write test code (unless explicitly requested by the user)
- When seeing working directory, current time, etc. in `<system-reminder>`, do not repeat them in responses
- **Push must be explicitly confirmed with the user beforehand**. Local commits are fine (commit after finishing a feature),
  but `git push` should always pause and ask "should I push?", then wait for user approval.

## 7. Project Current Status

Last updated: 2026-06-22 (R-014 token usage + code review fixes). Live:
- GitHub Actions CI (Ubuntu, Windows, Python 3.11/3.12)
- **612 pytest cases** (coverage table below)
- Dependency version locked in `requirements-locked.txt`
- Whisper ASR separate `requirements-whisper.txt` (faster-whisper, does not pollute main deps)
- R-014 token usage tracking fully integrated: `FileTokenUsageStore` with atomic writes, `AIResponse` return types on both providers, new UI sidebar entity "Tokens" with summary/task/model breakdown, CLI `tokens` subcommand
Recent commit history:
1. `chore: scaffold initial Vlog editing helper project`
2. `fix(compress): escape comma in scale expression`  ← Windows ffmpeg filter comma escaping
... (#3~#98 same as above) ...
98. `bcfbe04` `feat(ui): add transcripts tab, sidebar badge, and run step`  ← Task 8
99. `c6e01ec` `feat(whisper): reorder pipeline, add per-video transcribe rerun, plan toggle, and UI error handling`  ← Comprehensive enhancement
100. `1d1b46a` `fix(whisper): replace torch with ctranslate2 for CUDA detection (no torch dependency)`  ← Remove torch
101. `306f349` `feat(compress): real-time stderr progress with progress_callback for tracker`  ← Real-time progress
102. `11ea035` `fix(compress): skip_existing now matches existing files by stem instead of by path`  ← Stem matching
103. `c600840` `fix(ui): pollRunStatus shows progress when s.status==='running' even without live thread`  ← Progress panel
104. `417aa0a` `fix(ui): keep btn enabled when stale progress from interrupted run`  ← Button state
105. `eff8fce` `feat(ui): per-file compress log in run tab panel`  ← Compress log
106. `31abfac` `feat(processing-state): per-file pipeline state matrix with UI table`  ← State matrix
107. `8412e03` `fix(config): hf_endpoint defaults to empty, only overrides when configured`  ← Config fix
108. `1c5d681` `fix(cli): lazy imports prevent google-genai loading on whisper install`  ← Lazy imports
109. `fe1a078` `fix(compress): filter partial files (<256B) from existing_map`  ← Filter damaged files
110. `6a56eaf` `fix: batch fix 19 review issues from project-wide code audit`  ← Batch fix
111. `d0d0847` `fix(compress): fallback skip when split segments exist but source is original`  ← Compress branch
112. `1b53499` `fix(transcribe): resolve rerun 404, CUDA fallback, UI transcript display and seek`  ← Comprehensive fix
113. `41abe5b` `fix(security): add _is_safe_basename guard to POST /api/rerun`  ← C1
114. `89614a4` `fix(ui): delegate switchToOriginalThenCompress to setSource`  ← C2
115. `bce09ce` `fix(ui): replace addEventListener with onloadedmetadata`  ← C3
116. `dba1cd9` `fix(ai): fail fast on non-retryable 4xx errors in OpenAI compat`  ← C4
117. `18ccee4` `fix(config): filter unknown YAML fields from dataclass constructors`  ← C5
118. `71659aa` `fix(ai): cache provider instances to prevent HTTP connection leak`  ← C6
119. `fe511be` `fix(ui): capture video ref at dblclick in transcript edit`  ← I1
120. `8d3b2f8` `fix(ui): capture state at save() entry`  ← I2
121. `1406e0e` `fix(ui): guard startRun with btn.disabled check`  ← I3
122. `08d815c` `fix(ui): clean up portal close listener`  ← I4
123. `d2591a9` `fix(ui): handle suffix range bytes=-N`  ← I5
124. `b072240` `fix(security): add _is_safe_basename for cut day_label`  ← I6
125. `74c34f5` `fix(utils): remove hardcoded G:/ffmpeg`  ← I7
126. `e6e7666` `fix(tasks): handle stem without underscore`  ← I8
127. `9288216` `fix(utils): add stdout=DEVNULL to Popen`  ← I9
128. `60d765f` `fix(cli): pass project_dir to load_config`  ← I10
129. `947a320` `fix(log): block destructive calls on _TeeWriter`  ← I11
130. `ef2311d` `fix(ai): use configurable retry_attempts`  ← I12
131. `ef68308` `fix(review): align Gemini retry_attempts, thread-safe provider cache, test isolation`  ← Review feedback
132. `bebf21f` `fix(save): capture data refs at entry; sanitize index_prefix in rerun`  ← Review feedback
133. `8688a85` `fix(tests): mock ctranslate2 module for CI where it's not installed`  ← CI fix
134. `f51e7b9` `fix(tests): return int from mock ctranslate2.get_cuda_device_count`  ← CI fix
135. `88cbf4c` `fix(ci): pass config_path to whisper subcommands, lowercase .mp4 for Linux`  ← CI fix
136. `4abc241` `fix(whisper_cli): add missing Path import for F821`  ← Lint fix
137. `f4a6a71` `test: add 27 high-value unit tests for whisper, processing_state, and CLI`  ← 27 new tests
138. `a29a53c` `fix(plan): record ProcessingState after generating plan`  ← P0-5
139. `3660fea` `fix(ai): add max_tokens + temperature to OpenAI API calls`  ← P1-2
140. `78a0b69` `fix(compress): raise MIN_VALID_SIZE 256→50KB`  ← P2-7
141. `6d23de3` `fix(transcribe): use find_videos for recursive scanning`  ← P2-5
142. `cdcc873` `fix(ai): include file mtime in trip_context_cache key`  ← P2-3
143. `3ce9ef3` `fix(prompts): TRANSCRIPT_CONTEXT English→Chinese`  ← Q-6
144. `123c84f` `fix(tasks): use atomic writes for scripts/refine output`  ← P0-3
145. `097a6ff` `fix(split): clean up partial segments + atomic manifest`  ← P2-2
146. `eb93573` `fix(analyze): clean up stale existing files on source_file mismatch`  ← P2-6
147. `129de90` `feat(ai): add structured validation for AI responses`  ← P2-1
148. `d410c4e` `fix(compress): fix closure late-binding trap in progress callback`  ← Q-2
149. `298a729` `fix(ui): correct $() calls - use IDs without # prefix`  ← R-012
150. `de03cc2` `fix(ui): plan segment click integrates with preview system`  ← R-012
151. `67d8b0d` `feat(ui): preview bar blocks show seg number + tooltip with title and time window`  ← R-012
152. `0d322c2` `fix(ui): two-row preview bar, buttons work without clicking segment first, fix MouseEvent leak`  ← R-012
153. `e4818af` `fix(ui): preview bar blocks start preview when inactive`  ← R-012
154. `5029ba1` `feat(ui): play/pause toggle for preview, stop no longer resets to segment 0`  ← R-012
155. `7f5c0d6` `feat(ui): layout overhaul - resizable panels, dark OLED theme, run step sub-options`  ← Major layout overhaul
156. `3a5eaed` `fix(setup): improve idempotency, input dir check, and CUDA disk space handling`  ← Setup script robustness
157. `12c314e` `feat(ui): project remove, empty state, no default input_dir`  ← Project remove + empty state
158. `360b91a` `fix(ui): show placeholder instead of 'loading...' when no project loaded`  ← Empty state placeholder
159. `fcbccf5` `feat(serve): add quick-launch scripts for web UI`  ← Serve quick-launch scripts
160. `aa720d8` `fix(ui): move modal event binding before init early return; remove duplicate code`  ← Modal fix
161. `c1584df` `fix(ui): move all event handlers before try block so they work in empty state`  ← Event binding fix
162. `fe45f53` `fix: lint F541 f-string and UT assertion after empty-state changes`  ← lint + UT fix
163. `dc3ad72` `fix(config): propagate max_tokens from YAML to ProviderConfig`  ← C3
164. `45e09e3` `fix(ai): fix TOCTOU race in provider cache and close Gemini client properly`  ← C2+C4
165. `9ef45e2` `fix(transcribe): thread-safe os.environ with save/restore pattern`  ← C1
166. `326fe46` `feat(whisper): add POST /api/whisper/install with progress for UI model download`  ← R-016a
167. `e361f7d` `feat(ui): add whisper model download button + progress in transcript tab`  ← R-016b/c
168. `badb621` `fix(utils): handle trailing commas in extract_json with fallback repair (B-009)`  ← 6 new tests
169. `bdcc678` `fix(main): cross-platform venv detection and platform-agnostic check messages (B-007/B-011)`  ← sys.base_prefix
170. `7017ff6` `fix(analyze): deepcopy input in _validate_* to prevent side effects (B-008)`  ← Defensive copy
171. `cae3c9a` `feat(ui): differentiate project vs global config save message (R-015c)`  ← Config UX
172. `089dc6a` `feat(ui): add refine panel with context textarea and AI trigger button (R-003e)`  ← New route + UI
173. `f24bdf3` `fixup: address review findings - venv detection with sys.prefix, refine route security/proj_input/post-body cleanup`  ← Review fixes
174. `92a6d9e` `feat(config): add ai.debug_print_prompt for prompt debugging (R-018)`  ← Debug print
175. `6c3c231` `fix(compress): add ffprobe integrity check for skip_existing (B-072)`  ← Corrupt retry
176. `cd1da63` `feat(split): add reencode_split option for frame-accurate cuts (B-068)`  ← Keyframe fix
177. `94f4501` `fix(tasks): move elapsed_total to finally block for accurate ETA (B-004)`  ← ETA fix
178. `d799f21` `fix(config): restore missing analyze: header in config.example.yaml`  ← YAML structure fix
179. `91f1da4` `docs(config): add reencode_split example to config.example.yaml`  ← Config doc
180. `b4bd05b` `feat(config): auto-inject missing dataclass field defaults into config YAML`  ← Auto-upgrade
181. `aa9ddcf` `docs(spec): add R-014 token usage design doc`  ← Design doc
182. `01317f0` `feat(ai): add TokenUsage, AIResponse types and FileTokenUsageStore`  ← Core types
183. `e41c58f` `fix(ai): address code review - _merge_stats returns None, use _EMPTY_STATS constant, add lock to get_stats`  ← Code review fix
184. `94769e6` `feat(ai): Gemini provider returns AIResponse with token_usage`  ← Gemini
185. `ff5ac43` `refactor(ai): extract _extract_usage helper in Gemini provider`  ← Cleanup
186. `4814bc8` `feat(ai): OpenAI compat provider returns AIResponse with token_usage`  ← OpenAI compat
187. `3fb5e74` `fix(ai): guard against None content in openai_compat AIResponse`  ← Guard
188. `05ce1b9` `feat(analyze): collect token usage from AIResponse in _call_ai`  ← Pipeline integration
189. `8a1dfc8` `feat(tasks): inject FileTokenUsageStore into all AI pipeline steps`  ← Task injection
190. `4057373` `feat(ui): add GET /api/token-usage backend route`  ← Backend route
191. `b234a1b` `feat(cli): add tokens subcommand for token usage stats`  ← CLI
192. `e875159` `feat(ui): add Tokens sidebar entity with usage statistics panel`  ← UI
193. `27fb86a` `test: update provider tests for AIResponse return type`  <- Test update
194. `6efbcc3` `fix(ai): fix return type annotation in OpenAICompatProvider and add type hint to _call_ai fn parameter`  <- Code review fix

2026-06-18 Review fixes (based on `docs/analysis/2026-06-18-vlog-editing-helper-review.md`, see `docs/analysis/2026-06-18-review-fix-result.md`):
- **P0-1** `cut.py`: switched to `write_json_atomic` / `write_text_atomic` (missed atomic writes)
- **P0-2** `server.py`: project.json migration switched to `write_json_atomic`
- **P0-4** `plan.py`: transcript loading now checks `config.plan.use_transcripts`
- **R-2** `compress.py`: use `_get_audio_bitrate()` (ffprobe detection) instead of hardcoded 128kbps
- **R-3** `tasks/analyze.py`: `run_analyze_all` one-time `_build_stem_to_path` cache, avoids rglob per video
- **R-4** `tasks/cut.py` + `cut.py`: added `cancel_event` support to `run_cut_all` / `cut_one`
- **Q-2** `pipeline.py`: added `"cut"` to cancel_event propagation list
- Confirmed P0-3 (conftest cache cleanup), R-1 (AI response validation), Q-1 (compress closure) **were already fixed in advance**

Recent code review fixes (2026-06-16 second review, 5 S0 + 5 S1 + 1 S2 items):
- **S0-1** `runner.js`: `prog` undefined → `$('run-progress')`
- **S0-2** `analyze.py`: transcript not bound to source_stem → clip carries source_stem, only matches corresponding transcript
- **S0-3** `split.py`: missing manifest → outputs `_split_manifest.json` with source_stem/offset/duration
- **S0-4** pipeline recovery: added `write_json_atomic`/`write_text_atomic` (tmp+rename) + skip on JSON validation failure
- **S1-1** `/api/cut`: ignoring project query → accepts qs parameter
- **S1-2** transcript UI: `_resolve_stem` didn't strip `_segNN` → added `_SEG_SUFFIX_RE` to strip
- **S1-3** `_extract_audio`: hardcoded "ffmpeg" → accepts ffmpeg parameter
- **S1-4** Whisper batch was gated by `max_analyze_duration_min` → removed that check
- **S1-5** AI provider cache: by name only → composite key (name+api_key+base_url+proxy)
- **S2-3** Whisper model cache key: missing device/compute_type → added to key; update key on CUDA→CPU fallback

User's current trip: **2025 National Day holiday, 7-day independent travel in Paris, France** (`templates/trip_context.md`)
Known AI misidentification pitfall: mistaking Charles de Gaulle airport RER for Bangkok's Suvarnabhumi → section 5 of context already documents this.

2026-06-19 UI empty state fixes (project removal, empty project placeholder, event binding early registration):
- **Setup scripts**: `setup.ps1`/`setup.sh` added venv version detection (rebuild if <3.11), CUDA disk space check, setup.ps1 Python three-layer discovery (PATH → py launcher → scan install directories)
- **Project removal**: backend `POST /api/project/remove` + `_remove_from_registry`; frontend project card ✕ button
- **Empty state**: UI no longer loads `input_dir` as default project; empty project shows `—` placeholder instead of "loading..."
- **Event binding early**: all event handlers (modal, browse button, save, reload, tabs, player, keyboard shortcuts) moved before `try` block registration, ensuring they work even in empty state
- **Quick-launch**: added `serve.ps1` / `serve.sh` one-click Web UI startup

Project documentation status:
- 2026-06-16 comprehensive code review (5 parallel subagents): found **6 Critical + 12 Important + 36 Minor**, fixed 6+12+5, 31 Minor remaining
- 2026-06-16 second review (item-by-item): 5 S0 + 5 S1 + 1 S2 all fixed
- `ROADMAP.md` current tracking: R-001（✓）/ R-002（✓）/ R-003（a[✓] b[✓] c[✓] d[✓] e[✓] f[✓]）/ R-004（✓）/ R-005（✓）/ R-006（✓）/ R-007（✓）/ R-008/ R-009/ R-010/ R-011（✓）/ R-012（✓）/ R-013（✓）/ R-014（✓）/ R-015（a[✓] c[✓] d[✓]）/ R-016（a[✓] b[✓] c[✓]）+ Bug tracking（B-001~B-097）+ Performance optimization（P-001~P-003）+ Documentation upkeep（D-001~D-004）+ Architecture improvements（A-001~A-006）+ Code review P0~P3（14 items, 12 fixed）
- Whisper ASR fully integrated: standalone CLI (transcribe / whisper install / whisper check) + pipeline step + UI transcript tab + delete/edit/seek + 10% progress + CUDA fallback CPU + per-video rerun + full UT coverage (18 tests)
- CI compatibility fixes: ctranslate2 mock module, config_path parameter passing, Linux case sensitivity, F821 lint
- New ProcessingState UT (8 tests covering mark/reset_step/persistence/corruption recovery)
- New whisper_cli UT (6 tests covering check/install/not-installed/CUDA/missing-deps/pip failure)
- Per-project config implemented: optional `project.yaml` under each project directory, deep-merge overrides global config.yaml
- Video segment compression implemented (split.py + compress Phase 1/2), default 15-minute split threshold
- UI compressed view supports `_segNN` grouping tree; under original video view, split segments are independent entries with offset_sec conversion
- AI analysis progress refined: `progress_callback`贯穿整个分析流程
- Provider cache: factory caches by name, thread-safe, test isolation auto-cleanup
- Security fixes: rerun/cut path traversal defense (`_is_safe_basename`), non-retryable 4xx errors fail immediately, `index_prefix` sanitized
- Config fixes: unknown YAML fields silently ignored, `project.yaml` works via CLI, `FFMPEG_HOME` environment variable support
- 2026-06-17 comprehensive analysis report fixes: 10 commits covering usability (plan state/atomic writes/max_tokens/validation) through code quality (closure/transcript Chinese/prompts validation), see ROADMAP completed table
- 2026-06-18 R-012 preview progress bar completed: two-row layout (control bar + progress bar), play/pause toggle (no longer stop+reset), segment blocks show index + hover tooltip with title/time window, click/drag to jump segments, plan segment click integrates with preview system

2026-06-22 R-014 AI token usage statistics completed:
- **TokenUsage + AIResponse**: frozen dataclass for token counts, `AIResponse` container replacing bare `str` return on both providers
- **FileTokenUsageStore**: per-project token persistence with atomic writes + thread lock, `TokenUsageStore` ABC for future backends
- **Provider changes**: both Gemini and OpenAI-compat return `AIResponse` with `token_usage` extracted from API response; `_extract_usage()` helper extracted
- **Pipeline integration**: `_call_ai()` collects and records token usage; all 4 task modules inject `FileTokenUsageStore`
- **UI**: sidebar "Tokens" entity with summary cards, model/task breakdown tables, history view (last 100 entries)
- **CLI**: `main.py tokens` subcommand for terminal access
- **Code review**: fixed `OpenAICompatProvider.analyze_video` return type annotation; added `Callable[[], AIResponse]` type hint to `_call_ai` fn parameter
- All 612 tests passing

2026-06-20 Code review fixes + R-016 Whisper model UI download:
- **C3 fix**: `config.py:_parse_providers` was missing `max_tokens` propagation, user config was silently ignored and always 4096
- **C2 fix**: `factory.py` provider cache TOCTOU race, two threads with the same key would leak HTTP connection pools
- **C4 fix**: `gemini.py` `close()` was a no-op, `_clear_provider_cache` didn't release HTTP connections
- **C1 fix**: `transcribe.py` global `os.environ` unsynchronized multi-thread pollution, save/restore pattern + `_env_lock`
- **R-016a**: backend `POST /api/whisper/install` + `GET /api/whisper/install/status`, daemon thread + huggingface_hub callback for real-time progress
- **R-016b**: frontend shows "Download model" button in transcript error area + progress bar/speed/ETA polling
- **R-016c**: auto-rerun transcribe after download completes, poll for results and refresh

## 8. Testing & Development

### 8.1 Running Tests

```bash
# Full run
python -m pytest vlog_tool/tests/ -v

# Single module
python -m pytest vlog_tool/tests/test_utils.py -v
```

GitHub Actions automatically runs all tests on Python 3.11 / 3.12 (Ubuntu + Windows).

### 8.2 Coverage Details

| Module | Test Count | Coverage Content |
|--------|-----------|-----------------|
| `test_config.py` | 34 | Config loading / deep-merge / validation |
| `test_utils.py` | 34 | extract_json / mask_if_looks_like_key / sanitize_name / find_videos |
| `test_utils_expanded.py` | 20 | run_subprocess / discover_ffmpeg / atomic_io / run_ffmpeg |
| `test_cut.py` | 25 | Time parsing / filename generation |
| `test_log.py` | 13 | TeeWriter / format_size / format_duration |
| `test_progress.py` | 14 | ProgressTracker read/write/ETA/atomic write |
| `test_ai.py` | 11 | factory dispatch / provider instantiation / TaskName |
| `test_ai_gemini.py` | 25 | Gemini client / retry / upload / wait |
| `test_ai_openai_compat.py` | 17 | OpenAI compat / retry / close |
| `test_analyze.py` | 10 | `_resolve_original` file matching |
| `test_analyze_funcs.py` | 9 | `_wrap_with_context` / plan filtering |
| `test_split.py` | 7 | split_video segment calculation |
| `test_compress.py` | 7 | compress_video bitrate / params / cancel |
| `test_file_service.py` | 60 | Safe basename / atomic save / segment matching / config type conversion |
| `test_helpers.py` | 20 | `_next_index` / `_write_csv` / `_rewrite_text_file` |
| `test_project_service.py` | 22 | output dir / registry / step detection |
| `test_routes_*.py` | 48 | Video / plan / config / run / project / transcript route handlers |
| `test_tasks_*.py` | 12 | run_compress_all / run_analyze_all / run_transcribe_all orchestration |
| `test_transcribe.py` | 19 | Transcribe toggle / device / model / CUDA fallback |
| `test_routes_transcripts.py` | 18 | Transcript / whisper API routes |
| Others | 148 | pipeline / plan / processing_state / main / ratelimit / tasks_analyze/compress/cut/label/refine/scripts/transcribe / whisper_cli |

### 8.3 Code Formatting

Uses `ruff` for lint and formatting. The project includes a pre-commit hook that auto-formats before commit (see [§9.11](#911-pre-commit-hook)).

```bash
ruff format .
ruff check .
```

### 8.4 Dependency Version Locking

`requirements-locked.txt` records exact version numbers, used for CI and reproducible builds.
Daily development uses the looser `requirements.txt`.

---

## 9. Gotchas (Pitfalls Encountered)

### 9.1 Commas in ffmpeg Filter Expressions

In `scale=min(640,iw):-2`, the `,` is parsed by ffmpeg as a filter chain separator.
**Must** be written as `scale=min(640\,iw):-2` (in Python source: `\\,`).
See `vlog_tool/compress.py:24`.

### 9.2 Windows + `git filter-branch --msg-filter`

- When calling git via `cmd /c`, backslashes in paths are eaten by the shell as escape characters → always use forward slashes
- Chinese Windows' `sys.stdin.encoding` defaults to **GBK**, UTF-8 input gets decoded to `?` → Python filter scripts **must** use `sys.stdin.buffer.read()` for byte-level matching, **do not** use `sys.stdin.read()` text mode
- When PowerShell calls a bat file, paths containing spaces in parameters like `%1` get split → use `%~nx1` in the bat file to extract just the filename for comparison

### 9.3 Gemini File API

- After upload, file status is `PROCESSING`; must poll until `ACTIVE` before calling generate_content
- Poll interval is in `ai.providers.gemini.poll_interval_sec` (default 5 seconds)
- Access from mainland China requires a SOCKS5 proxy; use google-genai's `HttpOptions(transport=httpx.HTTPTransport(proxy=...))`

### 9.4 DeepSeek Model Names

- Standard models: `deepseek-chat` (V3), `deepseek-reasoner` (R1)
- Third-party API gateways may support custom names like `deepseek-v4-flash`; just fill in the actual available name
- If you encounter `404` or `model not found`, first fall back to the official standard model name for verification

### 9.5 `api_key_env` Field

- This is the **environment variable name** (e.g. `DEEPSEEK_API_KEY`), not the key itself
- Old code incorrectly filled the actual key into the `api_key_env` field, causing error messages to leak the key
- Fix: `vlog_tool/utils.py:mask_if_looks_like_key()` detects `sk-` / `AIza` prefixes and masks them

### 9.6 Misleading Name `analyze.skip_existing`

- Although the field is named `skip_existing`, it is actually a **skip toggle shared by all steps**
- Do not create a new `scripts.skip_existing` — reuse this one

### 9.7 Gemini Files API Upload Not Cleaned Up

- In `gemini.py`, `ensure_file_active` uploads video to File API, but **does not** request file deletion after the call completes
- Multiple analyze runs accumulate many files, eventually exhausting quotas (per-minute/daily upload limits)
- Fix: call `client.files.delete(name=file.name)` in a `finally` block to ensure cleanup
- Note: `with_retry` should not wrap the upload operation (otherwise retries re-upload), only wrap `wait` and `generate_content` after successful upload

### 9.8 Temporary File Residue

- Multiple places in the project use `NamedTemporaryFile(delete=False)` and forget to call `os.unlink`
- `.tmp` files are not automatically cleaned up on `interrupt` / `KeyboardInterrupt`
- Investigation: check temporary file usage in `server.py` / `utils.py`, prefer `delete=True` or `try/finally`

### 9.9 Function Side Effects

- Functions like `analyze_video` / `generate_voiceover` modify fields of the input dict (e.g. adding `_file_path` markers)
- If the caller reuses the same dict, unexpected side effects occur
- Fix: apply `copy.deepcopy()` to input parameters before modification

### 9.10 Cross-Platform File Ordering Inconsistency

- `Path.iterdir()` on Windows follows filesystem order (approximate creation time), on Linux the order is not guaranteed
- This causes `index` assignment to differ across systems
- Fix: always use `sorted(Path.iterdir())` to ensure consistent ordering

### 9.11 Pre-commit Hook

- The project provides a Python script at `.githooks/pre-commit` that auto-runs `ruff format` on staged `.py` files and re-stages them
- `setup.ps1` auto-sets `git config core.hooksPath .githooks`
- Manual config: `git config core.hooksPath .githooks`
- The hook depends on `ruff` in `.venv`; if not found, it silently skips (does not block the commit)

### 9.12 `_filter_dc()` and Dataclass Construction

- Misspelled field names in YAML (e.g. `whisper.modle_size`) cause `TypeError: unexpected keyword argument`
- Fix: call `_filter_dc(raw, DataclassType)` to filter unknown keys before all `**raw` unpacking
- Note: `ScriptConfig` uses explicit kwargs construction, no filtering needed; `_parse_providers`/`_parse_tasks` use `.get()` for safe reading

### 9.13 Provider Cache and Test Isolation

- `_provider_cache` in `ai/factory.py` is a module-level global variable, persisting across tests
- If test A caches a provider, test B's `monkeypatch` config changes may still get the old provider
- Fix: `_clear_provider_cache()` + `conftest.py`'s `autouse` fixture auto-clears before each test

### 9.14 `retry_attempts` Semantics

- `ProviderConfig.retry_attempts` means **extra retry attempts** (excluding the first), default `2`
- `with_retry(attempts=N)`'s `attempts` means **total call count** (including the first)
- Conversion formula: `with_retry(attempts=cfg.retry_attempts + 1)`
- Both providers (gemini + openai_compat) use the same formula to keep semantics consistent

### 9.15 `cancel_event` Propagation in Pipeline

- `pipeline.py:108` only passes `cancel_event` to `compress`, `transcribe`, `cut`
- `run_analyze_all` / `run_generate_scripts` / `run_plan_vlog` / `run_label_videos` have **no** `cancel_event` parameter
- When adding cancel support to a new step, follow the pattern in `cut.py`: accept `cancel_event: threading.Event | None` in function signature, check `if cancel_event and cancel_event.is_set(): break` inside the main loop
- All steps should propagate `cancel_event`; if a new step is added, add it to the propagation list in `pipeline.py`

### 9.16 `RateLimiter` Lock Reentrancy

- `RateLimiter.__enter__` holds `self._lock` during `time.sleep(wait)` — this blocks all threads even if their rate limit windows haven't expired
- This is safe for single-threaded use but defeats parallelism when `ThreadPoolExecutor` is used for concurrent AI calls
- Fix pattern: split into `acquire()` (locked, returns wait time) and let the caller sleep + make the API call outside the lock
- Any parallelization effort (P-001/Perf-1) must refactor this first

### 9.17 Whisper Download Thread Cancellation

- `whisper_routes.py` uses `ctypes.pythonapi.PyThreadState_SetAsyncExc` to kill the download thread
- This is unsafe: if the thread is blocked in a C extension (e.g., socket read), the exception injection is silently deferred
- `SystemExit` may skip `finally` blocks, leaving file locks / `.lock` files in inconsistent state
- Preferred approach: chunked `requests.get(stream=True)` with per-chunk cancel check, no `ctypes` needed
- Mark `B-092` / `U-007` for the fix

### 9.18 `/api/fs/dirs` Security

- `fs.py` has no path restriction — full filesystem is browseable
- When combined with `--host 0.0.0.0`, any device on LAN can read directory structure, video files, and write config
- Fix: restrict to user home directory by default, add `UI_TOKEN` env var for LAN mode
- The file has only 12% test coverage — a security-sensitive untested surface

### 9.19 beforeStop Hook (`shutdown.py`)

- `install_hooks()` registers `atexit` + `signal(SIGTERM)` (Unix) to call `before_stop()` on shutdown
- `before_stop()` (idempotent): kills registered ffmpeg subprocesses → closes provider HTTP connections → flushes IO
- `register_process(proc)` / `unregister_process(proc)`: every ffmpeg subprocess creation must wrap with these to avoid orphaned processes on SIGTERM
- Currently integrated in: `run_ffmpeg()` (utils.py) and `_extract_audio()` (tasks/transcribe.py)
- Both `main.py` and `server.py` call `install_hooks()` at startup and `before_stop()` in their `finally` blocks
- Any new ffmpeg subprocess creation must follow the same register/unregister pattern

### 9.20 Split Segment Sidecar Mapping (`videos.py:101`)

- `videos.py:101` `(text_sidecars.get(idx) or [None])[0]` always maps **all** split segments of the same video to the **first** text/script sidecar file
- Example: `001_GL010683_seg01.mp4`, `_seg02.mp4`, `_seg03.mp4` all get `text_json` pointing to `001_巴黎铁塔_part1.json`
- Affected features: texts tab display, voiceover tab display, save, refine — all read from `v.text_json` / `v.script_json`
- Root cause: sidecars are keyed by index prefix (e.g. `001`), but segments are not differentiated by their `_segNN` suffix
- Filenames like `001_巴黎铁塔_part1.json` itself has no `_segNN` marker, making it impossible to distinguish which segment it belongs to from the filename alone
- Fix requires either: (a) embedding `_segNN` into sidecar filenames, or (b) matching by compressed file stem rather than index prefix
- Tracked as B-097

### 9.21 Config Auto-Upgrade: Dataclass Defaults Injection

- `_upgrade_config_file()` in `loader.py` runs at the start of every `load_config()` call
- For each YAML section (`paths`, `proxy`, `ai`, `compress`, `analyze`, `naming`, `script`, `plan`, `whisper`), it checks the corresponding dataclass for fields not present in the YAML and injects their Python `field(default=...)` values
- Also covers `ai.providers.*` (per `ProviderConfig`) and `ai.tasks.*` (per `TaskConfig`)
- Handles both `config.yaml` and `project.yaml` independently
- `Path`-typed defaults are converted to strings via `str()` before YAML serialization to avoid unsafe `!!python/object` tags
- Writes back via `yaml.dump()` only when something changed; prints a summary to stdout
- **Trade-off**: PyYAML does not preserve comments — a one-time loss when new fields are injected
- Uses atomic write (tmp + `os.replace`) to prevent partial writes on crash
- Only the user's local config files are touched; `config.example.yaml` is never modified

## 10. Verification Flow

Minimal verification:
```bash
.\.venv\Scripts\python.exe main.py check    # Environment check
```

Run through a media directory:
```bash
.\.venv\Scripts\python.exe main.py analyze --force    # Run everything once
.\.venv\Scripts\python.exe main.py analyze             # Verify skip works (should all be skipped)
.\.venv\Scripts\python.exe main.py refine              # Verify trip context injection
.\.venv\Scripts\python.exe main.py serve --no-browser  # Verify UI starts (then Ctrl+C to exit)
```

## 11. Optimization Plan (2026-06-20 Code Review)

Based on external code review (`docs/analysis/2026-06-20-REVIEW-part1.md`), cross-referenced against actual project state.

### What both reviews got right (still actionable / already addressed)

| Finding | Action | Phase | Status |
|---------|--------|-------|--------|
| `make_handler` closure too large (432 lines) | Extract business logic to services | **U-001** | ✅ mostly done (routes/ + services/) |
| config.py 406 lines, 14 dataclasses | Split into `config/` package | **U-003** | ✅ done |
| File system as database | Repository layer (long-term) | Phase 3 | — |
| Config cache not true LRU | Fix in U-001a | **U-001** | ✅ done (`config_cache.py`) |
| No domain models | `@dataclass VideoAnalysis/Segment/VoiceoverScript` | Phase 3 | — |
| No token cost tracking | `ai/cost_tracker.py` | Phase 3 | — |
| Pipeline cancel not covering analyze/scripts/plan/label | Add cancel_event to all loop steps | **U-005** |
| `RateLimiter` lock blocks parallel AI calls | Split acquire from sleep | **U-006** |
| Whisper download ctypes thread kill unsafe | Replace with chunked download | **U-007** |
| `/api/fs/dirs` no auth/restriction for LAN mode | Add root restriction + token | **U-008** |
| Whisper low-confidence segments silently dropped | Mark `low_confidence` flag | **U-009** |

### What reviews got wrong (already fixed)

| Claim | Actual fix | Commit |
|-------|-----------|--------|
| server.py 547-line God Object | Split into 13 routes + 2 services (A-001 ✅) | `0918da0` |
| Provider cache no lifecycle | Composite key + lock + `_clear_provider_cache` (C2/C4 ✅) | `71659aa` + `ef68308` |
| UI contains business logic | `project_service.py` + `file_service.py` exist | `0918da0` |
| VIDEO_EXTS duplicate (B-019) | Centralized in `_constants.py` | ✅ |
| `format_index` hardcoded `3` (B-020) | All calls use `config.naming.index_width` | ✅ |

### What reviews missed (real issues found during cross-check)

| Issue | Detail | Fix |
|-------|--------|-----|
| `server.py:524` hardcodes `config_path.parent / "projects.json"` instead of `_registry_path()` | Fragile duplicate path logic | **U-004** |
| `serve.ps1`/`serve.sh` has hardcoded project paths | Not distributable | Needs de-localization |
| ROADMAP.md 656 lines — completed features not archived | Maintenance burden | Periodic cleanup |
| AGENTS.md §7 commit history overly long (100+ entries) | Should trim to ~30 | Periodic cleanup |
| `transcribe.py` low-confidence segs silently dropped | Information loss for downstream | **U-009** |
| `server.py` 6% coverage + `fs.py` 12% coverage | Security-sensitive untested surface | **U-010** |
| `videos.py:101` `(text_sidecars.get(idx) or [None])[0]` maps all split segments to first sidecar | All split segments share same text/script in UI | **B-097** |

### Tracking

See `ROADMAP.md` section "In Progress" — entries **U-002**, **U-007**, **U-008**, **U-010**.

---

## 12. Communication Template

If an AI assistant takes over, upon seeing `AGENTS.md` it should:

1. `git log --oneline -10` to understand recent changes
2. `git status` to check for uncommitted changes
3. Read `config.example.yaml` to understand config structure
4. Read `templates/trip_context.md` to understand the current trip background
5. Ask the user what they specifically want to do, don't assume

For new features: **discuss plan first → user confirms → implement → one commit → confirm with user before push**.
**Push only after user explicitly approves.**
