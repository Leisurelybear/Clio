# R-012 Preview Progress Bar & Interaction Control Design

## Overview

R-011 introduced plan preview playback (auto-advance through segments). R-012 extends it with:
- A visual progress bar showing the entire plan sequence below the video player
- Previous/play-pause/next control buttons
- Click/drag on progress bar to jump to any segment
- Protection against manual player timeline drag triggering auto-advance

Only visible when the user is viewing the Plan panel (`state.currentEntity === 'plan'`).

## Design Decisions

### 1. Progress Bar Representation

- **Timeline-proportional widths**: Each segment's bar width = `duration / totalDuration * 100%`, where `duration = end - start` from `use_timeline`. If `use_timeline` is missing or malformed, segments share equal width (fallback).
- **Color coding**: All segments use a neutral bar color (`#666` or similar). Current (active) segment highlighted with accent (`#60a5fa`). Completed segments get a slightly brighter shade.
- **No text labels on bar segments** — segment names shown in the control bar text area instead (to avoid crowding).

### 2. Control Bar Layout

```
[<< Prev]  [▶ Play / ■ Stop]  [Next >>]   |   Segment 3/11: "埃菲尔铁塔夜景"   |   [█████░░░░░░░░░]  3/11
```

- Located between `#player-info` and `.player-tip` inside `#player-pane` (`index.html` line 62-74)
- Visibility controlled by CSS: displayed only when `#player-pane` has class `plan-mode`
- Buttons use existing icons (play/stop from editor.js pattern; prev/next use chevron-left/chevron-right)
- Current segment name shown as text (from `seg.title || seg.index`)
- Progress bar on the right, spans remaining width

### 3. Interaction

- **Click on segment bar**: Sets `state.previewIndex` to that segment's index, calls `_playPreviewSegment()`
- **Drag on segment bar**: `mousedown` on the bar area begins drag tracking; `mousemove` determines which segment the cursor is over; `mouseup` commits the jump. Uses `document` event listeners to handle mouse leaving the bar element.
- **Button behaviors**:
  - `Prev`: Decrement `previewIndex` (wrap to 0), call `_playPreviewSegment()`
  - `Next`: Increment `previewIndex` (wrap to last), call `_playPreviewSegment()`
  - `Play/Stop`: Same as existing `startPreview()` / `stopPreview()` — toggles preview state
- **Keyboard**: Not required in this iteration (users typically use mouse for video browsing)

### 4. Manual Drag Protection

Problem: When user manually drags the player's native progress bar, `player.currentTime` changes rapidly, which could trigger the `timeupdate → currentTime >= _previewEndTime` auto-advance.

Solution: Guard the auto-advance condition with `!player.seeking`:
```js
if (state.previewActive && !player.seeking && state._previewEndTime !== null
    && player.currentTime >= state._previewEndTime) {
  // auto-advance
}
```

The HTML5 `<video>` element sets `seeking = true` during a seek operation and resets it after. This naturally prevents auto-advance during manual drag. No additional state needed.

### 5. Preview Bar State

No new state variables needed:
- `state.previewActive` — whether preview is running
- `state.previewIndex` — current segment index (-1 when stopped)
- `state._previewEndTime` — end time to trigger auto-advance

The preview bar reads these values reactively each time it renders.

## Files to Change

| File | Changes |
|------|---------|
| `vlog_tool/ui/static/index.html:62` | Add `<div id="preview-bar">` after `#player-info`, before `.player-tip` |
| `vlog_tool/ui/static/style.css` | Add `#preview-bar` styles, `.preview-bar-segment` segment blocks, `#player-pane.plan-mode` visibility, `.preview-bar-btn`, `.preview-seg-active` highlight |
| `vlog_tool/ui/static/src/viewer.js` | Add `renderPreviewBar()` (HTML generation + event binding), `_onSegmentClick(i)`, `_onSegmentDrag()` (mousedown/mousemove/mouseup), update `_playPreviewSegment()` to call `renderPreviewBar()`, update `setupPlayer()` seeking guard |
| `vlog_tool/ui/static/src/editor.js:250-257` | Remove inline preview buttons + counter span from `renderPlan()` |

### No changes to:
- `state.js` — existing fields sufficient
- `runner.js` — unrelated
- `sidebar.js` — existing `stopPreview()` calls remain sufficient

## Detailed Implementation

### index.html

Insert after `#player-info` closing div (line 73):
```html
<div id="preview-bar" style="display:none">
  <div class="preview-controls">
    <button id="btn-prev-seg" class="preview-bar-btn" title="上一个"></button>
    <button id="btn-play-preview" class="preview-bar-btn" title="播放/暂停"></button>
    <button id="btn-next-seg" class="preview-bar-btn" title="下一个"></button>
  </div>
  <span id="preview-seg-name" class="preview-seg-name">选择 segment</span>
  <div class="preview-seg-bar" id="preview-seg-bar">
    <!-- segment blocks rendered by JS in renderPreviewBar() -->
  </div>
</div>
```
Button icons are injected by `setupPlayer()` using `icon('skip-back', 14)` / `icon('play', 14)` / `icon('skip-forward', 14)` to stay consistent with the rest of the UI.

### viewer.js

New functions:

```js
function renderPreviewBar() {
  const bar = $('#preview-bar');
  if (!bar || state.currentEntity !== 'plan') { /* hide */ return; }
  // Show bar, calculate segment widths, render seg blocks, bind events
  // Update seg name, play/pause button state
}

function _onSegmentClick(i) {
  if (state.previewActive) {
    state.previewIndex = i;
    _playPreviewSegment();
  }
}

function _onSegmentDrag(e) {
  // mousedown on #preview-seg-bar → track mousemove → determine seg index → commit on mouseup
}

function _togglePreview() {
  if (state.previewActive) stopPreview();
  else startPreview();
}
```

Update `_playPreviewSegment`:
- After existing logic, call `renderPreviewBar()` to update bar highlight + seg name

Update `setupPlayer`:
- Change `timeupdate` guard to: `if (state.previewActive && !player.seeking && ...)`
- Bind prev/next buttons: `$('btn-prev-seg').onclick`, `$('btn-next-seg').onclick`, `$('btn-play-preview').onclick`

### style.css

```css
#preview-bar {
  display: flex; align-items: center; gap: var(--space-2);
  padding: var(--space-2) var(--space-1); flex-wrap: wrap;
}
#player-pane.plan-mode #preview-bar { display: flex; }

.preview-controls { display: flex; gap: 2px; }
.preview-bar-btn { /* similar to .btn-icon style but smaller */ }
.preview-seg-name { font-size: var(--text-xs); color: var(--text-secondary); flex-shrink: 0; max-width: 150px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.preview-seg-bar { display: flex; flex: 1; height: 8px; background: var(--bg-surface-2); border-radius: 4px; cursor: pointer; overflow: hidden; min-width: 100px; }
.preview-seg-block { height: 100%; transition: background var(--transition-fast); }
.preview-seg-block:hover { opacity: 0.8; }
.preview-seg-block.done { background: var(--text-tertiary); }
.preview-seg-block.active { background: var(--accent); }
.preview-seg-block.pending { background: var(--border); }
```

### editor.js

Replace lines 251-257 (inline preview buttons):
```js
// Preview bar is now rendered in viewer.js, below the player.
// Remove the inline controls from plan panel.
```

Update `renderPlan` to add `plan-mode` class to `#player-pane` and call `renderPreviewBar()`:
```js
$('player-pane').classList.add('plan-mode');
import('./viewer.js').then(mod => mod.renderPreviewBar());
```

Where `plan-mode` is removed:
- `sidebar.js` — all entity switch paths already call `stopPreview()`; add `$('player-pane').classList.remove('plan-mode')` alongside each call
- `editor.js:renderPlan()` — sets `plan-mode` each time plan is rendered (idempotent if already set)

## Error Handling & Edge Cases

1. **No plan loaded**: `renderPreviewBar()` checks `state.plan?.sequence?.length` — if absent, bar shows "暂无可预览内容" and is disabled.
2. **Segment without `use_timeline`**: Falls back to equal-width distribution. Skipped during auto-advance (existing behavior).
3. **Rapid clicking**: Each click on prev/next calls `_playPreviewSegment()` which resets `_previewEndTime` and player time. No debounce needed — video element handles concurrent seeks gracefully.
4. **Close plan tab while previewing**: Sidebar calls `stopPreview()` on entity switch (already implemented). Also remove `plan-mode` class.
5. **Bar drag outside element bounds**: `mouseup` listener is on `document`; if released outside, still commits the segment under cursor at release point.

## Acceptance Criteria

Per ROADMAP R-012:

- [x] R-012a: Preview control bar with prev/play-pause/next buttons + segment name + progress bar, rendered below player when viewing Plan panel
- [x] R-012b: Progress bar segments are clickable and draggable to jump to corresponding segment
- [x] R-012c: Manual slider drag does not trigger auto-advance (via `player.seeking` guard)
