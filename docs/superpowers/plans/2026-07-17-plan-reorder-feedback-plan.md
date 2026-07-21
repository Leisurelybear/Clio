# Plan Reorder Visual Feedback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** While reordering plan segments (drag or ↑/↓), show an insert-line during drag and a brief highlight on the segment’s new position after a successful move.

**Architecture:** Keep pure reorder in `plan-edit.js`. Add `computeDropToIndex` to map pointer half + over-index → `toIndex` for existing `reorderSequence` (final index of moved item). UI in `editor-plan.js` mutates drop classes during drag (no re-render on `dragover`); `applySequence(next, { highlightIndex })` re-renders then flashes `.plan-seg-just-moved`. CSS only for indicator + keyframes.

**Tech Stack:** Vanilla JS ES modules, Vitest, existing HTML5 DnD, `style.css` design tokens (`--accent`, `--accent-bg`, `--accent-glow`).

## Global Constraints

- No new npm/Python dependencies; no FLIP / third-party sortable.
- Do not change `reorderSequence` final-index semantics (splice out, splice in at `toIndex`).
- Do not change preview-active semantics (`state.previewIndex` leave as-is).
- One feature per commit; English commit messages; TDD for pure helpers.
- Work on `main` (no feature branch required per project prefs).
- Chinese UI copy only if new user-visible strings appear (this feature needs none).

## File map

| File | Responsibility |
| --- | --- |
| `clio/ui/static/src/plan-edit.js` | Pure: `computeDropToIndex(from, over, placeAfter, length)` → `number \| null` |
| `clio/ui/static/src/__tests__/plan-edit.test.js` | Unit tests for drop mapping |
| `clio/ui/static/style.css` | `.plan-seg-drop-before`, `.plan-seg-drop-after`, `.plan-seg-just-moved` + keyframes |
| `clio/ui/static/src/editor-plan.js` | DnD indicator, `applySequence` highlight, ↑↓ pass highlight |

---

### Task 1: Pure drop-to-index helper (TDD)

**Files:**
- Modify: `clio/ui/static/src/plan-edit.js`
- Test: `clio/ui/static/src/__tests__/plan-edit.test.js`

**Interfaces:**
- Consumes: existing `reorderSequence(sequence, fromIndex, toIndex)` — `toIndex` is the **final** index of the moved item after remove+insert.
- Produces: `computeDropToIndex(fromIndex, overIndex, placeAfter, length) → number | null`
  - `placeAfter === false` → gap **before** `overIndex`
  - `placeAfter === true` → gap **after** `overIndex`
  - Returns `null` when the gap is the item’s current slot (no-op)
  - Returned number is always a valid `toIndex` for `reorderSequence` (`0 .. length-1`)

**Mapping (document in code comment):**

```text
insertBefore = placeAfter ? overIndex + 1 : overIndex   // 0 .. length
same slot if insertBefore === fromIndex || insertBefore === fromIndex + 1 → null
toIndex = insertBefore > fromIndex ? insertBefore - 1 : insertBefore
```

- [ ] **Step 1: Write the failing tests**

Append to `clio/ui/static/src/__tests__/plan-edit.test.js`:

```js
import {
  reorderSequence,
  removeSegment,
  patchSegment,
  formatTimelineSec,
  setTimelineBound,
  insertSegment,
  computeDropToIndex,
} from '../plan-edit.js';

// ... existing describe stays ...

describe('computeDropToIndex', () => {
  const n = 4;

  it('returns null when dropping on own slot (before or after self)', () => {
    expect(computeDropToIndex(1, 1, false, n)).toBeNull();
    expect(computeDropToIndex(1, 1, true, n)).toBeNull();
    expect(computeDropToIndex(0, 0, false, n)).toBeNull();
    expect(computeDropToIndex(0, 0, true, n)).toBeNull();
  });

  it('maps before overIndex when dragging down', () => {
    // [A,B,C,D] drag A(0) before C(2) → final index 1 → [B,A,C,D]
    expect(computeDropToIndex(0, 2, false, n)).toBe(1);
    const seq = ['A', 'B', 'C', 'D'];
    expect(reorderSequence(seq, 0, 1)).toEqual(['B', 'A', 'C', 'D']);
  });

  it('maps after overIndex when dragging down to end-ish', () => {
    // drag A(0) after C(2) → final 2 → [B,C,A,D]
    expect(computeDropToIndex(0, 2, true, n)).toBe(2);
    expect(reorderSequence(['A', 'B', 'C', 'D'], 0, 2)).toEqual(['B', 'C', 'A', 'D']);
  });

  it('maps after last to end', () => {
    // drag A(0) after D(3) → final 3 → [B,C,D,A]
    expect(computeDropToIndex(0, 3, true, n)).toBe(3);
    expect(reorderSequence(['A', 'B', 'C', 'D'], 0, 3)).toEqual(['B', 'C', 'D', 'A']);
  });

  it('maps before first when dragging up', () => {
    // drag C(2) before A(0) → final 0
    expect(computeDropToIndex(2, 0, false, n)).toBe(0);
    expect(reorderSequence(['A', 'B', 'C', 'D'], 2, 0)).toEqual(['C', 'A', 'B', 'D']);
  });

  it('returns null for out-of-range inputs', () => {
    expect(computeDropToIndex(-1, 0, false, n)).toBeNull();
    expect(computeDropToIndex(0, 9, false, n)).toBeNull();
    expect(computeDropToIndex(0, 0, false, 0)).toBeNull();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd clio/ui && npm test -- --run src/__tests__/plan-edit.test.js
```

Expected: FAIL — `computeDropToIndex` is not exported / not defined.

- [ ] **Step 3: Implement minimal helper**

Add to `clio/ui/static/src/plan-edit.js` (after `reorderSequence`):

```js
/**
 * Map drag-over target to reorderSequence toIndex (final index of moved item).
 * @param {number} fromIndex
 * @param {number} overIndex segment under pointer
 * @param {boolean} placeAfter true if pointer in lower half of over segment
 * @param {number} length sequence length
 * @returns {number|null} toIndex, or null if no-op / invalid
 */
export function computeDropToIndex(fromIndex, overIndex, placeAfter, length) {
  const n = Number(length) | 0;
  const from = Number(fromIndex);
  const over = Number(overIndex);
  if (!Number.isFinite(from) || !Number.isFinite(over) || n <= 0) return null;
  if (from < 0 || from >= n || over < 0 || over >= n) return null;

  let insertBefore = placeAfter ? over + 1 : over;
  if (insertBefore < 0) insertBefore = 0;
  if (insertBefore > n) insertBefore = n;

  // Same gap as current position → no move
  if (insertBefore === from || insertBefore === from + 1) return null;

  // Convert original-list insertBefore to post-remove splice index (= final index)
  return insertBefore > from ? insertBefore - 1 : insertBefore;
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
cd clio/ui && npm test -- --run src/__tests__/plan-edit.test.js
```

Expected: PASS (all plan-edit tests).

- [ ] **Step 5: Commit**

```bash
git add clio/ui/static/src/plan-edit.js clio/ui/static/src/__tests__/plan-edit.test.js
git commit -m "$(cat <<'EOF'
feat(plan): computeDropToIndex for drag insert mapping

Pure helper maps pointer half + over segment to reorderSequence
toIndex; null when drop is a no-op.
EOF
)"
```

---

### Task 2: CSS for insert line + just-moved flash

**Files:**
- Modify: `clio/ui/static/style.css` (Plan structural edit section ~2010+)

**Interfaces:**
- Consumes: existing tokens `--accent`, `--accent-bg`, `--accent-glow`, `.plan-seg`
- Produces: classes used by Task 3

- [ ] **Step 1: Add styles after `.plan-seg-dragging`**

In `clio/ui/static/style.css`, replace/extend the plan drag block:

```css
.plan-seg-dragging {
  opacity: 0.5;
}
.plan-seg-drop-before {
  box-shadow: inset 0 3px 0 0 var(--accent);
}
.plan-seg-drop-after {
  box-shadow: inset 0 -3px 0 0 var(--accent);
}
.plan-seg-just-moved {
  animation: plan-seg-moved 0.7s ease;
}
@keyframes plan-seg-moved {
  0% {
    background: var(--accent-bg);
    box-shadow: var(--accent-glow);
    border-color: var(--accent);
  }
  100% {
    /* return to stylesheet defaults for .plan-seg */
  }
}
```

Keep existing `.plan-drag-handle` / toolbar rules unchanged.

- [ ] **Step 2: Commit**

```bash
git add clio/ui/static/style.css
git commit -m "$(cat <<'EOF'
style(plan): drop insert line and just-moved flash

Accent inset lines for drag target; 0.7s highlight after reorder.
EOF
)"
```

---

### Task 3: Wire editor-plan DnD indicator + post-move highlight

**Files:**
- Modify: `clio/ui/static/src/editor-plan.js`

**Interfaces:**
- Consumes: `computeDropToIndex`, `reorderSequence` from `./plan-edit.js`
- Produces: visual indicator during drag; `applySequence(next, { highlightIndex })`

- [ ] **Step 1: Extend module state and imports**

At top of `editor-plan.js`:

```js
import {
  reorderSequence,
  removeSegment,
  patchSegment,
  setTimelineBound,
  insertSegment,
  computeDropToIndex,
} from './plan-edit.js';

let _readinessTimer = null;
let _lastReadiness = { ok: true, errors: [], warnings: [] };
let _dragFromIndex = null;
let _dropToIndex = null; // final toIndex while dragging, or null
let _highlightTimer = null;
```

- [ ] **Step 2: Replace `applySequence` with highlight support**

```js
function applySequence(next, opts = {}) {
  if (!state.plan) return;
  state.plan.sequence = next;
  markDirty();
  renderPlan();
  const hi = opts.highlightIndex;
  if (hi == null || hi < 0) return;
  const el = document.querySelector(`#plan-list [data-preview-index="${hi}"]`);
  if (!el) return;
  el.classList.add('plan-seg-just-moved');
  try {
    el.scrollIntoView({ block: 'nearest' });
  } catch { /* ignore */ }
  if (_highlightTimer) clearTimeout(_highlightTimer);
  _highlightTimer = setTimeout(() => {
    el.classList.remove('plan-seg-just-moved');
    _highlightTimer = null;
  }, 700);
}
```

- [ ] **Step 3: Add indicator helpers (before `renderPlan` or near drag code)**

```js
function clearDropIndicator() {
  document.querySelectorAll('.plan-seg-drop-before, .plan-seg-drop-after').forEach((el) => {
    el.classList.remove('plan-seg-drop-before', 'plan-seg-drop-after');
  });
  _dropToIndex = null;
}

/**
 * Paint insert line for a pending toIndex (final index semantics via insertBefore gap).
 * Visual: line before segment k, or after last when moving to end.
 * We derive paint from from+to: show drop-before on target row, or drop-after on last.
 */
function paintDropIndicator(fromIndex, toIndex, length) {
  clearDropIndicator();
  if (toIndex == null || length <= 0) return;
  _dropToIndex = toIndex;
  const list = document.querySelectorAll('#plan-list .plan-seg');
  if (!list.length) return;

  // Recover insertBefore gap for painting:
  // toIndex is final index; insertBefore = toIndex if toIndex < from, else toIndex + 1
  const insertBefore = toIndex < fromIndex ? toIndex : toIndex + 1;
  if (insertBefore >= length) {
    list[length - 1]?.classList.add('plan-seg-drop-after');
  } else {
    list[insertBefore]?.classList.add('plan-seg-drop-before');
  }
}
```

- [ ] **Step 4: Update ↑ / ↓ handlers to pass highlightIndex**

Replace the up/down listeners inside the sequence `forEach`:

```js
li.querySelector('[data-move="up"]')?.addEventListener('click', (e) => {
  e.stopPropagation();
  if (i <= 0) return;
  const next = reorderSequence(p.sequence, i, i - 1);
  applySequence(next, { highlightIndex: i - 1 });
});
li.querySelector('[data-move="down"]')?.addEventListener('click', (e) => {
  e.stopPropagation();
  if (i >= p.sequence.length - 1) return;
  const next = reorderSequence(p.sequence, i, i + 1);
  applySequence(next, { highlightIndex: i + 1 });
});
```

- [ ] **Step 5: Replace dragstart / dragend / dragover / drop**

Inside the same `forEach` where listeners are attached:

```js
li.addEventListener('dragstart', (e) => {
  _dragFromIndex = i;
  _dropToIndex = null;
  li.classList.add('plan-seg-dragging');
  e.dataTransfer.effectAllowed = 'move';
  try {
    e.dataTransfer.setData('text/plain', String(i));
  } catch { /* IE ignore */ }
});
li.addEventListener('dragend', () => {
  li.classList.remove('plan-seg-dragging');
  clearDropIndicator();
  _dragFromIndex = null;
});
li.addEventListener('dragover', (e) => {
  e.preventDefault();
  e.dataTransfer.dropEffect = 'move';
  if (_dragFromIndex == null) return;
  const rect = li.getBoundingClientRect();
  const placeAfter = e.clientY > rect.top + rect.height / 2;
  const to = computeDropToIndex(_dragFromIndex, i, placeAfter, p.sequence.length);
  if (to == null) {
    clearDropIndicator();
    return;
  }
  paintDropIndicator(_dragFromIndex, to, p.sequence.length);
});
li.addEventListener('drop', (e) => {
  e.preventDefault();
  e.stopPropagation();
  if (_dragFromIndex == null) return;
  const rect = li.getBoundingClientRect();
  const placeAfter = e.clientY > rect.top + rect.height / 2;
  const to = computeDropToIndex(_dragFromIndex, i, placeAfter, p.sequence.length);
  const from = _dragFromIndex;
  clearDropIndicator();
  _dragFromIndex = null;
  li.classList.remove('plan-seg-dragging');
  if (to == null) return;
  applySequence(reorderSequence(p.sequence, from, to), { highlightIndex: to });
});
```

- [ ] **Step 6: Clear indicator when leaving the list**

After the `forEach` that builds segments (or once on `ol`):

```js
const ol = pane.querySelector('#plan-list');
// ... after segments appended ...
ol.addEventListener('dragleave', (e) => {
  // only when leaving the list itself, not entering a child
  if (!ol.contains(e.relatedTarget)) {
    clearDropIndicator();
  }
});
```

Note: if `ol` is recreated each `renderPlan`, binding once per render is fine (same as other listeners). Avoid stacking by binding only on the new `ol` node created that render (current pattern creates fresh DOM each time).

- [ ] **Step 7: Run unit tests + sanity**

```bash
cd clio/ui && npm test -- --run
```

Expected: all vitest tests PASS (including plan-edit).

- [ ] **Step 8: Manual checklist (app)**

1. Open a project with a multi-segment plan; open plan entity.
2. Drag segment down across 2+ rows → insert line moves with pointer half.
3. Drop → order changes; destination flashes ~0.7s and scrolls into view if needed.
4. Drag onto self → no dirty flash / no order change.
5. ↑ / ↓ → same flash on new row.
6. Cancel drag (Esc or drop outside) → line clears, no dirty.
7. Save still works after reorder.

- [ ] **Step 9: Commit**

```bash
git add clio/ui/static/src/editor-plan.js
git commit -m "$(cat <<'EOF'
feat(ui): plan drag insert line and post-reorder highlight

Show accent drop target while dragging; flash moved segment after
drop or up/down. Uses computeDropToIndex for no-op-safe mapping.
EOF
)"
```

---

### Task 4: Docs touch-up (optional, same day)

**Files:**
- Modify: `docs/superpowers/specs/2026-07-17-plan-reorder-feedback-design.md` — set **Status** to Implemented
- Modify: `ROADMAP.md` only if you add an R-ID for this UX (not required; can note under recently completed as a small UI polish)

- [ ] **Step 1: Mark design status**

Change header Status line to:

```markdown
**Status**: Implemented on `main` (insert line + just-moved flash; no FLIP)
```

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/specs/2026-07-17-plan-reorder-feedback-design.md
git commit -m "docs(spec): mark plan reorder feedback implemented"
```

---

## Spec coverage (self-review)

| Spec requirement | Task |
| --- | --- |
| Insert indicator during drag (before/after half) | Task 1 + 3 |
| Line after last segment | Task 3 `paintDropIndicator` drop-after |
| Post-drop highlight ~0.6–0.8s | Task 2 + 3 (700ms) |
| ↑/↓ same highlight | Task 3 |
| from===to no dirty / no flash | Task 1 null + Task 3 early return |
| No re-render on dragover | Task 3 class mutation only |
| Pure helper + vitest | Task 1 |
| No FLIP / no deps | Global constraints |
| preview semantics unchanged | Task 3 does not touch `state.previewIndex` |

## Placeholder scan

No TBD/TODO steps; code blocks are complete.

## Type consistency

- `computeDropToIndex(...) → number | null` used in dragover/drop.
- `applySequence(next, { highlightIndex })` — `highlightIndex` equals `to` from helper or `i±1` for buttons.
- CSS class names: `plan-seg-drop-before`, `plan-seg-drop-after`, `plan-seg-just-moved` match Task 2 and 3.

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-17-plan-reorder-feedback-plan.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks  
2. **Inline Execution** — this session, `executing-plans`, batch with checkpoints  

Which approach?
