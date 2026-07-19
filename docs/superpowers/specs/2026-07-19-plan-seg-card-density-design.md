# Design: Plan segment card density (R-030)

**Date**: 2026-07-19  
**Status**: **Implemented** on `main` (2026-07-19) — accordion cards, ghost buttons, preview auto-expand, review hardening, playhead↔plan timebase fix  
**Scope**: Plan entity UI only — sequence card layout + action button chrome  
**Approach**: C — collapsed list + expand to edit; accordion (one open); preview auto-expands current segment  
**Roadmap**: R-030 (this). Related open item R-031 (composite preview) is **out of scope**.

## 1. Goals and non-goals

### Goals

1. Reduce vertical space per sequence item so a typical day (10–15 segments) is scannable without endless scroll.
2. Align segment action controls (↑ ↓ · +插入 · 删除 · 起点 · 终点) with global ghost / `btn-secondary` visual language (not bare browser default buttons).
3. Keep all existing edit affordances available when a row is expanded (title, timeline, reason, voiceover, reorder, insert, delete, playhead bounds).
4. Give reason / voiceover enough room for multi-line text, with user-resizable height.

### Non-goals

- R-031: playing cut/composite media instead of hopping source videos (tracked separately in `ROADMAP.md`).
- Changing plan domain model / readiness / save / reorder pure helpers semantics.
- Per-segment AI regenerate (already deferred by choice).
- Collapsed-row inline editing of title/timeline without expand.
- Persisting user-resized textarea heights across re-renders or sessions.
- New DnD library or FLIP animations (R-026 reorder feedback stays as-is).

### Success criteria

- Default (collapsed) row height ≈ one compact line (~36–44px content + padding), showing: drag handle, ordinal, title, timeline, video index, chevron.
- At most one segment expanded at a time (accordion).
- When `state.previewActive` and `state.previewIndex` changes (manual bar click, prev/next, auto-advance, card-triggered preview), that index expands and others collapse.
- Expanded panel shows: editable title is already on the header row (or in panel — see §3); timeline + 起点/终点; reason + voiceover as side-by-side textareas (`resize: vertical`, min-height ~64px); ghost action buttons.
- Buttons match project dark/light tokens (border, hover, danger delete) consistent with `btn-secondary` / compact toolbar patterns.
- Existing tests for plan-edit pure helpers still pass; UI markup changes covered by lightweight unit tests where render helpers are extractable; no new deps.

## 2. Current baseline

| Surface | Behavior |
| --- | --- |
| `editor-plan.js` `renderPlan` | Each `li.plan-seg` always shows full form: toolbar (bare ↑↓ 插入 删除) + title + timeline+起终点 + reason + voiceover textarea |
| CSS `.plan-seg` | Shared with `.timeline-seg`; padding + stacked labels → ~150–180px+ per card |
| `.plan-move-btn` / `.plan-del-btn` / `.plan-ins-btn` / `.plan-tl-btn` | Only font-size + padding; inherit browser default chrome → visually off vs rest of UI |
| Preview | `viewer.js` `_playPreviewSegment` toggles `.preview-active` on cards; does not control expand state (none today) |

**Pain:** high chrome-to-content ratio; toolbar buttons look foreign; long sequences hard to scan while editing one row.

## 3. Layout

### 3.1 Collapsed row

Single horizontal grid (wrap only if editor column is extremely narrow):

```
[⠿]  N.  Title text (ellipsis)   00:00-00:10   [002]   ▸
```

- Ordinal `N.` is 1-based display index (same as list order), not video index.
- Title: plain text in collapsed mode (from `seg.title`); long titles ellipsis.
- Timeline: mono accent styling (reuse `.seg-time` / mono token patterns).
- Video index: muted `[idx]`.
- Chevron: ▸ collapsed / ▾ expanded.
- Drag handle remains the only grab target for reorder (existing semantics).

### 3.2 Expanded panel (below the row, same card)

```
[ title input full width ]          optional: keep title editable only when expanded
[ timeline input ] [起点] [终点]
[ 理由 textarea ]  [ 口播 textarea ]
              [↑] [↓] [+ 插入] [删除]
```

**Title placement (chosen):** collapsed shows read-only title text; expanded shows a full-width title **input** at the top of the panel (or replaces the header title with the input while expanded). Prefer: header title becomes the input when expanded so we do not duplicate title.

**Reason / voiceover:**

- `textarea` (not single-line `input`).
- Default ~3 lines / `min-height: 64px`.
- `resize: vertical` only.
- Side-by-side two columns when editor width allows; `@media` / container-friendly stack to one column when narrow (CSS `grid-template-columns: 1fr 1fr` with a max-width breakpoint or `minmax` that collapses — use a simple media query on editor width if container queries are not already used elsewhere; match existing CSS style).

**Actions:** ghost compact buttons; ↑↓ icon-sized (~26×26); 删除 danger color; disabled state for ↑ on first / ↓ on last unchanged.

### 3.3 Visual states

| State | Treatment |
| --- | --- |
| Default collapsed | surface-2 card, thin border |
| Hover collapsed | existing hover tokens |
| Expanded | same card; panel uses slightly darker inset (`bg` surface) + top divider |
| `preview-active` | keep accent border / glow (existing); can combine with expanded |
| `plan-seg-just-moved` | existing flash animation |
| Drop indicator | existing before/after lines |

## 4. Expand / collapse rules

Module-level state in `editor-plan.js` (survives full `renderPlan` re-renders):

```js
let _expandedSegIndex = null; // number | null
```

### 4.1 Accordion

- At most one expanded index.
- Expanding `i` sets `_expandedSegIndex = i` and re-renders (or toggles classes if we keep DOM — **prefer re-render via `renderPlan()`** for simplicity and consistency with dirty updates, unless re-render cost is painful; list sizes are small).

### 4.2 User toggles

Chosen rule (explicit, no ambiguity):

1. **Header click** (row body, not handle/inputs/buttons) → `expand(i)` **and** existing preview navigation (start/seek). Does **not** collapse on a second header click.
2. **Chevron button** → `stopPropagation` (no preview change); toggles expand for this index only (open → close; closed → open and close others).
3. **Collapse paths:** chevron on the open row, or expanding a different segment (accordion), or structural rules in §4.4.
4. Clicks on inputs / textareas / action buttons: `stopPropagation` — mirror existing `closest('input, textarea, button, .plan-drag-handle')` guard so they neither toggle expand nor steal preview incorrectly.

### 4.3 Preview auto-expand

Whenever preview current segment changes:

- Call `setExpandedSegIndex(state.previewIndex)` when `state.previewActive && state.previewIndex >= 0`.
- Hook points: after `_playPreviewSegment` updates index (viewer), and when plan re-renders under active preview.
- Avoid circular full re-render loops: viewer should set expanded index via a small exported setter or shared state field, then either call a lightweight `syncPlanExpandUI()` or `renderPlan()` once.

**Preferred wiring:**

- `state.planExpandedIndex` optional mirror **or** module export `setPlanExpandedIndex(i)` from `editor-plan.js`.
- `viewer.js` `_playPreviewSegment` / `stopPreview`: on index change while active, call `setPlanExpandedIndex(state.previewIndex)` which updates module state and re-renders plan if plan tab is mounted.
- `stopPreview`: **do not** force collapse; leave last expanded index.

### 4.4 Structural edits

| Action | Expand behavior |
| --- | --- |
| Insert after `i` | Expand the newly inserted index |
| Delete `i` | Expand `min(i, length-1)` if list non-empty, else `null` |
| Reorder (drag / ↑↓) | Keep expanded on the **moved item’s new index** (same as highlight index when provided) |

## 5. Button styling

Unify under shared classes (names illustrative; align with existing BEM-ish plan classes):

```css
.plan-icon-btn, .plan-ghost-btn {
  /* transparent bg, border, text-secondary, radius-sm, text-sm */
  /* hover: bg-hover, text-primary */
}
.plan-ghost-btn--danger { color: error; border transparent; hover error-bg }
.plan-icon-btn { width/height ~26px; padding 0; }
```

Map:

| Control | Class |
| --- | --- |
| ↑ ↓ | `plan-icon-btn` |
| +插入, 起点, 终点 | `plan-ghost-btn` |
| 删除 | `plan-ghost-btn plan-ghost-btn--danger` |

Remove reliance on unstyled native button chrome for these controls. Do not change global `btn-primary` / modal buttons.

## 6. Implementation sketch

### Files

| File | Change |
| --- | --- |
| `clio/ui/static/src/editor-plan.js` | Markup structure; expand state; chevron; wire insert/delete/reorder expand; export setter for viewer |
| `clio/ui/static/src/viewer.js` | On preview segment change → expand setter |
| `clio/ui/static/style.css` | Collapsed row grid; expand panel; ghost buttons; textarea grid; narrow stack |
| `clio/ui/static/src/__tests__/editor.test.js` (and/or small new helper tests) | Expand index helpers if extracted; snapshot/HTML contract if existing tests assert plan markup |

### Pure helpers (optional extract for TDD)

```js
export function nextExpandedAfterDelete(expanded, deletedIndex, newLength) { ... }
export function nextExpandedAfterInsert(afterIndex) { return afterIndex + 1; }
export function nextExpandedAfterMove(from, to, expanded) { ... }
```

### Render contract (collapsed HTML outline)

```html
<li class="plan-seg [preview-active] [plan-seg-expanded]" data-preview-index="i" draggable="true">
  <div class="plan-seg-header">
    <span class="plan-drag-handle">⠿</span>
    <span class="plan-seg-ord">1.</span>
    <span class="plan-seg-title-text">…</span> <!-- or input when expanded -->
    <span class="plan-seg-tl mono">00:00-00:10</span>
    <span class="plan-seg-vid">[002]</span>
    <button type="button" class="plan-seg-chevron" aria-expanded="false">▸</button>
  </div>
  <!-- if expanded -->
  <div class="plan-seg-panel">...</div>
</li>
```

### Accessibility

- Chevron button: `aria-expanded`, `aria-label` 展开/收起片段.
- Do not make the entire `li` a focus trap; keep inputs tabbable when expanded.

## 7. Testing

- Unit: expand-index helpers after insert/delete/move.
- Existing `plan-edit` reorder/remove/insert tests unchanged.
- If editor tests assert plan DOM strings, update expectations to collapsed structure + one expanded fixture.
- Manual: open plan with 10+ segments; expand/collapse; start preview and confirm auto-expand follows bar; resize reason textarea; ↑↓/drag still work; dirty + save unchanged.

## 8. Rollout

1. CSS + markup collapse/expand without changing data handlers.
2. Wire accordion + chevron.
3. Wire preview auto-expand.
4. Ghost buttons polish.
5. Tests + manual pass.

One feature commit preferred (R-030); split only if preview wiring needs a follow-up.

## 9. Out of scope reminders

- R-031 composite/cut preview timebase (ROADMAP entry only until its own design).
- Plan meta fields (theme / opening / ending) density — unchanged this pass.

## 10. Post-ship notes (2026-07-19)

Implemented as planned; review hardening landed same day:

- Preview auto-expand skips full re-render while focus is in another segment’s input; resync on blur.
- Header click no-ops when already expanded on the active preview segment; panel chrome does not seek.
- Readiness issue click sets expand + scroll.
- Defer expand DOM rebuild while drag is active.
- **Playhead bounds timebase:** `applyTimelineBound` uses `planSecFromPlayer(player.currentTime, video.offset_sec)` so `use_timeline` stays plan-local (symmetric with preview `seek = plan + offset`). Requires the open player file to match the segment’s video.
