# Design: Plan sequence reorder visual feedback

**Date**: 2026-07-17  
**Status**: Implemented on `main` (insert line + just-moved flash; no FLIP)  
**Scope**: Plan entity UI only — drag + ↑↓ reorder feedback  
**Approach**: A — pure CSS insert line + post-move highlight (no FLIP, no new deps)

## 1. Goals and non-goals

### Goals

1. While dragging a plan segment, show a clear **insertion indicator** (where the card will land).
2. After a successful reorder (drop or ↑/↓), the segment at its **new index** briefly **highlights** so the user can confirm the move.
3. Keep existing data path: `reorderSequence` → `applySequence` → full `renderPlan()` (no structural rewrite).

### Non-goals

- FLIP / layout-transition animation between old and new positions.
- Third-party DnD libraries (SortableJS, etc.).
- Global button style unification (separate track).
- Changing `reorderSequence` semantics or plan domain model.
- Multi-select reorder.

### Success criteria

- Dragging over another segment paints exactly one insert line (before/after that segment).
- Dropping with `from !== to` updates order and flashes the moved card at the new index for ~0.6–0.8s.
- ↑ / ↓ apply the same highlight on the destination index.
- Cancelled drag (dragend without drop / same index) clears indicator and does not mark dirty or flash.
- Existing preview-active styling still works; highlight can coexist for the flash duration.
- No new npm/Python dependencies; vitest pure-helper coverage if drop-target logic is extracted.

## 2. Current baseline

| Surface | Behavior |
| --- | --- |
| `plan-edit.js` `reorderSequence` | Pure array move; no DOM |
| `editor-plan.js` | HTML5 `draggable` on `.plan-seg`; `dragstart` sets `_dragFromIndex` + `.plan-seg-dragging`; `drop` → `applySequence(reorderSequence(...))` which always re-renders |
| ↑ / ↓ | Adjacent `reorderSequence` + `applySequence` |
| CSS | `.plan-seg-dragging { opacity: 0.5 }` only — no drop target, no post-move cue |

Pain: full re-render makes the list jump with no “it landed here” signal.

## 3. Behavior detail

### 3.1 Drag indicator

- Track `_dragFromIndex` (existing) and `_dropAtIndex` (new): intended **destination index in the current list** (same meaning as `toIndex` in `reorderSequence`).
- On `dragover` over a segment `i`:
  - `preventDefault` + `dropEffect = 'move'` (existing).
  - Decide before vs after from pointer Y vs element mid-Y:
    - upper half → drop **before** `i` → `_dropAtIndex = i`
    - lower half → drop **after** `i` → `_dropAtIndex = i + 1`
  - Map to a visual “line before segment `k`” where `k = _dropAtIndex` (line after last segment: special case on last item or list footer).
- On `dragleave` of list (not merely child leave): clear indicator if leaving `#plan-list`.
- On `dragend`: clear dragging class + `_dropAtIndex` UI (even if drop already ran).

**Indicator rendering (preferred):** CSS class on the segment that would sit **after** the gap, e.g. `.plan-seg-drop-before` → `box-shadow` / `::before` top border in accent. For “after last item”, apply `.plan-seg-drop-after` on the last segment (bottom line).

Re-applying indicator: either mutate classes without full re-render during drag (preferred — avoid `renderPlan` on every `dragover`), or throttle class toggles on the existing DOM nodes.

### 3.2 Post-move highlight

- Extend `applySequence(next, opts = {})`:
  - `opts.highlightIndex` optional number.
  - After `renderPlan()`, if `highlightIndex` is valid, add `.plan-seg-just-moved` to `[data-preview-index="${highlightIndex}"]`, optional `scrollIntoView({ block: 'nearest' })`, remove class on `animationend` or timeout (~700ms).
- Call sites:
  - `drop`: `to = computed drop index` (clamped after accounting for remove-then-insert; prefer computing with same rules as `reorderSequence` and pass **final index of the moved item**).
  - ↑: `highlightIndex = i - 1`
  - ↓: `highlightIndex = i + 1`
- If `fromIndex === toIndex`, do nothing (no `markDirty`, no highlight).

**Final index note:** `reorderSequence` does splice-out then splice-in at `toIndex`. Visual “line before k” must map to the same `toIndex` the pure helper expects. Document mapping in a small pure helper if non-obvious:

```js
// optional extract for tests
export function dropIndexFromPointer(fromIndex, overIndex, placeAfter) { ... }
export function movedItemIndexAfterReorder(fromIndex, toIndex) { ... }
```

### 3.3 Edge cases

| Case | Behavior |
| --- | --- |
| Drop on self / same slot | no-op |
| Empty sequence | no drag |
| Single item | drag allowed but only same slot → no-op |
| Preview-active segment moved | after re-render, preview index still refers to sequence index; if preview was active on moved row, keep `state.previewIndex` updated if product already does — **do not change preview semantics in this task** unless move already shifts it (today full re-render uses current `state.previewIndex`; leave as-is) |
| Rapid ↑↑ | each apply re-renders + new flash on latest dest |

## 4. CSS

```css
.plan-seg-drop-before { /* top accent line */ }
.plan-seg-drop-after  { /* bottom accent line on last */ }
.plan-seg-just-moved {
  animation: plan-seg-moved 0.7s ease;
}
@keyframes plan-seg-moved {
  from { background: var(--accent-bg); box-shadow: var(--accent-glow); border-color: var(--accent); }
  to   { /* back to normal */ }
}
```

Use existing design tokens (`--accent`, `--accent-bg`, `--accent-glow`). No new color system.

## 5. Files

| File | Change |
| --- | --- |
| `clio/ui/static/src/editor-plan.js` | drop-at tracking; class toggles during drag; `applySequence` highlight; ↑↓ pass index |
| `clio/ui/static/style.css` | drop line + just-moved keyframes |
| `clio/ui/static/src/plan-edit.js` | optional pure helpers only if mapping needs tests |
| `clio/ui/static/src/__tests__/plan-edit.test.js` | tests for any new pure helpers |

## 6. Testing

- **Unit:** pure helpers for drop/toIndex mapping (if extracted).
- **Manual checklist:** drag up/down across 3+ segments; drop on self; ↑ on first (disabled); ↓ on last (disabled); cancel drag; highlight visible after re-render; dirty save still works.

## 7. Implementation order

1. CSS classes + keyframes.
2. Optional pure helpers + tests.
3. Wire dragover indicator (no re-render).
4. Wire drop + ↑↓ highlight via `applySequence`.
5. Manual pass on plan panel.

## 8. Out of scope follow-ups

- Button system unification (`btn-primary` / plan toolbar / empty CTAs).
- Video menu package commit (separate, already implemented).
- R-027 logs filter.
- R-025 i18n.
