# Design: ffmpeg missing-path handling

**Date**: 2026-07-18  
**Status**: Design approved (Phase A); B/C deferred until A ships  
**Scope**: Detect missing ffmpeg/ffprobe at serve time, surface a clear UI warning, soft-disable the highest-traffic media entry points, and fail cleanly without lock/error storms. Later phases add setup zip fallback and UI one-click install.  
**Approach**: Phased A → B → C. Reuse `resolve_binary` / `discover_ffmpeg_bin` and existing `runtime-warnings` banner. No serve-time auto-download in A.

## 1. Goals and non-goals

### Goals

1. When ffmpeg or ffprobe is missing, the **UI still starts** (browse, plan, config, logs, tokens remain usable).
2. Users **immediately see** why media work will fail (banner), not after a mid-pipeline stack trace.
3. Highest-traffic media entry points are **soft-disabled** with a clear reason (⋮ menu + runner start).
4. Waveform and background jobs must **not** write `.generating` / cool-down `.error` files for a missing binary (environment issue, not a retriable extract failure).
5. Detection uses the **same resolution path** as compress/cut/waveform (`resolve_binary` + PATH / known install roots).
6. Later: setup can still install when package managers fail (B); UI can one-click install like Whisper (C).

### Non-goals (all phases unless noted)

- Blocking `clio serve` / UI boot until ffmpeg exists.
- Silent auto-download on every serve (opt-in only in C, never default).
- Shipping ffmpeg binaries inside the git repo.
- Replacing `doctor` CLI (it stays FAIL-on-missing; A is UI-visible serve-time UX).
- Perfect UI greying of every obscure button (cover, reindex, etc.) — backend clear errors suffice for A.
- Running `ffmpeg -version` on every check in A (existence is enough; corrupt binary is rare).

### Success criteria (Phase A)

- With no ffmpeg on PATH and empty `paths.ffmpeg`/`ffprobe`: UI loads; warning banner appears once deps are known; compress/transcribe (and label when shown) menu items disabled; runner blocks start if a media step needing ffmpeg is selected.
- Waveform shows “需要 ffmpeg” (or equivalent) without polling storms or writing waveform lock/error files.
- Starting compress via any remaining path returns the existing `FileNotFoundError` message (setup script hint).
- With ffmpeg discoverable: no banner; menus/runner behave as today.
- Unit tests cover probe helper, warning builder, early-fail waveform path; vitest for menu/runner guards if pure helpers are extracted.

## 2. Current baseline

| Surface | Behavior |
| --- | --- |
| `resolve_binary(configured, fallback)` | Non-empty configured path must be a file; empty → `discover_ffmpeg_bin` (PATH + WinGet/choco/scoop/common dirs / `FFMPEG_HOME`) |
| `doctor.py` | FAIL if ffmpeg/ffprobe not found; does not install |
| `setup.ps1` | winget `Gyan.FFmpeg` only; on failure prints manual download URL — **no zip fallback** |
| `setup.sh` | apt/dnf/pacman/zypper/brew; no static zip |
| Serve | Does **not** install or soft-disable; tasks fail at `resolve_binary` |
| `runtime-warnings.js` | Config debug prompt, LAN host/token, orphaned cut bak — **no deps warning** |
| Whisper | `/api/whisper/check` + install progress pattern (model for C, not A) |
| Waveform | Missing binary still goes through job → `.error` cool-down (bug for env missing case) |

Pain: “找不到可执行文件: ffmpeg” after users already started work; bare name `"ffmpeg"` was incorrectly treated as a configured path (fixed separately). Users who skip setup or lose PATH get no proactive guidance in the UI.

## 3. Phasing

| Phase | Name | Delivers |
| --- | --- | --- |
| **A** | Detect + warn + soft-disable | Probe, banner, `state.deps`, menu/runner/waveform gates, early fail without lock/error |
| **B** | Setup zip fallback | After winget/package-manager failure, download static build → local tools dir → optional write `paths.ffmpeg`/`ffprobe` |
| **C** | UI one-click install | Banner action “安装 ffmpeg”, progress, hot-update resolve path (Whisper-like) |

Order is fixed: **A → B → C**. This document specifies A in full; B/C are design sketches so later work stays aligned.

---

## 4. Phase A — architecture

```
loadConfig / init / config save
        │
        └─► probe_ffmpeg_deps(cfg.paths)   # pure helper, no download
                    │
                    ├─ ok true  → state.deps = { ok:true, ffmpeg, ffprobe }
                    └─ ok false → state.deps = { ok:false, missing:[...], detail }
                              → runtime-warnings warning banner
                              → buildVideoMenuItems(..., deps) disables media actions
                              → runner start intercepts media steps
                              → loadWaveformForCurrentVideo short-circuits

Media task entry (compress/cut/label/transcribe/waveform extract)
        │
        ├─ A UI: disabled / toast (best effort)
        └─ always: resolve_binary → FileNotFoundError with setup hint (unchanged contract)
```

### 4.1 Probe helper (Python)

New pure function (suggested location: `clio/utils.py` or small `clio/deps.py` — prefer next to `resolve_binary`):

```python
def probe_ffmpeg_deps(
    ffmpeg_configured: str = "",
    ffprobe_configured: str = "",
) -> dict:
    """Return availability without starting jobs.

    {
      "ok": bool,                 # True only if BOTH resolve
      "ffmpeg": str | None,       # resolved path
      "ffprobe": str | None,
      "missing": list[str],       # subset of ["ffmpeg", "ffprobe"]
      "detail": str,              # Chinese short message for UI
    }
    """
```

Rules:

- Pass **empty string** when config is empty (never coerce to bare `"ffmpeg"`).
- Call the same discovery as `resolve_binary` / `discover_ffmpeg_bin` (do not reimplement search roots).
- Catch `FileNotFoundError` per binary; do not raise from the probe.
- `detail` must name **which** binary is missing (one or both).
- No subprocess encode; existence of resolved path is enough for A.
- Cheap enough to call on config load; optional process-level cache invalidates when configured paths change (not required for A if call is just two `discover`/`which` lookups).

### 4.2 HTTP surface

**Preferred for A:** either

1. **Dedicated lightweight route** `GET /api/deps/ffmpeg` returning the probe dict (mirrors `/api/whisper/check`), **or**
2. Embed the same object under an existing boot payload if one already fits without bloating config.

Decision for implementation: **dedicated `GET /api/deps/ffmpeg`** — keeps config routes pure, matches Whisper check pattern, easy to test. No POST in A.

Response shape:

```json
{
  "ok": false,
  "ffmpeg": null,
  "ffprobe": null,
  "missing": ["ffmpeg", "ffprobe"],
  "detail": "未找到 ffmpeg、ffprobe。请运行 setup.ps1 / setup.sh，或在 config.yaml 的 paths.ffmpeg / paths.ffprobe 中填写路径。"
}
```

When ok:

```json
{
  "ok": true,
  "ffmpeg": "C:\\...\\ffmpeg.exe",
  "ffprobe": "C:\\...\\ffprobe.exe",
  "missing": [],
  "detail": ""
}
```

Uses project-resolved config paths (same as other handlers: `handler._get_config(proj_dir).paths`).

### 4.3 Frontend state and banner

- After config is available (init + after config save), call `GET /api/deps/ffmpeg` and store:

  `state.deps = { ok, ffmpeg, ffprobe, missing, detail }`  
  (or `state.ffmpegDeps` — pick one name and use consistently)

- Extend `buildRuntimeWarnings` with optional `ffmpegDeps` / `deps`:

  | Condition | level | id | text |
  | --- | --- | --- | --- |
  | `ok === false` | **`warning`** (not danger) | `ffmpeg-missing` | Use `detail` or a short fixed Chinese string listing missing binaries + “压缩 / 裁剪 / 转录抽音 / 波形等不可用” |

- **No action button in A** (no “打开设置” unless config UI already surfaces paths clearly; “安装 ffmpeg” is Phase C).
- Refresh banner path: include deps in `refreshRuntimeWarningsBanner` / equivalent so cut-orphan refresh does not drop the ffmpeg warning (pass last known `state.deps`).

### 4.4 Soft-disable scope (narrow)

| Surface | Behavior when `!state.deps.ok` |
| --- | --- |
| `buildVideoMenuItems` | Disable actions that **hard-require** ffmpeg: `compress`, `transcribe` (audio extract), and `label` if present. Set `title` to deps.detail or “需要 ffmpeg/ffprobe”. Keep remove/relink/analyze (analyze stays disabled for other reasons as today). |
| Runner (`runner.js`) | On start (and optionally preview): if selected steps intersect `{compress, label, transcribe}`, block with toast/status using deps.detail. **Do not** block `analyze` / `voiceover` / `plan` solely for missing ffmpeg. |
| Waveform | If deps known and not ok: `setWaveformStatus('需要 ffmpeg')` (or detail), **do not** call `/api/waveform`. If deps not yet loaded: existing flow OK; once deps fail, cancel further polls. |
| Cover / reindex / cut button / other | **No A UI work** — rely on backend `resolve_binary` error text. |
| Play / plan / config / logs | Unchanged |

Signature change example:

```js
buildVideoMenuItems(video, source, deps = null)
// when deps && deps.ok === false → force-disable media actions above
```

### 4.5 Waveform early-fail (backend)

In `ensure_waveform` **or** the route **before** `write_lock` / job spawn:

1. Resolve ffmpeg (and ffprobe if duration needed) via the same empty-string contract.
2. If missing: return  
   `{"status":"error","error":"<setup hint>","code":"missing_binary","key": key}`  
   with HTTP **503** or **400** (prefer **503** only if we want parity with current extract errors; **400** is also fine for “client env incomplete” — implementer picks one and tests stick to it).  
3. **Must not** create `.generating` or `.error` cool-down files for `missing_binary`.

Frontend already maps 503 error body to status text; also handle `code === 'missing_binary'` if present.

### 4.6 Backend tasks (A)

No new middleware. Existing `resolve_binary` messages stay:

> 找不到 {fallback}。请运行 setup.ps1 / setup.sh 安装，或在 config.yaml 的 paths 中填写路径。

Optional later (not A): preflight on `POST /api/run/start` returning 400 with missing deps — nice if cheap; not required if runner client already blocks.

## 5. Phase B — setup zip fallback (sketch)

**Trigger:** package manager install fails or is unavailable (Windows: winget fails; Linux: no known package manager; etc.).

**Behavior:**

1. Download a known static build (document exact URL/source in implementation plan — e.g. Gyan essentials or BtbN build; pin version or “latest stable” policy).
2. Extract to a **user-local** directory, preference order:  
   `{repo}/tools/ffmpeg/` **or** `%LOCALAPPDATA%/clio/ffmpeg` / `~/.local/share/clio/ffmpeg`  
   (prefer user-local outside repo so git stays clean; still allow repo-relative for portable dev).
3. Verify `ffmpeg` + `ffprobe` exist under extracted `bin`.
4. Optionally write absolute paths into **global** config `paths.ffmpeg` / `paths.ffprobe` if empty (do not overwrite user paths).
5. Ensure `discover_ffmpeg_bin` also searches the new install root (if not written to config).

**Non-goals for B:** UI progress bar (that is C); silent background download without user running setup.

## 6. Phase C — UI one-click install (sketch)

Mirror Whisper install:

| Piece | Role |
| --- | --- |
| Banner action | “安装 ffmpeg” when `ok === false` |
| `POST /api/deps/ffmpeg/install` | Start background download/extract (reuse B’s downloader) |
| `GET /api/deps/ffmpeg/install/status` | Progress pct + message |
| Cancel | Optional, if long download |
| On success | Re-probe; update `state.deps`; clear banner; no server restart required if resolve always re-reads paths/discovery |

**Constraints:**

- Explicit user click only (no silent install on serve).
- Show size/network warning in copy if download is large.
- Failures surface in banner/toast; do not leave half-extracted dirs as “ok”.

## 7. Error handling summary

| Case | A behavior |
| --- | --- |
| Neither binary found | Banner warning; soft-disable compress/transcribe/label; waveform early message; tasks FileNotFoundError |
| Only one found | `ok: false`, `missing: ["ffprobe"]` (or ffmpeg), detail names the gap |
| Configured path wrong | Probe fails that binary (resolve treats non-file as missing); same as today for tasks |
| Binary exists but broken | May show ok until task runs — accepted for A |
| User installs ffmpeg mid-session | Next deps refresh (config save or manual re-fetch on banner visibility / next init path) clears banner — A may re-fetch on each `refreshRuntimeWarningsBanner` or only on config load; prefer **re-fetch on banner refresh and config save** so mid-session install is visible without full reload |

## 8. Testing

### Phase A

| Layer | Cases |
| --- | --- |
| `probe_ffmpeg_deps` | both found; only ffmpeg; only ffprobe; neither; bad configured path; empty config uses discover |
| Route `GET /api/deps/ffmpeg` | JSON shape; uses config paths |
| Waveform | missing binary → error with `code=missing_binary`, no lock file, no `.error` cool-down file |
| `buildRuntimeWarnings` | injects warning when deps.ok false; level warning; id `ffmpeg-missing` |
| `buildVideoMenuItems` | disables compress/transcribe when deps.ok false; online original still can remove |
| Runner helper (if extracted) | blocks start when media steps selected and !ok |

### Phase B/C

Deferred tests around download mocks, extract layout, install status machine.

## 9. Files likely touched (Phase A only)

| File | Change |
| --- | --- |
| `clio/utils.py` or `clio/deps.py` | `probe_ffmpeg_deps` |
| `clio/ui/routes/` (new small module or config-adjacent) | `handle_get_deps_ffmpeg` |
| `clio/ui/server.py` | Register GET route |
| `clio/tasks/waveform.py` and/or `clio/ui/routes/waveform.py` | Early missing-binary return, no lock/error |
| `clio/ui/static/src/runtime-warnings.js` | ffmpeg warning |
| `clio/ui/static/src/main.js` / `sidebar-data.js` | fetch deps, refresh banner |
| `clio/ui/static/src/state.js` | `deps` field |
| `clio/ui/static/src/video-menu.js` | deps-aware disable |
| `clio/ui/static/src/runner.js` | start guard |
| `clio/ui/static/src/waveform.js` | short-circuit when !deps.ok |
| Tests: `test_utils` / new `test_deps`, route tests, vitest menu/warnings/waveform |

## 10. Implementation order (A)

1. Probe helper + unit tests  
2. GET route + test  
3. Waveform early-fail + test  
4. Frontend state + banner + tests  
5. Menu + runner + waveform short-circuit + tests  
6. Manual smoke: no-ffmpeg env / with-ffmpeg env  

B and C each get their own implementation plan after A is merged and verified.

## 11. Decisions log

| Decision | Choice | Why |
| --- | --- | --- |
| Serve auto-install | No (A/B); opt-in click only (C) | Avoid surprise network/disk use; setup remains primary |
| Soft-disable breadth | Narrow (menu + runner + waveform) | Full greying is incomplete and expensive; backend already errors |
| Banner level | warning not danger | UI is still usable; danger reserved for security-ish issues |
| API | Dedicated GET `/api/deps/ffmpeg` | Clear, testable, Whisper-like |
| Waveform missing binary | No lock, no error cool-down | Env fix should retry immediately |
| Steps needing ffmpeg | compress, label, transcribe | analyze/voiceover/plan do not call ffmpeg directly |
| Empty config path | Keep `""`, never `"ffmpeg"` | Bare name is treated as file path and breaks resolve |

## 12. Open items for later plans (not blockers for A)

- Exact static-build URL and checksum policy (B).  
- Whether install writes global vs project config (B/C default: global paths only if empty).  
- Optional `ffmpeg -version` health check (post-A).  
- Preflight on `POST /api/run/start` (optional A+).  
