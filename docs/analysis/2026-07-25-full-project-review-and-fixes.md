# Clio Full Project Logic Review and Fixes

**Date:** 2026-07-25  
**HEAD at review start:** `19a348f` (`fix(label): unlink partial labeled mp4 on cancel`)  
**Scope:** 98 production Python files, 35 frontend JavaScript modules, configuration/persistence boundaries, AI providers, media pipeline, plan/cut/export, Web UI routes/services/state, and automated tests.  
**Result:** No new Critical/P0 defect found. Seven verified defects were fixed with regression coverage.

## 1. Executive Summary

The project is in good condition for its intended local, single-user workflow. The current test suite already covers most core contracts, and the July 20/23 hardening work closed the previous high-risk path/auth/cancellation findings.

This review found the remaining actionable defects concentrated in four areas:

1. Configuration accepted values that inevitably fail later in ffmpeg, Whisper, export, or provider polling.
2. Gemini provider configuration exposed `timeout_sec` and `max_tokens` but did not apply them.
3. Cut/JianYing index matching was inconsistent with configurable `naming.index_width` and readiness normalization.
4. Frontend asynchronous state could be overwritten by an older video request, and two timeline/run-state edge cases used the wrong state.

All seven verified findings below are fixed in the working tree. No schema or API endpoint was added.

## 2. Verification Snapshot

| Check | Result | Notes |
| --- | ---: | --- |
| `ruff check clio main.py` | PASS | No lint errors |
| `python -m pytest clio/tests/ -q` | PASS | 1327 collected; 1326 passed, 1 skipped |
| `npm test -- --run` | PASS | 310 tests across 29 files |
| `mypy clio --exclude clio/tests` | Known debt | 36 errors in 13 files, down from 37 in 14 files at review start |
| `git diff --check` | PASS | No whitespace errors |

Environment: Python 3.11.9, Node 24.18.0.

## 3. Fixed Findings

### R034-01 — Invalid configuration reached runtime failures

**Severity:** Medium  
**Affected:** `clio/config/validators.py`

The merged/global validators allowed several invalid values:

- `compress.fps <= 0`
- `compress.crf < 0` or `> 51`
- Gemini `timeout_sec <= 0`
- Gemini `poll_interval_sec <= 0`, which can create a busy polling loop
- unsupported `export.canvas_ratio`
- invalid project Whisper enum values because `ProjectWhisperConfig.sanitize()` was never called by the V2 load path
- non-positive script/plan sizing values

**Fix:** Added bounded/positive validation and project Whisper sanitization to the shared merged validation path. Manual YAML edits and Web UI saves now fail early with a specific configuration error instead of failing inside ffmpeg, Gemini, Whisper, or export.

**Tests:** `clio/tests/test_config.py`

### R034-02 — Gemini ignored provider timeout and output-token settings

**Severity:** Medium  
**Affected:** `clio/ai/gemini.py`

`ProviderConfig.timeout_sec` and `max_tokens` were applied by the OpenAI-compatible provider but ignored by Gemini. Users could configure those fields without any behavioral effect.

**Fix:** Build `types.HttpOptions(timeout=...)` using the SDK's millisecond contract, preserve proxy transports, and pass `GenerateContentConfig(max_output_tokens=...)` to both text and video generation when the configured value is positive.

**Tests:** `clio/tests/test_ai_gemini.py`

### R034-03 — AI video protocol omitted cancellation

**Severity:** Low  
**Affected:** `clio/ai/base.py`, `clio/analyze.py`

Production calls passed `cancel_event` to `VideoAIProvider.analyze_video`, and Gemini implemented it, but the protocol did not declare it. This produced a mypy error and made alternate provider implementations easy to get wrong.

**Fix:** Added `cancel_event: threading.Event | None` to the protocol. This removed one production mypy error and aligned the provider contract with runtime behavior.

### R034-04 — Cut and JianYing did not consistently honor index width

**Severity:** Medium  
**Affected:** `clio/tasks/cut.py`, `clio/export/jianying.py`, `clio/main.py`, `clio/ui/routes/export.py`

Readiness checks normalized indexes such as `1`, `001`, and custom-width forms, but cut/export still relied on literal filename prefixes or hard-coded `zfill(3)`. A valid plan could pass readiness and then skip media when `naming.index_width` was not three or when AI/user-edited plan indexes were unpadded.

**Fix:** Reused `expand_index_keys()` for exact index-token matching, removed glob interpolation from cut lookup, propagated `config.naming.index_width` through CLI and Web export, and applied the same normalization to JianYing source mapping/fallback lookup.

**Tests:** `clio/tests/test_tasks_cut.py`, `clio/tests/test_export.py`

### R034-05 — Rapid video switching allowed stale data overwrite

**Severity:** Medium  
**Affected:** `clio/ui/static/src/sidebar.js`

`selectVideo()` awaited texts, voiceover, transcript, and plan requests sequentially. If the user selected video B before video A finished loading, A's slower response could overwrite B's editor state and trigger a render/save for the wrong video.

**Fix:** Load optional artifacts concurrently, assign results only when the request generation and selected filename are still current, and suppress stale-request error status updates.

**Tests:** `clio/ui/static/src/__tests__/sidebar-select-video.test.js`

### R034-06 — Re-rendering the Run tab could disable completion navigation

**Severity:** Low  
**Affected:** `clio/ui/static/src/runner.js`

`renderRun()` always cleared `_expectDoneNavigation` and `_seenNonTerminal`. Returning to the Run tab while a pipeline was active could therefore lose the flag that opens the relevant result after completion.

**Fix:** Preserve navigation state while `_runActive` is true and reset only when idle.

**Tests:** `clio/ui/static/src/__tests__/runner.test.js`

### R034-07 — “Current time” used original source time instead of transcript time

**Severity:** Low  
**Affected:** `clio/ui/static/src/editor-texts.js`

For legacy segmented media shown on the original video, transcript timestamps are segment-local while the player is positioned at `offset_sec + local_time`. The manual transcript form copied raw `player.currentTime`, creating timestamps shifted by the segment offset.

**Fix:** Convert player time back to transcript-local time by subtracting the current original video's offset and clamping at zero.

**Tests:** `clio/ui/static/src/__tests__/transcript-time.test.js`

## 4. Reviewed but Not Changed

### Existing mypy debt

The remaining 36 errors are pre-existing and cluster in:

- `clio/ui/routes/videos.py`: `ArtifactIndex.lookup()` overload/union narrowing
- `clio/tasks/scripts.py`: branch-local counter type reuse
- `clio/ui/services/run_preview.py`: legacy `AppConfig.input` typing and truthy integer generators
- `clio/transcribe.py`: temporary mutation through the read-only combined Whisper view
- smaller annotation/name-reuse issues in `gpmf.py`, `processing_state.py`, `doctor.py`, `transcripts.py`, `compare_models.py`, `config_routes.py`, and `server.py`

These are worth a dedicated typing cleanup, but most are not demonstrated runtime defects. This review intentionally avoided mixing a broad annotation refactor into behavior fixes.

### Config auto-upgrade writes during load

`_upgrade_config_file()` mutates YAML files while reading them. This is surprising for a generic loader, but it is an explicit project contract documented in the maintenance instructions. No change was made.

### Query token in media/EventSource URLs

The browser app places the API token in video/EventSource query parameters because those browser primitives cannot use the shared `fetch()` bearer-header path. This can expose the token through URL-oriented diagnostics or intermediaries when serving beyond localhost. The current server requires authentication for sensitive routes and auto-generates a token for non-local bind, but a cookie/session design would be stronger for LAN use.

### Arbitrary project/output directory selection

Project creation accepts user-selected project and output directories. Restricting output under the project root would improve a strict remote threat model but would also remove the supported external-drive workflow. This remains a product/security design decision rather than a safe maintenance-only change.

### Token usage history growth

`.token_usage.json` retains an unbounded call history while also maintaining aggregates. It is low risk for normal personal use, but a future retention limit or rotation policy would prevent long-running projects from growing indefinitely.

## 5. Regression Coverage Added

- Invalid ffmpeg/provider/export/Whisper config boundaries
- Gemini HTTP timeout and positive `max_tokens`
- Unpadded plan index matched to four-digit media filenames
- JianYing custom-width source mapping and prefix fallback
- Stale video selection response suppression
- Active-run completion-navigation preservation
- Legacy transcript timestamp offset conversion

## 6. Final Assessment

The codebase remains safe to continue developing on `main` for the documented local workflow. The highest-value next maintenance item is a dedicated mypy/typing pass around `ArtifactIndex.lookup()` and combined config views; the highest-value security design item is replacing query-string API tokens before treating non-localhost serving as a stronger multi-user boundary.
