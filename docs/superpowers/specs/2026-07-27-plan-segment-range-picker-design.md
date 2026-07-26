# Design: Plan segment range picker (source-video dual-handle)

**Date**: 2026-07-27  
**Status**: Draft — awaiting implementation plan  
**Scope**: Plan entity UI — per-segment start/end selection via modal with independent video + dual-handle range  
**Approach**: A — lightweight custom range modal (no new deps)  
**Related**: R-030 plan card density; R-031a global preview timeline; prior removal of broken playhead 起点/终点 buttons (2026-07-27)

## 1. Goals and non-goals

### Goals

1. Each expanded plan segment has a control that opens a **modal** to pick start/end of `use_timeline` by watching the **source video**.
2. Modal hosts an **independent `<video>`** so the main composite preview is not hijacked.
3. Selection uses a **dual-handle range** over the **full source duration** (`0 … duration`).
4. Dragging a handle **seeks the modal video** to that handle’s time so the frame matches the bound.
5. On apply, write plan-local `use_timeline` (`MM:SS-MM:SS`) with the same **offset_sec** timebase as existing preview seek (`fileSec = planSec + offset`, write `planSec = max(0, fileSec − offset)`).
6. Keep pure conversion / clamp logic unit-testable; no new third-party UI libraries.

### Non-goals

- Waveform inside the modal.
- In-selection loop play / separate playhead beyond handle-driven seek.
- Dual-handle zoom / “focus around current selection” (full duration only in v1).
- Changing readiness / cut / export semantics.
- Changing main player composite timeline behavior when the modal is open (do not rewrite `previewGlobalSec` / `previewIndex` on open).
- Re-introducing the old one-click 起点/终点 buttons on the card (replaced by this modal).
- Keyboard nudge of handles in v1 (can add later).

### Success criteria

- Expanded panel shows a ghost button (e.g. **选区**) next to the timeline text field.
- Opening the picker loads the segment’s resolved video; invalid index → toast, no modal.
- Initial selection = parsed current `use_timeline` mapped to file seconds and clamped; empty/invalid → default `0 … min(5, duration)` (or equivalent short default).
- Handles cannot cross; minimum span **1 second**.
- Apply updates `sequence[i].use_timeline`, marks dirty, refreshes card timeline text + composite preview bar widths; Cancel / Esc / backdrop discards.
- `plan-edit` pure helpers cover parse / clamp / file↔plan / format; existing plan-edit tests still pass.

## 2. UX

### 2.1 Entry

- Only on **expanded** segment panel, in the timeline row:

```
[ timeline input MM:SS-MM:SS ]  [选区]
```

- Collapsed rows: no picker control.

### 2.2 Modal layout

```
选区 — 第 N 段 · [index] title
┌─────────────────────────────┐
│     <video> (modal only)    │
└─────────────────────────────┘
  |========[====]=============|   dual handles on full duration
  start label          end label
              [取消]  [应用]
```

- Title line identifies ordinal, video index, and segment title.
- Range track represents **source file** time `0 … duration`.
- Numeric start/end shown as read-only labels in v1 (card text field remains the manual escape hatch).
- Primary: **应用**; secondary: **取消**.

### 2.3 Interaction

| Action | Behavior |
| --- | --- |
| Open | Resolve video by `seg.index`; set modal `video.src` via existing `/api/video` query shape (file, source, project, token, abspath as needed). Pause state of main player left alone. |
| `loadedmetadata` | Set track max = `duration`; place handles from initial selection. |
| Drag start handle | Clamp to `[0, end − 1]`; seek modal video to start. |
| Drag end handle | Clamp to `[start + 1, duration]`; seek modal video to end. |
| Apply | Convert file start/end → plan-local; `patchSegment` + dirty + refresh preview timeline chrome; close. |
| Cancel / Esc / backdrop | Close without writing. |
| Load error / offline | Show inline error in modal; disable Apply. |

### 2.4 Timebase

| Direction | Formula |
| --- | --- |
| Plan → file (open / seek) | `fileSec = planSec + (offset_sec > 0 ? offset_sec : 0)` |
| File → plan (apply) | `planSec = max(0, fileSec − offset)` via existing `planSecFromPlayer` |
| Display / store | `formatTimelineSec` → `MM:SS-MM:SS` (floor seconds, same as today) |

`use_timeline` remains plan-local; composite preview still uses `planSec + offset` on seek.

## 3. Architecture

### 3.1 Modules

| Module | Responsibility |
| --- | --- |
| `plan-edit.js` | Pure: parse range → `{start,end}`, clamp selection to duration + min span, format range string, reuse `planSecFromPlayer` / `formatTimelineSec`. Optional thin wrappers: `selectionFromUseTimeline`, `useTimelineFromFileSelection`. |
| `plan-range-picker.js` **(new)** | Modal open/close, bind once, load video, dual-handle pointer events, seek, apply/cancel callbacks. No plan list rendering. |
| `editor-plan.js` | Render **选区** button; `openPlanRangePicker({ segIndex, onApply })` wires apply into `state.plan.sequence` + `_refreshPreviewTimeline` + in-place DOM update. |
| `index.html` | `#modal-plan-range` shell (backdrop, dialog, video, track, labels, actions). |
| `style.css` | Modal video size, track, handles, selected band; match existing modal / ghost tokens. |

### 3.2 State (picker-local)

Keep in module closure, not global `state.js`:

- `segIndex`, `video` ref, `offsetSec`
- `duration`, `startSec`, `endSec` (file time)
- pointer drag which-handle

Do not set `state.currentVideo` from the modal player (avoids desync with main preview identity). Build `video.src` the same way as `viewer._loadAndSeekSource` but only on the modal element.

### 3.3 Apply path (editor-plan)

```
onApply({ segIndex, use_timeline })
  → sequence[segIndex] = patchSegment(..., { use_timeline })
  → markDirty()
  → update header .plan-seg-tl + input[data-k=use_timeline] if present
  → _refreshPreviewTimeline()
  → scheduleReadinessCheck()
```

Same dirty/readiness behavior as typing the timeline field.

## 4. Dual-handle implementation notes

- Track is a single bar; selected interval is a filled middle; two absolutely positioned handles.
- Pointer capture on `pointerdown` of a handle; `pointermove` / `pointerup` on document or track.
- Convert clientX → ratio of track width → seconds; clamp per §2.3.
- Min span: **1.0** second (if duration &lt; 1s, allow full duration as only selection).
- No library; pointer events only (mouse + basic touch).

## 5. Testing

| Layer | Coverage |
| --- | --- |
| Unit (`plan-edit.test.js`) | parse empty/invalid; clamp min span; plan↔file with/without offset; format round-trip; default selection when empty |
| Manual | Open on segment with/without timeline; drag both ends; apply reflects on card + preview bar; cancel no-op; missing video toast; Esc closes |

DOM drag tests optional / deferred.

## 6. Docs touchpoints

- `clio/ui/README.md` plan edit table: document **选区** modal instead of removed 起点/终点.
- `docs/cli-reference.md` one-liner if it still mentions playhead bounds only.

## 7. Open decisions (resolved in brainstorm)

| Topic | Choice |
| --- | --- |
| Where video plays | Independent modal player |
| How to set bounds | Dual-handle range |
| Selectable span | Full source duration |
| Drag feedback | Seek modal video to the moved handle |
| Approach | A — custom modal, no new deps |
| Modules | New `plan-range-picker.js` + pure helpers in `plan-edit.js` |

## 8. Implementation order (for plan skill)

1. Pure helpers + tests in `plan-edit.js`.
2. HTML shell + CSS for modal/track/handles.
3. `plan-range-picker.js` open/load/drag/apply/cancel.
4. Wire **选区** in `editor-plan.js` apply path.
5. README / cli-reference nits.
6. Manual smoke on a multi-segment plan with `offset_sec` if available.
