# Plan Segment Card Density (R-030) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collapse plan sequence cards into a scannable one-line list with accordion expand-to-edit, ghost action buttons, resizable reason/voiceover textareas, and auto-expand of the preview-active segment.

**Architecture:** Keep data/edit pure helpers in `plan-edit.js`. Add pure expand-index helpers there (TDD). UI state `_expandedSegIndex` lives in `editor-plan.js`; `renderPlan()` rebuilds collapsed headers + optional expand panel. `viewer.js` calls exported `setPlanExpandedIndex` when preview segment changes. CSS owns density + ghost buttons.

**Tech Stack:** Vanilla JS ES modules, Vitest, existing `style.css` design tokens, no new deps.

**Spec:** `docs/superpowers/specs/2026-07-19-plan-seg-card-density-design.md`

## Global Constraints

- No new npm/Python dependencies.
- Do not change plan domain model, readiness API, save path, or `reorderSequence` / insert / delete pure semantics.
- R-031 composite preview is out of scope (do not change which media file preview plays).
- Work on `main` (project preference: no feature branch required).
- One feature per commit where practical; English commit messages; Chinese UI copy for new labels only.
- TDD for pure expand-index helpers before wiring DOM.
- Prefer full `renderPlan()` on expand change (list sizes are small).

## File map

| File | Responsibility |
| --- | --- |
| `clio/ui/static/src/plan-edit.js` | Pure: `nextExpandedAfterDelete`, `nextExpandedAfterInsert`, `nextExpandedAfterMove` |
| `clio/ui/static/src/__tests__/plan-edit.test.js` | Unit tests for expand helpers |
| `clio/ui/static/src/editor-plan.js` | `_expandedSegIndex`, `setPlanExpandedIndex`, collapsed/expanded markup, handlers |
| `clio/ui/static/src/viewer.js` | Call `setPlanExpandedIndex` from `_playPreviewSegment` when preview index changes |
| `clio/ui/static/style.css` | Header grid, panel, ghost/icon buttons, textarea grid + narrow stack |

---

### Task 1: Pure expand-index helpers (TDD)

**Files:**
- Modify: `clio/ui/static/src/plan-edit.js`
- Test: `clio/ui/static/src/__tests__/plan-edit.test.js`

**Interfaces:**
- Consumes: none (pure index math).
- Produces:
  - `nextExpandedAfterDelete(expanded, deletedIndex, newLength) → number | null`
  - `nextExpandedAfterInsert(afterIndex) → number`  // always `afterIndex + 1` (new item index)
  - `nextExpandedAfterMove(fromIndex, toIndex, expanded) → number | null`
    - if `expanded === fromIndex` → return `toIndex` (moved item’s new index)
    - if `expanded` is null → null
    - if item between from/to shifted, adjust expanded the same way list indices shift after remove+insert at `toIndex` (same semantics as `reorderSequence`)

**Index-shift rule for move** (match `reorderSequence`: splice out `from`, splice in at `to`):

```text
if expanded is null → null
if expanded === from → to
// after removing `from`, indices > from decrement by 1
let e = expanded > from ? expanded - 1 : expanded
// after inserting at `to`, indices >= to increment by 1
if (e >= to) e = e + 1
return e
```

- [ ] **Step 1: Write the failing tests**

Append to `clio/ui/static/src/__tests__/plan-edit.test.js` (extend the existing import list):

```js
import {
  reorderSequence,
  removeSegment,
  patchSegment,
  formatTimelineSec,
  setTimelineBound,
  insertSegment,
  computeDropToIndex,
  computeDragAutoScrollDelta,
  nextExpandedAfterDelete,
  nextExpandedAfterInsert,
  nextExpandedAfterMove,
} from '../plan-edit.js';

describe('nextExpandedAfterDelete', () => {
  it('returns null when list becomes empty', () => {
    expect(nextExpandedAfterDelete(0, 0, 0)).toBeNull();
  });

  it('keeps same index when deleting after expanded', () => {
    expect(nextExpandedAfterDelete(1, 2, 3)).toBe(1);
  });

  it('decrements when deleting before expanded', () => {
    expect(nextExpandedAfterDelete(2, 0, 3)).toBe(1);
  });

  it('clamps to last when deleting the expanded last item', () => {
    // delete index 2 from length 3 → newLength 2; was expanded 2 → min(2, 1) = 1
    expect(nextExpandedAfterDelete(2, 2, 2)).toBe(1);
  });

  it('returns null when expanded was null', () => {
    expect(nextExpandedAfterDelete(null, 1, 2)).toBeNull();
  });
});

describe('nextExpandedAfterInsert', () => {
  it('expands the newly inserted index (afterIndex + 1)', () => {
    expect(nextExpandedAfterInsert(0)).toBe(1);
    expect(nextExpandedAfterInsert(-1)).toBe(0); // prepend: afterIndex -1 → insert at 0
    expect(nextExpandedAfterInsert(2)).toBe(3);
  });
});

describe('nextExpandedAfterMove', () => {
  it('follows the moved item when it was expanded', () => {
    expect(nextExpandedAfterMove(0, 2, 0)).toBe(2);
    expect(nextExpandedAfterMove(2, 0, 2)).toBe(0);
  });

  it('shifts expanded when another item moves across it', () => {
    // [0,1,2,3] move 0→2; expanded was 2 → after remove 0 becomes 1, insert at 2 → stays 1? 
    // remove 0: [1,2,3] indices: old1→0, old2→1, old3→2; expanded old2 → 1
    // insert at to=2: [1,2, moved, 3] → indices >=2 bump; expanded 1 stays 1
    expect(nextExpandedAfterMove(0, 2, 2)).toBe(1);
  });

  it('returns null when nothing expanded', () => {
    expect(nextExpandedAfterMove(0, 2, null)).toBeNull();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm test -- clio/ui/static/src/__tests__/plan-edit.test.js`

Expected: FAIL — `nextExpandedAfterDelete` / `Insert` / `Move` not exported.

- [ ] **Step 3: Implement helpers in `plan-edit.js`**

Append:

```js
/**
 * Expanded index after deleting deletedIndex; newLength is length after delete.
 * @param {number|null|undefined} expanded
 * @param {number} deletedIndex
 * @param {number} newLength
 * @returns {number|null}
 */
export function nextExpandedAfterDelete(expanded, deletedIndex, newLength) {
  if (expanded == null || !Number.isFinite(Number(expanded))) return null;
  const n = Number(newLength) | 0;
  if (n <= 0) return null;
  let e = Number(expanded);
  const d = Number(deletedIndex);
  if (Number.isFinite(d) && e > d) e -= 1;
  if (e < 0) return null;
  if (e >= n) e = n - 1;
  return e;
}

/**
 * Expanded index for a segment inserted after afterIndex (-1 = prepend → index 0).
 * @param {number} afterIndex
 * @returns {number}
 */
export function nextExpandedAfterInsert(afterIndex) {
  const a = Number(afterIndex);
  if (!Number.isFinite(a) || a < -1) return 0;
  return a + 1;
}

/**
 * Expanded index after reorderSequence(from, to).
 * @param {number} fromIndex
 * @param {number} toIndex
 * @param {number|null|undefined} expanded
 * @returns {number|null}
 */
export function nextExpandedAfterMove(fromIndex, toIndex, expanded) {
  if (expanded == null || !Number.isFinite(Number(expanded))) return null;
  const from = Number(fromIndex);
  const to = Number(toIndex);
  let e = Number(expanded);
  if (!Number.isFinite(from) || !Number.isFinite(to)) return e;
  if (e === from) return to;
  if (e > from) e -= 1;
  if (e >= to) e += 1;
  return e;
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm test -- clio/ui/static/src/__tests__/plan-edit.test.js`

Expected: PASS for all new + existing plan-edit tests.

- [ ] **Step 5: Commit**

```bash
git add clio/ui/static/src/plan-edit.js clio/ui/static/src/__tests__/plan-edit.test.js
git commit -m "$(cat <<'EOF'
feat(plan): add expand-index helpers for accordion segment cards

Pure helpers for delete/insert/move so UI can keep a single expanded
row consistent with list reordering.
EOF
)"
```

---

### Task 2: CSS — collapsed header, panel, ghost buttons, textareas

**Files:**
- Modify: `clio/ui/static/style.css` (plan section ~1018–1036 and R-026 block ~2128–2225)

**Interfaces:**
- Consumes: existing tokens `--bg-surface-2`, `--bg-hover`, `--border`, `--accent`, `--text-*`, `--radius-*`, `--space-*`, `--font-mono`, `--error` / `--err`
- Produces: classes used by Task 3 markup (names fixed here)

- [ ] **Step 1: Replace / extend plan structural CSS**

Keep existing `.plan-seg`, drop indicators, just-moved, readiness. Update toolbar-related rules and add:

```css
/* R-030 plan segment density */
.plan-seg {
  padding: 0;
  overflow: hidden;
}
.plan-seg-header {
  display: grid;
  grid-template-columns: auto auto minmax(0, 1fr) auto auto auto;
  gap: 6px 8px;
  align-items: center;
  padding: 8px 10px;
  cursor: pointer;
}
.plan-seg-header:hover {
  background: var(--bg-hover);
}
.plan-seg-ord {
  color: var(--text-muted);
  font-size: var(--text-xs);
  min-width: 1.4em;
}
.plan-seg-title-text {
  font-weight: 500;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
}
.plan-seg-tl {
  font-family: var(--font-mono);
  color: var(--accent);
  font-size: var(--text-xs);
  font-weight: 500;
  white-space: nowrap;
}
.plan-seg-vid {
  color: var(--text-muted);
  font-size: var(--text-xs);
  white-space: nowrap;
}
.plan-seg-chevron {
  /* reset to icon ghost */
  width: 26px;
  height: 26px;
  padding: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  color: var(--text-muted);
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  cursor: pointer;
  font: inherit;
  font-size: var(--text-sm);
  line-height: 1;
}
.plan-seg-chevron:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
  border-color: var(--border);
}
.plan-seg-panel {
  border-top: 1px solid var(--border);
  padding: 8px 10px 10px;
  background: var(--bg-surface);
}
.plan-seg-panel label {
  margin-top: 0;
}
.plan-seg-panel .plan-title-input {
  width: 100%;
  margin-bottom: 6px;
}
.plan-seg-fields {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  margin: 6px 0 8px;
}
.plan-seg-fields textarea {
  min-height: 64px;
  resize: vertical;
  margin-top: 3px;
  line-height: 1.45;
}
@media (max-width: 1100px) {
  .plan-seg-fields {
    grid-template-columns: 1fr;
  }
}
.plan-seg-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  justify-content: flex-end;
  align-items: center;
}
.plan-ghost-btn,
.plan-icon-btn {
  font: inherit;
  font-size: var(--text-xs);
  font-weight: 500;
  padding: 3px 8px;
  cursor: pointer;
  background: transparent;
  color: var(--text-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 3px;
  line-height: 1.2;
  transition: all var(--transition-fast);
}
.plan-ghost-btn:hover,
.plan-icon-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
  border-color: var(--border-light);
}
.plan-ghost-btn:disabled,
.plan-icon-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.plan-icon-btn {
  width: 26px;
  height: 26px;
  padding: 0;
}
.plan-ghost-btn--danger {
  color: var(--error, var(--err, #ef4444));
  border-color: transparent;
}
.plan-ghost-btn--danger:hover {
  background: var(--error-bg, rgba(239, 68, 68, 0.12));
  border-color: var(--error, #ef4444);
  color: var(--error, #ef4444);
}
/* timeline row inside panel */
.plan-timeline-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
}
.plan-timeline-row input {
  flex: 1 1 8rem;
  min-width: 6rem;
}
/* legacy class names: map old buttons if any leftover */
.plan-move-btn { /* superseded by .plan-icon-btn — leave empty or delete old rules */ }
```

Also: ensure `.plan-seg label { margin-top: var(--space-2); }` does not blow up header spacing — panel labels only. Prefer:

```css
.plan-seg > label { margin-top: var(--space-2); } /* if any remain */
.plan-seg-panel label { margin-top: 0; display: block; font-size: var(--text-xs); color: var(--text-secondary); }
```

Remove or neutralize old bare-button-only rules for `.plan-move-btn`, `.plan-del-btn`, `.plan-ins-btn`, `.plan-tl-btn` that only set font-size/padding without theme (replaced by ghost classes).

- [ ] **Step 2: Visual smoke (no automated test)**

Open UI plan tab later after Task 3; for this task only ensure CSS parses (no syntax error). Optional: no commit until Task 3 if you prefer one UI commit — **this plan commits CSS with Task 3** if you want fewer commits, **or** commit CSS alone:

```bash
git add clio/ui/static/style.css
git commit -m "style(plan): add collapsed segment card and ghost button styles"
```

Preferred: **commit CSS in Task 3** together with markup so the app never half-styles. Skip standalone CSS commit; keep this task as “apply CSS file changes” without commit, then commit in Task 3.

---

### Task 3: `renderPlan` collapsed markup + accordion state

**Files:**
- Modify: `clio/ui/static/src/editor-plan.js`
- Uses CSS from Task 2

**Interfaces:**
- Consumes: `nextExpandedAfterDelete|Insert|Move` from `plan-edit.js`
- Produces:
  - module `let _expandedSegIndex = null`
  - `export function setPlanExpandedIndex(index, { render = true } = {})`
  - `export function getPlanExpandedIndex()` (optional, for tests)
  - Updated `renderPlan()` segment DOM

- [ ] **Step 1: Imports and expand state**

At top of `editor-plan.js`, extend plan-edit import:

```js
import {
  reorderSequence,
  removeSegment,
  patchSegment,
  setTimelineBound,
  insertSegment,
  computeDropToIndex,
  computeDragAutoScrollDelta,
  nextExpandedAfterDelete,
  nextExpandedAfterInsert,
  nextExpandedAfterMove,
} from './plan-edit.js';
```

After other module lets:

```js
let _expandedSegIndex = null;

export function getPlanExpandedIndex() {
  return _expandedSegIndex;
}

/**
 * @param {number|null} index
 * @param {{ render?: boolean }} [opts]
 */
export function setPlanExpandedIndex(index, opts = {}) {
  const render = opts.render !== false;
  let next = index;
  if (next != null) {
    const n = Number(next);
    if (!Number.isFinite(n) || n < 0) next = null;
    else next = n | 0;
  } else {
    next = null;
  }
  if (next === _expandedSegIndex) {
    if (render && next != null && state.plan) {
      // still ensure DOM class if needed — skip full render when unchanged
    }
    return;
  }
  _expandedSegIndex = next;
  if (render && state.plan && state.currentEntity === 'plan') {
    renderPlan();
  }
}
```

Note: `state.currentEntity` — verify field name in `state.js` (may be `'plan'` when plan selected). If entity gate is wrong, fall back to: render when `#plan-list` exists.

Safer gate:

```js
if (render && document.getElementById('plan-list')) {
  renderPlan();
}
```

Avoid infinite loop: `setPlanExpandedIndex` only calls `renderPlan` when index **changes**.

- [ ] **Step 2: Replace segment `li.innerHTML` in `renderPlan` forEach**

Replace the current always-open form with:

```js
const expanded = _expandedSegIndex === i;
const titleText = seg.title || '';
const tlText = seg.use_timeline || '';
const vid = seg.index || '?';

li.className = 'plan-seg'
  + (state.previewActive && state.previewIndex === i ? ' preview-active' : '')
  + (expanded ? ' plan-seg-expanded' : '');
li.dataset.previewIndex = String(i);
li.draggable = true;

li.innerHTML = `
  <div class="plan-seg-header">
    <span class="plan-drag-handle" title="拖拽排序" aria-hidden="true">⠿</span>
    <span class="plan-seg-ord">${i + 1}.</span>
    <span class="plan-seg-title-text" title="${escapeHtml(titleText)}">${escapeHtml(titleText || '(无标题)')}</span>
    <span class="plan-seg-tl">${escapeHtml(tlText || '—')}</span>
    <span class="plan-seg-vid">[${escapeHtml(String(vid))}]</span>
    <button type="button" class="plan-seg-chevron" data-chevron
      aria-expanded="${expanded ? 'true' : 'false'}"
      aria-label="${expanded ? '收起片段' : '展开片段'}">${expanded ? '▾' : '▸'}</button>
  </div>
  ${expanded ? `
  <div class="plan-seg-panel">
    <label class="plan-title-field">标题
      <input class="plan-title-input" value="${escapeHtml(titleText)}" data-k="title">
    </label>
    <label class="plan-timeline-row">时间轴
      <input value="${escapeHtml(tlText)}" data-k="use_timeline" placeholder="00:10-00:45">
      <button type="button" class="plan-ghost-btn" data-tl="start" title="用播放器当前位置作为起点">起点</button>
      <button type="button" class="plan-ghost-btn" data-tl="end" title="用播放器当前位置作为终点">终点</button>
    </label>
    <div class="plan-seg-fields">
      <label>理由
        <textarea rows="3" data-k="reason">${escapeHtml(seg.reason || '')}</textarea>
      </label>
      <label>口播
        <textarea rows="3" data-k="voiceover_hint">${escapeHtml(seg.voiceover_hint || '')}</textarea>
      </label>
    </div>
    <div class="plan-seg-actions">
      <button type="button" class="plan-icon-btn" data-move="up" title="上移" ${i === 0 ? 'disabled' : ''}>↑</button>
      <button type="button" class="plan-icon-btn" data-move="down" title="下移" ${i === p.sequence.length - 1 ? 'disabled' : ''}>↓</button>
      <button type="button" class="plan-ghost-btn" data-ins title="在此后插入片段">+ 插入</button>
      <button type="button" class="plan-ghost-btn plan-ghost-btn--danger" data-del title="删除片段">删除</button>
    </div>
  </div>` : ''}
`;
```

- [ ] **Step 3: Wire click handlers**

Keep existing preview `li.onclick` but update ignore selector:

```js
li.onclick = (e) => {
  if (e.target.closest('input, textarea, button, .plan-drag-handle')) return;
  // header / card body: expand + preview
  if (_expandedSegIndex !== i) {
    _expandedSegIndex = i;
    // re-render after preview path, or set flag — simplest: set then continue and call renderPlan at end
  }
  // ... existing preview seek logic ...
  // After starting preview, ensure expanded:
  _expandedSegIndex = i;
  // Avoid double render: only renderPlan if expand changed and preview path doesn't already renderPlan
};
```

**Concrete pattern** (avoid thrash):

```js
li.onclick = (e) => {
  if (e.target.closest('input, textarea, button, .plan-drag-handle')) return;
  const expandChanged = _expandedSegIndex !== i;
  _expandedSegIndex = i;

  const v = state.videos.find(x => x.index === seg.index);
  if (!v) {
    setStatus(`找不到视频 [${seg.index}]，请重新生成规划`, 'warn');
    if (expandChanged) renderPlan();
    return;
  }
  if (state.previewActive) {
    state.previewIndex = i;
    _playPreviewSegment(); // will also set expand via Task 4; ok if idempotent
  } else {
    startPreview(i);
  }
  if (expandChanged && !state.previewActive) {
    // startPreview → renderPlan already; if preview path re-renders plan, skip
  }
  // Safest: if expandChanged, renderPlan() once unless startPreview/renderPlan already ran
  if (expandChanged) renderPlan();
};
```

**Problem:** `startPreview` already calls `renderPlan` via editor import. So:

```js
li.onclick = (e) => {
  if (e.target.closest('input, textarea, button, .plan-drag-handle')) return;
  _expandedSegIndex = i;
  const v = state.videos.find(x => x.index === seg.index);
  if (!v) {
    setStatus(`找不到视频 [${seg.index}]，请重新生成规划`, 'warn');
    renderPlan();
    return;
  }
  if (state.previewActive) {
    state.previewIndex = i;
    _playPreviewSegment();
    renderPlan(); // refresh expand + preview-active classes
  } else {
    startPreview(i); // already renderPlan inside
  }
};
```

Chevron:

```js
li.querySelector('[data-chevron]')?.addEventListener('click', (e) => {
  e.stopPropagation();
  _expandedSegIndex = _expandedSegIndex === i ? null : i;
  renderPlan();
});
```

- [ ] **Step 4: Structural edit expand updates**

**↑ / ↓** after `applySequence(..., { highlightIndex })` also set expand:

```js
// up
const newIdx = i - 1;
_expandedSegIndex = nextExpandedAfterMove(i, newIdx, _expandedSegIndex);
applySequence(reorderSequence(p.sequence, i, newIdx), { highlightIndex: newIdx });
// applySequence calls renderPlan — expand already set
```

Actually `applySequence` re-reads `_expandedSegIndex` on render — set **before** `applySequence`:

```js
_expandedSegIndex = nextExpandedAfterMove(i, i - 1, i); // prefer follow moved item when acting on i
// Spec: keep expanded on moved item’s new index when user reorders the expanded row.
// When reordering via ↑ on row i, treat expanded as following i → i-1:
_expandedSegIndex = i - 1;
applySequence(reorderSequence(p.sequence, i, i - 1), { highlightIndex: i - 1 });
```

Same for ↓ → `i + 1`.

**Delete:**

```js
const nextSeq = removeSegment(p.sequence, i);
_expandedSegIndex = nextExpandedAfterDelete(_expandedSegIndex, i, nextSeq.length);
applySequence(nextSeq);
```

**Insert** (after `promptInsertAfter` succeeds / inside after `insertSegment`):

```js
// after building next sequence
const next = insertSegment(p.sequence, afterIndex, { index, title });
_expandedSegIndex = nextExpandedAfterInsert(afterIndex);
applySequence(next, { highlightIndex: _expandedSegIndex });
```

**Drag drop:** after computing `to`, before `applySequence`:

```js
_expandedSegIndex = nextExpandedAfterMove(from, to, _expandedSegIndex);
// optional: if user dragged the expanded card, force expand to `to`:
// if (from === previousExpanded) _expandedSegIndex = to;
applySequence(reorderSequence(...), { highlightIndex: to });
```

- [ ] **Step 5: Clamp expand on render**

At start of segment loop or before forEach:

```js
if (_expandedSegIndex != null) {
  if (!p.sequence.length) _expandedSegIndex = null;
  else if (_expandedSegIndex >= p.sequence.length) _expandedSegIndex = p.sequence.length - 1;
}
```

- [ ] **Step 6: Keep field handlers**

`[data-k]` oninput, `[data-tl]`, move/ins/del — same as before, only query within `li` (panel exists only when expanded).

- [ ] **Step 7: Manual check + commit (Tasks 2+3)**

Manual:
1. Open plan with multiple segments — all collapsed one-line.
2. Chevron expands one; second chevron switches accordion.
3. Edit reason/voiceover, resize textarea, dirty+save still works.
4. ↑↓/drag/insert/delete update order and expand per rules.
5. Buttons look ghost, delete is danger-colored.

```bash
git add clio/ui/static/style.css clio/ui/static/src/editor-plan.js
git commit -m "$(cat <<'EOF'
feat(ui): collapse plan segments with accordion expand panel

Show one-line headers by default, expand a single segment for editing,
use ghost action buttons, and keep expand index across structural edits.
EOF
)"
```

---

### Task 4: Preview auto-expand wiring

**Files:**
- Modify: `clio/ui/static/src/viewer.js`
- Modify: `clio/ui/static/src/editor-plan.js` (export already done)

**Interfaces:**
- Consumes: `setPlanExpandedIndex` from `./editor-plan.js` (or dynamic import to avoid circular deps)

**Circular dependency check:**  
`editor-plan.js` already imports `viewer.js` (`renderPreviewBar`, `startPreview`, `_playPreviewSegment`).  
**Do not** static-import `editor-plan` from `viewer.js`. Use dynamic import:

```js
function _syncPlanExpandFromPreview() {
  if (!state.previewActive || state.previewIndex < 0) return;
  import('./editor-plan.js').then((mod) => {
    if (typeof mod.setPlanExpandedIndex === 'function') {
      mod.setPlanExpandedIndex(state.previewIndex);
    }
  });
}
```

- [ ] **Step 1: Call from `_playPreviewSegment`**

At end of successful path in `_playPreviewSegment` (after `state.previewIndex` is known and segment is valid), before or after `renderPreviewBar`:

```js
_syncPlanExpandFromPreview();
```

When skipping missing video and incrementing index, the recursive call will sync.

- [ ] **Step 2: Do not collapse on `stopPreview`**

No call to clear expand (spec).

- [ ] **Step 3: Avoid double full render storms**

`setPlanExpandedIndex` no-ops render when index unchanged. When preview advances 1→2, one `renderPlan` is expected.

If `_playPreviewSegment` + `setPlanExpandedIndex` both cause `renderPlan`, ensure `setPlanExpandedIndex` is the one that expands; `startPreview` already calls `renderPlan` once — order:

1. `state.previewIndex = i`
2. `setPlanExpandedIndex(i)` → may `renderPlan`
3. rest of preview UI

Or: `setPlanExpandedIndex(i, { render: false })` inside viewer, and rely on existing `renderPlan` from `startPreview` / editor. **Chosen:**

```js
import('./editor-plan.js').then((mod) => {
  mod.setPlanExpandedIndex(state.previewIndex, { render: true });
});
```

Accept one re-render per segment change.

- [ ] **Step 4: Manual test**

1. Start preview from bar — segment 0 expands.
2. Next / auto-advance — expand follows.
3. Click progress bar segment — expands that index.
4. Stop preview — last expand remains.

- [ ] **Step 5: Commit**

```bash
git add clio/ui/static/src/viewer.js clio/ui/static/src/editor-plan.js
git commit -m "$(cat <<'EOF'
feat(ui): auto-expand plan segment under preview playhead

Keep the accordion panel in sync with previewIndex while preview is active.
EOF
)"
```

---

### Task 5: Regression tests + ROADMAP status

**Files:**
- Modify: `clio/ui/static/src/__tests__/plan-edit.test.js` (already in Task 1)
- Modify: `ROADMAP.md` — mark R-030 delivered when done
- Optional: small test that `setPlanExpandedIndex` clamps — only if easy under vitest without full DOM; otherwise skip

- [ ] **Step 1: Run full frontend unit suite**

Run: `npm test`

Expected: all pass.

- [ ] **Step 2: Update ROADMAP R-030 status**

In `ROADMAP.md` R-030 section:

```markdown
**Status:** Done (2026-07-19) — collapsed accordion cards + ghost buttons + preview auto-expand. Spec: `docs/superpowers/specs/2026-07-19-plan-seg-card-density-design.md`. Plan: `docs/superpowers/plans/2026-07-19-plan-seg-card-density-plan.md`.
```

Remove R-030 from the open items table (or mark done in table if project keeps historical rows — match style of R-028a: leave detail section Done, remove from top open table).

- [ ] **Step 3: Commit**

```bash
git add ROADMAP.md
git commit -m "docs: mark R-030 plan segment card density done"
```

---

## Spec coverage checklist

| Spec requirement | Task |
| --- | --- |
| Collapsed one-line header (handle, ord, title, tl, idx, chevron) | 3 |
| Accordion one expanded | 3 |
| Expand panel: title, timeline+bounds, reason\|voiceover textareas, actions | 3 |
| Ghost / icon / danger buttons | 2, 3 |
| Textarea min-height 64px, resize vertical, 2-col → 1-col narrow | 2 |
| Chevron toggles expand only | 3 |
| Header click expand + preview | 3 |
| Preview index → auto-expand | 4 |
| stopPreview keeps expand | 4 |
| Insert/delete/move expand index | 1, 3 |
| No R-031 media change | (none) |
| Pure helper tests | 1 |

## Placeholder / consistency self-review

- Helper names consistent: `nextExpandedAfterDelete|Insert|Move` across tasks.
- CSS class names match markup in Task 3.
- Dynamic import avoids `viewer` ↔ `editor-plan` cycle.
- No TBD steps remaining.

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-19-plan-seg-card-density-plan.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks  
2. **Inline Execution** — this session with executing-plans and checkpoints  

Which approach?
