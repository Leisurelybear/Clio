# Design: Plan preview chrome + composite waveform (R-031a polish / R-031a2)

**Date**: 2026-07-19  
**Status**: **Implemented** on `main` (2026-07-19)  
**Scope**: Plan-tab player chrome only — classic progress fill + playhead; composite peaks waveform on the plan global timebase  
**Roadmap**: Follow-up to **R-031a** (global scrub on source media). Does **not** implement R-031b (cut/concat media).  
**Depends on**: R-031a shipped (`plan-timeline.js`, `seekToGlobal`, `previewGlobalSec`)

## 1. Goals and non-goals

### Goals

1. Make the plan preview bar read as a **real progress control**: continuous **elapsed fill**, clear **current position** (playhead with cap), segment boundaries as light ticks — not “whole active segment painted accent.”
2. On Plan entity with a non-empty sequence, the waveform under the player shows a **stitched composite** of per-source peaks sliced by each segment’s `use_timeline`, laid out on the same global axis as R-031a (`Σ use_timeline`).
3. Waveform scrub and progress-bar scrub share the **same** composite timebase and seek path (`seekToGlobal`).
4. Leaving Plan restores **single-source** waveform load + source-domain scrub (existing behavior).

### Non-goals

- Backend `GET /api/waveform/plan` or server-side compose.
- Prefer cut files / day concat for peaks (R-031b).
- Second global max-normalize across stitched peaks (would flatten quiet segments).
- Hiding native `<video controls>` (optional tip only).
- Sidebar mini-waveforms, spectrogram, real-time VU.
- Changing plan domain / readiness / cut / export.

### Success criteria

- Plan bar: fill width tracks `previewGlobalSec / total`; playhead is visually obvious (thicker stem + top cap); active segment is **not** a solid accent slab.
- During playback/scrub, fill and playheads update via **style only** (no full bar `innerHTML` every tick).
- Plan waveform spans full composite duration; scrubbing it jumps across segment boundaries via `seekToGlobal`.
- Segment source hop during preview **does not** replace the composite waveform with a single-file load.
- Missing/pending peaks for some indexes: zero-fill those slices; optional status “部分波形生成中…”.
- Unit tests for pure slice/compose; existing waveform unit tests stay green.

## 2. Baseline / pain

| Surface | Today |
| --- | --- |
| `#preview-seg-bar` | Segment blocks with done/active/pending colors; 2px playhead; full `innerHTML` on every `renderPreviewBar` |
| Active segment | Entire block uses accent background — competes with playhead |
| `#waveform-bar` | Peaks for `state.currentVideo` only; playhead = `currentTime/duration`; scrub sets `player.currentTime` |
| `_loadAndSeekSource` | Always calls `loadWaveformForCurrentVideo()` — **destroys** composite waveform on every plan hop |

## 3. Locked decisions (review)

| # | Decision |
| --- | --- |
| 1 | Progress: classic **fill** + prominent playhead; **no** full-segment accent fill; segment labels muted |
| 2 | Soft-update fill/playhead styles during play/scrub; full bar rebuild only when sequence/structure changes |
| 3 | While `isGlobalTimelineUi()`, **do not** call single-file `loadWaveformForCurrentVideo` from media hop; use plan compose loader |
| 4 | Plan waveform scrub/playhead use `previewGlobalSec / total` + `seekToGlobal`; inject seek handler to avoid `waveform`↔`viewer` cycles |
| 5 | `targetBins = clamp(round(totalSec * 2), 400, 2000)` (match backend `_MIN_BINS`/`_MAX_BINS`) |
| 6 | Resample with **window max**; missing peaks → zeros; **no** second global normalize |
| 7 | Leave Plan → single-file waveform + source scrub again |

## 4. Progress bar chrome

### 4.1 Layers (bottom → top)

1. Track background (existing bar surface).
2. Segment blocks: width from `segmentWidths`; **neutral** pending/done tints only; right border as boundary; **no** solid accent for “current.”
3. `.preview-progress-fill` — absolute, left 0, height 100%, width `% = global/total`, accent at ~35–45% opacity.
4. `.preview-playhead` — ~3px vertical stem + small top triangle/dot (CSS); z-index above fill; `pointer-events: none`.
5. Segment index labels: lower opacity (~0.4); optional hide below min block width via CSS.

### 4.2 Soft update API (viewer)

```js
function softUpdatePreviewChrome(tl) {
  // set fill width + playhead left from previewGlobalSec / tl.total
  // do NOT rebuild segment DOM
}
```

- `seekToGlobal` / `ontimeupdate` / scrub move → `softUpdatePreviewChrome` + `updateCompositeClock`.
- `renderPreviewBar()` full rebuild when: enter Plan, sequence length/order change, `use_timeline` structural refresh from editor, stop preview reset labels.

### 4.3 Interaction

Unchanged from R-031a: drag bar → global sec; click block → segment `globalStart`; drag does not force play.

## 5. Composite waveform

### 5.1 Pure module `plan-waveform.js`

```js
/**
 * Slice source peaks for plan-local [planStart, planEnd) mapped onto
 * peaks covering [0, sourceDurationSec].
 * @returns {number[]}
 */
export function slicePeaks(peaks, sourceDurationSec, planStart, planEnd)

/**
 * Max-pool or pad/trim peaks to exactly targetLen bins.
 * @returns {number[]}
 */
export function resamplePeaksMax(peaks, targetLen)

/**
 * @param {PlanTimeline} timeline  from plan-timeline.buildTimeline
 * @param {Record<string, { peaks: number[], duration_sec: number } | null | 'pending'>} byVideoIndex
 * @param {{ targetBins?: number }} [opts]
 * @returns {{ peaks: number[], total: number, targetBins: number, missingSegIndexes: number[] }}
 */
export function composePlanPeaks(timeline, byVideoIndex, opts)
```

**slicePeaks:**  
- If `sourceDurationSec <= 0` or empty peaks → `[]` (caller treats as missing).  
- `i0 = floor(planStart / dur * n)`, `i1 = ceil(planEnd / dur * n)`, clamp to `[0, n]`.  
- Return `peaks.slice(i0, max(i0, i1))`.

**composePlanPeaks:**  
- `targetBins = clamp(round(timeline.total * 2), 400, 2000)` unless opts override (still clamp).  
- Skip `duration <= 0` segments (no bins).  
- For each positive segment:  
  - bins_i = max(1, round(duration_i / total * targetBins)); adjust last segment so sum = targetBins.  
  - Lookup `byVideoIndex[videoIndex]`; if missing/pending/null → zeros of length bins_i; record segIndex in `missingSegIndexes`.  
  - Else `resamplePeaksMax(slicePeaks(...), bins_i)`.  
- Concatenate; return.

### 5.2 Loading (`waveform.js`)

| Mode | When | Behavior |
| --- | --- | --- |
| Source | `!isPlanGlobal` | Existing `loadWaveformForCurrentVideo` |
| Plan | Plan entity + non-empty sequence | `loadPlanWaveform()` |

**`loadPlanWaveform`:**

1. Bump module `_planLoadToken`.  
2. `tl = buildTimeline(sequence)`.  
3. Unique `videoIndex` values → resolve `state.videos` entry → `buildWaveformQuery` → parallel `GET /api/waveform` (reuse poll-on-pending pattern per key).  
4. Fill module cache `Map<index, { peaks, duration_sec } | 'pending' | null>`.  
5. `composePlanPeaks` → `setWaveformPeaks`.  
6. If any pending and token current: schedule poll for pending keys only; recompose when ready.  
7. Status: empty if all ready; `部分波形生成中…` if partial; error string if all failed.

**Cache invalidation:**  
- Full refetch when set of video indexes or project/source changes.  
- **Recompose only** when `use_timeline` / order changes but indexes unchanged (`recomposePlanWaveformFromCache()`).

### 5.3 Hook from viewer / editor

- `_loadAndSeekSource`: if global plan UI → **skip** `loadWaveformForCurrentVideo()`.  
- Enter Plan / `renderPlan` first paint / day switch: `loadPlanWaveform()`.  
- `editor-plan` `_refreshPreviewTimeline`: recompose from cache + soft-update chrome.  
- Leave Plan (`stopPreview` not enough — entity change in sidebar): call `loadWaveformForCurrentVideo()` or `resetWaveform` then load current file.

### 5.4 Scrub + playhead (no circular imports)

In `setupPlayer` / waveform bind:

```js
// waveform.js
let _planSeek = null; // { isPlan: () => boolean, seekGlobal: (sec) => void, getGlobalRatio: () => number }

export function setWaveformPlanBridge(bridge) { _planSeek = bridge; }

// seekFromEvent:
if (_planSeek?.isPlan()) {
  const total = ... // from last compose total stored module-side, or bridge.getTotal()
  const g = timeFromClientX(clientX, rect, total);
  _planSeek.seekGlobal(g);
  updateWaveformPlayhead(null); // uses bridge ratio
  return;
}

// updateWaveformPlayhead:
if (_planSeek?.isPlan()) {
  ratio = _planSeek.getGlobalRatio(); // previewGlobalSec / total
} else {
  ratio = playheadRatio(player.currentTime, player.duration);
}
```

`viewer.setupPlayer` registers the bridge once (dynamic values read from `state` + last compose total exposed via `getPlanWaveformTotal()`).

## 6. CSS

| Selector | Change |
| --- | --- |
| `.preview-seg-bar` | Keep relative; ensure overflow visible enough for playhead cap (or clip carefully) |
| `.preview-progress-fill` | New absolute fill layer |
| `.preview-playhead` | Wider stem + `::before` cap |
| `.preview-seg-block.active` | Neutral highlight (e.g. slightly brighter border/bg), **not** full accent fill |
| `.preview-seg-block.done` | Slightly darker than pending |
| `.preview-seg-label` | opacity ~0.4 |

## 7. Files

| File | Change |
| --- | --- |
| `clio/ui/static/src/plan-waveform.js` | **New** pure compose |
| `clio/ui/static/src/__tests__/plan-waveform.test.js` | **New** |
| `clio/ui/static/src/waveform.js` | Plan load, bridge, playhead/scrub branch, module cache |
| `clio/ui/static/src/viewer.js` | Fill layer, soft-update, skip single load on hop, register bridge, trigger plan load |
| `clio/ui/static/src/editor-plan.js` | Recompose on timeline edit |
| `clio/ui/static/style.css` | Fill + playhead + muted blocks |
| `ROADMAP.md` | Note R-031a polish / a2 under R-031 |
| `clio/ui/README.md` | Plan composite waveform + progress chrome |

**No** Python/API changes.

## 8. Testing

### Unit (`plan-waveform.test.js`)

1. `slicePeaks` mid-range, start 0, end past duration (clamp).  
2. Empty peaks / zero duration → empty or safe.  
3. `resamplePeaksMax` to longer/shorter length; zeros.  
4. `composePlanPeaks` two segments durations 10+5 → bin sum = targetBins; proportions ≈ 2:1.  
5. Missing map entry → zeros for that segment; `missingSegIndexes` set.  
6. `targetBins` clamped to [400, 2000].  
7. Zero-duration segment contributes no bins.

### Regression

- `waveform.test.js` (timeFromClientX, buildWaveformQuery) green.  
- `plan-timeline.test.js` green.

### Manual

1. Plan multi-index: bar fill + playhead track continuously; active block not a solid blue slab.  
2. Waveform shows energy across whole plan; drag waveform crosses sources.  
3. Play through boundary: waveform **does not** flash empty / reload single file.  
4. Edit `use_timeline`: bar proportions + waveform recompose without full app reload.  
5. Switch to a video entity: single-file waveform returns.  
6. 起点/终点 still correct with offset.

## 9. Risks

| Risk | Mitigation |
| --- | --- |
| Hop reloads single waveform | Skip load in plan mode (decision 3) |
| waveform ↔ viewer import cycle | Bridge injection (decision 4) |
| Sparse bins on short plans | Floor 400 bins (decision 5) |
| Loudness incomparable across clips | Accept; no global renorm (decision 6) |
| Full innerHTML flicker | Soft-update (decision 2) |
| Many unique sources | Parallel fetch + existing backend job cap |

## 10. Decisions log

| Decision | Choice | Rationale |
| --- | --- | --- |
| Bar style | Classic fill + cap playhead | User: current position unclear |
| Waveform | Client stitch of source peaks | Reuse cache; no backend |
| targetBins | 400–2000 @ ~2/s | Align with `clio/tasks/waveform.py` |
| Resample | Window max | Envelope fidelity |
| Hop behavior | Keep plan waveform | Fixes dual-timebase pain of R-031a |

## 11. Implementation readiness

Approved in conversation 2026-07-19 (7 review resolutions). Next: implementation plan (`writing-plans`) then implement on `main`.
