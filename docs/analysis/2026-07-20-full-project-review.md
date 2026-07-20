# Full Project Review — Clio (vlog-video-analysis)

**Date:** 2026-07-20  
**HEAD:** `aae85d7` (`fix(export): narrow MediaIdentity before reading index (mypy)`)  
**Scope:** Full static review of production code under `clio/` (pipeline, config/AI, UI server, frontend, tests/CI/hygiene). Read-only; no code was modified.

Five parallel domain reviews + independent verification of historical P0s and top findings. Findings below are **verified against current source** unless marked *plausible residual*.

---

## 1. Verification Snapshot

| Check | Result | Notes |
|---|---:|---|
| `python -m pytest clio/tests/ -q` | **PASS** | **1272 passed, 1 skipped** in ~35s (local Python 3.10.6; project targets 3.11+) |
| `ruff check clio main.py` | **PASS** | All checks passed |
| `mypy clio` (excl. tests) | **FAIL** | ~38 production errors (union-attr on `ArtifactIndex.lookup`, `AppConfig.input`, protocol drift, etc.) |
| `npm test -- --run` | **PASS** | **261 tests / 23 files** (Node v24.18.0) |
| Working tree | clean | No uncommitted review edits |

**Scale (approx.):** ~35k LOC Python + ~11k LOC frontend JS (excl. tests); 80+ pytest modules; R-031a/a2 just landed.

---

## 2. Executive Summary

The project is in **strong shape for a personal local AI preprocessing tool**. Compared with the 2026-07-04 review, several historical **P0s are fixed** (route auth default-on, selected-file artifact matching, physical split removed, cancel on analyze/label/ffmpeg core paths, `.env` atomic write, `debug_print_prompt` default false).

Remaining high-value work clusters in:

1. **Plan readiness index normalization** — `"1"` vs `"001"` can hard-block cut/export; offline collection is a no-op.  
2. **Config/AI hot-reload holes** — global PUT skips full validation; provider cache not cleared after env/config change; yaml `api_key` still writable.  
3. **LAN/token threat model residuals** — run/cut body paths accept arbitrary dirs; secrets returned in cleartext GETs; Windows FS browser is whole-disk.  
4. **Frontend run SSE lifecycle** — switching to Plan stops SSE so run completion can be missed.  
5. **Test realism** — selected-file helpers and auth route matrix still under-tested; `.coverage` is tracked in git.

**Verdict:** Safe to keep shipping on `main` for localhost personal use. Before treating `--host 0.0.0.0` as a real multi-user boundary, fix Critical items under §4.1–4.3. Before trusting plan cut/export readiness, fix §4.4–4.5.

---

## 3. Prior P0 Status (2026-07-04 → 2026-07-20)

| Historical P0 | Status | Evidence |
|---|---|---|
| Read APIs only partially protected (`_sensitive` allowlist) | **FIXED** | All routes default `auth_required=True` (`clio/ui/router.py:18,27`); GET checks `route.auth_required` (`server.py:301`); no `_sensitive` remains |
| Selected-video filter uses wrong stem (scripts/label/refine) | **FIXED** | `_matches_selected_artifact` reads `media_identity` / `source_file` / `compressed_file` / `index` (`tasks/_helpers.py:62–93`); used by scripts/refine/label |
| `cancel_event` not passed to `analyze_video` / label ffmpeg / split | **FIXED (core)** | `analyze.py:199–205` → `gemini.py:150–185`; `label.py:143`; `split.py` accepts cancel. Residual: Whisper / `generate_text` / mid-`generate_content` |
| `splits_subdir` ignored; split pollutes `compressed/` | **FIXED (by design)** | Physical split removed from compress (`tasks/compress.py`); logical windows only (`analyze_windows.py`). Config knobs deprecated no-ops |
| UI original recursive input | **FIXED** (earlier) | Per prior review status + current videos routes |
| Config numeric validation too thin | **Partial** | Core ranges validated; whisper sanitize not on V2 load; global PUT skips full validate |
| `.env` writes not atomic | **FIXED** | `env_routes.py` uses `write_text_atomic` |
| `debug_print_prompt` default True | **FIXED** | `GlobalAIConfig.debug_print_prompt: bool = False` (`models.py:111`) |
| `project_service` `input_dir` accepts any dir | **FIXED for qs; residual elsewhere** | `resolve_project_input` registry-scoped (`project_service.py:347–363`); still open via project create/add + run body override |

---

## 4. Confirmed Issues

Severity calibration:

- **Critical** — wrong results / data loss / security under realistic use  
- **Important** — real bugs or maintainability hazards that should land soon  
- **Minor** — polish, docs, low-probability edges  

### 4.1 Critical — Plan readiness index padding / offline dead code

**C1. `index_missing` false positives from `"1"` vs `"001"`**

- **Where:** `clio/plan_readiness.py:125–145`, `:59–72`; plan emits `format_index` → `"001"` (`tasks/plan.py:94`); texts often store `index` as int → `str` → `"1"`.  
- **What's wrong:** Exact string membership. If compressed files are offline and only texts exist, `known` may be `{"1"}` while plan has `"001"` → **hard error**, cut/export blocked.  
- **Fix:** Normalize with `format_index` / int equality; always insert both padded and raw forms into `known`.  
- **Tests:** Unit cases for int/str/padded mismatch with only texts present.

**C2. `collect_project_indices` offline path is a no-op**

- **Where:** `clio/plan_readiness.py:149–162`  
- **What's wrong:** Loop over `load_selected_videos` never appends to `offline`; `video_offline` warnings never fire.  
- **Fix:** Map path → plan index via `.vmeta` / `media_identity` / texts, then mark offline when `not p.is_file()`.

### 4.2 Critical — Config / AI layer

**C3. `load_global_config` never runs `_validate_config`**

- **Where:** `clio/config/loader.py:429–469`; UI global PUT / provider CRUD via `load_global_config`.  
- **Impact:** Invalid provider `type`, negative timeouts, etc. can be saved; later full load fails or runtime surprises.  
- **Fix:** Extract `validate_global_config` and call from every global write path.

**C4. Provider cache not invalidated on env/config hot-reload; cache key incomplete**

- **Where:** `clio/ai/factory.py:34–64`, `_clear_provider_cache` only used from tests/shutdown; **not** from `env_routes` / `config_routes` after write.  
- **Impact:** After rotating API key or proxy, live clients keep old key until TTL (default 60 min) or process exit.  
- **Fix:** Call `_clear_provider_cache()` on every config/env/provider write; include `timeout_sec` / `max_tokens` / `retry_attempts` / RPM in cache key (or generation counter).

**C5. YAML `api_key` still fully supported and re-serialized**

- **Where:** `parsers.py:_resolve_api_key`; provider normalize in config routes; missing-key error text still mentions yaml.  
- **Impact:** Keys can land in `config.yaml`, appear in GET `/api/config/raw` and `/api/providers`, backups, migrations — contradicts “keys only in `.env`”.  
- **Fix:** Reject/warn non-empty yaml `api_key` in validate; strip on write; error text → `.env` only; mask keys in GET.

### 4.3 Critical — UI security under LAN + token model

(Auth default-on is good; residual is **capability after token**.)

**C6. `POST /api/run/start` body `project_dir`/`input_dir` bypasses registry**

- **Where:** `run.py:_apply_run_project_dir_override` — only `is_dir()`.  
- **Impact:** Authenticated caller can run full pipeline against any directory.  
- **Fix:** Same allowlist as `resolve_project_input`.

**C7. `POST /api/cut` `output_dir` unsandboxed**

- **Where:** `plan.py:128–139`; `tasks/cut.py:resolve_cut_output_dir` resolves absolute with no root check.  
- **Impact:** Arbitrary write/overwrite of video files under OS user privileges.  
- **Fix:** Constrain under project `output_dir` (or explicit allowlist).

**C8. Project create/add enrolls any existing directory**

- **Where:** `routes/projects.py` create/add.  
- **Impact:** After enrollment, full project API surface applies (artifacts, video stream, etc.).  
- **Fix:** Restrict to home + configured media roots (or confirm dialog with explicit root allowlist).

**C9. Secrets over HTTP in token mode**

- **Where:** `GET /api/env` full plaintext; providers/config expose `api_key`; auth accepts `?token=` (logs + browser history).  
- **Fix:** Mask keys in GET; prefer Authorization header only for API (media may need short-lived ticket); do not log query token.

### 4.4 Critical — Frontend

**C10. `selectPlan` tears down run EventSource**

- **Where:** `sidebar.js:87–88` → `runner._stopRunPoll()`; status handler also `if (!prog) return` (`runner.js:381–383`).  
- **Impact:** Start run → switch to 编排 → job finishes → UI misses done handlers (no plan reload / video refresh).  
- **Fix:** App-level SSE independent of entity; or only stop after terminal status.

**C11. Player “same source” uses `src.includes(encodeURIComponent(file))`**

- **Where:** `viewer.js:106–109`.  
- **Impact:** Basename substring false-positive (`vid.mp4` ⊂ `other_vid.mp4`) → skip reload, seek wrong media.  
- **Fix:** Parse `URL` query `file=` exact match (+ source).

**C12. Plan day_label unescaped in `<option>`**

- **Where:** `editor-plan.js:335–336`.  
- **Impact:** Attribute break / XSS if day_label contains `"` / `<`.  
- **Fix:** `escapeHtml` or DOM `option` APIs.

---

## 5. Important Issues

### Pipeline / domain

| ID | Issue | Where | Fix sketch |
|---|---|---|---|
| I1 | Plan ignores `files=` selection (always all texts) | `tasks/plan.py:53–55` | Honor filter or refuse with explicit `global:true` |
| I2 | Whisper / text AI cancel only at boundaries | `transcribe.py`, `analyze.py` generate_text, `gemini` generate_content | Best-effort cancel between retries; document limits |
| I3 | Label `ProcessingState` keyed by AI title stem | `label.py:120` | Prefer `media_identity` / `source_file` like scripts |
| I4 | Serial voiceover: one failure aborts batch | `scripts.py` serial path | Try/except + mark error, continue |
| I5 | Jianying can write empty draft | `export/jianying.py` | Fail if sequence non-empty and zero materials |
| I6 | Compress cancel leaves partial outputs | `tasks/compress.py` | Unlink incomplete on cancel |
| I7 | Refine returns `len(target_files)` not successes | `tasks/refine.py` | `return completed` |
| I8 | Progress ETA not reset per phase | `progress.py` | Reset `_start` on phase change |
| I9 | `VideoAIProvider.analyze_video` protocol lacks `cancel_event` | `ai/base.py:46–48` | Align protocol; gate video on type/capabilities |
| I10 | Legacy `split.py` + config knobs still present | `split.py`, models | R-029d: delete or hard-deprecate |

### Config / AI

| ID | Issue | Fix sketch |
|---|---|---|
| I11 | Whisper `sanitize()` never on V2 load | Call after `load_project_config` |
| I12 | Token store unbounded + per-instance lock | Cap history; process-wide store by path |
| I13 | Auto-upgrade mutates yaml on read | Opt-in migrate / explicit command |
| I14 | Validation gaps (canvas_ratio, poll_interval 0, fps/crf) | Extend `_validate_config` |
| I15 | Gemini ignores `timeout_sec` / `max_tokens` | Wire into SDK config |

### UI server

| ID | Issue | Fix sketch |
|---|---|---|
| I16 | Windows FS browser = whole disk | Optional root allowlist for non-local hosts |
| I17 | Waveform abspath allowlist weaker than `/api/video` | Align with selected-set rules |
| I18 | No JSON body size / Content-Length validation | Cap e.g. 8–32 MiB; safe `int` |
| I19 | `hmac.compare_digest` for token | Constant-time compare |
| I20 | ArtifactIndex.lookup typing (union) → mypy noise + footguns | Narrow return type / overload |

### Frontend

| ID | Issue | Fix sketch |
|---|---|---|
| I21 | Strict `index ===` on plan header click | `String()` normalize like seek path |
| I22 | Native `<video controls>` still source timebase on Plan | Hide native scrub in plan mode or map to `seekToGlobal` |
| I23 | `renderRun` resets completion navigation flags | Preserve mid-run flags |
| I24 | Selection mode re-renders full list every checkbox | Patch DOM / virtualize |
| I25 | Transcript “当前时间” ignores `offset_sec` | Reuse jump-time helper |
| I26 | Token in media URL query | Media ticket or header-capable path |

### Tests / hygiene

| ID | Issue | Fix sketch |
|---|---|---|
| I27 | **No unit tests** for `_matches_selected_*` | Parametrize original vs compressed vs identity-only |
| I28 | files_filter tests use identical artificial stems | Realistic `002_GL010684` vs `002_街头风景.json` |
| I29 | Auth coverage sample-based, not route-complete | Parametrize sensitive GET/DELETE |
| I30 | **`.coverage` tracked in git** (~78KB stale DB) | Untrack + ignore `.coverage` / `htmlcov/` / `coverage.xml` |
| I31 | CI pins float for ruff/mypy/pytest | `requirements-dev.txt` lock |
| I32 | mypy CI only partial modules | Expand or document incomplete gate |

---

## 6. Minor Issues (selected)

- Duplicated `parseTimecode` (`utils.js` vs `plan-timeline.js`) — drift risk.  
- `editor-config.js` ~1648 lines god module.  
- `package.json` still named `vlog-editing-helper`.  
- AGENTS/README understate CI matrix (also macOS).  
- README badge `1200+` tests OK (1272 pytest + 261 vitest).  
- Local ignored junk: `projects.json.tmp.*`, `MagicMock/`, `opencode_session_import.json` (~16MB) — clean workspace periodically.  
- `serve.ps1` hardcodes 8800 vs `serve.sh` default asymmetry.  
- Progress/session log process-global under multi-project serve.

---

## 7. Strengths (keep doing this)

1. **MediaIdentity + ArtifactIndex + .vmeta/.vindex** — coherent v2 identity with v1 fallbacks; cut/export prefer identity.  
2. **Logical analyze windows** replacing physical split (R-029) — correct long-clip direction.  
3. **Atomic writes** widely used (`write_json_atomic`, config `_save_atomic`, cut backups).  
4. **Selected-file matching redesign** (`_matches_selected_artifact`) — historical P0 fixed properly.  
5. **Router auth default-on** + auto token on non-local bind — big security upgrade since July 4.  
6. **Plan pure helpers** (`plan-timeline.js`, `plan-waveform.js`, `plan-edit.js`) + Vitest coverage — R-031a/a2 good pattern.  
7. **Plan accordion / expand-defer** careful against mid-edit re-render wipe.  
8. **XSS discipline** — `escapeHtml` widely used on AI/plan fields (except C12 day_label).  
9. **Test volume** — 1272 pytest + 261 vitest; multi-OS CI (ubuntu/windows/macos × 3.11/3.12).  
10. **Docs discipline** — ROADMAP/CHANGELOG/AGENTS/design-plan pairs for non-trivial features.

---

## 8. Architecture / Maintainability Risks

### 8.1 Artifact identity still dual-track

MediaIdentity exists, but many paths still use `idx_*` globs and stem heuristics. Root of historical filter bugs and remaining label-state keying issues.

**Direction:** One “artifact index service” per project used by list/filter/rerun/label/cut/export/readiness.

### 8.2 Auth is route-default-good, capability-model incomplete

Token gates *who*, not *what*. After token, FS browser + project enroll + cut output_dir are full local-user powers — fine for localhost personal use; not fine as multi-user LAN service.

**Direction:** Document threat model explicitly; for LAN, sandbox write/run roots.

### 8.3 Provider lifecycle vs UI hot-reload

Config cache invalidates; AI provider cache does not. UX says “热加载” while in-flight and cached clients may be stale.

### 8.4 Frontend dual timebase (accepted residual)

R-031a composite clock coexists with native video controls source timebase. Documented residual; still top UX footgun on Plan.

### 8.5 Typechecking debt

~38 production mypy errors, CI only checks a subset. Protocol drift (`cancel_event` on Gemini but not on `VideoAIProvider`) already shows up as mypy noise and weak runtime gates.

---

## 9. Open ROADMAP Alignment

| ID | Item | Review note |
|---|---|---|
| R-025 | i18n | Large; no correctness risk if deferred |
| R-027 | Session log filter | Small UX; independent |
| R-028b/c | ffmpeg zip / UI install | Complements R-028a deps probe already shipped |
| R-029d | Dead physical-split cleanup | Aligns with I10; reduces hazard of reintroduction |
| R-031b | Prefer cut/composite media on plan timeline | Addresses dual-timebase residual partially |

**Suggested inserts (not yet on ROADMAP):**

- Plan readiness index normalize + offline collection (C1/C2)  
- Provider cache clear on config/env write (C4)  
- Cut/run path sandbox under project roots (C6/C7)  
- Run SSE app-lifetime (C10)  
- Untrack `.coverage` + selected-file unit tests (I27/I30)

---

## 10. Recommended Priority Order

### P0 — this week

1. **C1/C2** plan readiness index normalize + offline  
2. **C4** `_clear_provider_cache` on env/config/provider write  
3. **C10** keep run SSE across entity switches  
4. **C11/C12** player same-src exact match + escape day_label  
5. **I30** untrack `.coverage` + gitignore coverage artifacts  

### P1 — next sprint

6. **C3/C5** global validate + strip yaml api_key + mask GET  
7. **C6/C7** sandbox run project_dir + cut output_dir  
8. **I1/I3/I4/I5** plan files policy, label state stem, serial scripts, empty draft fail  
9. **I27/I28** realistic selected-file unit + integration tests  
10. **I9/I20** protocol + ArtifactIndex typing cleanup (helps mypy)  

### P2 — when touching related code

11. Whisper/text cancel gaps (I2)  
12. Body size limits (I18)  
13. Waveform abspath parity (I17)  
14. R-029d dead split cleanup  
15. Expand mypy CI surface  

---

## 11. Domain Review Coverage

| Domain | Coverage | Method |
|---|---|---|
| Core pipeline / tasks / plan / export | Full production files | Dedicated reviewer + spot-verify C1/C2/cancel/filter |
| Config + AI providers | Full config/ + ai/ + examples | Dedicated reviewer + spot-verify factory/cache/validate |
| UI server / routes / services | Full ui backend | Dedicated reviewer + auth matrix |
| Frontend ES modules | All production `src/*.js` + index | Dedicated reviewer + spot-verify C10–C12 |
| Tests / CI / hygiene | Workflows, hooks, packaging, sample tests | Dedicated reviewer + git ls-files |

This is **not** a formal “every line of every test” audit. Production modules above were read in full or near-full by domain agents; tests were sampled for realism gaps rather than line-audited.

---

## 12. Assessment

| Question | Answer |
|---|---|
| Ready for continued personal localhost use? | **Yes** |
| Ready for LAN multi-user with token as only boundary? | **No** — fix C6–C9 first |
| Ready to trust cut/export readiness gates? | **Mostly, with C1/C2 caveat** when compressed offline |
| Regressions vs 2026-07-04? | Net **improvement** on auth, identity filter, split, cancel core, defaults |
| Biggest new risk surface since last full review? | Plan global timeline UX dual-timebase + SSE lifecycle; export readiness index edge cases |

**Overall:** Clio is a mature personal pipeline with unusually strong tests and docs for its size. The next quality jump is less “new features” and more **boundary hardening** (readiness indices, provider cache, LAN sandboxes, SSE lifecycle) plus **test realism** for identity filtering.

---

## Appendix A — Historical review map

| Date | Doc |
|---|---|
| 2026-07-04 | `docs/analysis/2026-07-04-current-project-review.md` |
| 2026-07-06 | `docs/analysis/2026-07-06-ut-review.md` |
| 2026-07-16 | iteration notes |
| 2026-07-20 | **this document** |

## Appendix B — Commands re-run for this review

```bash
python -m pytest clio/tests/ -q          # 1272 passed, 1 skipped
ruff check clio main.py                  # clean
mypy clio --exclude clio/tests           # ~38 errors
npm test -- --run                        # 261 passed
git rev-parse HEAD                       # aae85d7…
```
