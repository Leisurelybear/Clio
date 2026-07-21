# Agents Docs Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Slim AGENTS.md from 49KB to ~12KB by extracting changelog, gotchas, and optimization plan into separate on-demand files, and extract how-to guides as opencode skills.

**Architecture:** Content is moved (not rewritten) — existing text is copied verbatim from old AGENTS.md sections into new files. AGENTS.md is then trimmed to its essential core, with cross-references to the new files. Skills are created from procedural sections with minimal adaptation.

**Tech Stack:** Markdown files only. Skills follow agentskills.io specification (YAML frontmatter + markdown body).

---

## File Structure

| File | Action | Source |
|------|--------|--------|
| `CHANGELOG.md` | Create | Old AGENTS.md §7 (lines 229-415) |
| `docs/superpowers/agents/gotchas.md` | Create | Old AGENTS.md §9 (lines 473-619) |
| `docs/superpowers/agents/optimization-plan.md` | Create | Old AGENTS.md §11 (lines 636-680) |
| `docs/superpowers/agents/directory-tree.md` | Create | Old AGENTS.md §3 (lines 23-116) |
| `AGENTS.md` | Modify | Rewrite from old AGENTS.md, keep only core sections |
| `.opencode/skills/adding-ai-provider/SKILL.md` | Create | Old AGENTS.md §5.1 |
| `.opencode/skills/adding-new-task/SKILL.md` | Create | Old AGENTS.md §5.2 |
| `.opencode/skills/adding-cli-subcommand/SKILL.md` | Create | Old AGENTS.md §5.5 |

---

### Task 1: Create CHANGELOG.md

**Files:**
- Create: `CHANGELOG.md`

- [ ] **Step 1: Write CHANGELOG.md**

Content extracted from old AGENTS.md §7 (lines 229-415). Follows Keep a Changelog format with sections ordered newest-first.

```markdown
# Changelog

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
```

- [ ] **Step 2: Verify file exists and has expected sections**

Run: `Select-String -Pattern "^## 2026" CHANGELOG.md | Measure-Line | Select-Object -ExpandProperty Lines`

Expected: At least 6 dated sections (2026-06-24, 2026-06-22, 2026-06-20, 2026-06-19, 2026-06-18, 2026-06-17)

- [ ] **Step 3: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: extract changelog from AGENTS.md to CHANGELOG.md"
```

---

### Task 2: Create docs/superpowers/agents/gotchas.md

**Files:**
- Create: `docs/superpowers/agents/gotchas.md`
- Create parent dir if needed

- [ ] **Step 1: Write gotchas.md**

Copy verbatim from old AGENTS.md §9 (lines 473–619), preserving all 21 gotcha entries. Add a header referencing the original source.

```markdown
# Gotchas — Known Pitfalls & Lessons Learned

> Extracted from AGENTS.md §9. Reference document — load on demand when debugging or modifying affected modules.

## 9.1 Commas in ffmpeg Filter Expressions

In `scale=min(640,iw):-2`, the `,` is parsed by ffmpeg as a filter chain separator.
**Must** be written as `scale=min(640\,iw):-2` (in Python source: `\\,`).
See `vlog_tool/compress.py:24`.

## 9.2 Windows + `git filter-branch --msg-filter`

- When calling git via `cmd /c`, backslashes in paths are eaten by the shell as escape characters → always use forward slashes
- Chinese Windows' `sys.stdin.encoding` defaults to **GBK**, UTF-8 input gets decoded to `?` → Python filter scripts **must** use `sys.stdin.buffer.read()` for byte-level matching, **do not** use `sys.stdin.read()` text mode
- When PowerShell calls a bat file, paths containing spaces in parameters like `%1` get split → use `%~nx1` in the bat file to extract just the filename for comparison

## 9.3 Gemini File API

- After upload, file status is `PROCESSING`; must poll until `ACTIVE` before calling generate_content
- Poll interval is in `ai.providers.gemini.poll_interval_sec` (default 5 seconds)
- Access from mainland China requires a SOCKS5 proxy; use google-genai's `HttpOptions(transport=httpx.HTTPTransport(proxy=...))`

## 9.4 DeepSeek Model Names

- Standard models: `deepseek-chat` (V3), `deepseek-reasoner` (R1)
- Third-party API gateways may support custom names like `deepseek-v4-flash`; just fill in the actual available name
- If you encounter `404` or `model not found`, first fall back to the official standard model name for verification

## 9.5 `api_key_env` Field

- This is the **environment variable name** (e.g. `DEEPSEEK_API_KEY`), not the key itself
- Old code incorrectly filled the actual key into the `api_key_env` field, causing error messages to leak the key
- Fix: `vlog_tool/utils.py:mask_if_looks_like_key()` detects `sk-` / `AIza` prefixes and masks them

## 9.6 Misleading Name `analyze.skip_existing`

- Although the field is named `skip_existing`, it is actually a **skip toggle shared by all steps**
- Do not create a new `scripts.skip_existing` — reuse this one

## 9.7 Gemini Files API Upload Not Cleaned Up

- In `gemini.py`, `ensure_file_active` uploads video to File API, but **does not** request file deletion after the call completes
- Multiple analyze runs accumulate many files, eventually exhausting quotas (per-minute/daily upload limits)
- Fix: call `client.files.delete(name=file.name)` in a `finally` block to ensure cleanup
- Note: `with_retry` should not wrap the upload operation (otherwise retries re-upload), only wrap `wait` and `generate_content` after successful upload

## 9.8 Temporary File Residue

- Multiple places in the project use `NamedTemporaryFile(delete=False)` and forget to call `os.unlink`
- `.tmp` files are not automatically cleaned up on `interrupt` / `KeyboardInterrupt`
- Investigation: check temporary file usage in `server.py` / `utils.py`, prefer `delete=True` or `try/finally`

## 9.9 Function Side Effects

- Functions like `analyze_video` / `generate_voiceover` modify fields of the input dict (e.g. adding `_file_path` markers)
- If the caller reuses the same dict, unexpected side effects occur
- Fix: apply `copy.deepcopy()` to input parameters before modification

## 9.10 Cross-Platform File Ordering Inconsistency

- `Path.iterdir()` on Windows follows filesystem order (approximate creation time), on Linux the order is not guaranteed
- This causes `index` assignment to differ across systems
- Fix: always use `sorted(Path.iterdir())` to ensure consistent ordering

## 9.11 Pre-commit Hook

- The project provides a Python script at `.githooks/pre-commit` that auto-runs `ruff format` on staged `.py` files and re-stages them
- `setup.ps1` auto-sets `git config core.hooksPath .githooks`
- Manual config: `git config core.hooksPath .githooks`
- The hook depends on `ruff` in `.venv`; if not found, it silently skips (does not block the commit)

## 9.12 `_filter_dc()` and Dataclass Construction

- Misspelled field names in YAML (e.g. `whisper.modle_size`) cause `TypeError: unexpected keyword argument`
- Fix: call `_filter_dc(raw, DataclassType)` to filter unknown keys before all `**raw` unpacking
- Note: `ScriptConfig` uses explicit kwargs construction, no filtering needed; `_parse_providers`/`_parse_tasks` use `.get()` for safe reading

## 9.13 Provider Cache and Test Isolation

- `_provider_cache` in `ai/factory.py` is a module-level global variable, persisting across tests
- If test A caches a provider, test B's `monkeypatch` config changes may still get the old provider
- Fix: `_clear_provider_cache()` + `conftest.py`'s `autouse` fixture auto-clears before each test

## 9.14 `retry_attempts` Semantics

- `ProviderConfig.retry_attempts` means **extra retry attempts** (excluding the first), default `2`
- `with_retry(attempts=N)`'s `attempts` means **total call count** (including the first)
- Conversion formula: `with_retry(attempts=cfg.retry_attempts + 1)`
- Both providers (gemini + openai_compat) use the same formula to keep semantics consistent

## 9.15 `cancel_event` Propagation in Pipeline

- `pipeline.py:108` only passes `cancel_event` to `compress`, `transcribe`, `cut`
- `run_analyze_all` / `run_generate_scripts` / `run_plan_vlog` / `run_label_videos` have **no** `cancel_event` parameter
- When adding cancel support to a new step, follow the pattern in `cut.py`: accept `cancel_event: threading.Event | None` in function signature, check `if cancel_event and cancel_event.is_set(): break` inside the main loop
- All steps should propagate `cancel_event`; if a new step is added, add it to the propagation list in `pipeline.py`

## 9.16 `RateLimiter` Lock Reentrancy

- `RateLimiter.__enter__` holds `self._lock` during `time.sleep(wait)` — this blocks all threads even if their rate limit windows haven't expired
- This is safe for single-threaded use but defeats parallelism when `ThreadPoolExecutor` is used for concurrent AI calls
- Fix pattern: split into `acquire()` (locked, returns wait time) and let the caller sleep + make the API call outside the lock
- Any parallelization effort (P-001/Perf-1) must refactor this first

## 9.17 Whisper Download Thread Cancellation

- `whisper_routes.py` uses `ctypes.pythonapi.PyThreadState_SetAsyncExc` to kill the download thread
- This is unsafe: if the thread is blocked in a C extension (e.g., socket read), the exception injection is silently deferred
- `SystemExit` may skip `finally` blocks, leaving file locks / `.lock` files in inconsistent state
- Preferred approach: chunked `requests.get(stream=True)` with per-chunk cancel check, no `ctypes` needed
- Mark `B-092` / `U-007` for the fix

## 9.18 `/api/fs/dirs` Security

- `fs.py` has no path restriction — full filesystem is browseable
- When combined with `--host 0.0.0.0`, any device on LAN can read directory structure, video files, and write config
- Fix: restrict to user home directory by default, add `UI_TOKEN` env var for LAN mode
- The file has only 12% test coverage — a security-sensitive untested surface

## 9.19 beforeStop Hook (`shutdown.py`)

- `install_hooks()` registers `atexit` + `signal(SIGTERM)` (Unix) to call `before_stop()` on shutdown
- `before_stop()` (idempotent): kills registered ffmpeg subprocesses → closes provider HTTP connections → flushes IO
- `register_process(proc)` / `unregister_process(proc)`: every ffmpeg subprocess creation must wrap with these to avoid orphaned processes on SIGTERM
- Currently integrated in: `run_ffmpeg()` (utils.py) and `_extract_audio()` (tasks/transcribe.py)
- Both `main.py` and `server.py` call `install_hooks()` at startup and `before_stop()` in their `finally` blocks
- Any new ffmpeg subprocess creation must follow the same register/unregister pattern

## 9.20 Split Segment Sidecar Mapping (`videos.py:101`)

- `videos.py:101` `(text_sidecars.get(idx) or [None])[0]` always maps **all** split segments of the same video to the **first** text/script sidecar file
- Example: `001_GL010683_seg01.mp4`, `_seg02.mp4`, `_seg03.mp4` all get `text_json` pointing to `001_巴黎铁塔_part1.json`
- Affected features: texts tab display, voiceover tab display, save, refine — all read from `v.text_json` / `v.script_json`
- Root cause: sidecars are keyed by index prefix (e.g. `001`), but segments are not differentiated by their `_segNN` suffix
- Filenames like `001_巴黎铁塔_part1.json` itself has no `_segNN` marker, making it impossible to distinguish which segment it belongs to from the filename alone
- Fix requires either: (a) embedding `_segNN` into sidecar filenames, or (b) matching by compressed file stem rather than index prefix
- Tracked as B-097

## 9.21 Config Auto-Upgrade: Dataclass Defaults Injection

- `_upgrade_config_file()` in `loader.py` runs at the start of every `load_config()` call
- For each YAML section (`paths`, `proxy`, `ai`, `compress`, `analyze`, `naming`, `script`, `plan`, `whisper`), it checks the corresponding dataclass for fields not present in the YAML and injects their Python `field(default=...)` values
- Also covers `ai.providers.*` (per `ProviderConfig`) and `ai.tasks.*` (per `TaskConfig`)
- Handles both `config.yaml` and `project.yaml` independently
- `Path`-typed defaults are converted to strings via `str()` before YAML serialization to avoid unsafe `!!python/object` tags
- Writes back via `yaml.dump()` only when something changed; prints a summary to stdout
- **Trade-off**: PyYAML does not preserve comments — a one-time loss when new fields are injected
- Uses atomic write (tmp + `os.replace`) to prevent partial writes on crash
- Only the user's local config files are touched; `config.example.yaml` is never modified
```

- [ ] **Step 2: Create directory and write file**

```bash
New-Item -ItemType Directory -Path "docs/superpowers/agents" -Force
```

- [ ] **Step 3: Verify line count matches original (≈147 lines from §9)**

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/agents/gotchas.md
git commit -m "docs: extract gotchas from AGENTS.md to on-demand reference"
```

---

### Task 3: Create docs/superpowers/agents/optimization-plan.md

**Files:**
- Create: `docs/superpowers/agents/optimization-plan.md`

- [ ] **Step 1: Write optimization-plan.md**

Copy from old AGENTS.md §11 (lines 636–680). Add context header.

```markdown
# Optimization Plan — Active Refactoring Items

> Extracted from AGENTS.md §11. Reference document — load on demand when planning refactoring work.

Based on external code review (`docs/analysis/2026-06-20-review-part1.md`), cross-referenced against actual project state.

## What Both Reviews Got Right (Still Actionable)

| Finding | Action | Phase | Status |
|---------|--------|-------|--------|
| `make_handler` closure too large (432 lines) | Extract business logic to services | **U-001** | ✅ mostly done (routes/ + services/) |
| config.py 406 lines, 14 dataclasses | Split into `config/` package | **U-003** | ✅ done |
| File system as database | Repository layer (long-term) | Phase 3 | — |
| Config cache not true LRU | Fix in U-001a | **U-001** | ✅ done (`config_cache.py`) |
| No domain models | `@dataclass VideoAnalysis/Segment/VoiceoverScript` | Phase 3 | — |
| No token cost tracking | `ai/cost_tracker.py` | Phase 3 | — |
| Pipeline cancel not covering analyze/scripts/plan/label | Add cancel_event to all loop steps | **U-005** | ❌ |
| `RateLimiter` lock blocks parallel AI calls | Split acquire from sleep | **U-006** | ❌ |
| Whisper download ctypes thread kill unsafe | Replace with chunked download | **U-007** | ❌ |
| `/api/fs/dirs` no auth/restriction for LAN mode | Add root restriction + token | **U-008** | ❌ |
| Whisper low-confidence segments silently dropped | Mark `low_confidence` flag | **U-009** | ❌ |

## What Reviews Got Wrong (Already Fixed)

| Claim | Actual fix | Commit |
|-------|-----------|--------|
| server.py 547-line God Object | Split into 13 routes + 2 services (A-001 ✅) | `0918da0` |
| Provider cache no lifecycle | Composite key + lock + `_clear_provider_cache` (C2/C4 ✅) | `71659aa` + `ef68308` |
| UI contains business logic | `project_service.py` + `file_service.py` exist | `0918da0` |
| VIDEO_EXTS duplicate (B-019) | Centralized in `_constants.py` | ✅ |
| `format_index` hardcoded `3` (B-020) | All calls use `config.naming.index_width` | ✅ |

## What Reviews Missed (Real Issues Found During Cross-Check)

| Issue | Detail | Fix |
|-------|--------|-----|
| `server.py:524` hardcodes `config_path.parent / "projects.json"` instead of `_registry_path()` | Fragile duplicate path logic | **U-004** |
| `serve.ps1`/`serve.sh` has hardcoded project paths | Not distributable | Needs de-localization |
| ROADMAP.md 656 lines — completed features not archived | Maintenance burden | Periodic cleanup |
| AGENTS.md §7 commit history overly long (100+ entries) | Should trim to ~30 | Periodic cleanup |
| `transcribe.py` low-confidence segs silently dropped | Information loss for downstream | **U-009** |
| `server.py` 6% coverage + `fs.py` 12% coverage | Security-sensitive untested surface | **U-010** |
| `videos.py:101` `(text_sidecars.get(idx) or [None])[0]` maps all split segments to first sidecar | All split segments share same text/script in UI | **B-097** |

## Tracking

See `ROADMAP.md` section "In Progress" — entries **U-002**, **U-007**, **U-008**, **U-010**.
```

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/agents/optimization-plan.md
git commit -m "docs: extract optimization plan from AGENTS.md to on-demand reference"
```

---

### Task 4: Create docs/superpowers/agents/directory-tree.md

**Files:**
- Create: `docs/superpowers/agents/directory-tree.md`

- [ ] **Step 1: Write directory-tree.md**

Copy the full directory tree from old AGENTS.md §3 (lines 23–116) with file-level annotations.

```markdown
# Full Directory Tree

> Extracted from AGENTS.md §3. Reference document — load on demand when exploring codebase structure.

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
│   │   └── ...                  # Other task modules (compress, analyze, cut, scripts, refine, label, transcribe)
│   ├── ui/                    # Local Web UI (visual editing of AI output; stdlib http.server, zero new deps)
│   │   ├── server.py            # UIHandler (BaseHTTPRequestHandler) + make_handler + run
│   │   ├── README.md            # UI usage documentation
│   │   ├── routes/              # Route handlers
│   │   │   ├── refine.py           # POST /api/refine (AI refine trigger)
│   │   │   ├── transcripts.py      # Transcript GET/PUT API
│   │   │   └── whisper_routes.py   # Whisper check API
│   │   └── static/              # Frontend, no build step, ES modules
│   │       ├── index.html
│   │       ├── style.css
│   │       └── src/
│   │           ├── main.js
│   │           ├── layout.js        # Draggable panels, collapse, persistence
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
│       └── openai_compat.py   # OpenAI compatible: DeepSeek / OpenAI / Tongyi Qianwen / Moonshot (Kimi) (wrapped with_retry)
├── templates/
│   ├── vlog_template.md       # Voice-over style template (user-customizable)
│   └── trip_context.md        # Trip background & AI rules (auto-injected into all prompts)
├── config.example.yaml        # Config template committed to git
├── .env.example               # Env variable template committed to git
├── config.yaml / .env         # User's local real config, gitignored
├── requirements.txt           # Loose dev dependencies
├── requirements-locked.txt    # Reproducible build with pinned versions
├── .github/workflows/test.yml # GitHub Actions CI (pushes + PRs)
├── vlog_tool/tests/           # Unit tests (pytest, 624 cases)
│   ├── conftest.py            # Shared fixtures
│   ├── test_ai.py             # 11 tests - factory dispatch / TaskName / provider instantiation
│   ├── test_ai_gemini.py      # 25 tests - Gemini client / retry / upload / wait
│   ├── test_ai_openai_compat.py# 17 tests - OpenAI compat / retry / close
│   ├── test_analyze.py        # 10 tests - _resolve_original file matching
│   ├── test_analyze_funcs.py  # 9 tests - _wrap_with_context / plan filtering
│   ├── test_compress.py       # 7 tests - compress_video bitrate / params / cancel
│   ├── test_config.py         # 34 tests - config loading/merging/validation
│   ├── test_cut.py            # 25 tests - time parsing / filename generation / cutting
│   ├── test_file_service.py   # 60 tests - safe basename / atomic save / segment matching
│   ├── test_helpers.py        # 20 tests - _next_index / _write_csv / _rewrite_text_file
│   ├── test_log.py            # 13 tests - TeeWriter / format_size / format_duration
│   ├── test_main.py           # 7 tests - CLI subcommand dispatch
│   ├── test_pipeline.py       # 6 tests - cancel_event + files/overwrite propagation
│   ├── test_plan.py           # 2 tests - plan prompt transcript injection
│   ├── test_processing_state.py# 8 tests - mark / reset / persistence / corruption recovery
│   ├── test_progress.py       # 14 tests - ProgressTracker read/write/ETA/atomic write
│   ├── test_project_service.py# 22 tests - output dir / registry / step detection
│   ├── test_ratelimit.py      # 12 tests - RateLimiter interval/logging
│   ├── test_routes_config.py  # 5 tests - config GET/PUT/INIT routes
│   ├── test_routes_plan.py    # 6 tests - plan GET/PUT/cut routes
│   ├── test_routes_projects.py# 9 tests - project CRUD routes
│   ├── test_routes_run.py     # 8 tests - run start/status/rerun/cancel routes
│   ├── test_routes_texts.py   # 8 tests - texts/voiceover GET/PUT routes
│   ├── test_routes_transcripts.py# 18 tests - transcript/whisper API routes
│   ├── test_routes_videos.py  # 8 tests - videos GET routes
│   ├── test_split.py          # 7 tests - split_video segment calculation
│   ├── test_tasks_analyze.py  # 8 tests - run_analyze_all + files/overwrite
│   ├── test_tasks_compress.py # 5 tests - run_compress_all + files_filter
│   ├── test_tasks_cut.py      # 11 tests - run_cut_all / offset / cancel
│   ├── test_tasks_label.py    # 8 tests - run_label_videos + files/overwrite
│   ├── test_tasks_refine.py   # 21 tests - run_refine_texts/scripts/fix_mode + files_filter
│   ├── test_tasks_scripts.py  # 10 tests - run_generate_scripts + files/overwrite
│   ├── test_tasks_transcribe.py# 12 tests - run_transcribe_all + files_filter
│   ├── test_transcribe.py     # 19 tests - transcribe toggle / device / model / CUDA fallback
│   ├── test_utils.py          # 34 tests - extract_json / mask_key / sanitize / find_videos / with_retry
│   ├── test_utils_expanded.py # 20 tests - run_subprocess / discover_ffmpeg / atomic_io / run_ffmpeg
│   └── test_whisper_cli.py    # 6 tests - whisper check/install status
```
```

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/agents/directory-tree.md
git commit -m "docs: extract directory tree from AGENTS.md to on-demand reference"
```

---

### Task 5: Rewrite AGENTS.md (the bootloader)

**Files:**
- Modify: `AGENTS.md`

- [ ] **Step 1: Write the new AGENTS.md**

New target: ~150 lines / <12KB. Contains only:
- §1 Project identity
- §2 Tech stack
- §3 Directory structure (simplified tree, no file comments — reference directory-tree.md)
- §4 Key conventions (commit, workflow, code style, config, prompts, refine special modes)
- §5 User preferences
- §6 AI transfer protocol
- §7 Quick reference (test commands, verify flow, code formatting)
- §8 On-demand loading index

```markdown
# AGENTS.md — AI Maintenance Manual & Project Memory

> Quick reference for **AI assistants taking over maintenance**.
> User preference: Chinese for conversation, **English** for commit messages and this document.

## 1. Project in One Sentence

An **AI preprocessing pipeline**: raw travel vlog footage → ffmpeg compression → Gemini reviews video + DeepSeek writes script → JianYing (CapCut) manual editing.

## 2. Tech Stack

- **Python 3.11+** (PEP 604 `X | None`, dataclass)
- **ffmpeg / ffprobe** (video processing; GoPro 4K → 640p 5MB compressed)
- **google-genai** (Gemini 2.5 Flash video File API)
- **httpx** (DeepSeek / OpenAI compatible calls)
- **PyYAML** (config parsing)
- **pytest** (unit tests, auto-run in CI; **624 test cases**)

Dependencies in `requirements.txt`; `setup.ps1`/`setup.sh` creates venv + installs ffmpeg + copies `.env` in one click.

## 3. Directory Structure (Simplified)

```
vlog-video-analysis/
├── main.py                    CLI entry
├── vlog_tool/
│   ├── config.py              AppConfig + load_config
│   ├── shutdown.py            beforeStop hook
│   ├── pipeline.py            High-level pipeline orchestration
│   ├── analyze.py             AI interaction functions
│   ├── compress.py            ffmpeg wrapper
│   ├── prompts.py             All prompt templates
│   ├── transcribe.py          Whisper ASR core
│   ├── whisper_cli.py         Whisper CLI
│   ├── utils.py               ffmpeg discovery, file IO, extract_json
│   ├── log.py                 Logging (hourly rotating, TeeWriter)
│   ├── tasks/                 Pipeline steps (per-step modules)
│   ├── ui/                    Web UI (stdlib http.server)
│   │   ├── server.py          HTTP server
│   │   ├── routes/            Route handlers (refine, transcripts, whisper)
│   │   └── static/            Frontend (no build step, ES modules)
│   └── ai/                    AI providers
│       ├── base.py            TaskName enum, Provider Protocol
│       ├── factory.py         Provider lookup by name
│       ├── gemini.py          Gemini multimodal
│       └── openai_compat.py   DeepSeek / OpenAI / Tongyi / Moonshot
├── templates/                  vlog_template.md, trip_context.md
├── config.example.yaml / .env.example
├── requirements.txt / requirements-locked.txt
├── .github/workflows/test.yml
└── vlog_tool/tests/            pytest unit tests (624 cases)
```

> See `docs/superpowers/agents/directory-tree.md` for full tree with file-level annotations and test coverage details.

## 4. Key Conventions

### 4.1 Commit

- **English** message, **Conventional Commits**: `type(scope): subject`
- **Each commit as small as possible** — one independent feature/fix per commit
- Types: `feat` / `fix` / `refactor` / `docs` / `chore`
- History rewriting: use `git rebase -i --root`; on Windows use byte-level Python filter (see gotchas.md §9.2)

### 4.2 Workflow

- **Plan first, then implement**: record in ROADMAP.md, confirm approach, then code
- **Document new modules**: README.md for users, AGENTS.md for AI (purpose, entry, conventions)

### 4.3 Code Style

- No comments unless explaining **why** (WHAT is self-evident)
- Chinese for user-facing copy (CLI prompts, error messages)
- Default `skip_existing=True` shared by all steps (controlled by `analyze` toggle)
- AI-returned JSON uses `extract_json()`: first `json.loads`, then regex `{}`

### 4.4 Configuration

- Repo commits `config.example.yaml` / `.env.example`; real files gitignored
- No local paths, proxy IPs, API keys in examples (use placeholders)
- After config changes, update both example and READMEs

### 4.5 Prompts

- All in `vlog_tool/prompts.py` as constants
- Trip context injected via `_wrap_with_context()` before all prompts
- Output format: JSON (for `extract_json()` parsing)

### 4.6 Refine Special Modes

**Changing AI for refine stage:** `refine_text` falls back to `video_analyze` by default. To use a cheaper pure-text model:

```yaml
ai:
  tasks:
    refine_text:
      provider: deepseek
      model: deepseek-chat
```

**Targeted fix mode (`--fix`):** For known errors (place names, numbering), more reliable than free review:
- Use with `-i` specifying a **single** json file
- Switches to "Targeted fix based on user feedback" prompt
- `_changelog` first entry always "Modified XXX per user feedback"
- Implemented in `prompts.py`: `REFINE_TEXT_FIX_PROMPT` / `REFINE_SCRIPT_FIX_PROMPT`

## 5. User Preferences

- Language: Chinese for conversation, **English** for commits/docs/AGENTS.md
- Commit granularity: one feature per commit, **do not batch**
- History rewriting: force-push accepted
- **No** API keys / local paths in config files
- **No** test code (unless explicitly requested)
- **Push must be explicitly confirmed**. Local commits fine, `git push` requires user approval.

## 6. AI Transfer Protocol

Upon taking over, the AI should:

1. `git log --oneline -10` — recent changes
2. `git status` — uncommitted changes
3. Read `config.example.yaml` — config structure
4. Read `templates/trip_context.md` — current trip background
5. Read `docs/superpowers/agents/gotchas.md` — known pitfalls (only if modifying affected modules)
6. Read `CHANGELOG.md` — project history (only if needed)
7. Ask the user what they want to do

For new features: **discuss plan first → user confirms → implement → one commit → confirm before push**.

## 7. Quick Reference

### Running Tests

```bash
# Full run
python -m pytest vlog_tool/tests/ -v
# Single module
python -m pytest vlog_tool/tests/test_utils.py -v
```

GitHub Actions runs tests on Python 3.11/3.12 (Ubuntu + Windows).

### Code Formatting

```bash
ruff format .
ruff check .
```

Pre-commit hook auto-runs ruff on staged `.py` files (`.githooks/pre-commit`).

### Verification Flow

```bash
python main.py check                           # Environment check
python main.py analyze --force                 # Run everything once
python main.py analyze                         # Verify skip works
python main.py refine                          # Verify trip context injection
python main.py serve --no-browser              # Verify UI starts
```

### Dependency Locking

`requirements.txt` (loose) for daily dev; `requirements-locked.txt` (pinned) for CI.

## 8. On-Demand Loading Index

| If you need to... | Load this |
|---|---|
| Understand the project quickly | AGENTS.md (already loaded) |
| See project history and recent changes | `CHANGELOG.md` |
| Know known pitfalls and traps | `docs/superpowers/agents/gotchas.md` |
| Check active refactoring items | `docs/superpowers/agents/optimization-plan.md` |
| See full directory tree with annotations | `docs/superpowers/agents/directory-tree.md` |
| Add a new AI provider | Skill: `adding-ai-provider` |
| Add a new AI task | Skill: `adding-new-task` |
| Add a new CLI subcommand | Skill: `adding-cli-subcommand` |
```

- [ ] **Step 2: Verify new AGENTS.md size**

Run: `(Get-Item "AGENTS.md").Length / 1KB`

Expected: ~10-12KB (down from 49KB)

- [ ] **Step 3: Verify all content from old AGENTS.md is preserved somewhere**

Checklist:
- §1 → still in AGENTS.md §1 ✅
- §2 → still in AGENTS.md §2 ✅
- §3 full tree → moved to directory-tree.md ✅
- §4 → still in AGENTS.md §4 (trimmed) ✅
- §5.1 → moved to skill adding-ai-provider ✅
- §5.2 → moved to skill adding-new-task ✅
- §5.3 + §5.4 → still in AGENTS.md §4.6 ✅
- §5.5 → moved to skill adding-cli-subcommand ✅
- §6 → still in AGENTS.md §5 ✅
- §7 changelog → moved to CHANGELOG.md ✅
- §8 → still in AGENTS.md §7 ✅
- §9 gotchas → moved to gotchas.md ✅
- §10 verification → still in AGENTS.md §7 ✅
- §11 optimization plan → moved to optimization-plan.md ✅
- §12 transfer protocol → still in AGENTS.md §6 ✅

- [ ] **Step 4: Commit**

```bash
git add AGENTS.md
git commit -m "docs: slim AGENTS.md to essential bootloader, move detailed refs to on-demand files"
```

---

### Task 6: Create skill — adding-ai-provider

**Files:**
- Create: `.opencode/skills/adding-ai-provider/SKILL.md`

- [ ] **Step 1: Create directory and write skill file**

Content from old AGENTS.md §5.1 adapted to skill format.

```markdown
---
name: adding-ai-provider
description: Use when adding a new AI provider, registering a model, configuring API access for a new LLM/video service
---

# Adding a New AI Provider

## Overview

A new AI provider needs an implementation file, registration in the provider factory, config example, and documentation.

## Implementation

1. Create `vlog_tool/ai/<name>.py` implementing `TextAIProvider` and/or `VideoAIProvider` from `base.py`
2. Register in `vlog_tool/ai/factory.py:_PROVIDER_TYPES`
3. Add example config in `config.example.yaml`
4. Verify with `python main.py check` (auto-lists all registered providers)
5. Update README (CN/EN) with usage instructions

## Common Mistakes

- Forgetting to add the provider to `_PROVIDER_TYPES` — `main.py check` will not list it
- API key in `api_key_env` field instead of env var name — use `mask_if_looks_like_key()` guard
- Missing retry wrapping — both Gemini and OpenAI-compat use `with_retry()`
```

- [ ] **Step 2: Commit**

```bash
git add .opencode/skills/adding-ai-provider/SKILL.md
git commit -m "docs: extract adding-ai-provider skill from AGENTS.md"
```

---

### Task 7: Create skill — adding-new-task

**Files:**
- Create: `.opencode/skills/adding-new-task/SKILL.md`

- [ ] **Step 1: Create directory and write skill file**

Content from old AGENTS.md §5.2 adapted to skill format.

```markdown
---
name: adding-new-task
description: Use when adding a new AI task (e.g. subtitle translation), creating a pipeline step, defining a new prompt for the AI analysis pipeline
---

# Adding a New AI Task

## Overview

A new AI task touches the prompt constants, analysis function, pipeline orchestration, and CLI registration.

## Implementation

1. `vlog_tool/ai/base.py` — add enum value to `TaskName`
2. `vlog_tool/prompts.py` — add prompt constant
3. `vlog_tool/analyze.py` — add `task_xxx()` function, reuse `_wrap_with_context()`
4. `vlog_tool/pipeline.py` — add `run_xxx_all()` with `cancel_event` propagation
5. `main.py` — register subcommand, reuse `_add_io_args()`
6. Update READMEs

## Common Mistakes

- Writing trip context manually instead of using `_wrap_with_context()`
- Output not in JSON format — breaks `extract_json()` parsing
- Forgetting `cancel_event` propagation — add to pipeline.py's event list
- Skipping `skip_existing` integration — consistent with other steps
```

- [ ] **Step 2: Commit**

```bash
git add .opencode/skills/adding-new-task/SKILL.md
git commit -m "docs: extract adding-new-task skill from AGENTS.md"
```

---

### Task 8: Create skill — adding-cli-subcommand

**Files:**
- Create: `.opencode/skills/adding-cli-subcommand/SKILL.md`

- [ ] **Step 1: Create directory and write skill file**

Content from old AGENTS.md §5.5 adapted to skill format.

```markdown
---
name: adding-cli-subcommand
description: Use when adding a new CLI command, registering a subcommand parser under main.py
---

# Adding a New CLI Subcommand

## Overview

CLI subcommands are registered in `main.py` using `argparse`. Each follows a consistent pattern.

## Implementation

1. In `main.py`, create parser: `p_X = sub.add_parser(...)` with appropriate arguments
2. Add dispatch branch matching the subcommand name
3. Reuse `_add_io_args()` for `-i`/`-o` arguments
4. Use `config.analyze.skip_existing` for skip behavior (consistent with other steps)
5. Update READMEs

## Common Mistakes

- Not reusing `_add_io_args()` — leads to inconsistent CLI interface
- Creating new `skip_existing` config fields — reuse `analyze.skip_existing`
- Forgetting README update — users discover features through CLI docs
```

- [ ] **Step 2: Commit**

```bash
git add .opencode/skills/adding-cli-subcommand/SKILL.md
git commit -m "docs: extract adding-cli-subcommand skill from AGENTS.md"
```

---

## Spec Coverage Verification

| Spec Requirement | Task |
|-----------------|------|
| AGENTS.md slimmed to ~12KB | Task 5 |
| CHANGELOG.md extracted | Task 1 |
| Gotchas extracted | Task 2 |
| Optimization plan extracted | Task 3 |
| Directory tree extracted | Task 4 |
| Skill: adding-ai-provider | Task 6 |
| Skill: adding-new-task | Task 7 |
| Skill: adding-cli-subcommand | Task 8 |
| All existing info preserved | Verified in Task 5 Step 3 |
