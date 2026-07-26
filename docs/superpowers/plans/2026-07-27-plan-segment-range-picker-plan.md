# Plan Segment Range Picker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users set each plan segment’s `use_timeline` by opening a modal with an independent source-video player and a dual-handle range selector.

**Architecture:** Pure selection/timebase helpers live in `plan-edit.js` (unit-tested). A new `plan-range-picker.js` owns modal open/close, independent `<video>`, dual-handle pointer drag, and seek-to-handle. `editor-plan.js` only adds a **选区** button and applies the resulting `use_timeline` into plan state (dirty + preview bar refresh). No new npm deps; main composite player is never rewritten by the picker.

**Tech Stack:** Vanilla ES modules, Vitest, existing `/api/video` Range streaming, existing modal CSS tokens.

**Spec:** `docs/superpowers/specs/2026-07-27-plan-segment-range-picker-design.md`

## Global Constraints

- No third-party range/timeline libraries.
- Modal player must **not** set `state.currentVideo`.
- Opening the modal must **not** rewrite `state.previewGlobalSec` / `state.previewIndex`.
- `use_timeline` stays plan-local; file time uses `+ offset_sec` / `planSecFromPlayer` symmetrically with `viewer.js`.
- Min selection span: **1 second** (if `duration < 1`, allow full `[0, duration]`).
- Default empty selection: `0 … min(5, duration)`.
- Floor seconds when formatting (`formatTimelineSec`), same as today.
- Chinese UI copy: button **选区**, actions **取消** / **应用**.

---

### Task 1: Pure range helpers + unit tests

**Files:**
- Modify: `clio/ui/static/src/plan-edit.js`
- Modify: `clio/ui/static/src/__tests__/plan-edit.test.js`

**Interfaces:**
- Consumes: existing `formatTimelineSec`, `planSecFromPlayer`, private `parseTimelineParts` / `timecodeToSec` (export or reuse via new public helpers)
- Produces:
  - `parseUseTimeline(range: string) → { startSec: number, endSec: number } | null`
  - `fileSecFromPlan(planSec: number, offsetSec?: number) → number`
  - `clampFileSelection({ startSec, endSec, duration, minSpan?: number }) → { startSec, endSec }`
  - `selectionFromUseTimeline(useTimeline: string, duration: number, offsetSec?: number) → { startSec, endSec }` (file seconds; applies default if parse fails)
  - `useTimelineFromFileSelection(startSec: number, endSec: number, offsetSec?: number) → string`

- [ ] **Step 1: Write the failing tests**

Append to `plan-edit.test.js` imports and a new `describe` block:

```js
import {
  // ...existing
  parseUseTimeline,
  fileSecFromPlan,
  clampFileSelection,
  selectionFromUseTimeline,
  useTimelineFromFileSelection,
} from '../plan-edit.js';

describe('range picker helpers', () => {
  it('parseUseTimeline reads mm:ss-mm:ss', () => {
    expect(parseUseTimeline('00:10-00:40')).toEqual({ startSec: 10, endSec: 40 });
    expect(parseUseTimeline('')).toBeNull();
    expect(parseUseTimeline('nope')).toBeNull();
    expect(parseUseTimeline('00:10')).toBeNull();
  });

  it('fileSecFromPlan adds positive offset only', () => {
    expect(fileSecFromPlan(15, 40)).toBe(55);
    expect(fileSecFromPlan(15, 0)).toBe(15);
    expect(fileSecFromPlan(15, -5)).toBe(15);
  });

  it('clampFileSelection enforces min span and duration', () => {
    expect(clampFileSelection({ startSec: 10, endSec: 40, duration: 100 }))
      .toEqual({ startSec: 10, endSec: 40 });
    expect(clampFileSelection({ startSec: -5, endSec: 200, duration: 50 }))
      .toEqual({ startSec: 0, endSec: 50 });
    expect(clampFileSelection({ startSec: 20, endSec: 20.5, duration: 100, minSpan: 1 }))
      .toEqual({ startSec: 20, endSec: 21 });
    expect(clampFileSelection({ startSec: 0, endSec: 0.2, duration: 0.5, minSpan: 1 }))
      .toEqual({ startSec: 0, endSec: 0.5 });
  });

  it('selectionFromUseTimeline maps plan→file and defaults empty', () => {
    expect(selectionFromUseTimeline('00:10-00:40', 100, 0))
      .toEqual({ startSec: 10, endSec: 40 });
    expect(selectionFromUseTimeline('00:10-00:40', 200, 40))
      .toEqual({ startSec: 50, endSec: 80 });
    expect(selectionFromUseTimeline('', 100, 0))
      .toEqual({ startSec: 0, endSec: 5 });
    expect(selectionFromUseTimeline('bad', 3, 0))
      .toEqual({ startSec: 0, endSec: 3 });
  });

  it('useTimelineFromFileSelection maps file→plan', () => {
    expect(useTimelineFromFileSelection(55, 80, 40)).toBe('00:15-00:40');
    expect(useTimelineFromFileSelection(10, 25, 0)).toBe('00:10-00:25');
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
npx vitest run clio/ui/static/src/__tests__/plan-edit.test.js
```

Expected: FAIL — `parseUseTimeline` / other exports not defined.

- [ ] **Step 3: Implement helpers in `plan-edit.js`**

Add after `planSecFromPlayer` (keep existing private `parseTimelineParts` / `timecodeToSec`):

```js
/** @returns {{ startSec: number, endSec: number } | null} */
export function parseUseTimeline(range) {
  const parts = parseTimelineParts(range);
  if (!parts) return null;
  const startSec = timecodeToSec(parts.start);
  const endSec = timecodeToSec(parts.end);
  if (startSec == null || endSec == null) return null;
  return { startSec, endSec };
}

/** Plan-local seconds → source file seconds (preview seek direction). */
export function fileSecFromPlan(planSec, offsetSec = 0) {
  const t = Number(planSec);
  if (!Number.isFinite(t)) return 0;
  const off = Number(offsetSec);
  const o = Number.isFinite(off) && off > 0 ? off : 0;
  return Math.max(0, t + o);
}

/**
 * Clamp a file-time selection into [0, duration] with minSpan.
 * If duration < minSpan, return full [0, duration].
 */
export function clampFileSelection({ startSec, endSec, duration, minSpan = 1 }) {
  const dur = Number(duration);
  const d = Number.isFinite(dur) && dur > 0 ? dur : 0;
  let start = Number(startSec);
  let end = Number(endSec);
  if (!Number.isFinite(start)) start = 0;
  if (!Number.isFinite(end)) end = start;
  start = Math.max(0, Math.min(start, d));
  end = Math.max(0, Math.min(end, d));
  if (end < start) {
    const tmp = start;
    start = end;
    end = tmp;
  }
  const span = Number(minSpan);
  const min = Number.isFinite(span) && span > 0 ? span : 1;
  if (d <= 0) return { startSec: 0, endSec: 0 };
  if (d < min) return { startSec: 0, endSec: d };
  if (end - start < min) {
    if (start + min <= d) end = start + min;
    else {
      end = d;
      start = Math.max(0, end - min);
    }
  }
  return { startSec: start, endSec: end };
}

/**
 * Build file-time selection from plan use_timeline + duration.
 * Empty/invalid → default 0..min(5, duration), then clamp.
 */
export function selectionFromUseTimeline(useTimeline, duration, offsetSec = 0) {
  const dur = Number(duration);
  const d = Number.isFinite(dur) && dur > 0 ? dur : 0;
  const parsed = parseUseTimeline(useTimeline);
  let start;
  let end;
  if (parsed) {
    start = fileSecFromPlan(parsed.startSec, offsetSec);
    end = fileSecFromPlan(parsed.endSec, offsetSec);
  } else {
    start = 0;
    end = Math.min(5, d);
  }
  return clampFileSelection({ startSec: start, endSec: end, duration: d, minSpan: 1 });
}

/** File-time selection → plan-local use_timeline string. */
export function useTimelineFromFileSelection(startSec, endSec, offsetSec = 0) {
  const startPlan = planSecFromPlayer(startSec, offsetSec);
  const endPlan = planSecFromPlayer(endSec, offsetSec);
  const s = startPlan == null ? 0 : startPlan;
  const e = endPlan == null ? s : endPlan;
  const lo = Math.min(s, e);
  const hi = Math.max(s, e);
  return `${formatTimelineSec(lo)}-${formatTimelineSec(hi)}`;
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
npx vitest run clio/ui/static/src/__tests__/plan-edit.test.js
```

Expected: all tests PASS (existing + new).

- [ ] **Step 5: Commit**

```bash
git add clio/ui/static/src/plan-edit.js clio/ui/static/src/__tests__/plan-edit.test.js
git commit -m "$(cat <<'EOF'
feat(plan): add range-picker pure timebase helpers

Parse/clamp/format use_timeline selections in file vs plan seconds
for the dual-handle segment picker.
EOF
)"
```

---

### Task 2: Modal shell + CSS + dual-handle picker module

**Files:**
- Modify: `clio/ui/static/index.html` (add `#modal-plan-range` after `#modal-plan-insert`)
- Modify: `clio/ui/static/style.css` (range picker styles near `.plan-insert-*`)
- Create: `clio/ui/static/src/plan-range-picker.js`

**Interfaces:**
- Consumes: `parseUseTimeline` not required at open (uses `selectionFromUseTimeline`, `useTimelineFromFileSelection`, `clampFileSelection`, `formatTimelineSec` from `plan-edit.js`); `$`, `escapeHtml` from `utils.js`; `state` for `source` / `currentProjectName` only when building video URL
- Produces:
  - `openPlanRangePicker(opts: { segIndex: number, video: { file, abs_path?, offset_sec?, index?, title? }, useTimeline: string, title?: string, onApply: (payload: { segIndex: number, use_timeline: string }) => void }) → void`
  - `closePlanRangePicker() → void`

- [ ] **Step 1: Add modal HTML**

Insert before the relink modal (after plan-insert is fine):

```html
<!-- Plan range: dual-handle use_timeline on source video -->
<div id="modal-plan-range" class="modal" style="display:none;">
  <div class="modal-backdrop"></div>
  <div class="modal-dialog modal-dialog-wide">
    <h3 id="plan-range-title">选区</h3>
    <p id="plan-range-error" class="err" style="display:none;"></p>
    <video id="plan-range-video" class="plan-range-video" controls playsinline preload="metadata"></video>
    <div class="plan-range-times">
      <span id="plan-range-start-label">00:00</span>
      <span class="muted">–</span>
      <span id="plan-range-end-label">00:00</span>
      <span id="plan-range-dur-label" class="muted"></span>
    </div>
    <div id="plan-range-track" class="plan-range-track" aria-label="选区时间轴">
      <div id="plan-range-fill" class="plan-range-fill"></div>
      <button type="button" id="plan-range-handle-start" class="plan-range-handle" data- whic h="start" aria-label="起点"></button>
      <button type="button" id="plan-range-handle-end" class="plan-range-handle" data-which="end" aria-label="终点"></button>
    </div>
    <div class="modal-actions">
      <button id="plan-range-cancel" class="btn-secondary" type="button">取消</button>
      <button id="plan-range-apply" class="btn-primary" type="button">应用</button>
    </div>
  </div>
</div>
```

**Fix typo when implementing:** use `data-which="start"` (not `data- whic h`). Correct handle markup:

```html
<button type="button" id="plan-range-handle-start" class="plan-range-handle" data-which="start" aria-label="起点"></button>
<button type="button" id="plan-range-handle-end" class="plan-range-handle" data-which="end" aria-label="终点"></button>
```

- [ ] **Step 2: Add CSS**

Append near plan-insert styles:

```css
.plan-range-video {
  display: block;
  width: 100%;
  max-height: 50vh;
  background: #000;
  border-radius: var(--radius-md);
  margin: var(--space-3) 0;
}
.plan-range-times {
  display: flex;
  align-items: center;
  gap: 6px;
  font-variant-numeric: tabular-nums;
  font-size: var(--text-sm);
  margin-bottom: var(--space-2);
}
.plan-range-track {
  position: relative;
  height: 28px;
  margin: 8px 0 4px;
  border-radius: var(--radius-sm);
  background: var(--bg-surface-2);
  border: 1px solid var(--border);
  touch-action: none;
  user-select: none;
}
.plan-range-fill {
  position: absolute;
  top: 4px;
  bottom: 4px;
  left: 0;
  width: 0;
  background: var(--accent-bg, rgba(59, 130, 246, 0.35));
  border: 1px solid var(--accent);
  border-radius: 2px;
  pointer-events: none;
}
.plan-range-handle {
  position: absolute;
  top: 2px;
  bottom: 2px;
  width: 12px;
  margin-left: -6px;
  padding: 0;
  border: 1px solid var(--accent);
  border-radius: 3px;
  background: var(--bg-surface);
  cursor: ew-resize;
  z-index: 1;
}
.plan-range-handle:hover,
.plan-range-handle:focus-visible {
  background: var(--accent-bg);
  outline: none;
}
.plan-range-handle:focus-visible {
  box-shadow: 0 0 0 2px var(--border-focus);
}
```

- [ ] **Step 3: Implement `plan-range-picker.js`**

Create the module with this shape (full logic required — do not leave stubs):

```js
import { state } from './state.js';
import { $ } from './utils.js';
import {
  formatTimelineSec,
  selectionFromUseTimeline,
  useTimelineFromFileSelection,
  clampFileSelection,
} from './plan-edit.js';

let _bound = false;
let _segIndex = -1;
let _offsetSec = 0;
let _duration = 0;
let _startSec = 0;
let _endSec = 0;
let _onApply = null;
let _dragWhich = null; // 'start' | 'end' | null

function videoUrlFor(v) {
  const projParam = state.currentProjectName
    ? `&project=${encodeURIComponent(state.currentProjectName)}` : '';
  const tokenParam = sessionStorage.getItem('api_token');
  const extraParam = tokenParam ? `&token=${encodeURIComponent(tokenParam)}` : '';
  const absParam = v?.abs_path ? `&abspath=${encodeURIComponent(v.abs_path)}` : '';
  const source = state.source || 'compressed';
  return `/api/video?file=${encodeURIComponent(v.file)}&source=${source}${absParam}${projParam}${extraParam}`;
}

function ensureBound() {
  if (_bound) return;
  _bound = true;
  const modal = $('modal-plan-range');
  modal?.querySelector('.modal-backdrop')?.addEventListener('click', closePlanRangePicker);
  $('plan-range-cancel')?.addEventListener('click', closePlanRangePicker);
  $('plan-range-apply')?.addEventListener('click', applySelection);
  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape') return;
    if ($('modal-plan-range')?.style.display !== 'flex') return;
    closePlanRangePicker();
  });

  const track = $('plan-range-track');
  const onMove = (e) => {
    if (!_dragWhich || !track) return;
    const rect = track.getBoundingClientRect();
    if (rect.width <= 0) return;
    const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    const sec = ratio * _duration;
    if (_dragWhich === 'start') {
      const next = clampFileSelection({
        startSec: sec,
        endSec: _endSec,
        duration: _duration,
        minSpan: 1,
      });
      // Keep end fixed when possible: re-clamp start only
      _startSec = Math.min(next.startSec, _endSec);
      const fixed = clampFileSelection({
        startSec: _startSec,
        endSec: _endSec,
        duration: _duration,
        minSpan: 1,
      });
      _startSec = fixed.startSec;
      _endSec = fixed.endSec;
    } else {
      const fixed = clampFileSelection({
        startSec: _startSec,
        endSec: sec,
        duration: _duration,
        minSpan: 1,
      });
      _startSec = fixed.startSec;
      _endSec = fixed.endSec;
    }
    paintHandles();
    seekToHandle(_dragWhich);
  };
  const onUp = () => {
    if (!_dragWhich) return;
    _dragWhich = null;
    document.removeEventListener('pointermove', onMove);
    document.removeEventListener('pointerup', onUp);
  };
  ['plan-range-handle-start', 'plan-range-handle-end'].forEach((id) => {
    $(id)?.addEventListener('pointerdown', (e) => {
      e.preventDefault();
      e.stopPropagation();
      _dragWhich = $(id).dataset.which === 'end' ? 'end' : 'start';
      try { e.currentTarget.setPointerCapture?.(e.pointerId); } catch { /* ignore */ }
      document.addEventListener('pointermove', onMove);
      document.addEventListener('pointerup', onUp);
      seekToHandle(_dragWhich);
    });
  });
  // Optional: click on track moves nearest handle — nice-to-have, not required by spec.
}

function paintHandles() {
  const fill = $('plan-range-fill');
  const hs = $('plan-range-handle-start');
  const he = $('plan-range-handle-end');
  const d = _duration > 0 ? _duration : 1;
  const leftPct = (_startSec / d) * 100;
  const rightPct = (_endSec / d) * 100;
  if (hs) hs.style.left = `${leftPct}%`;
  if (he) he.style.left = `${rightPct}%`;
  if (fill) {
    fill.style.left = `${leftPct}%`;
    fill.style.width = `${Math.max(0, rightPct - leftPct)}%`;
  }
  const sl = $('plan-range-start-label');
  const el = $('plan-range-end-label');
  const dl = $('plan-range-dur-label');
  if (sl) sl.textContent = formatTimelineSec(_startSec);
  if (el) el.textContent = formatTimelineSec(_endSec);
  if (dl) dl.textContent = `/ ${formatTimelineSec(_duration)}`;
}

function seekToHandle(which) {
  const video = $('plan-range-video');
  if (!video) return;
  const t = which === 'end' ? _endSec : _startSec;
  try {
    video.currentTime = t;
  } catch { /* ignore seek before ready */ }
}

function setError(msg) {
  const el = $('plan-range-error');
  if (!el) return;
  if (!msg) {
    el.style.display = 'none';
    el.textContent = '';
    return;
  }
  el.style.display = 'block';
  el.textContent = msg;
}

function setApplyEnabled(ok) {
  const btn = $('plan-range-apply');
  if (btn) btn.disabled = !ok;
}

function applySelection() {
  if (typeof _onApply !== 'function') {
    closePlanRangePicker();
    return;
  }
  const use_timeline = useTimelineFromFileSelection(_startSec, _endSec, _offsetSec);
  const segIndex = _segIndex;
  const cb = _onApply;
  closePlanRangePicker();
  cb({ segIndex, use_timeline });
}

export function closePlanRangePicker() {
  const modal = $('modal-plan-range');
  if (modal) modal.style.display = 'none';
  const video = $('plan-range-video');
  if (video) {
    try { video.pause(); } catch { /* ignore */ }
    video.removeAttribute('src');
    try { video.load(); } catch { /* ignore */ }
  }
  _segIndex = -1;
  _onApply = null;
  _dragWhich = null;
  _duration = 0;
  setError('');
}

/**
 * @param {{
 *   segIndex: number,
 *   video: { file: string, abs_path?: string, offset_sec?: number, index?: string, title?: string },
 *   useTimeline: string,
 *   title?: string,
 *   onApply: (p: { segIndex: number, use_timeline: string }) => void,
 * }} opts
 */
export function openPlanRangePicker(opts) {
  ensureBound();
  const modal = $('modal-plan-range');
  const video = $('plan-range-video');
  if (!modal || !video || !opts?.video?.file) return;

  _segIndex = Number(opts.segIndex) | 0;
  _offsetSec = Number(opts.video.offset_sec) || 0;
  _onApply = opts.onApply;
  _duration = 0;
  _startSec = 0;
  _endSec = 0;
  setApplyEnabled(false);
  setError('');

  const heading = $('plan-range-title');
  if (heading) {
    const idx = opts.video.index != null ? String(opts.video.index) : '?';
    const name = opts.title || opts.video.title || opts.video.file || '';
    heading.textContent = `选区 — 第 ${_segIndex + 1} 段 · [${idx}] ${name}`;
  }

  const onMeta = () => {
    _duration = Number.isFinite(video.duration) && video.duration > 0 ? video.duration : 0;
    if (_duration <= 0) {
      setError('无法读取视频时长');
      setApplyEnabled(false);
      return;
    }
    const sel = selectionFromUseTimeline(opts.useTimeline || '', _duration, _offsetSec);
    _startSec = sel.startSec;
    _endSec = sel.endSec;
    paintHandles();
    seekToHandle('start');
    setApplyEnabled(true);
  };
  const onErr = () => {
    setError('视频加载失败（文件可能离线）');
    setApplyEnabled(false);
  };

  video.onloadedmetadata = onMeta;
  video.onerror = onErr;
  video.src = videoUrlFor(opts.video);
  modal.style.display = 'flex';
  paintHandles();
}
```

**Implementation notes for the agent:**
- Prefer keeping drag clamp logic correct: when dragging start, prefer fixing end and clamping start to `[0, end - minSpan]`; when dragging end, start fixed, end in `[start + minSpan, duration]`. The `clampFileSelection` helper already expands span if too small — either call it after tentative assign or write explicit one-sided clamps. Both OK if tests for pure helpers pass and manual drag never crosses.
- Do **not** assign `state.currentVideo`.
- Clear `src` on close so the modal does not keep decoding in background.

- [ ] **Step 4: Syntax-check the new module**

Run:

```bash
node --check clio/ui/static/src/plan-range-picker.js
```

Expected: no output (exit 0).

- [ ] **Step 5: Commit**

```bash
git add clio/ui/static/index.html clio/ui/static/style.css clio/ui/static/src/plan-range-picker.js
git commit -m "$(cat <<'EOF'
feat(ui): add plan segment range picker modal

Independent source video player with dual-handle selection for
use_timeline; pure helpers drive clamp and timebase conversion.
EOF
)"
```

---

### Task 3: Wire **选区** into plan editor + docs

**Files:**
- Modify: `clio/ui/static/src/editor-plan.js`
- Modify: `clio/ui/README.md` (plan edit table)
- Modify: `docs/cli-reference.md` only if the UI blurb still omits range picker (optional one-liner)

**Interfaces:**
- Consumes: `openPlanRangePicker` from `./plan-range-picker.js`; `patchSegment` already imported
- Produces: expanded panel button `data-range-pick` that opens picker and applies `use_timeline`

- [ ] **Step 1: Import and open helper**

At top of `editor-plan.js`:

```js
import { openPlanRangePicker } from './plan-range-picker.js';
```

Add a function near other plan mutators:

```js
function openRangePickerForSegment(segIndex) {
  const p = state.plan;
  if (!p?.sequence?.[segIndex]) return;
  const seg = p.sequence[segIndex];
  const v = (state.videos || []).find((x) => String(x.index) === String(seg.index));
  if (!v?.file) {
    addToast(`找不到视频 [${seg.index || '?'}]，无法打开选区`, 'warning');
    return;
  }
  openPlanRangePicker({
    segIndex,
    video: v,
    useTimeline: seg.use_timeline || '',
    title: seg.title || '',
    onApply: ({ segIndex: i, use_timeline }) => {
      if (!state.plan?.sequence?.[i]) return;
      state.plan.sequence[i] = patchSegment(state.plan.sequence[i], { use_timeline });
      markDirty();
      _refreshPreviewTimeline();
      const li = document.querySelector(`#plan-list [data-preview-index="${i}"]`);
      if (li) {
        const headerTl = li.querySelector('.plan-seg-tl');
        if (headerTl) headerTl.textContent = use_timeline || '—';
        const input = li.querySelector('input[data-k="use_timeline"]');
        if (input) input.value = use_timeline;
      } else {
        renderPlan();
      }
      scheduleReadinessCheck();
    },
  });
}
```

- [ ] **Step 2: Add button in expanded timeline row**

In `renderPlan` expanded panel markup, change timeline row to:

```js
<label class="plan-timeline-row">时间轴
  <input value="${escapeHtml(tlText)}" data-k="use_timeline" placeholder="00:10-00:45">
  <button type="button" class="plan-ghost-btn" data-range-pick title="在源视频上拖选起止时间">选区</button>
</label>
```

Wire click with other panel buttons (inside the `forEach` after create):

```js
li.querySelector('[data-range-pick]')?.addEventListener('click', (e) => {
  e.stopPropagation();
  openRangePickerForSegment(i);
});
```

- [ ] **Step 3: Update README plan table**

In `clio/ui/README.md`, ensure the operations table includes something like:

```markdown
| 选区 | 弹窗内独立源视频 + 双端拖拽选 `use_timeline`（plan 时间基，含 `offset_sec`）；主成片预览不被改写 |
```

And timeline row description still says manual `MM:SS-MM:SS` remains available.

Optional `docs/cli-reference.md` UI sentence: mention range-picker modal for `use_timeline` if still only describing text edit.

- [ ] **Step 4: Run unit tests again**

```bash
npx vitest run clio/ui/static/src/__tests__/plan-edit.test.js
```

Expected: PASS.

- [ ] **Step 5: Manual smoke (required before claiming done)**

1. Start UI, open a project with a plan and known videos.
2. Expand a segment → **选区** → modal video loads.
3. Drag start/end; picture seeks to handle.
4. **应用** → card timeline + preview bar segment widths update; dirty indicator on.
5. Undo mentally: change timeline, open again, **取消** → no write.
6. Expand segment with bad index (if possible) → toast, no modal.
7. Esc / backdrop closes and clears modal video src.

- [ ] **Step 6: Commit**

```bash
git add clio/ui/static/src/editor-plan.js clio/ui/README.md docs/cli-reference.md
git commit -m "$(cat <<'EOF'
feat(ui): wire plan 选区 button to range picker

Expanded segments open the dual-handle source picker; apply writes
use_timeline and refreshes composite preview chrome.
EOF
)"
```

---

## Spec coverage checklist

| Spec requirement | Task |
| --- | --- |
| Expanded **选区** entry | Task 3 |
| Independent modal `<video>` | Task 2 |
| Dual-handle full-duration range | Task 2 |
| Drag seek to handle | Task 2 |
| Plan ↔ file offset timebase | Task 1 + 2 apply |
| Apply dirty + preview refresh | Task 3 |
| Cancel / Esc / backdrop discard | Task 2 |
| Missing video toast | Task 3 |
| Load error disables apply | Task 2 |
| Min span 1s / default 0–5 | Task 1 |
| Pure helpers unit-tested | Task 1 |
| No main preview state rewrite | Task 2/3 (do not touch previewIndex on open) |
| Docs | Task 3 |
| No new deps | Global |

## Self-review notes

- No TBD placeholders in tasks.
- `openPlanRangePicker` / `closePlanRangePicker` names consistent across Task 2–3.
- `useTimelineFromFileSelection` / `selectionFromUseTimeline` names match tests and picker.
- HTML step called out the `data-which` typo explicitly so implementers do not copy a broken attribute.
