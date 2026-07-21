# Plan Preview Chrome + Composite Waveform (R-031a2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Classic progress fill + clear playhead on the plan bar; stitched multi-source peaks waveform on the R-031a global timebase with composite scrub.

**Architecture:** Pure `plan-waveform.js` for slice/resample/compose. `waveform.js` owns plan fetch cache + bridge for seek/ratio. `viewer.js` soft-updates fill/playhead, skips single-file waveform load while on Plan, registers bridge and triggers plan load.

**Tech Stack:** Vanilla JS ES modules, Vitest, existing `/api/waveform`, no new deps.

**Spec:** `docs/superpowers/specs/2026-07-19-plan-preview-chrome-waveform-design.md`

## Global Constraints

- No backend API changes.
- No R-031b cut media.
- Work on `main`; English commits; Chinese UI status strings only.
- TDD pure `plan-waveform` first.
- Avoid waveform↔viewer static import cycle: use `setWaveformPlanBridge`.
- `targetBins = clamp(round(total*2), 400, 2000)`.
- Plan hop must not call `loadWaveformForCurrentVideo`.

## File map

| File | Role |
| --- | --- |
| `plan-waveform.js` | New pure: slicePeaks, resamplePeaksMax, composePlanPeaks |
| `__tests__/plan-waveform.test.js` | New unit tests |
| `waveform.js` | Plan load/cache/bridge/scrub/playhead branch |
| `viewer.js` | Fill DOM, softUpdate, skip hop load, bridge, loadPlanWaveform trigger |
| `editor-plan.js` | Recompose on timeline edit |
| `style.css` | Fill, playhead cap, muted blocks |
| `ROADMAP.md` / `clio/ui/README.md` | Notes |

---

### Task 1: Pure plan-waveform (TDD)

**Files:** Create `clio/ui/static/src/plan-waveform.js`, `clio/ui/static/src/__tests__/plan-waveform.test.js`

**Interfaces:**
```js
export function slicePeaks(peaks, sourceDurationSec, planStart, planEnd) // → number[]
export function resamplePeaksMax(peaks, targetLen) // → number[]
export function composePlanPeaks(timeline, byVideoIndex, opts?) 
// → { peaks, total, targetBins, missingSegIndexes }
```

- [ ] **Step 1: Write failing tests** (see spec §8 cases: mid slice, clamp, resample, two-seg compose ~2:1, missing zeros, bins clamp 400–2000, zero-duration skip)

- [ ] **Step 2:** `npx vitest run clio/ui/static/src/__tests__/plan-waveform.test.js` → FAIL

- [ ] **Step 3: Implement plan-waveform.js**

```js
export function slicePeaks(peaks, sourceDurationSec, planStart, planEnd) {
  const arr = Array.isArray(peaks) ? peaks : [];
  const n = arr.length;
  const dur = Number(sourceDurationSec);
  if (!n || !(dur > 0)) return [];
  const s = Math.max(0, Number(planStart) || 0);
  const e = Math.max(s, Number(planEnd) || 0);
  const i0 = Math.min(n, Math.max(0, Math.floor((s / dur) * n)));
  const i1 = Math.min(n, Math.max(i0, Math.ceil((Math.min(e, dur) / dur) * n)));
  return arr.slice(i0, i1);
}

export function resamplePeaksMax(peaks, targetLen) {
  const t = Math.max(0, Number(targetLen) | 0);
  const arr = Array.isArray(peaks) ? peaks : [];
  if (t === 0) return [];
  if (!arr.length) return Array(t).fill(0);
  if (arr.length === t) return arr.slice();
  const out = new Array(t);
  for (let i = 0; i < t; i++) {
    const a = Math.floor((i / t) * arr.length);
    const b = Math.max(a + 1, Math.floor(((i + 1) / t) * arr.length));
    let m = 0;
    for (let j = a; j < b && j < arr.length; j++) m = Math.max(m, Number(arr[j]) || 0);
    out[i] = m;
  }
  return out;
}

export function composePlanPeaks(timeline, byVideoIndex, opts = {}) {
  const total = timeline?.total || 0;
  const segs = (timeline?.segments || []).filter((s) => s.duration > 0);
  let targetBins = opts.targetBins != null
    ? Number(opts.targetBins)
    : Math.round(total * 2);
  if (!Number.isFinite(targetBins)) targetBins = 400;
  targetBins = Math.max(400, Math.min(2000, targetBins | 0));
  if (!segs.length || total <= 0) {
    return { peaks: Array(targetBins).fill(0), total, targetBins, missingSegIndexes: [] };
  }
  // allocate bins proportional; fix sum to targetBins on last
  const bins = segs.map((s) => Math.max(1, Math.round((s.duration / total) * targetBins)));
  let sum = bins.reduce((a, b) => a + b, 0);
  bins[bins.length - 1] = Math.max(1, bins[bins.length - 1] + (targetBins - sum));
  // re-clamp if last went non-positive edge cases
  const peaks = [];
  const missingSegIndexes = [];
  segs.forEach((seg, k) => {
    const entry = byVideoIndex?.[seg.videoIndex];
    const need = bins[k];
    if (!entry || entry === 'pending' || !Array.isArray(entry.peaks)) {
      peaks.push(...Array(need).fill(0));
      missingSegIndexes.push(seg.segIndex);
      return;
    }
    const sliced = slicePeaks(entry.peaks, entry.duration_sec, seg.planStart, seg.planEnd);
    peaks.push(...resamplePeaksMax(sliced, need));
  });
  // length fix
  if (peaks.length > targetBins) return { peaks: peaks.slice(0, targetBins), total, targetBins, missingSegIndexes };
  while (peaks.length < targetBins) peaks.push(0);
  return { peaks, total, targetBins, missingSegIndexes };
}
```

- [ ] **Step 4:** tests PASS

- [ ] **Step 5: Commit** `feat(ui): add plan-waveform pure compose helpers (R-031a2)`

---

### Task 2: Waveform plan mode + bridge

**Files:** Modify `clio/ui/static/src/waveform.js`

- [ ] Module state: `_planBridge`, `_planCache` Map, `_planTotal`, `_planLoadToken`, `_composeMode` ('source'|'plan')

- [ ] `setWaveformPlanBridge(bridge)`, `getPlanWaveformTotal()`, `recomposePlanWaveformFromCache()`, `loadPlanWaveform()`, `isPlanWaveformMode()`

- [ ] `loadPlanWaveform`: unique indexes → fetch → cache → compose → setWaveformPeaks; poll pending

- [ ] `updateWaveformPlayhead` / scrub: if bridge.isPlan() use global ratio / seekGlobal(total)

- [ ] `loadWaveformForCurrentVideo`: set mode source; clear plan compose mode

- [ ] Export new functions

- [ ] Commit `feat(ui): plan composite waveform load and scrub bridge (R-031a2)`

---

### Task 3: Viewer chrome + hop skip + bridge

**Files:** `viewer.js`, `style.css`

- [ ] `renderPreviewBar`: insert `.preview-progress-fill`; mute active styles; playhead still present

- [ ] `softUpdatePreviewChrome(tl)` updates fill + playhead left only

- [ ] Call softUpdate from seek/timeupdate/scrub instead of full render when possible

- [ ] `_loadAndSeekSource`: if `isGlobalTimelineUi()` skip `loadWaveformForCurrentVideo`

- [ ] `setupPlayer`: register bridge; on plan render trigger `loadPlanWaveform`

- [ ] When entity leaves plan (renderPreviewBar hides / sidebar already stopPreview): ensure source waveform reload — call from `renderPreviewBar` when `!isPlan` once or export helper called from sidebar — simplest: in `renderPreviewBar` when transitioning off plan call loadWaveformForCurrentVideo. Use module flag `_wasPlanBar`.

- [ ] CSS for fill, playhead cap, muted blocks

- [ ] Commit `feat(ui): plan progress fill playhead and plan waveform wiring (R-031a2)`

---

### Task 4: Editor recompose + docs

**Files:** `editor-plan.js`, `ROADMAP.md`, `clio/ui/README.md`

- [ ] `_refreshPreviewTimeline`: also `recomposePlanWaveformFromCache()`

- [ ] ROADMAP note under R-031a polish done / a2

- [ ] README: composite waveform + progress chrome

- [ ] `npx vitest run clio/ui/static/src/__tests__`

- [ ] Commit `docs(ui): R-031a2 plan chrome and composite waveform notes`

---

## Spec coverage

| Spec | Task |
| --- | --- |
| Fill + playhead chrome | T3 |
| Soft-update | T3 |
| Skip single load on hop | T3 |
| plan-waveform pure | T1 |
| load/compose/poll | T2 |
| Bridge scrub | T2 |
| Leave plan restore | T3 |
| Editor recompose | T4 |
| Docs | T4 |
