# R-033 Hardening + Pipeline Robustness — Design

Date: 2026-07-23  
Status: approved for planning  
Scope: **R-033a–e** + selected pipeline bugs (I1/I3/I4/I7/I8) + Critical/Important residuals (export `day`, run config deepcopy, log blank rows; Wave6 cancel cleanup + waveform abspath when capacity allows).

## Goal

Close post-review security/capability holes and fix verified pipeline correctness bugs so localhost + token use is safer and task results/progress numbers are trustworthy. No new product features.

## Non-goals

- R-032 desktop packaging, R-025 i18n, R-031b cut-prefer preview, R-027e historical logs, R-028b/c ffmpeg install
- I9 `VideoAIProvider.cancel_event` protocol, I11 whisper `sanitize` on V2 load, I12–I15 config/AI polish
- I22 native video timebase on Plan, I23 `renderRun` flags, I25 transcript “当前时间” offset
- Cut `glob(f"{idx}_*")` prefix ambiguity, Jianying `expand_index_keys` parity, project create `output_dir` sandbox
- Multi-user SaaS threat model; removing `?token=` media URLs (I26)
- Large ArtifactIndex / identity-service refactor

These residuals stay on ROADMAP / review notes only.

## Background

| Source | Notes |
| --- | --- |
| ROADMAP R-033 | a sandbox · b yaml api_key · c global validate · d body/compare_digest · e selected-match tests — all Open as of 2026-07-22 |
| `docs/analysis/2026-07-20-full-project-review.md` | C1/C2/C4/C10–C12 fixed; C6/C7/C5/C3/I18/I19 and many Important items still open |
| Code scan 2026-07-23 | Confirmed R-033a–e OPEN; new Critical: export `day` path escape; Important: run cache mutation, waveform fail-open, cancel partials |
| Baseline tests | pytest 1277 passed, vitest 292 passed (2026-07-23) |

Product is a personal local pipeline. Auth gates *who*; R-033 tightens *what* an authenticated caller can do with body paths, secrets, and request size.

## Approach (Wave order — security first)

```text
Wave0  fix(log): blank session_log rows from print split writes
Wave1  Critical: export day + run day_label basename · run deepcopy before body mutation
Wave2  R-033a sandbox · R-033d body cap + hmac.compare_digest
Wave3  R-033b api_key · R-033c validate_global_config
Wave4  R-033e unit tests for _matches_selected_*
Wave5  Pipeline I1 / I3 / I4 / I7 / I8
Wave6  (capacity) cancel partial cleanup · waveform abspath align with /api/video
docs   ROADMAP R-033 phases done + residual list
```

One feature per commit (English messages). Prefer small, revertible commits on `main`.

### Success criteria

1. R-033a–e behaviors match this spec and have automated tests.
2. `POST /api/export` `day` and run `day_label` reject unsafe basenames (400).
3. `POST /api/run/start` body flags do not mutate shared cached `AppConfig`.
4. I1/I3/I4/I7/I8 behave as specified below.
5. Full `pytest` + `vitest` green; no new intentional mypy debt in touched code.

---

## Wave0 — Session log blank rows

**Files:** `clio/log.py`, `clio/tests/test_log.py` (already drafted in working tree).

**Behavior:** `_TeeWriter.write` only calls `session_log.write` when `message.rstrip()` is non-empty, so `print()`’s separate `"\n"` write does not create empty UI “信息” rows.

---

## Wave1 — Critical fast fixes

### 1a Export `day` + run `day_label` basename

**Where:**
- `clio/ui/routes/export.py` — `day` joins plan path and `output/export/{day}_{fmt}`
- `clio/ui/routes/run.py` — `day_label` is passed into the pipeline / plan filenames (same class of join); currently **unsanitized** (scan residual)

**Behavior:** Use `file_service._is_safe_basename` (already: non-empty, len≤200, no `/` `\` `..`, no control chars). Fail → **400** with `invalid day` / `invalid day_label` (same status as `POST /api/cut` day_label, not GET plan’s 403).

**Tests:** `day`/`day_label` of `"../x"`, `"a/b"` → 400; `day1` still works.

### 1b Run config deepcopy

**Where:** `clio/ui/routes/run.py` — body fields such as `use_transcripts` currently mutate cached config when `project_dir` override is absent (`cfg.plan.use_transcripts = …` on the object from `_get_config`).

**Behavior:** Before any body-driven field write, `cfg = copy.deepcopy(cfg)` (always on the start path, or whenever mutation is possible). `project_dir` override already deepcopies; unify so no path mutates the cache.

**Tests:** Shared cache mock / two sequential starts — first sets `use_transcripts: false`; second omits the flag; second run’s cfg must keep the **default** `use_transcripts` from a fresh load (assert **field value**, not object identity — deepcopy always changes identity).

---

## Wave2 — R-033a / R-033d

### R-033a Sandbox

**`POST /api/run/start` body `project_dir` / `input_dir`**

- Resolve: `Path(...).expanduser().resolve()`.
- Allowlist: same as `resolve_project_input` — current serve project root + all paths in `projects.json` registry.
- Not allowed or not a directory → **400** with clear error (`not allowed` / `not found`).
- On success: deepcopy + set `_project_dir` as today.

**`POST /api/cut` body `output_dir`**

- Omitted: default `output/cuts/<day_label>` unchanged.
- Provided: resolved path must be under `config.paths.output_dir` (`is_relative_to` or equivalent; Windows-safe resolve).
- Outside → **400**, no cuts written.

**Shared helper:** Prefer one `assert_allowed_project_dir` / `is_under_root` used by query resolution and run body, so allowlists cannot drift.

### R-033d Body size + token compare

**JSON PUT/POST** (`clio/ui/server.py`)

- Constant `MAX_JSON_BODY_BYTES = 8 * 1024 * 1024` (8 MiB).
- Parse `Content-Length`; missing → treat as **0** (empty body; same as today). Invalid/negative / non-int → **400**.
- Chunked / no Content-Length: out of scope — stdlib handler continues to require Content-Length for non-empty JSON (document only).
- `length > MAX` → **413** without reading unbounded body (do not `rfile.read(length)` when over cap).
- Else `rfile.read(length)` + JSON parse as today.

**Auth token**

- Bearer and `?token=` compared with `hmac.compare_digest` **only when both sides are `str` and `len` equal**.
- Length mismatch or missing token: return **401** without calling `compare_digest` (Python requires equal-length inputs).
- Keep `?token=` for media URL compatibility (I26 out of scope).

---

## Wave3 — R-033b / R-033c

### R-033b yaml `api_key`

| Path | Behavior |
| --- | --- |
| Runtime resolve | **Keep env-first, yaml fallback** (`_resolve_api_key` today): if `api_key_env` set and env non-empty → env; else yaml `api_key`. Avoids hard-breaking yaml-only installs mid-session. |
| Write / `_normalize_provider` / raw PUT | **Strip on write:** never persist a non-empty `api_key` into yaml (force `""` or omit). Client may still POST a key; it is discarded. |
| GET providers / config / raw | **Mask** any non-empty `api_key` as `"********"` before JSON response. Apply to `handle_get_providers`, provider create/update **response body**, and any GET that dumps provider dicts from yaml (`handle_get_config_raw` / global raw). Keep `api_key_env` name. |
| Error copy | `gemini` / `doctor` / `main`: point only to `.env` / env var; do not suggest yaml `api_key`. |

**Policy summary:** runtime still accepts legacy yaml keys; **new writes never store keys**; **reads never return cleartext keys**; messaging is env-only. Follow-up (out of scope): fail validation if yaml key non-empty after a deprecation window.

### R-033c `validate_global_config`

- New `validate_global_config(GlobalConfig) -> None` covering **global-layer** rules only (no project `tasks`):
  - provider `type` ∈ supported set (same as `_require_supported_provider_type`)
  - per provider: `requests_per_minute`, `retry_attempts`, `max_tokens`, `timeout_sec`, `poll_interval_sec` all **`>= 0`** (match `_validate_config`: **0 is allowed**, e.g. unlimited / default-style — **not** `timeout_sec > 0`)
  - `ai.provider_ttl_min >= 0`
  - proxy: if `enabled` then `url` non-empty (same as full validate)
  - `naming.index_width >= 1` if present on global naming
- Call from end of `load_global_config` and any global PUT / provider write path that currently only “load to parse”.
- Failure → do not commit bad yaml; API **400** / raise `ValueError`.

---

## Wave4 — R-033e tests only

**Where:** `clio/tasks/_helpers.py` (`_matches_selected_stem`, `_matches_selected_artifact`); tests in `clio/tests/test_helpers.py` (or dedicated module).

**Cases (minimum):**

1. Filename stem ≠ selection, but JSON `media_identity.compressed_stem` / `original_stem` matches.
2. Match via `source_file` / `compressed_file` only.
3. `index` int / zero-padded string behavior as implemented today.
4. Corrupt / non-JSON → `False`.
5. Direct stem match still `True` (regression).

No production change unless a test exposes a clear bug.

---

## Wave5 — Pipeline bugs

### I1 Plan respects `files=`

**Where:** `clio/tasks/plan.py` (pipeline already forwards `files=` from run/CLI).

- `files is None`: all texts (plus existing day filter) — **unchanged full-project plan**.
- `files is not None` (including **`[]`**): filter texts with `_selected_stems` + `_matches_selected_artifact`. Empty list → zero clips after filter.
- After filter, zero clips: log clearly and return/skip **without** writing a success plan from empty context (align with scripts/refine early-exit style).
- Log text: report filtered count; remove “ignore selection / 使用所有素材” messaging.

### I3 Label `ProcessingState` key

**Where:** `clio/tasks/label.py`.

- Prefer `source_file` / `compressed_file` / identity stems (same spirit as `scripts.py`), not `json_file.stem.split("_", 1)[-1]` title stem.
- Tests: file basename title ≠ `source_file` stem → state keys use source stem.

### I4 Serial voiceover try/except

**Where:** `clio/tasks/scripts.py` serial branch (`max_workers <= 1`).

- Mirror parallel: catch per-file errors, count, continue; `cancelled` still breaks; end-of-batch warning if any failures.

### I7 Refine return success count

**Where:** `clio/tasks/refine.py`.

- `run_refine_texts` / `run_refine_scripts` return `completed`, not `len(target_files)`.
- Call sites that assumed “return == targets” must tolerate lower counts.

### I8 Progress ETA phase reset

**Where:** `clio/progress.py`.

- On `update(phase=…)` when phase **changes**: `self._start = time.monotonic()`; reset `current` (existing); set `eta_sec = None` until new samples.
- Tests with frozen/monotonic clock.

---

## Wave6 — Capacity extras

### 6a Cancel / failure partial cleanup

**Compress:** on `InterruptedError` or failed write for this attempt, `unlink` partial `use_out` (or write via temp+rename). Do not delete known-good finished files.

**Cut `replace_file_safely`:** on `write_fn` failure with `bak is None`, unlink partial `dest` before re-raise; with `bak`, keep restore behavior.

### 6b Waveform abspath allowlist

Align `clio/ui/routes/waveform.py` `_original_allowed` with `videos.py` original abspath gate (`handle_get_video` ~525–538):

| Case | Today (waveform) | Target (= video) |
| --- | --- | --- |
| No `videos.json` / empty selection | **allow any** abspath | **deny** abspath (`False` / 403-class) |
| Path exact-resolved ∈ selected | allow | allow |
| Basename-only match (`s.name == vp.name`) | **allow** | **deny** (video requires exact resolved path) |

Prefer shared predicate if cheap. If time-boxed, ship 6a only and list 6b under residual.

---

## Testing & commits

- Style: mock/monkeypatch unit tests by default.
- Suggested commit topics match Waves (Wave5 may be five commits).
- Per-wave / final:

```bash
python -m pytest clio/tests/ -q --tb=line
npm test -- --run
```

## Risks

| Risk | Mitigation |
| --- | --- |
| Cut sandbox too strict | Allow entire `output_dir` tree; default cuts path unchanged |
| Old yaml `api_key` users | Runtime still reads yaml key; GET mask + strip on save + env-only errors |
| 8 MiB body cap | Config/plan JSON well under; constant adjustable; 413 message |
| Plan `files=` stricter | Unspecified files still full scan; UI already sends selection on other steps |
| Label state key migration | New marks use source stem; orphan old keys OK |
| Cancel unlink too aggressive | Only unlink current write target on failure/interrupt |

## Rollback

Independent commits on `main` → per-commit `git revert`. No DB migrations. Stripped yaml keys recover only from backup/history (keys belong in `.env`).

## Residual (document only)

- I9, I11–I15, I22, I23, I25  
- Cut index prefix glob; Jianying index expand; project create `output_dir`  
- Query-token media URLs  
- Deprecate/fail non-empty yaml `api_key` at load after migration window  
- Export `jianying_draft_dir` write target sandbox (copy destination)  
- Chunked request bodies without Content-Length  

## Docs after implementation

- Mark R-033a–e done on `ROADMAP.md`; note pipeline fixes under recently completed if no separate IDs.
- Implementation plan: `docs/superpowers/plans/2026-07-23-r033-hardening-and-pipeline-robustness-plan.md` (writing-plans next).
