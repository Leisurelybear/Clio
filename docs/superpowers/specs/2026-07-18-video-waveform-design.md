# Design: Video player audio waveform (lazy peaks)

**Date**: 2026-07-18  
**Status**: Implemented on `main` (lazy peaks + player scrub bar; regenerate menu deferred)  
**Scope**: Main player pane only — scrubbable amplitude waveform under `<video>`  
**Approach**: Backend lazy peaks cache from **original** source + non-blocking frontend render/poll

## 1. Goals and non-goals

### Goals

1. Show an **amplitude waveform** under the main player so users can spot loud/exciting moments at a glance.
2. Waveform is **clickable/draggable** to seek the current video.
3. Peaks prefer the **original source file** (where speech/ambient audio lives) when the player shows a full-file media; for **split compressed segments**, peaks use the **currently loaded file** so duration matches the bar (see §6.4).
4. **Never block video load**: open/play immediately; draw waveform when peaks are ready.
5. **Lazy generation** with disk cache; first open may kick a background job; subsequent opens are instant.
6. **Crash-safe**: interrupted generation is detected via lock + `started_at` and re-kicked.

### Non-goals

- Sidebar mini-waveforms (out of scope; list already has AI cover thumbs).
- Binding peaks generation to compress/analyze pipeline (optional later).
- Spectrogram, multi-channel, real-time VU meter, or Web Audio-only path.
- Replacing native `<video controls>` with a full custom player chrome.
- Perfect sample-accurate alignment between original peaks and a split compressed segment’s absolute timeline (we stretch peaks to **current player duration**).

### Success criteria

- Selecting a video with an online original: either peaks appear immediately (cache hit) or a pending state shows while video plays; when ready, waveform paints without reload.
- Click/drag on the bar seeks `player.currentTime` proportionally.
- Concurrent requests for the same source do **not** start two ffmpeg jobs.
- Stale `*.generating` older than `STALE_SEC` is treated as failed lock and regenerates.
- Offline original with available compressed: fallback peaks from compressed (marked in API); no original and no compressed: empty/error UI, no hang.
- Unit tests for path resolution, cache/pending/stale, and pure scrub mapping; vitest for render/seek helpers if extracted.

## 2. Current baseline

| Surface | Behavior |
| --- | --- |
| `index.html` `#player-pane` | `<video id="player" controls>` in `.player-wrap`; `#player-info`; plan `#preview-bar` |
| `viewer.js` | `playVideoSegment` sets `/api/video?...`; plan preview scrub on `#preview-seg-bar` only |
| Audio tooling | Transcribe extracts audio via ffmpeg; **no** peaks/waveform product |
| Covers | `output/covers/` + `GET /api/cover` (pattern to mirror for peaks files) |

Pain: no visual cue for audio energy; users scrub blindly or rely on AI segments only.

## 3. Architecture

```
selectVideo / playVideoSegment
        │
        ├─► set player.src  (unchanged, non-blocking)
        │
        └─► GET /api/waveform?file&source&abspath&project…
                    │
                    ├─ ready     → 200 { peaks, duration_sec, audio_source }
                    ├─ pending   → 202 { status: "pending", started_at }
                    ├─ missing   → kick background job → 202 pending
                    └─ error     → 4xx/5xx short message

Background job (per cache key, exclusive):
  original path (prefer) → ffmpeg mono downsample → bin max-abs peaks
  → atomic write output/waveforms/<key>.json → remove .generating
```

### 3.1 Cache key and files

| Item | Convention |
| --- | --- |
| Directory | `{project_output}/waveforms/` |
| Ready file | `<key>.json` |
| Lock file | `<key>.generating` JSON: `{ "started_at": <unix>, "source_path": "...", "pid": optional }` |
| Optional error | `<key>.error` short text (or omit; next open retries after cool-down) |

**Key construction** (stable, filesystem-safe):

```
key = sha1( normalized_abs_path_utf8 )[:16]
```

- Prefer resolved absolute path of the **audio source file** used for generation (original when used, else compressed).
- Do **not** key only on display `file` name (collisions across projects are already scoped by `project_output`; within project, abs path is safer than stem alone).
- Response may also include `stem` for debugging.

### 3.2 Peaks JSON schema

```json
{
  "version": 1,
  "source_path": "D:/.../GL010695.MP4",
  "audio_source": "original",
  "duration_sec": 312.4,
  "bin_count": 1200,
  "peaks": [0.02, 0.15, 0.88, ...]
}
```

- `peaks[i]` ∈ `[0, 1]` — max absolute amplitude in that bin after mono conversion.
- `bin_count`: clamp by duration — e.g. `clamp(round(duration_sec * 2), 400, 2000)` (tunable constant in one place).
- File size target: typically well under 50 KB.

### 3.3 Source resolution order

1. If request provides `abspath` (or video list match abs path) and file exists → **original**.
2. Else resolve original via existing video index / `videos.json` / match fields used by `/api/video`.
3. Else if compressed artifact exists for this entry → **compressed** fallback, `audio_source: "compressed"`.
4. Else → 404 / empty; do not spin forever.

FPS=1 compressed may still have usable audio track depending on compress settings; fallback is best-effort for offline original.

## 4. API

### 4.1 `GET /api/waveform`

Query params (align with `/api/video` / `/api/cover`):

- `file`, `source` (`compressed` \| `original` — UI source mode)
- `abspath` optional
- `project` / `project_dir` / `token` as elsewhere

**Responses:**

| HTTP | Body |
| --- | --- |
| 200 | Full peaks JSON (+ `status: "ready"`) |
| 202 | `{ "status": "pending", "started_at": <unix>, "key": "..." }` |
| 404 | `{ "ok": false, "error": "no media" }` |
| 500 | `{ "ok": false, "error": "..." }` generation hard-fail after mark |

**Side effects on GET:**

- If ready file exists and is valid `version: 1` → return it (no job).
- If lock exists and `now - started_at <= STALE_SEC` (default **900s / 15 min**) → 202 pending, **do not** start another job.
- If lock exists and stale → delete lock, treat as missing.
- If missing → create lock (`started_at=now`), start background worker, return 202.
- Invalid/corrupt ready JSON → delete and regenerate (same as missing).

### 4.2 `POST /api/waveform/regenerate` (P1, optional same PR if cheap)

Body/query identifies same media. Deletes ready + lock + error for key, then kicks generation; returns 202. Wire to video menu “重新生成波形” only if menu pattern is trivial; otherwise defer to follow-up.

### 4.3 Concurrency

- In-process: `threading.Lock` or dict of per-key locks so two GETs cannot both pass the “missing” check.
- Cross-process / crash: file lock is the durable signal.
- Global worker cap: **1–2** concurrent ffmpeg waveform jobs (queue the rest as pending without starting).

## 5. Generation pipeline

1. Resolve input path (readable video).
2. Write/refresh `.generating`.
3. Run ffmpeg (conceptually):

   - mono, low sample rate (e.g. 8000 Hz), raw f32le or s16le to pipe **or** short temp under `waveforms/.tmp/`
   - Prefer pipe to avoid multi-GB dumps; if pipe is fragile on Windows, use temp wav then delete in `finally`.

4. Stream samples; for each bin compute max abs; normalize by global max (or fixed headroom) so peaks use full 0–1 range.
5. Write `<key>.json.tmp` then `os.replace` → `<key>.json`.
6. Remove `.generating` (and `.error` if any).
7. On failure: remove `.generating`, optionally write `.error`, log; next GET may retry (optional cool-down: if `.error` mtime < 60s, return 500 with message instead of tight loop).

**Cancel:** not required for v1; leaving the UI does not cancel the job (good for “next open ready”).

## 6. Frontend UI

### 6.1 DOM

Insert under `.player-wrap` (or between wrap and `#player-info`):

```html
<div id="waveform-bar" class="waveform-bar" hidden>
  <canvas id="waveform-canvas"></canvas>
  <div class="waveform-playhead" hidden></div>
  <div class="waveform-status" aria-live="polite"></div>
</div>
```

### 6.2 Visual states

| State | UI |
| --- | --- |
| no video | `hidden` |
| pending | bar visible, muted status “波形生成中…”, empty/flat track; playhead still tracks video if playing |
| ready | draw peaks; clear status |
| error | short status; flat track |

Height ~28–36px; fill uses theme accent with alpha; playhead 1–2px solid.

### 6.3 Interaction

- **Click / drag** on bar: `t = clamp(x / width, 0, 1) * player.duration` → `player.currentTime = t` (if `duration` finite).
- **Playhead**: `timeupdate` + `requestAnimationFrame` throttle; position `currentTime / duration * width`.
- **Resize**: `ResizeObserver` on bar → redraw canvas from last peaks.
- **Video change**: abort poll timer; clear peaks; new GET.
- **Poll while 202**: every 2–3s, max ~120 attempts or until video changes; on 200 draw; on hard error stop and show status.

### 6.4 Timebase note

Peaks shape is from original (or fallback) duration. Scrub **always** maps to `HTMLVideoElement.duration` of the **currently loaded** element so user seek matches what they hear. If durations differ significantly, peaks are linearly stretched/squashed to the bar — acceptable for “where is loud” discovery.

Segment offset (`offset_sec`) does not shift the waveform for v1; when playing a compressed segment that is a slice of original, peaks still represent the **whole source file** if keyed by original path — **important edge case**:

- **Rule for v1:** key and generate peaks for the **file that is the audio basis**. When UI plays a **segment compressed file**, prefer generating from **that segment’s original** only if we can pass the original path; the waveform then shows **full original** energy, while player duration is segment length → mismatch.

**Mitigation (explicit):**

- When current item is a split segment (`segment_label` / `offset_sec` present) **and** audio_source is full original, either:
  - **(Preferred v1)** generate/cache peaks from the **compressed segment file** when `source===compressed'` and player is that segment (so duration matches), **or**
  - still prefer original only when playing non-segment / full-file original.

**Resolved choice for this design:**  
- Default preference remains **original full file** when the player’s media is the full original or a non-split compressed sibling of similar full duration.  
- When the playing file is a **split segment** (`group_key` + `segment_label`), compute peaks from the **file actually loaded in the player** (usually that compressed segment) so bar duration matches. Document in API `audio_source` and `aligned: true|false`.

## 7. Module layout (suggested)

| Piece | Location |
| --- | --- |
| Peaks compute + cache IO | `clio/tasks/waveform.py` (or `clio/waveform.py` if tiny) |
| HTTP handlers | `clio/ui/routes/waveform.py` or extend media routes |
| Route registration | `clio/ui/server.py` |
| UI | `clio/ui/static/src/viewer.js` (+ small `waveform.js` if `viewer.js` grows) |
| CSS | `clio/ui/static/style.css` |
| Tests | `clio/tests/test_tasks_waveform.py`, `test_routes_waveform.py`; vitest helpers under `static/src/__tests__/` |

Follow existing patterns: `HandlerProtocol`, project output resolution, safe basename / resolve-in-dir for any user-supplied names.

## 8. Testing

**Python**

- Cache key stability; ready hit skips ffmpeg (mock).
- Missing → creates lock + schedules job (mock executor).
- Pending non-stale → no second job.
- Stale lock → re-kick.
- Atomic write leaves no half JSON on simulated crash mid-write (tmp + replace).
- Source resolution: original exists; original missing + compressed; neither.

**JS**

- Scrub math pure function: `timeFromClientX(x, width, duration)`.
- Pending poll stops on video change (mock timers).

**Manual**

- Long original first open: video plays, status pending, then waveform appears.
- Kill server mid-generate: restart, reopen → stale recovery regenerates.
- Offline original path: compressed fallback or clear error.

## 9. Rollout / docs

- No ROADMAP ID required unless product wants R-0xx; can note under UI player polish.
- UI README: one line under player — waveform from original audio, lazy cache in `output/waveforms/`.
- No new npm deps; no new Python deps beyond existing ffmpeg usage.

## 10. Implementation order (for writing-plans)

1. `tasks/waveform.py`: peaks extract + cache/lock/stale helpers + tests.  
2. Route `GET /api/waveform` + registration + route tests.  
3. DOM/CSS + viewer hook: GET, draw, seek, playhead.  
4. Pending poll + video-change cancel.  
5. Segment alignment rule (play-file vs full original) + test.  
6. Optional regenerate menu item.  
7. Docs touch + manual smoke.

## 11. Decisions log

| Decision | Choice | Why |
| --- | --- | --- |
| Placement | Main player under video (A) | Best for “find moments” |
| Peaks source preference | Original when available | Speech on source |
| Generation timing | Lazy on first waveform request | User request; no pipeline coupling |
| Blocking | Never block video load | UX |
| Long jobs | Background + lock + stale re-kick | Survive interrupt; no duplicate work |
| Frontend decode | No | Long vlogs; mirror server ffmpeg |
| Segment mismatch | Prefer peaks of **currently loaded** file when split segment | Duration alignment |
