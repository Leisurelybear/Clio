# R-012 Preview Progress Bar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a visual progress bar and control buttons below the video player for plan preview playback.

**Architecture:** Static HTML skeleton in `index.html`, CSS in `style.css`, JS logic in `viewer.js` (new `renderPreviewBar()` + interaction handlers). Existing `state.previewActive`/`previewIndex`/`_previewEndTime` reused. Preview bar visibility tied to `plan-mode` class on `#player-pane`.

**Tech Stack:** Vanilla JS (ES modules), CSS custom properties, HTML5 `<video>` element.

---

### Task 1: Add preview bar HTML to index.html

**Files:**
- Modify: `vlog_tool/ui/static/index.html:62-77`

- [ ] **Step 1: Insert preview bar HTML after `#player-info`**

Insert a new `<div id="preview-bar">` between `#player-info` (line 73) and `.player-tip` (line 74):

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

- [ ] **Step 2: Commit**

```bash
git add vlog_tool/ui/static/index.html
git commit -m "feat(ui): add preview bar HTML skeleton for R-012"
```

---

### Task 2: Add CSS styles for preview bar

**Files:**
- Modify: `vlog_tool/ui/static/style.css:274` (before `.player-tip`)

- [ ] **Step 1: Append CSS rules after `#playback-speed` block (line 273)**

```css
/* ── Preview Bar (R-012) ───────────────────────────────────── */
#preview-bar {
  display: none; align-items: center; gap: var(--space-2);
  padding: 2px var(--space-1); flex-wrap: wrap;
  font-size: var(--text-xs);
}
#player-pane.plan-mode #preview-bar { display: flex; }

.preview-controls { display: flex; gap: 2px; align-items: center; }
.preview-bar-btn {
  background: var(--bg-surface-2); color: var(--text-secondary);
  border: 1px solid var(--border); border-radius: var(--radius-sm);
  padding: 3px 6px; cursor: pointer; font: inherit;
  display: inline-flex; align-items: center; justify-content: center;
  transition: all var(--transition-fast); line-height: 1;
}
.preview-bar-btn:hover { background: var(--bg-hover); color: var(--text-primary); border-color: var(--border-light); }
.preview-bar-btn:active { background: var(--bg-active); }
.preview-bar-btn.preview-active { background: var(--accent); color: #fff; border-color: var(--accent); }

.preview-seg-name {
  color: var(--text-secondary); flex-shrink: 0;
  max-width: 160px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}

.preview-seg-bar {
  display: flex; flex: 1; height: 8px;
  background: var(--bg-surface-2); border-radius: 4px;
  cursor: pointer; overflow: hidden; min-width: 80px;
}
.preview-seg-block {
  height: 100%; transition: background var(--transition-fast);
  border-right: 1px solid var(--bg-surface);
}
.preview-seg-block:last-child { border-right: none; }
.preview-seg-block:hover { opacity: 0.8; }
.preview-seg-block.done { background: var(--text-tertiary); }
.preview-seg-block.active { background: var(--accent); }
.preview-seg-block.pending { background: var(--border); }
```

- [ ] **Step 2: Commit**

```bash
git add vlog_tool/ui/static/style.css
git commit -m "feat(ui): add preview bar CSS styles for R-012"
```

---

### Task 3: Add renderPreviewBar() and interaction handlers to viewer.js

**Files:**
- Modify: `vlog_tool/ui/static/src/viewer.js`

- [ ] **Step 1: Add import for `icon`**

Add to imports at top (line 1):
```js
import { icon } from './api.js';
```

- [ ] **Step 2: Add `renderPreviewBar()` function after `setupPlayer()` (before exports)**

```js
// ── Preview bar (R-012) ──────────────────────────────────────
function renderPreviewBar() {
  const bar = $('#preview-bar');
  if (!bar) return;
  const isPlan = state.currentEntity === 'plan';
  bar.style.display = isPlan ? '' : 'none';
  if (!isPlan) return;
  const p = state.plan;
  if (!p || !p.sequence || !p.sequence.length) {
    bar.innerHTML = '<span class="muted">暂无可预览内容</span>';
    return;
  }

  // Calculate total duration for proportional widths
  let totalDuration = 0;
  const durations = p.sequence.map(seg => {
    const parts = (seg.use_timeline || '').split('-');
    if (parts.length >= 2) {
      const start = parseTimecode(parts[0].trim());
      const end = parseTimecode(parts[1].trim());
      const d = end - start;
      if (d > 0) { totalDuration += d; return d; }
    }
    return 0;
  });

  // Build bar segments
  const barHtml = p.sequence.map((seg, i) => {
    const w = totalDuration > 0 ? (durations[i] / totalDuration * 100) : (100 / p.sequence.length);
    const cls = i < state.previewIndex ? 'done'
      : i === state.previewIndex && state.previewActive ? 'active'
      : 'pending';
    return `<div class="preview-seg-block ${cls}" data-seg="${i}" style="width:${w}%"></div>`;
  }).join('');

  bar.innerHTML = barHtml;

  // Bind click events to segment blocks
  bar.querySelectorAll('.preview-seg-block').forEach(el => {
    el.onclick = () => {
      const i = parseInt(el.dataset.seg);
      if (state.previewActive && i >= 0 && i < p.sequence.length) {
        state.previewIndex = i;
        _playPreviewSegment();
      }
    };
  });
}
```

- [ ] **Step 3: Add drag-to-seek handler**

Add after `renderPreviewBar()`:
```js
let _dragStartX = 0;
let _dragTargetSeg = -1;

function _setupPreviewBarDrag() {
  const segBar = $('#preview-seg-bar');
  if (!segBar) return;
  const p = state.plan;
  if (!p || !p.sequence || !p.sequence.length) return;

  const _onDragMove = (e) => {
    const rect = segBar.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const pct = Math.max(0, Math.min(1, x / rect.width));
    // Find which segment this falls in based on proportional widths
    let totalDuration = 0;
    const durs = p.sequence.map(seg => {
      const parts = (seg.use_timeline || '').split('-');
      if (parts.length >= 2) {
        const s = parseTimecode(parts[0].trim());
        const e2 = parseTimecode(parts[1].trim());
        const d = e2 - s;
        if (d > 0) { totalDuration += d; return d; }
      }
      return 0;
    });
    let accum = 0;
    let idx = 0;
    for (let i = 0; i < durs.length; i++) {
      const w = totalDuration > 0 ? durs[i] / totalDuration : 1 / durs.length;
      accum += w;
      if (pct <= accum) { idx = i; break; }
      if (i === durs.length - 1) idx = i;
    }
    // Highlight hovered segment
    segBar.querySelectorAll('.preview-seg-block').forEach(el => {
      el.classList.toggle('active', parseInt(el.dataset.seg) === idx && state.previewActive);
    });
    _dragTargetSeg = idx;
  };

  const _onDragEnd = () => {
    document.removeEventListener('mousemove', _onDragMove);
    document.removeEventListener('mouseup', _onDragEnd);
    if (_dragTargetSeg >= 0 && state.previewActive) {
      state.previewIndex = _dragTargetSeg;
      _playPreviewSegment();
    }
    _dragTargetSeg = -1;
  };

  segBar.onmousedown = (e) => {
    _dragStartX = e.clientX;
    const rect = segBar.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const pct = x / rect.width;
    if (pct >= 0 && pct <= 1) {
      _onDragMove(e); // immediate preview
    }
    document.addEventListener('mousemove', _onDragMove);
    document.addEventListener('mouseup', _onDragEnd);
    e.preventDefault();
  };
}
```

- [ ] **Step 4: Update `_playPreviewSegment()` to call `renderPreviewBar()` and update seg name**

At the end of `_playPreviewSegment()` (after the counter update at line 85), add a call to update the preview bar:

Replace lines 77-85 (the setStatus + highlight + counter block) with:
```js
  setStatus(`预览 [${state.previewIndex + 1}/${p.sequence.length}] ${seg.title || seg.index}`, 'ok');

  // Update highlight in plan panel
  document.querySelectorAll('.plan-seg').forEach(el => {
    el.classList.toggle('preview-active', parseInt(el.dataset.previewIndex) === state.previewIndex);
  });

  // Update preview bar
  renderPreviewBar();
  const segNameEl = $('#preview-seg-name');
  if (segNameEl) segNameEl.textContent = `${state.previewIndex + 1}/${p.sequence.length} ${seg.title || seg.index}`;

  // Update play/stop button
  const playBtn = $('#btn-play-preview');
  if (playBtn) {
    playBtn.innerHTML = `${icon('stop', 14)}`;
    playBtn.classList.add('preview-active');
    playBtn.title = '停止预览';
    playBtn.onclick = stopPreview;
  }
```

- [ ] **Step 5: Update `stopPreview()` to reset preview bar**

Add to the end of `stopPreview()` (after `setStatus` at line 52):
```js
  renderPreviewBar();
  const segNameEl = $('#preview-seg-name');
  if (segNameEl) segNameEl.textContent = '预览已停止';
  const playBtn = $('#btn-play-preview');
  if (playBtn) {
    playBtn.innerHTML = `${icon('play', 14)}`;
    playBtn.classList.remove('preview-active');
    playBtn.title = '预览播放';
    playBtn.onclick = startPreview;
  }
```

- [ ] **Step 6: Update `startPreview()` to set initial preview bar state**

Add before the `import('./editor.js')` call at line 41:
```js
  renderPreviewBar();
  const segNameEl = $('#preview-seg-name');
  if (segNameEl) segNameEl.textContent = `1/${p.sequence.length} ${p.sequence[0]?.title || p.sequence[0]?.index || ''}`;
  const playBtn = $('#btn-play-preview');
  if (playBtn) {
    playBtn.innerHTML = `${icon('stop', 14)}`;
    playBtn.classList.add('preview-active');
    playBtn.title = '停止预览';
    playBtn.onclick = stopPreview;
  }
```

- [ ] **Step 7: Update `setupPlayer()` — add seeking guard + prev/next button bindings**

Change the `timeupdate` handler (line 99) to add `!player.seeking`:
```js
    if (state.previewActive && !player.seeking && state._previewEndTime !== null && player.currentTime >= state._previewEndTime) {
```

At the end of `setupPlayer()` (before line 114 / `player.onerror`), add:
```js
  // Preview bar buttons
  const prevBtn = $('#btn-prev-seg');
  if (prevBtn) {
    prevBtn.innerHTML = `${icon('chevron_right', 14)}`;
    prevBtn.style.transform = 'scaleX(-1)';
    prevBtn.onclick = () => {
      if (!state.previewActive) return;
      const p = state.plan;
      if (!p || !p.sequence || !p.sequence.length) return;
      state.previewIndex = Math.max(0, state.previewIndex - 1);
      _playPreviewSegment();
    };
  }
  const nextBtn = $('#btn-next-seg');
  if (nextBtn) {
    nextBtn.innerHTML = `${icon('chevron_right', 14)}`;
    nextBtn.onclick = () => {
      if (!state.previewActive) return;
      const p = state.plan;
      if (!p || !p.sequence || !p.sequence.length) return;
      state.previewIndex = Math.min(p.sequence.length - 1, state.previewIndex + 1);
      _playPreviewSegment();
    };
  }
  const playBtn = $('#btn-play-preview');
  if (playBtn) {
    playBtn.innerHTML = `${icon('play', 14)}`;
    playBtn.onclick = startPreview;
  }

  // Init drag handler
  _setupPreviewBarDrag();
```

- [ ] **Step 8: Update exports to include `renderPreviewBar`**

Update the export block at the end:
```js
export {
  playVideoSegment,
  startPreview,
  stopPreview,
  _playPreviewSegment,
  setupPlayer,
  renderPreviewBar,
};
```

- [ ] **Step 9: Run lint and commit**

```bash
git add vlog_tool/ui/static/src/viewer.js
git commit -m "feat(ui): add preview bar rendering and interaction handlers for R-012"
```

---

### Task 4: Remove inline preview buttons from editor.js

**Files:**
- Modify: `vlog_tool/ui/static/src/editor.js:250-280`

- [ ] **Step 1: Replace inline preview button block**

Replace lines 250-257 (the `<h3>` + preview buttons block):
```js
    <h3>顺序 (sequence) — ${(p.sequence || []).length} 项</h3>
    <div style="display:flex;gap:6px;margin-bottom:8px;">
      ${state.previewActive
        ? `<button id="btn-stop-preview" class="btn-primary" style="flex:1">${icon('stop', 16)} 停止预览</button>
           <span class="hint" style="display:flex;align-items:center;color:var(--accent);font-weight:500;">${state.previewIndex + 1}/${(p.sequence || []).length}</span>`
        : `<button id="btn-start-preview" class="btn-primary" style="flex:1">${icon('play', 16)} 预览播放</button>`
      }
    </div>
```

With simply:
```js
    <h3>顺序 (sequence) — ${(p.sequence || []).length} 项</h3>
```

- [ ] **Step 2: Remove start btn / stop btn event binding code**

Remove lines 277-280:
```js
  const startBtn = $('btn-start-preview');
  if (startBtn) startBtn.onclick = startPreview;
  const stopBtn = $('btn-stop-preview');
  if (stopBtn) stopBtn.onclick = stopPreview;
```

- [ ] **Step 3: Remove unused imports for `startPreview`/`stopPreview`**

Remove from the import at line 14:
```js
import { playVideoSegment, startPreview, stopPreview } from './viewer.js';
```
Replace with:
```js
import { playVideoSegment } from './viewer.js';
```

Also remove unused `icon` import if it's only used for preview buttons. Check if `icon` is used elsewhere in editor.js first (it's used in plan save button at line ~240, renderConfig, etc. — keep it).

- [ ] **Step 4: Add `plan-mode` class toggling in `renderPlan()`**

Add at the start of `renderPlan()` (after `const pane = ...` at line ~237):
```js
  // Show preview bar below player
  $('player-pane').classList.add('plan-mode');
  import('./viewer.js').then(mod => mod.renderPreviewBar());
```

- [ ] **Step 5: Commit**

```bash
git add vlog_tool/ui/static/src/editor.js
git commit -m "feat(ui): remove inline preview buttons, delegate to bar in viewer.js for R-012"
```

---

### Task 5: Add plan-mode toggling to sidebar.js entity switches

**Files:**
- Modify: `vlog_tool/ui/static/src/sidebar.js`

- [ ] **Step 1: Add `plan-mode` removal alongside each `stopPreview()` call**

In `selectVideo()` (line 301-302): After `stopPreview()`, add:
```js
  $('player-pane').classList.remove('plan-mode');
```

In `selectPlan()` (line 346-347): After `stopPreview()`, add:
```js
  $('player-pane').classList.add('plan-mode');
```

In `selectRun()` (line 364-365): After `stopPreview()`, add:
```js
  $('player-pane').classList.remove('plan-mode');
```

In `selectConfig()` (line 375-376): After `stopPreview()`, add:
```js
  $('player-pane').classList.remove('plan-mode');
```

In `selectLogs()` (line 400-401): After `stopPreview()`, add:
```js
  $('player-pane').classList.remove('plan-mode');
```

In `setSource()` (line 412): After `stopPreview()`, add:
```js
  $('player-pane').classList.remove('plan-mode');
```

In `goToRunTab()` (line 448): check if there's a `stopPreview()` call — if not, add:
```js
  $('player-pane').classList.remove('plan-mode');
```

Also add `$` import if not already present:
```js
import { $, ... } from './utils.js';
```

- [ ] **Step 2: Commit**

```bash
git add vlog_tool/ui/static/src/sidebar.js
git commit -m "feat(ui): toggle plan-mode class on entity switch for R-012"
```
