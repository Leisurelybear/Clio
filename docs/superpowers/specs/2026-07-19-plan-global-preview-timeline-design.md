# Design: Plan global preview timeline (R-031 Phase A)

**Date**: 2026-07-19  
**Status**: Approved for implementation  
**Scope**: Plan-tab video preview UX — continuous **global** progress scrub on the plan composite timebase; media remains **source-video** seek hops  
**Roadmap**: R-031 Phase A (this). Phase B (cut / concat media) deferred.  
**Approach**: Pure `plan-timeline.js` timebase + `viewer.js` global scrub UI (option 2)

## 1. Goals and non-goals

### Goals

1. Under the video player, when the user is on the **Plan** entity with a non-empty `sequence`, the progress UI is a **continuous global timeline** (0 → Σ segment durations), not “click a segment block to start that source clip only.”
2. **Drag** is the primary interaction: pointer position maps to a global second; the player loads the correct source video and seeks to the mapped `use_timeline` position.
3. Segment **color blocks** remain as secondary chrome (proportion of duration); **click block** = jump to that segment’s **global start**.
4. Playback advances continuously across segment boundaries (auto source hop), driven by the **same** global timebase as the bar and clock.
5. Player clock on Plan shows **composite** time: `成片 mm:ss / 总 mm:ss`.
6. Timeline math is pure, unit-tested, and shared by scrub / playhead / auto-advance.

### Non-goals (Phase A)

- Prefer cut clips under `output/cuts/<day>/` or a day-level concat file (**R-031 Phase B**).
- Auto-running cut / real-time ffmpeg filtergraph for preview.
- Transitions, gaps, speed ramps, multi-track.
- Composite (stitched) waveform — waveform stays **per source file**.
- Changing cut / export / jianying pipelines.
- Forcing composite clock outside Plan entity.

### Success criteria

- Plan + sequence: bar is scrubbable to any global second; playhead and clock follow composite time.
- Continuous play crosses segments without requiring manual next.
- Editing `use_timeline` (including 起点/终点) rebuilds widths/total immediately from in-memory plan.
- Invalid / zero-duration segments do not hang playback; bar remains usable.
- Existing plan-edit helpers and R-030 accordion focus-safe behavior still pass tests.
- No new runtime dependencies.

## 2. Problem / baseline

| Surface | Today |
| --- | --- |
| Preview bar (R-012) | Segment blocks sized by `use_timeline`; **click/drag selects segment index** then `_playPreviewSegment` from that segment’s **start** |
| `_playPreviewSegment` | Resolves `state.videos` by `seg.index`, seeks `use_timeline` start + `offset_sec` on **source** media |
| Clock | Source `currentTime / duration` |
| Accordion (R-030) | Auto-expand when `previewActive` + `previewIndex` changes |
| Cut outputs | Per-segment files under `output/cuts/<day>/`; **not** used by preview |

**UX pain (user):** Right-hand segment list already jumps to a segment; the **player chrome** should be a **global** scrubber that auto-switches media by time — like watching an edited result’s timeline, even though files are still sources.

**Roadmap note:** Original R-031 text emphasized cut/composite media. Phase A delivers the **timebase + scrub UX** on sources; Phase B swaps the media layer without redoing the axis.

## 3. Decisions (locked)

| Topic | Choice |
| --- | --- |
| Global duration | **A** — Σ durations from each segment’s `use_timeline` (live plan; no cut required) |
| Bar chrome | **B** — global scrub + retained segment color blocks |
| Media | **C** — Phase A source only; cut preference is Phase B |
| When global UI is on | **B** — Plan entity + non-empty sequence (no need to press 预览 first) |
| Clock | **A** — composite only while global UI is on |
| Architecture | Pure `plan-timeline.js` + viewer integration |
| Drag → play | Drag does **not** force `play()`; if already playing, keep playing; if paused, stay paused |
| Accordion | Global position changes update `previewIndex` and sync expand **even when** `previewActive` is false (extends R-030 trigger) |
| Mode state | **No** persisted `previewMode`; derive `isGlobalTimelineUi` from `currentEntity === 'plan' && sequence.length > 0` |
| Zero / invalid duration | Skip in continuous play; width = share of **positive** durations; if **all** invalid, equal widths |
| Scrub performance | Same-segment: throttled seek (rAF / ~50ms); cross-segment: change `src` only when `segIndex` changes; pointerup commits final seek |

## 4. Time model (`plan-timeline.js`)

### 4.1 Input / output

**Input:** `sequence` array items with `use_timeline` (`"HH:MM:SS - HH:MM:SS"` or formats already accepted by `parseTimecode` after split on `-`).

**Per segment record:**

| Field | Meaning |
| --- | --- |
| `segIndex` | Index in `sequence` |
| `videoIndex` | `seg.index` |
| `planStart` / `planEnd` | Seconds in **plan domain** (from `use_timeline`; **no** `offset_sec`) |
| `duration` | `max(0, planEnd - planStart)`; invalid parse → `0` |
| `globalStart` / `globalEnd` | Half-open `[globalStart, globalEnd)` on composite axis; cumulative over sequence order |

**Total:** sum of `duration` (zero-duration segments contribute `0` to total but keep index slots).

### 4.2 API (pure)

```js
buildTimeline(sequence) → { segments: TimelineSeg[], total: number }
globalToLocal(timeline, globalSec) → { segIndex, localSec, planSec, videoIndex }
localToGlobal(timeline, segIndex, localSec) → number
clampGlobal(timeline, globalSec) → number
```

- `localSec` ∈ `[0, duration]` (clamped).
- `planSec = planStart + localSec` (caller adds `offset_sec` for source seek).
- `globalSec < 0` → clamp 0; `globalSec >= total` → last segment end (or last positive segment).
- Empty sequence → `{ segments: [], total: 0 }`.
- `globalToLocal` on a zero-duration segment at a boundary: resolve to **next positive-duration** segment when possible (playback skip); if none, last segment end.

### 4.3 Width policy (UI helper, may live next to build)

- Let `positive = segments.filter(d => d.duration > 0)`.
- If `positive.length === 0` and `segments.length > 0`: each width `1/n` (equal fallback, R-012-compatible).
- Else: width ∝ `duration / total` for positive segments; zero-duration segments get **minimal** width (e.g. fixed ~2px or 0.5% floor) so they remain visible but not dominant — **or** zero visual width if floor complicates hit-testing; implementer picks floor **≥ 0** and documents in plan. Prefer **0 width** for zero-duration when any positive exists (unclickable; click falls through to neighbors via global x mapping on full bar).

Hit-testing always uses **full bar x → globalSec → globalToLocal**, not per-block index alone (blocks are visual only except explicit click-to-segment-start).

### 4.4 Source seek (call site, not pure module)

```
seekToGlobal(globalSec):
  { segIndex, planSec, videoIndex } = globalToLocal(...)
  v = videos.find(index === videoIndex)
  seekSec = planSec + (v.offset_sec || 0)
  playVideoSegment(v.file, seekSec)  // play/pause per §3 drag rules
  previewIndex = segIndex
  previewGlobalSec = clampGlobal(globalSec)
  sync accordion (focus-safe)
```

Continuous play end-of-segment:

```
on timeupdate (when previewActive or continuous play):
  planSec = player.currentTime - offset
  localSec = planSec - planStart
  globalSec = localToGlobal(segIndex, localSec)
  if globalSec >= seg.globalEnd (or currentTime >= planEnd+offset): advance to next positive segment
```

Keep `!player.seeking` guard (R-012) against native seek thrash.

## 5. UI / interaction

### 5.1 Visibility

`isGlobalTimelineUi` when `state.currentEntity === 'plan'` and `state.plan?.sequence?.length > 0`.

- Show preview bar (existing `#preview-bar` / plan-mode).
- Enable global scrub + composite clock.
- Leave Plan or empty sequence: restore non-composite clock behavior; stop or leave preview per existing stop rules.

### 5.2 Bar

- Segment blocks: width per §4.3; classes done / active / idle (R-012 colors OK).
- **Playhead** thumb or vertical line at `previewGlobalSec / total`.
- **Pointer drag** on bar: map x → globalSec → seekToGlobal; do not force play.
- **Click block**: jump to that segment’s `globalStart` (secondary).
- Prev / Next: previous/next **segment globalStart** (skip zero-duration if needed).
- Play / Pause: continuous play along global axis from `previewGlobalSec` (or 0); reuses preview session flags as needed (`previewActive` true while intentionally playing through).

### 5.3 Clock

While `isGlobalTimelineUi`:

```
player-time text = `${fmtTime(previewGlobalSec)} / ${fmtTime(total)}`
```

Optionally prefix label `成片` in the same string for clarity. Do **not** show source duration as primary.

### 5.4 Native `<video>` controls

If the player exposes native seek UI that shows **source** duration, Phase A should either hide native progress where feasible or document “use the bar under the player.” Prefer matching existing controls policy in `index.html` / CSS; do not invent a second composite native control.

### 5.5 Accordion (R-030 extension)

Whenever `previewIndex` changes due to scrub, prev/next, or auto-advance — **including** when `previewActive === false` — call the same focus-safe expand path as preview (`_syncPlanExpandFromPreview` or equivalent). Mid-edit focus protection stays.

### 5.6 起点 / 终点

Unchanged: write plan-domain times via `planSecFromPlayer(currentTime, offset_sec)`; require loaded source matches segment video. After timeline field changes, rebuild timeline and clamp `previewGlobalSec` (prefer keep `segIndex`, else scale by total ratio).

### 5.7 Waveform

Still loaded for **current source** file. Scrubbing the **global** bar does not reinterpret waveform peaks as composite. Known dual timebase; Phase A accepts it.

## 6. State

| Field | Role |
| --- | --- |
| `previewGlobalSec` | Authoritative composite playhead for UI (number ≥ 0) |
| `previewActive` | Continuous play-through session (play button / auto-advance) |
| `previewIndex` | Current segment index for chrome + accordion |
| `_previewEndTime` | Optional: source-domain end for current segment auto-advance (keep if simpler than pure global compare) |

**Do not** add `previewMode` enum — derive UI mode from entity + sequence.

Rebuild timeline whenever plan sequence or any `use_timeline` changes (renderPlan / patch path can call `renderPreviewBar` / invalidate cache). Caching `buildTimeline` result on state is optional; cheap to recompute.

## 7. Files

| File | Change |
| --- | --- |
| `clio/ui/static/src/plan-timeline.js` | **New** pure timeline helpers |
| `clio/ui/static/src/__tests__/plan-timeline.test.js` | **New** unit tests |
| `clio/ui/static/src/viewer.js` | Global scrub, composite clock, seekToGlobal, continuous advance |
| `clio/ui/static/src/state.js` | `previewGlobalSec` (and defaults) |
| `clio/ui/static/style.css` | Playhead thumb / scrub cursor if needed |
| `clio/ui/static/src/editor-plan.js` | After timeline edits, refresh preview bar; expand on index without requiring previewActive if logic lives here |
| `ROADMAP.md` | R-031 Phase A / B split; mark A in progress → done when shipped |
| `clio/ui/README.md` | Plan global bar + composite clock; media still source hop; Phase B open |
| `docs/cli-reference.md` | Align serve blurb if it still says only R-031 composite |

**No** backend route changes in Phase A.

## 8. Testing

### Unit (`plan-timeline.test.js`)

1. Empty sequence → total 0.
2. Single segment duration and identity mapping.
3. Multi-segment cumulative `globalStart` / `globalEnd`.
4. `clampGlobal` below 0 and above total.
5. `t == globalEnd` of segment i maps to start of i+1 (or end of last).
6. Invalid / missing `use_timeline` → duration 0.
7. `end < start` → duration 0.
8. `offset_sec` never appears in pure module (no parameter).
9. Skip chain: consecutive zero-duration does not infinite-loop helper used for “next playable.”

### Regression

- `plan-edit` pure tests unchanged green.
- Accordion focus-safe behavior preserved (manual / existing tests).
- R-012 seeking guard retained.

### Manual

1. Plan tab: drag bar across two different `videoIndex` sources — media switches; clock stays composite.
2. Play through boundary — auto-advance without extra click.
3. Pause, drag, release — remains paused at new position.
4. Edit `use_timeline` length — bar proportions and total update.
5. Leave Plan tab — clock / bar not stuck in composite-only if inappropriate.
6. 起点/终点 still write plan times correctly with `offset_sec`.

## 9. Phase B (out of scope; pointer only)

When cut clips exist for the day, prefer playing trimmed files (start at 0, duration ≈ clip length) mapped onto the **same** global axis; optional single concat file later. Fallback to Phase A source hop + optional hint “尚未裁剪…”. No change to `Σ use_timeline` as the default axis unless product revisits decision A.

## 10. Risks

| Risk | Mitigation |
| --- | --- |
| Source hop jank at boundaries | Accept in Phase A; Phase B cuts reduce in-file seeks |
| Dual timebase (clock vs waveform) | Composite clock label; waveform stays source |
| Drag thrashing load/seek | Throttle + src change only on segIndex change |
| R-030 expand only on previewActive | Explicitly extend to global position changes |
| ROADMAP readers expect cut media | Phase A/B split in ROADMAP + this doc title |

## 11. Decisions log

| Decision | Choice | Rationale |
| --- | --- | --- |
| Primary UX | Global scrub bar | User: segment list already jumps; player needs full-timeline drag |
| Duration basis | Σ use_timeline | Live edit; no cut dependency |
| Media Phase A | Source seek hop | Fastest path to scrub UX |
| Architecture | plan-timeline pure module | Testable; Phase B swaps media layer only |
| Drag play policy | No force play | Editing scrub habit |
| Accordion | Follow previewIndex always on Plan global UI | Bar and list stay aligned |
| Zero duration | Skip play; width policy §4.3 | Avoid hang; bar still maps by x |

## 12. Implementation readiness

Spec approved in conversation 2026-07-19 (multi-dimension review + six default resolutions accepted). Next: `writing-plans` → implement on `main` per project preference.
