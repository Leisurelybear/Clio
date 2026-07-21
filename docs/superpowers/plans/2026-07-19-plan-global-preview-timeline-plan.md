# Plan Global Preview Timeline (R-031 Phase A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On Plan entity, turn the player preview bar into a continuous global scrub timeline (Σ `use_timeline` durations) with composite clock and auto source-hop by global time; media stays source-video seeks (Phase B cut media later).

**Architecture:** Pure `plan-timeline.js` builds the composite axis and maps global ↔ plan-local seconds. `viewer.js` owns scrub/playhead/clock/hop using that module; `state.previewGlobalSec` is the UI playhead. Accordion follows `previewIndex` even when not in continuous play. No backend changes.

**Tech Stack:** Vanilla JS ES modules, Vitest (`npm test` / `npx vitest run`), existing `style.css` tokens, no new deps.

**Spec:** `docs/superpowers/specs/2026-07-19-plan-global-preview-timeline-design.md`

## Global Constraints

- No new npm/Python dependencies.
- Phase A: **source media only** — do not load cut clips or concat files.
- Do not change plan domain model, readiness, cut, export, or waveform peak format.
- Work on `main` (project preference).
- One feature per commit where practical; English commits; Chinese UI strings only.
- TDD pure timeline module before wiring DOM.
- Reuse `parseTimecode` / `fmtTime` from `utils.js` inside pure module only if tests can import them; **prefer local pure parse in `plan-timeline.js`** (copy the small logic) so unit tests need no DOM/`state` import chain. Mirror `parseTimecode` behavior from `utils.js`.
- Keep R-012 `!player.seeking` auto-advance guard.
- Keep R-030 focus-safe accordion resync on blur.

## File map

| File | Responsibility |
| --- | --- |
| `clio/ui/static/src/plan-timeline.js` | **New** pure: `buildTimeline`, `clampGlobal`, `globalToLocal`, `localToGlobal`, `nextPlayableSegIndex`, `segmentWidths` |
| `clio/ui/static/src/__tests__/plan-timeline.test.js` | **New** unit tests |
| `clio/ui/static/src/state.js` | Add `previewGlobalSec: 0` |
| `clio/ui/static/src/viewer.js` | Global scrub, playhead, composite clock, seekToGlobal, continuous advance |
| `clio/ui/static/style.css` | Relative bar + playhead line; scrub cursor |
| `clio/ui/static/index.html` | Optional playhead element inside `#preview-seg-bar` (or inject via JS) |
| `clio/ui/static/src/editor-plan.js` | After timeline field change, call `renderPreviewBar()`; ensure expand works when preview inactive (if expand only wired from viewer, viewer path is enough) |
| `ROADMAP.md` | R-031 Phase A/B split; mark A done when shipped |
| `clio/ui/README.md` | Global bar + composite clock; source hop; Phase B open |
| `docs/cli-reference.md` | Align serve blurb if still “composite is R-031” only |

---

### Task 1: Pure plan-timeline module (TDD)

**Files:**
- Create: `clio/ui/static/src/plan-timeline.js`
- Create: `clio/ui/static/src/__tests__/plan-timeline.test.js`

**Interfaces:**
- Consumes: none (no DOM, no `state`).
- Produces (all exported):

```js
/**
 * @typedef {{ segIndex: number, videoIndex: string, planStart: number, planEnd: number, duration: number, globalStart: number, globalEnd: number }} TimelineSeg
 * @typedef {{ segments: TimelineSeg[], total: number }} PlanTimeline
 */

/** @param {Array<{index?: string, use_timeline?: string}>} sequence */
export function buildTimeline(sequence) // → PlanTimeline

export function clampGlobal(timeline, globalSec) // → number

/**
 * @returns {{ segIndex: number, localSec: number, planSec: number, videoIndex: string } | null }
 * null only if no segments
 */
export function globalToLocal(timeline, globalSec)

/** localSec clamped to [0, duration]; empty/invalid segIndex → 0 */
export function localToGlobal(timeline, segIndex, localSec) // → number

/**
 * Next segment index with duration > 0 after fromIndex (exclusive).
 * If none, null. fromIndex = -1 means “first playable”.
 */
export function nextPlayableSegIndex(timeline, fromIndex)

/**
 * Width fractions 0..1 per segment for UI (sum ≈ 1).
 * Positive durations: duration/total.
 * All zero or empty total with n>0: equal 1/n.
 */
export function segmentWidths(timeline) // → number[]
```

**Parse rules (must match product):**
- Split `use_timeline` on first `-` that separates two timecodes; existing code uses `.split('-')` and takes `[0]`, `[1]` after trim — keep **same** as `viewer.js` today: `parts = (use_timeline||'').split('-')`, need `parts.length >= 2`, `parseTimecode` each.
- Local `parseTimecode` copy:

```js
function parseTimecode(s) {
  if (!s) return 0;
  const parts = String(s).split(':').map(parseFloat);
  if (parts.length === 3 && parts.every(Number.isFinite)) {
    return parts[0] * 3600 + parts[1] * 60 + parts[2];
  }
  if (parts.length === 2 && parts.every(Number.isFinite)) {
    return parts[0] * 60 + parts[1];
  }
  return parseFloat(s) || 0;
}
```

- `duration = max(0, planEnd - planStart)`; if parts missing → duration 0, planStart=planEnd=0.
- Half-open: segment i owns `[globalStart, globalEnd)`; last segment’s end is inclusive for clamp (globalSec >= total → end of last segment).

**`globalToLocal` algorithm:**
1. If no segments → null.
2. `t = clampGlobal(timeline, globalSec)`.
3. Find first seg where `t < seg.globalEnd` OR last seg if `t >= total`.
4. If chosen seg has `duration === 0`, walk forward with `nextPlayableSegIndex` to first positive; if none, stay on last seg with localSec=0.
5. `localSec = min(duration, max(0, t - globalStart))` for positive duration segs; `planSec = planStart + localSec`.

- [ ] **Step 1: Write the failing tests**

Create `clio/ui/static/src/__tests__/plan-timeline.test.js`:

```js
import { describe, it, expect } from 'vitest';
import {
  buildTimeline,
  clampGlobal,
  globalToLocal,
  localToGlobal,
  nextPlayableSegIndex,
  segmentWidths,
} from '../plan-timeline.js';

const seq3 = [
  { index: '001', use_timeline: '00:10-00:20' }, // 10s
  { index: '002', use_timeline: '01:00-01:05' }, // 5s
  { index: '003', use_timeline: '00:00-00:15' }, // 15s
];

describe('buildTimeline', () => {
  it('empty sequence', () => {
    const t = buildTimeline([]);
    expect(t.segments).toEqual([]);
    expect(t.total).toBe(0);
  });

  it('single segment', () => {
    const t = buildTimeline([{ index: '001', use_timeline: '00:00-00:30' }]);
    expect(t.total).toBe(30);
    expect(t.segments[0]).toMatchObject({
      segIndex: 0,
      videoIndex: '001',
      planStart: 0,
      planEnd: 30,
      duration: 30,
      globalStart: 0,
      globalEnd: 30,
    });
  });

  it('multi cumulative', () => {
    const t = buildTimeline(seq3);
    expect(t.total).toBe(30);
    expect(t.segments.map((s) => s.globalStart)).toEqual([0, 10, 15]);
    expect(t.segments.map((s) => s.globalEnd)).toEqual([10, 15, 30]);
  });

  it('invalid timeline → duration 0', () => {
    const t = buildTimeline([{ index: 'x', use_timeline: '' }]);
    expect(t.segments[0].duration).toBe(0);
    expect(t.total).toBe(0);
  });

  it('end < start → duration 0', () => {
    const t = buildTimeline([{ index: 'x', use_timeline: '00:40-00:10' }]);
    expect(t.segments[0].duration).toBe(0);
  });
});

describe('clampGlobal / maps', () => {
  it('clamp', () => {
    const t = buildTimeline(seq3);
    expect(clampGlobal(t, -5)).toBe(0);
    expect(clampGlobal(t, 100)).toBe(30);
    expect(clampGlobal(t, 12)).toBe(12);
  });

  it('globalToLocal mid second seg', () => {
    const t = buildTimeline(seq3);
    const loc = globalToLocal(t, 12);
    expect(loc.segIndex).toBe(1);
    expect(loc.localSec).toBe(2);
    expect(loc.planSec).toBe(62); // 01:00 + 2
    expect(loc.videoIndex).toBe('002');
  });

  it('t at boundary globalEnd maps to next start', () => {
    const t = buildTimeline(seq3);
    const loc = globalToLocal(t, 10);
    expect(loc.segIndex).toBe(1);
    expect(loc.localSec).toBe(0);
    expect(loc.planSec).toBe(60);
  });

  it('localToGlobal inverse', () => {
    const t = buildTimeline(seq3);
    expect(localToGlobal(t, 1, 2)).toBe(12);
    expect(localToGlobal(t, 0, 0)).toBe(0);
  });

  it('globalToLocal null on empty', () => {
    expect(globalToLocal(buildTimeline([]), 0)).toBeNull();
  });
});

describe('nextPlayableSegIndex / widths', () => {
  it('skips zero duration', () => {
    const t = buildTimeline([
      { index: 'a', use_timeline: '00:00-00:10' },
      { index: 'b', use_timeline: '' },
      { index: 'c', use_timeline: '00:00-00:05' },
    ]);
    expect(nextPlayableSegIndex(t, -1)).toBe(0);
    expect(nextPlayableSegIndex(t, 0)).toBe(2);
    expect(nextPlayableSegIndex(t, 2)).toBeNull();
  });

  it('widths proportional', () => {
    const t = buildTimeline(seq3);
    const w = segmentWidths(t);
    expect(w[0]).toBeCloseTo(10 / 30);
    expect(w[1]).toBeCloseTo(5 / 30);
    expect(w[2]).toBeCloseTo(15 / 30);
  });

  it('all zero → equal widths', () => {
    const t = buildTimeline([
      { index: 'a', use_timeline: '' },
      { index: 'b', use_timeline: '00:10-00:05' },
    ]);
    expect(segmentWidths(t)).toEqual([0.5, 0.5]);
  });
});
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
npx vitest run clio/ui/static/src/__tests__/plan-timeline.test.js
```

Expected: cannot find module or exports missing.

- [ ] **Step 3: Implement `plan-timeline.js`**

Create `clio/ui/static/src/plan-timeline.js` with full implementations of the interfaces above (no DOM). Keep functions pure and side-effect free.

Minimal skeleton:

```js
function parseTimecode(s) { /* as above */ }

function parseRange(useTimeline) {
  const parts = String(useTimeline || '').split('-');
  if (parts.length < 2) return { planStart: 0, planEnd: 0, duration: 0 };
  const planStart = parseTimecode(parts[0].trim());
  const planEnd = parseTimecode(parts[1].trim());
  const duration = Math.max(0, planEnd - planStart);
  return { planStart, planEnd, duration };
}

export function buildTimeline(sequence) {
  const segs = Array.isArray(sequence) ? sequence : [];
  const segments = [];
  let g = 0;
  for (let i = 0; i < segs.length; i++) {
    const { planStart, planEnd, duration } = parseRange(segs[i]?.use_timeline);
    const globalStart = g;
    const globalEnd = g + duration;
    segments.push({
      segIndex: i,
      videoIndex: String(segs[i]?.index ?? ''),
      planStart,
      planEnd,
      duration,
      globalStart,
      globalEnd,
    });
    g = globalEnd;
  }
  return { segments, total: g };
}

export function clampGlobal(timeline, globalSec) {
  const total = timeline?.total || 0;
  const t = Number(globalSec);
  if (!Number.isFinite(t) || t < 0) return 0;
  if (total <= 0) return 0;
  if (t > total) return total;
  return t;
}

export function nextPlayableSegIndex(timeline, fromIndex) {
  const segs = timeline?.segments || [];
  const start = (Number(fromIndex) | 0) + 1;
  for (let i = Math.max(0, start); i < segs.length; i++) {
    if (segs[i].duration > 0) return i;
  }
  return null;
}

export function globalToLocal(timeline, globalSec) {
  const segs = timeline?.segments || [];
  if (!segs.length) return null;
  const t = clampGlobal(timeline, globalSec);
  let idx = segs.length - 1;
  for (let i = 0; i < segs.length; i++) {
    if (t < segs[i].globalEnd || (i === segs.length - 1)) {
      // boundary: t === globalEnd of i and i not last → next
      if (t >= segs[i].globalEnd && i < segs.length - 1) continue;
      idx = i;
      // if t exactly at globalEnd of previous, loop continues; handle:
      break;
    }
  }
  // Prefer explicit: first i where t < globalEnd; else last
  idx = segs.length - 1;
  for (let i = 0; i < segs.length; i++) {
    if (t < segs[i].globalEnd) {
      idx = i;
      break;
    }
  }
  if (segs[idx].duration === 0) {
    const n = nextPlayableSegIndex(timeline, idx - 1);
    if (n != null) idx = n;
  }
  const seg = segs[idx];
  const localSec = seg.duration > 0
    ? Math.min(seg.duration, Math.max(0, t - seg.globalStart))
    : 0;
  return {
    segIndex: idx,
    localSec,
    planSec: seg.planStart + localSec,
    videoIndex: seg.videoIndex,
  };
}

export function localToGlobal(timeline, segIndex, localSec) {
  const seg = timeline?.segments?.[segIndex];
  if (!seg) return 0;
  const local = Number(localSec);
  const l = Number.isFinite(local) ? Math.min(seg.duration, Math.max(0, local)) : 0;
  return seg.globalStart + l;
}

export function segmentWidths(timeline) {
  const segs = timeline?.segments || [];
  const n = segs.length;
  if (!n) return [];
  const total = timeline.total || 0;
  if (total <= 0) return segs.map(() => 1 / n);
  return segs.map((s) => s.duration / total);
}
```

**Fix boundary carefully in real implementation:** for `t === 10` with seg0 `[0,10)`, seg1 `[10,15)`, result must be seg1 local 0. The loop `t < globalEnd` yields idx=1 when t=10. For `t === total` (30), all `t < globalEnd` fail → last seg, localSec = duration.

- [ ] **Step 4: Run tests — expect PASS**

```bash
npx vitest run clio/ui/static/src/__tests__/plan-timeline.test.js
```

- [ ] **Step 5: Commit**

```bash
git add clio/ui/static/src/plan-timeline.js clio/ui/static/src/__tests__/plan-timeline.test.js
git commit -m "$(cat <<'EOF'
feat(ui): add pure plan-timeline composite timebase (R-031a)

Unit-tested global↔local mapping for plan preview scrub axis.
EOF
)"
```

---

### Task 2: State + composite clock + seekToGlobal core

**Files:**
- Modify: `clio/ui/static/src/state.js` (preview fields ~33–36)
- Modify: `clio/ui/static/src/viewer.js`

**Interfaces:**
- Consumes: `buildTimeline`, `globalToLocal`, `localToGlobal`, `clampGlobal`, `nextPlayableSegIndex` from `./plan-timeline.js`
- Produces (internal + export if useful):
  - `isGlobalTimelineUi()` → boolean
  - `getPlanTimeline()` → PlanTimeline from `state.plan.sequence`
  - `seekToGlobal(globalSec, { play?: boolean })` — default `play` false; if player already playing, keep playing
  - `updateCompositeClock()` — sets `#player-time` when global UI on
  - Export `renderPreviewBar` still; export `seekToGlobal` only if editor needs it (optional)

- [ ] **Step 1: Add state field**

In `state.js` preview section:

```js
  previewActive: false,
  previewIndex: -1,
  previewGlobalSec: 0,
  _previewEndTime: null,
```

- [ ] **Step 2: Implement helpers in viewer.js**

Near top of `viewer.js` after imports:

```js
import {
  buildTimeline,
  clampGlobal,
  globalToLocal,
  localToGlobal,
  nextPlayableSegIndex,
  segmentWidths,
} from './plan-timeline.js';

function isGlobalTimelineUi() {
  return state.currentEntity === 'plan'
    && Array.isArray(state.plan?.sequence)
    && state.plan.sequence.length > 0;
}

function getPlanTimeline() {
  return buildTimeline(state.plan?.sequence || []);
}

function updateCompositeClock() {
  if (!isGlobalTimelineUi()) return;
  const tl = getPlanTimeline();
  const g = clampGlobal(tl, state.previewGlobalSec);
  const el = $('player-time');
  if (el) el.textContent = `成片 ${fmtTime(g)} / ${fmtTime(tl.total)}`;
}

/**
 * @param {number} globalSec
 * @param {{ play?: boolean, syncExpand?: boolean }} [opts]
 */
function seekToGlobal(globalSec, opts = {}) {
  const tl = getPlanTimeline();
  const loc = globalToLocal(tl, globalSec);
  if (!loc) return;
  const wasPlaying = !$('player')?.paused;
  const wantPlay = opts.play === true || (opts.play !== false && wasPlaying);

  state.previewIndex = loc.segIndex;
  state.previewGlobalSec = clampGlobal(tl, globalSec);

  const v = state.videos.find((x) => x.index === loc.videoIndex);
  if (!v) {
    setStatus(`跳过视频 [${loc.videoIndex}]，找不到对应文件`, 'warn');
    updateCompositeClock();
    if (opts.syncExpand !== false) _syncPlanExpandFromPreview();
    return;
  }
  const seekSec = loc.planSec + (v.offset_sec || 0);
  const seg = tl.segments[loc.segIndex];
  state._previewEndTime = seg
    ? seg.planEnd + (v.offset_sec || 0)
    : null;

  // playVideoSegment always calls play(); patch behavior:
  // temporarily use load+seek, then play only if wantPlay
  _loadAndSeekSource(v, seekSec, wantPlay);

  updateCompositeClock();
  renderPreviewBar();
  if (opts.syncExpand !== false) _syncPlanExpandFromPreview();
}

function _loadAndSeekSource(v, seekSec, wantPlay) {
  const player = $('player');
  const doSeek = () => {
    player.currentTime = seekSec;
    if (wantPlay) player.play().catch(() => {});
    else player.pause();
  };
  state.currentVideo = v.file;
  $('player-name').textContent = v.file;
  const same =
    player.src
    && player.src.includes(encodeURIComponent(v.file))
    && player.readyState >= 1;
  if (same) {
    doSeek();
  } else {
    player.onloadedmetadata = () => {
      doSeek();
      if (!isGlobalTimelineUi()) {
        $('player-time').textContent = `${fmtTime(0)} / ${fmtTime(player.duration)}`;
      }
    };
    const projParam = state.currentProjectName
      ? `&project=${encodeURIComponent(state.currentProjectName)}` : '';
    const tokenParam = sessionStorage.getItem('api_token');
    const extraParam = tokenParam ? `&token=${encodeURIComponent(tokenParam)}` : '';
    const absParam = v?.abs_path ? `&abspath=${encodeURIComponent(v.abs_path)}` : '';
    player.src = `/api/video?file=${encodeURIComponent(v.file)}&source=${state.source}${absParam}${projParam}${extraParam}`;
  }
  import('./waveform.js').then((m) => {
    if (typeof m.loadWaveformForCurrentVideo === 'function') {
      // existing import path: loadWaveformForCurrentVideo already imported at top
    }
  });
  // Prefer calling already-imported loadWaveformForCurrentVideo()
  loadWaveformForCurrentVideo();
}
```

**Important:** Refactor `playVideoSegment` to call `_loadAndSeekSource(v, seekTo, true)` to avoid duplication, or leave `playVideoSegment` as-is and only use `_loadAndSeekSource` for global seek. Prefer **refactor playVideoSegment** to share load path.

- [ ] **Step 3: Composite clock on timeupdate when global UI**

In `setupPlayer` → `player.ontimeupdate`, after waveform update:

```js
if (isGlobalTimelineUi() && state.previewIndex >= 0) {
  const tl = getPlanTimeline();
  const seg = tl.segments[state.previewIndex];
  const v = state.videos.find((x) => x.index === seg?.videoIndex);
  const offset = v?.offset_sec || 0;
  if (seg && seg.duration > 0) {
    const planSec = Math.max(0, player.currentTime - offset);
    const local = Math.min(seg.duration, Math.max(0, planSec - seg.planStart));
    state.previewGlobalSec = localToGlobal(tl, state.previewIndex, local);
  }
  updateCompositeClock();
} else {
  $('player-time').textContent = `${fmtTime(player.currentTime)} / ${fmtTime(player.duration)}`;
}
```

Keep existing auto-advance block, but when advancing:

```js
if (state.previewActive && !player.seeking && state._previewEndTime !== null
    && player.currentTime >= state._previewEndTime) {
  const tl = getPlanTimeline();
  const next = nextPlayableSegIndex(tl, state.previewIndex);
  if (next == null) {
    stopPreview();
    setStatus('预览播放完毕', 'ok');
    return;
  }
  const g = tl.segments[next].globalStart;
  state.previewActive = true;
  seekToGlobal(g, { play: true });
  return;
}
```

Similarly `player.onended` → same next-playable logic.

- [ ] **Step 4: `_syncPlanExpandFromPreview` when previewIndex set without previewActive**

Today it returns early if `!state.previewActive`. Change to:

```js
function _syncPlanExpandFromPreview() {
  if (state.previewIndex < 0) return;
  // remove: if (!state.previewActive || state.previewIndex < 0) return;
  // keep focus-safe logic as-is
  ...
}
```

Callers that only want expand during preview still work; scrub will now expand too.

- [ ] **Step 5: Smoke unit (optional)** — state field exists; no new test required if pure tests cover mapping. Run:

```bash
npx vitest run clio/ui/static/src/__tests__/plan-timeline.test.js clio/ui/static/src/__tests__/plan-edit.test.js
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add clio/ui/static/src/state.js clio/ui/static/src/viewer.js
git commit -m "$(cat <<'EOF'
feat(ui): seekToGlobal and composite clock for plan preview (R-031a)

Wire plan-timeline into viewer; expand accordion on previewIndex without requiring previewActive.
EOF
)"
```

---

### Task 3: Global scrub bar + playhead UI

**Files:**
- Modify: `clio/ui/static/src/viewer.js` — `renderPreviewBar`, `_setupPreviewBarDrag`
- Modify: `clio/ui/static/style.css` (~858–882)
- Optionally: `clio/ui/static/index.html` if adding static playhead node

**Interfaces:**
- Consumes: `segmentWidths`, `getPlanTimeline`, `seekToGlobal`, `state.previewGlobalSec`
- Produces: scrub maps x → globalSec; playhead DOM position

- [ ] **Step 1: CSS playhead**

Update `.preview-seg-bar` to `position: relative` and add:

```css
.preview-seg-bar {
  /* existing props */
  position: relative;
  cursor: ew-resize;
}
.preview-playhead {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 2px;
  margin-left: -1px;
  background: var(--accent);
  box-shadow: 0 0 4px var(--accent-glow, rgba(96, 165, 250, 0.6));
  pointer-events: none;
  z-index: 2;
}
```

- [ ] **Step 2: Rewrite renderPreviewBar widths + playhead**

```js
function renderPreviewBar() {
  const bar = $('preview-bar');
  if (!bar) return;
  const isPlan = state.currentEntity === 'plan';
  bar.style.display = isPlan ? 'flex' : 'none';
  if (!isPlan) return;
  const p = state.plan;
  const segBar = $('preview-seg-bar');
  if (!segBar) return;

  if (!p || !p.sequence || !p.sequence.length) {
    segBar.innerHTML = '<span class="muted">暂无可预览内容</span>';
    return;
  }

  const tl = buildTimeline(p.sequence);
  const widths = segmentWidths(tl);
  const segHtml = p.sequence.map((seg, i) => {
    const w = (widths[i] || 0) * 100;
    const cls = state.previewIndex < 0
      ? 'pending'
      : i < state.previewIndex
        ? 'done'
        : i === state.previewIndex
          ? 'active'
          : 'pending';
    const tooltip = `${seg.title || ''} [${seg.use_timeline || ''}]`.trim();
    return `<div class="preview-seg-block ${cls}" data-seg="${i}" style="width:${w}%" title="${escapeHtml(tooltip)}"><span class="preview-seg-label">${i + 1}</span></div>`;
  }).join('');

  const pct = tl.total > 0
    ? (clampGlobal(tl, state.previewGlobalSec) / tl.total) * 100
    : 0;
  segBar.innerHTML = `${segHtml}<div class="preview-playhead" id="preview-playhead" style="left:${pct}%"></div>`;

  // Click block → segment globalStart (does not force play)
  segBar.querySelectorAll('.preview-seg-block').forEach((el) => {
    el.onclick = (e) => {
      e.stopPropagation();
      const i = parseInt(el.dataset.seg, 10);
      if (!Number.isFinite(i) || i < 0 || i >= p.sequence.length) return;
      const g = tl.segments[i].globalStart;
      seekToGlobal(g, { play: false });
    };
  });

  if (isGlobalTimelineUi()) updateCompositeClock();
}
```

Note: **active** class no longer requires `previewActive` — current segment is highlighted whenever `previewIndex` matches.

- [ ] **Step 3: Replace drag with global scrub**

Replace `_setupPreviewBarDrag` / `_dragTargetSeg` with:

```js
let _scrubbing = false;
let _lastSeekTs = 0;

function _setupPreviewBarDrag() {
  const segBar = $('preview-seg-bar');
  if (!segBar) return;

  const globalFromEvent = (e) => {
    const p = state.plan;
    if (!p?.sequence?.length) return null;
    const tl = buildTimeline(p.sequence);
    if (tl.total <= 0) return { tl, g: 0 };
    const rect = segBar.getBoundingClientRect();
    if (rect.width <= 0) return { tl, g: 0 };
    const pct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    return { tl, g: pct * tl.total };
  };

  const onMove = (e) => {
    if (!_scrubbing) return;
    const hit = globalFromEvent(e);
    if (!hit) return;
    state.previewGlobalSec = hit.g;
    // update playhead only for responsiveness
    const ph = $('preview-playhead');
    if (ph && hit.tl.total > 0) {
      ph.style.left = `${(hit.g / hit.tl.total) * 100}%`;
    }
    updateCompositeClock();
    const now = performance.now();
    if (now - _lastSeekTs >= 50) {
      _lastSeekTs = now;
      seekToGlobal(hit.g, { play: false, syncExpand: false });
    }
  };

  const onUp = (e) => {
    if (!_scrubbing) return;
    _scrubbing = false;
    document.removeEventListener('mousemove', onMove);
    document.removeEventListener('mouseup', onUp);
    const hit = globalFromEvent(e);
    if (hit) seekToGlobal(hit.g, { play: false, syncExpand: true });
  };

  segBar.onmousedown = (e) => {
    if (e.button !== 0) return;
    // ignore if only clicking a block? still scrub — block click also fires;
    // use mousedown scrub; block onclick may double-seek same place — OK
    _scrubbing = true;
    _lastSeekTs = 0;
    onMove(e);
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
    e.preventDefault();
  };
}
```

**Click vs drag:** block `onclick` after drag may fire — acceptable double seek. Optional: if movement > 4px, suppress click via flag.

- [ ] **Step 4: Prev/Next/Play use global**

```js
// prev
prevBtn.onclick = () => {
  const tl = getPlanTimeline();
  if (!tl.segments.length) return;
  let i = state.previewIndex;
  if (i < 0) i = 0;
  // jump to previous playable start, or current start if mid-segment > 0.5s into local
  const cur = tl.segments[i];
  const local = state.previewGlobalSec - (cur?.globalStart || 0);
  if (local > 0.5) {
    seekToGlobal(cur.globalStart, { play: state.previewActive });
    return;
  }
  let p = i - 1;
  while (p >= 0 && tl.segments[p].duration <= 0) p--;
  if (p < 0) p = 0;
  seekToGlobal(tl.segments[p].globalStart, { play: state.previewActive });
};

// next
nextBtn.onclick = () => {
  const tl = getPlanTimeline();
  const n = nextPlayableSegIndex(tl, state.previewIndex < 0 ? -1 : state.previewIndex);
  if (n == null) return;
  seekToGlobal(tl.segments[n].globalStart, { play: state.previewActive });
};
```

**startPreview(startIndex):**

```js
function startPreview(startIndex) {
  const p = state.plan;
  if (!p?.sequence?.length) return;
  state.previewActive = true;
  const tl = buildTimeline(p.sequence);
  let idx = typeof startIndex === 'number' ? startIndex : 0;
  if (tl.segments[idx]?.duration <= 0) {
    const n = nextPlayableSegIndex(tl, idx - 1);
    idx = n == null ? 0 : n;
  }
  const g = tl.segments[idx]?.globalStart ?? 0;
  // UI bits (status, expand) keep existing pattern...
  seekToGlobal(g, { play: true });
  _setPlayBtnPause();
  // accordion + renderPlan same as today
}
```

**`_playPreviewSegment`:** reimplement as thin wrapper:

```js
function _playPreviewSegment() {
  if (!state.previewActive) {
    // still allow positioning
  }
  const tl = getPlanTimeline();
  if (!tl.segments.length || state.previewIndex >= tl.segments.length) {
    stopPreview();
    setStatus('预览播放完毕', 'ok');
    return;
  }
  if (tl.segments[state.previewIndex].duration <= 0) {
    const n = nextPlayableSegIndex(tl, state.previewIndex);
    if (n == null) {
      stopPreview();
      return;
    }
    state.previewIndex = n;
  }
  seekToGlobal(tl.segments[state.previewIndex].globalStart, {
    play: state.previewActive,
  });
}
```

- [ ] **Step 5: Manual check list** (document in commit body)

1. Plan tab, drag bar mid-segment → clock composite, video seeks mid-range.  
2. Drag across two indexes → media switches.  
3. Play across boundary → auto next.  
4. Pause + drag → stays paused.  
5. Click block → segment start.  

- [ ] **Step 6: Commit**

```bash
git add clio/ui/static/src/viewer.js clio/ui/static/style.css clio/ui/static/index.html
git commit -m "$(cat <<'EOF'
feat(ui): global scrub playhead on plan preview bar (R-031a)

Map bar x to composite seconds; segment blocks jump to globalStart.
EOF
)"
```

---

### Task 4: Timeline edit refresh + docs

**Files:**
- Modify: `clio/ui/static/src/editor-plan.js` — after `use_timeline` / 起点/终点 patches that call `renderPlan`, also `import('./viewer.js').then(m => m.renderPreviewBar())` if not already
- Modify: `ROADMAP.md` R-031 section
- Modify: `clio/ui/README.md` (preview note ~152)
- Modify: `docs/cli-reference.md` serve blurb ~312

- [ ] **Step 1: Ensure bar rebuilds after plan edits**

Search `editor-plan.js` for `use_timeline` / `setTimelineBound` / markDirty paths. After mutating sequence timeline, call:

```js
import('./viewer.js').then((m) => {
  if (typeof m.renderPreviewBar === 'function') m.renderPreviewBar();
}).catch(() => {});
```

If `renderPlan` already triggers something that refreshes the bar, skip duplicate. Grep `renderPreviewBar` from editor-plan first.

Also clamp `previewGlobalSec` when total shrinks:

```js
import { buildTimeline, clampGlobal } from './plan-timeline.js';
// after sequence change:
const tl = buildTimeline(state.plan.sequence);
state.previewGlobalSec = clampGlobal(tl, state.previewGlobalSec);
```

- [ ] **Step 2: ROADMAP**

Replace open R-031 blurb with Phase split:

```markdown
| R-031a | Plan global preview timeline (scrub + composite clock, source media) | Medium | High |
| R-031b | Prefer cut/composite media on that timeline | Medium | Medium |
```

Mark **R-031a Done** when this work ships; keep R-031b open with pointer to Phase B in the design doc.

- [ ] **Step 3: README + cli-reference**

`clio/ui/README.md` — replace “源视频片段 hop / R-031” with:

```markdown
- Plan 页签：预览条为**成片全局时间轴**（Σ use_timeline），可拖动；时钟显示成片时间；媒体仍为源视频 seek hop。Cut/合成片优先见 ROADMAP **R-031b**。
```

`docs/cli-reference.md` serve blurb — similar one-liner.

- [ ] **Step 4: Run full frontend unit suite**

```bash
npx vitest run clio/ui/static/src/__tests__
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add clio/ui/static/src/editor-plan.js ROADMAP.md clio/ui/README.md docs/cli-reference.md
git commit -m "$(cat <<'EOF'
docs(ui): ship R-031a global plan timeline notes

Refresh preview bar after plan timeline edits; split R-031a/b in ROADMAP.
EOF
)"
```

---

### Task 5: Verification gate

**Files:** none new

- [ ] **Step 1: Automated**

```bash
npx vitest run clio/ui/static/src/__tests__/plan-timeline.test.js clio/ui/static/src/__tests__/plan-edit.test.js
npx vitest run clio/ui/static/src/__tests__
```

- [ ] **Step 2: Manual golden path** (or `/verify` / `/run` if available)

1. Open project with multi-segment plan spanning ≥2 video indexes.  
2. Open 编排 (Plan).  
3. Confirm bar visible; clock shows `成片 … / …` after first scrub or play.  
4. Drag slowly within one segment — no spurious full reloads every pixel (throttle).  
5. Drag across boundary — source file name changes.  
6. Press play — crosses segments.  
7. Edit a segment duration — bar width/total updates.  
8. 起点/终点 still write correct plan times with offset.  
9. Switch to 设置/视频 — bar hides; clock not stuck with only 成片 if not plan (source clock restores on timeupdate).

- [ ] **Step 3: Final commit only if verification fixes needed**; otherwise done.

---

## Spec coverage checklist

| Spec requirement | Task |
| --- | --- |
| Pure timeline module + unit tests | T1 |
| Σ use_timeline axis | T1 |
| globalToLocal / localToGlobal / clamp / skip zero | T1 |
| segmentWidths equal fallback | T1 |
| previewGlobalSec state | T2 |
| seekToGlobal + offset_sec | T2 |
| Composite clock | T2 |
| Accordion without previewActive | T2 |
| Auto-advance next playable | T2 |
| Global scrub + throttle | T3 |
| Playhead chrome | T3 |
| Click block → globalStart | T3 |
| Prev/Next global | T3 |
| startPreview via global | T3 |
| Rebuild after timeline edit | T4 |
| ROADMAP Phase A/B + README | T4 |
| Manual verification | T5 |
| Phase B cut media | **Out of scope** (no task) |
| Native video controls hide | Spec soft; T5 notes “use bar”; optional CSS not required if cost high |

## Self-review notes

- No TBD placeholders.
- Signatures consistent: `seekToGlobal(globalSec, { play, syncExpand })`.
- `playVideoSegment` must not fight pause policy — Task 2 shares `_loadAndSeekSource`.
- Boundary `t === globalEnd` covered in T1 tests.

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-19-plan-global-preview-timeline-plan.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks  
2. **Inline Execution** — this session with executing-plans and checkpoints  

Which approach?
