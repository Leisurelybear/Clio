# Full Code Audit — `feat/whisper-transcription`

**Branch:** `feat/whisper-transcription` (base `fbde7de` → HEAD `1b53499`)
**Date:** 2026-06-16
**Scope:** All modules (core, AI, pipeline, tasks, UI backend, UI frontend, tests)
**Method:** Parallel subagent review (5 agents), cross-referenced

---

## Severity Key

| Level | Meaning | Action |
|-------|---------|--------|
| 🔴 **Critical** | Data loss, security hole, crash loop | Fix before merge |
| 🟠 **Important** | Functional bug, perf regression, bad UX | Fix before merge |
| 🟡 **Minor** | Code smell, fragile pattern, cosmetic | Fix or doc |

---

## 🔴 Critical (6)

### C1. Path traversal in POST /api/rerun
**File:** `vlog_tool/ui/routes/run.py:70`
**Fix:** Add `if not _is_safe_basename(video_basename): return 403`
**Detail:** `video_basename` from JSON body is not sanitized. `proj_input / "../../etc/passwd"` allows arbitrary file access via `run_compress_all`/`run_analyze_all`.

### C2. Empty-state button doesn't load videos
**File:** `vlog_tool/ui/static/src/sidebar.js:430`
**Fix:** Call `setSource('original')` instead of manually mutating state; or add `await loadVideos()` at end.
**Detail:** `switchToOriginalThenCompress()` changes `state.source` and renders buttons but never calls `loadVideos()`. User sees stale "暂无压缩视频" after clicking "切换到原视频".

### C3. Video segment listener leak
**File:** `vlog_tool/ui/static/src/viewer.js:11`
**Fix:** Replace `addEventListener` with single `player.onloadedmetadata = ...` assignment.
**Detail:** `playVideoSegment()` attaches a new `loadedmetadata` listener on every call without removing the previous one. Rapid clicks accumulate listeners, all firing sequentially on load.

### C4. OpenAI non-retryable 4xx errors silently retried
**File:** `vlog_tool/ai/openai_compat.py:54`
**Fix:** Wrap 401/403/404 before they reach `with_retry`; fail fast.
**Detail:** Invalid API keys or unknown models cause 3 total attempts with ~3s delay. `raise_for_status()` raises `httpx.HTTPStatusError` for all 4xx codes, and `retry_on=(httpx.HTTPError,)` catches it.

### C5. YAML unknown field → TypeError crash
**File:** `vlog_tool/config.py:281` (also lines 365-379 for all other config dataclasses)
**Fix:** Filter input dict: `{k: v for k, v in raw.items() if k in WhisperConfig.__dataclass_fields__}`
**Detail:** `WhisperConfig(**raw)` raises `TypeError` on typos like `whisper.modle_size`. Same issue for `ProxyConfig`, `CompressConfig`, `AnalyzeConfig`, `NamingConfig`, `PlanConfig`.

### C6. Provider/resource leak (HTTP connections never closed)
**File:** `vlog_tool/ai/factory.py:22` + `vlog_tool/analyze.py:96`
**Fix:** Cache providers by `(provider_name, model)` in factory; or ensure callers always call `provider.close()`.
**Detail:** Every `analyze_video`/`generate_voiceover`/etc call creates a new provider (and new `httpx.Client`). Providers are never closed — HTTP connections leak across a batch of many files.

---

## 🟠 Important (12)

### I1. Race condition in transcript edit onblur
**File:** `vlog_tool/ui/static/src/editor.js:168`
**Fix:** Capture `state.currentVideo` inside `ondblclick` before creating textarea; reference captured value in `onblur` instead of reading from state.

### I2. Race condition in save() reads stale state
**File:** `vlog_tool/ui/static/src/editor.js:374`
**Fix:** Capture `tab`, `entity`, `video` at function entry; use captured values throughout.

### I3. Double-click starts two pipelines
**File:** `vlog_tool/ui/static/src/runner.js:56`
**Fix:** `btn.disabled = true` immediately at function entry, before any async operation.

### I4. Portal event listener memory leak
**File:** `vlog_tool/ui/static/src/sidebar.js:179`
**Fix:** After `clone.remove()`, also `document.removeEventListener('click', _portalCloseHandler)` and set `_portalCloseHandler = null`.

### I5. Range request: suffix range (`bytes=-500`) unsupported
**File:** `vlog_tool/ui/server.py:252`
**Fix:** Detect empty start + non-empty end → treat as suffix range: `start = size - end; end = size - 1`.

### I6. POST /api/cut day_label path traversal
**File:** `vlog_tool/ui/routes/plan.py:55`
**Fix:** `if not _is_safe_basename(day_label): return 403`

### I7. Hardcoded `G:/ffmpeg` in `discover_ffmpeg_bin`
**File:** `vlog_tool/utils.py:96`
**Fix:** Remove `G:/ffmpeg`, use `os.environ.get('FFMPEG_HOME')` or standard install paths.

### I8. `_resolve_original` ValueError crash on malformed stem
**File:** `vlog_tool/tasks/analyze.py:34` + `vlog_tool/tasks/transcribe.py:75`
**Fix:** Wrap `split("_", 1)` in try/except ValueError; add `if "_" not in compressed_stem: return None` guard.

### I9. `run_ffmpeg` stdout pipe deadlock potential
**File:** `vlog_tool/utils.py:174`
**Fix:** Add `stdout=subprocess.DEVNULL` (unless streaming output is intended).

### I10. CLI ignores project.yaml overrides
**File:** `main.py:34`
**Fix:** Resolve `project_dir` from `-i` arg or working directory; pass to `load_config()`.

### I11. `_TeeWriter.__getattr__` exposes raw stdout/stderr
**File:** `vlog_tool/log.py:98`
**Fix:** Intercept destructive calls (`close`, `writelines`, `truncate`) and raise `AttributeError` or no-op.

### I12. Hardcoded retry attempts in OpenAI compat
**File:** `vlog_tool/ai/openai_compat.py:62`
**Fix:** Use `self._retry = cfg.retry_attempts` stored in `__init__`.

---

## 🟡 Minor (25+)

### M1. `_parse_whisper` / `_parse_proxy` etc: TypeError on unknown fields (C5 companion)
- **File:** `config.py:281,365-379`
- **Fix:** Filter dataclass fields before `**raw` unpacking

### M2. `deep_merge` shares nested dict references
- **File:** `config.py:304`
- **Fix:** `result[key] = deep_merge(deepcopy(base[key]), deepcopy(override[key]))`

### M3. `yaml.safe_load` unhandled YAMLError
- **File:** `config.py:339`
- **Fix:** try/except with source path in error message

### M4. `_path()` doesn't expand `~`
- **File:** `config.py:170`
- **Fix:** `value = os.path.expanduser(value)`

### M5. `mask_if_looks_like_key` prefix list incomplete
- **File:** `utils.py:84`
- **Fix:** Add `gsk_`, `nvapi-`, `pplx-`, `fsk_`, `deepseek` prefixes

### M6. `with_retry` uses `except BaseException`
- **File:** `utils.py:42`
- **Fix:** Use `except Exception` (KeyboardInterrupt/SystemExit should not be caught)

### M7. `get_duration_sec` / `probe_video_info` no error handling
- **File:** `utils.py:134`
- **Fix:** try/except with default return or ValueError with path context

### M8. `run_ffmpeg` stderr_lines memory unbounded
- **File:** `utils.py:162`
- **Fix:** Keep only last 200 lines: `stderr_lines[-200:]`

### M9. `progress.py`: ETA negative when current > total
- **File:** `progress.py:72`
- **Fix:** `remaining = max(0, total - current)`

### M10. `progress.py`: tmp.replace fails on Windows file lock
- **File:** `progress.py:46` (also `processing_state.py:38`)
- **Fix:** wrap in try/except, fall back to direct write

### M11. `processing_state.py`: `_STEPS` is mutable list
- **File:** `processing_state.py:8`
- **Fix:** Change to tuple

### M12. `sys.excepthook` infinite recursion risk
- **File:** `log.py:77`
- **Fix:** threading flag to prevent reentrant hook

### M13. `_HourlyFileHandler._rotate` no explicit flush
- **File:** `log.py:39`
- **Fix:** Acceptable (every line is flushed); can add atexit handler

### M14. `excepthook` uses `logger.error(tb_text)` which may re-enter hook
- **File:** `log.py:111`
- **Fix:** Guard with reentrancy flag; fallback to `sys.__stderr__.write` if reentered

### M15. Gemini `_wait_for_file` duplicates progress output
- **File:** `gemini.py:97`
- **Fix:** `if not on_progress: print(...)` to avoid double-printing when callback is provided

### M16. Gemini `_call_with_retry` has unused `model` parameter
- **File:** `gemini.py:93`
- **Fix:** Remove the parameter or use it

### M17. `GeminiProvider.close()` is no-op
- **File:** `gemini.py:107`
- **Fix:** Check if `genai` library exposes `client.close()`; document if not

### M18. Transcript prompt language inconsistency
- **File:** `prompts.py:131`
- **Fix:** Translate `TRANSCRIPT_CONTEXT` to Chinese or document bilingual design

### M19. `transcribe.py` module-level `import faster_whisper` adds 200ms+ to import chain
- **File:** `transcribe.py:20-22`
- **Fix:** Move import into `_get_model()`; use `check_whisper()` as sole forward guard

### M20. CUDA fallback also catches network errors on model download
- **File:** `transcribe.py:71`
- **Fix:** Separate download errors from CUDA init errors; or also catch `ConnectionError`

### M21. `whisper_cli.py` typo "和以预下载" should be "正在预下载"
- **File:** `whisper_cli.py:46`
- **Fix:** Fix the Chinese string

### M22. `whisper_cli.py` ctranslate2 import may fail
- **File:** `whisper_cli.py:37,63`
- **Fix:** wrap in try/except ImportError

### M23. `existing_map` only matches by stem (not subdirectory)
- **File:** `tasks/compress.py:47-56`
- **Fix:** Use `(stem, parent_stem)` compound key if files in different subdirs share stems

### M24. `_parse_timestamp_sec` silently returns 0.0 on parse failure
- **File:** `analyze.py:85`
- **Fix:** try/except with logging.warning

### M25. `_call_ai` missing type annotation for `fn` parameter
- **File:** `analyze.py:75`
- **Fix:** `fn: Callable[[], str]`

### M26. `run_full_pipeline` hardcodes `day_label="day1"`
- **File:** `pipeline.py:32`
- **Fix:** Accept `day_label` as parameter and pass through from CLI

### M27. `tasks/analyze.py:68` unguarded `_list_compressed` FileNotFoundError
- **File:** `tasks/analyze.py:68`
- **Fix:** Check `config.compressed_dir.is_dir()` before calling

### M28. Config form binds both onchange AND oninput
- **File:** `editor.js:540`
- **Fix:** Remove redundant onchange for text inputs that already have oninput

### M29. `seg.index || '?'` treats index 0 as falsy
- **File:** `editor.js:288` and `sidebar.js:131`
- **Fix:** Use `seg.index ?? '?'` and `v.index != null ? ...`

### M30. PollRunStatus continues polling after tab switch
- **File:** `runner.js:52`
- **Fix:** Call `_stopRunPoll()` in `selectVideo()`, `selectConfig()`, `selectPlan()`

### M31. Empty-state button click doesn't await async functions
- **File:** `main.js:102`
- **Fix:** Make onclick handler async and `await selectPlan()` etc.

### M32. `loadConfig()` no try/catch
- **File:** `sidebar.js:36`
- **Fix:** Wrap in try/catch, show specific error message

### M33. `playVideoSegment()` src matching is fragile substring check
- **File:** `viewer.js:8`
- **Fix:** Parse `file` query param via `URLSearchParams`

### M34. Portal close handler lifecycle fragile
- **File:** `sidebar.js:169`
- **Fix:** Always `removeEventListener` before re-attaching

### M35. Undefined CSS variable `--bg-primary`
- **File:** `style.css:628`
- **Fix:** Define `--bg-primary` in `:root` or replace with existing variable

### M36. Template literal shows `[undefined]` for missing seg.index
- **File:** `editor.js:296`
- **Fix:** Use `${seg.index ?? '?'}`

---

## ✅ Files with No Significant Issues

| File | Notes |
|------|-------|
| `vlog_tool/_constants.py` | Clean |
| `vlog_tool/split.py` | Clean |
| `vlog_tool/cut.py` | Clean |
| `vlog_tool/compress.py` | Clean |
| `vlog_tool/tasks/scripts.py` | Clean |
| `vlog_tool/tasks/plan.py` | Clean |
| `vlog_tool/ui/routes/transcripts.py` | Clean |
| `vlog_tool/ui/routes/projects.py` | Clean |
| `vlog_tool/ui/routes/config_routes.py` | Clean |
| `vlog_tool/ui/routes/processing_state_routes.py` | Clean |
| `vlog_tool/ui/routes/fs.py` | Clean |
| `vlog_tool/ui/routes/whisper_routes.py` | Clean |
| `vlog_tool/ui/services/project_service.py` | Clean |
| `vlog_tool/ui/static/src/state.js` | Clean |
| `vlog_tool/ui/static/src/api.js` | Clean |
| `vlog_tool/ui/static/src/utils.js` | Clean |
| `vlog_tool/ui/static/index.html` | Clean |
| `vlog_tool/ui/static/style.css` | 1 minor (M35) |
| `vlog_tool/prompts.py` | 1 minor (M18) |

---

## Summary

| Severity | Count |
|----------|-------|
| 🔴 Critical | 6 |
| 🟠 Important | 12 |
| 🟡 Minor | 36 |

**Top priorities for next sprint:**
1. **C1** + **C5** — Config type errors + rerun path traversal (security)
2. **C2** + **C3** — Frontend state corruption + listener leaks (UX stability)
3. **C4** + **C6** — API retry waste + connection leaks (resource efficiency)
4. **I1-I4** — Race conditions in save/edit/run (data integrity)
5. **I7** — Remove hardcoded `G:/ffmpeg` (portability)
