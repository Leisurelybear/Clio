# Design: Sidebar optimization (sticky compact header, video list search/filter, accurate per-stage counts)

**Date**: 2026-08-08
**Status**: Draft — awaiting implementation plan
**Scope**: Rework the left sidebar of the web UI (`clio/ui/static`) across three axes: ① fixed compact top task area, ② video list optimized for many videos (search + status filter chips), ③ replace the inaccurate bottom pipeline indicator with an accurate per-video-VIEW count bar.
**Approach**: Frontend-only (HTML/CSS/ES modules). No new backend routes.
**Related**: `clio/ui/static/index.html`, `clio/ui/static/style.css`, `clio/ui/static/src/sidebar-data.js`, `clio/ui/static/src/sidebar.js`, `clio/ui/static/src/main.js`, `clio/ui/static/src/video-menu.js`, `clio/ui/static/src/runner.js`, `clio/ui/static/src/sidebar-rerun.js`, `clio/ui/static/src/editor-plan.js`, `clio/ui/static/src/__tests__/sidebar-data.test.js`, `docs/analysis/2026-07-20-full-project-review.md` (R-040 B-1 related work on missing-key banner is untouched).

## 1. Goals and non-goals

### Goals

1. **① 固定紧凑的顶部任务区**: The top area (project name + entity navigation) stays **sticky** while the video list scrolls, and occupies **less vertical space**:
   - Merge 打开项目 / 新建 / 打开目录 into a single `打开项目 ▾` dropdown button in the header row.
   - Re-render the 5 entity nav items (编排/设置/运行/日志/统计) as a **single compact icon row** instead of 5 tall vertical rows.
2. **② 视频列表多视频体验**: Add a **search box** (index / filename / title) and **status filter chips** above the list; click a chip to reduce the list to matching videos. Preserve the existing row layout: cover thumbnail + name + title; list **stays in the initial order** (no new sort control).
3. **③ 阶段指示准确化**: Remove the bottom **流水线 `step-list`** whose "done" truth came from coarse directory scans (`_detect_steps` in `project_service.py:66`). Replace with a **per-video count bar** (`压缩/分析/口播/转录`) computed from each video's own artifact fields in the currently selected source view — click a cell to filter the list to videos missing (or done with) that stage.

### Non-goals

- No new backend endpoints; all counts/filters derive from already-loaded `state.videos`.
- No changes to run-preview (`runner.js` run tab `run-step-list`) or processing state; only the sidebar `#step-list` block is replaced.
- No thumbnails generation changes; existing `/api/cover` thumbnails remain.
- No sorting controls, no drag reorder, no virtualized list (rendering stays DOM-based list).
- Keyboard shortcuts 1–5 for entity switching keep working.

### Success criteria

- Top module gets sticky; scrolling a long video list leaves project + nav visible; sidebar top block is visually smaller than today.
- The three project actions (open/new/reveal dir) accessible from the header dropdown, wiring preserved.
- `renderVideoList` re-renders when: search text changes (debounced), a chip is toggled, or a count-bar cell is clicked. `state.videos.length` count text stays on the 视频 heading.
- Chips (and their live counts) match video fields in the current source view:
  - `压缩 (未压缩)` — original view only, `isCompressStepDone` false;
  - `缺分析` — `!text_json`;
  - `缺口播` — `!script_json`;
  - `缺转录` — `!transcript_file`;
  - `离线` — `video.missing`;
  - 全部 — count of currently loaded list (by source).
- Count-bar cells show `done/total` computed from the **same view's** video list. Backend not queried.
- `state.steps`-driven UI removal is complete: `#step-list` removed, `renderSteps` call sites updated, no dangling references/tests.
- Vitest runs for `clio/ui/static/src/__tests__/*` still green; `npm test` passes.

## 2. Current behavior (verified)

- layout: `#sidebar .sidebar-scroll` is `flex:1; overflow-y:auto`; the whole block (project-actions buttons + `#project-list` entities + 视频 h3 + `#video-list` + 流水线 h3 + `#step-list`) scrolls together (`style.css:531`).
- `project-actions` hold 3 sidebar buttons (打开项目/打开目录/新建); `project-list` has 5 tall rows.
- Video rows (`renderVideoItem` in `sidebar-data.js`) render cover (`videoThumbHtml`) + info (name/`video-title`/step badges `video-step-badges` with labels 压缩/分析/口播/转录) + menu.
- Bottom `#step-list` is filled by `renderSteps()` from `state.steps={compress,analyze,scripts,plan,label,cut}`; labels map keys to Chinese in the function, fed from `/_api/project` `steps` (coarse FS scans `_detect_steps`).
- `renderSteps()` is called from `main.js:391/530`, `sidebar-rerun.js:160`, `runner.js:517`, `editor-plan.js:861-862`, and re-exported via `sidebar.js`.

## 3. Design

### 3.1 HTML structure (`index.html`)

```html
<aside id="sidebar">
  <div class="panel-header">… (unchanged project name) …</div>
  <div class="sidebar-scroll">
    <!-- ① 重做顶部: header (sticky) + project dropdown + nav icon row -->
    <div class="sidebar-top">
      <div class="sidebar-top-row sidebar-sticky">
        <span id="proj-name-sidebar" class="sidebar-top-title">加载中...</span>
        <div class="sidebar-project-menu">
          <button id="btn-project-menu" class="sidebar-btn compact" type="button" title="项目操作">
            打开项目 ▾
          </button>
          <div id="project-menu" class="project-menu" hidden>
            <button id="btn-open-project" …>打开项目</button>
            <button id="btn-new-project" …>新建项目</button>
            <button id="btn-reveal-project-sidebar" …>打开目录</button>
          </div>
        </div>
      </div>
      <ul id="project-list" class="project-list-icons">… 5 <li data-entity=…> icon rows …/ul>
      <!-- NO 打开项目/新建/打开目录 buttons on their own row anymore -->
    </div>

    <h3>视频 <span id="video-count" …></h3>
    <div class="video-list-actions">（保留 添加视频 / 选择视频 两个按钮）</div>
    <div id="offline-summary" …></div>

    <!-- ② 搜索 + chips -->
    <div id="video-filter-bar" class="video-filter-bar">
      <input id="video-filter-input" type="text" placeholder="搜索 index / 文件名 / 标题…" autocomplete="off">
      <div id="video-filter-chips" class="video-filter-chips"></div>
    </div>

    <ul id="video-list"></ul>

    <!-- ③ 替换掉 流水线 h3 + #step-list：改为精确计数条 -->
    <div id="stage-count-bar" class="stage-count-bar">
      <div class="stage-count-cell" data-stage="compress">压缩<br><b>…</b></div>
      <div class="stage-count-cell" data-stage="analyze">分析<br><b>…</b></div>
      <div class="stage-count-cell" data-stage="voiceover">口播<br><b>…</b></div>
      <div class="stage-count-cell" data-stage="transcribe">转录<br><b>…</b></div>
    </div>
  </div>
</aside>
```

Notes:
- The `.sidebar-sticky` wrapper (`thead` sticky) implemented with `position: sticky` so the header + icons stay fixed while `.sidebar-scroll` scrolls; add enough padding/bottom so sticky works (`z-index`).
- IDs `btn-open-project` / `btn-new-project` / `btn-reveal-project-sidebar` keep their existing onclick wiring in `main.js` — only the DOM location changes (they move inside `.project-menu`).

### 3.2 Filter state and rendering (`sidebar-data.js`)

- Add `state.videoFilter = { q: '', stages: new Set() }` (chip single-selection semantics: `state.videoFilter.stages` holds the active single chip name or empty = 全部).
- New pure helper: `matchVideoFilter(video, source, q)` (exported for tests):
  - matches q (lowercased, trimmed) against `video.index`, file name (stripped numeric prefix like current display), and `video.title`.
  - stage chips map to the per-source predicates below.
- Per-source stage predicate map (re-factored from `isCompressStepDone` semantics in `video-menu.js`):
  - `compress` — original view: `!isCompressStepDone(video, source)` means "缺压缩"; compressed view: all online videos already compressed (chip hidden in compressed view).
  - `analyze` — `!video.text_json`
  - `voiceover` — `!video.script_json`
  - `transcribe` — `!video.transcript_file`
  - `offline` — `!!video.missing`
- `renderVideoList` applies filters at the top: `const visible = state.videos.filter(v => matchVideoFilter(v, state.source))`; groups/segment-group headers are only rendered for visible items; `video-count` on the heading shows `visible/total`.
- Debounced input (`input` event, ~150ms) sets `state.videoFilter.q` and calls `renderVideoList`.
- Chip rendering: counts = `filteredByStage(videos, '缺X')` then label `缺分析 (n)`. Chips are **single-select**: clicking a chip activates it; clicking again or the 全部 chip clears back to the full list.
- `updateStageCountBar()` computes per-stage counts from current source's video list (full list, regardless of filter — counts are world-view; live on sidebar). Called from `renderVideoList`.

### 3.3 Count bar (replace `renderSteps`)

- Remove `#step-list` + `styles` for `.step-list/.step-item`; remove `renderSteps()` and its export paths.
- New `renderStageCountBar()` in `sidebar-data.js`:
  - cells: 压缩 / 分析 / 口播 / 转录 (= `buildVideoStepBadges` four labels).
  - per-cell `done` = images in current source matching the predicate; `total` = `state.videos.length`.
  - if `activeStage` matches a cell, add `colors`; clicking a cell toggles filter chip to that stage (missing) and shows done count in title/tooltip.
- Update all former `renderSteps()` callsites (all replaced with `renderVideoList()`, which also refreshes the count bar):
  - `main.js:391/530`
  - `sidebar-rerun.js:160`
  - `runner.js:517`
  - `editor-plan.js:862` (`state.steps.cut = true`) → drop the `steps.cut` write (cut is not a per-file stage cell) + replace with `renderVideoList()`.
  - `sidebar-data.js:167` (`state.steps = proj.steps`): keep stored but no longer read by the sidebar; mark deprecated, no test change.
- Update/extend existing Vitest for `sidebar-data` (`__tests__/sidebar-data.test.js`) — add `matchVideoFilter` unit coverage; adapt any test asserting `.step-list`.

### 3.4 Row bump: step badges → small dots; per-video menu preserved

- In `renderVideoItem`, replace `.video-step-badges` (labels) with `.video-step-dots` rendering 4 dots (● done / ○ pending) colored per stage, tooltip = full "压缩: done" line. Keeps per-file signal while shrinking height.
- The per-video **⋮ action menu** (`video-actions` in `renderVideoItem`) is **unchanged**: `.menu-btn` + portal dropdown menu (单个视频 压缩/重分析/重跑口播/Whisper 转录/重跑全部/重新关联/移除项目) still renders on the right side of every row. Only the step badges row below the name is replaced by dots; thumb + name + title + duration + match badge + menu all stay.
- Existing `video-step-badges.done/running` classes in `video-menu.js` unchanged; keep `buildVideoStepBadges` (used by tests) but the sidebar renders dots from it.

### 3.5 CSS (`style.css`)

- `#sidebar .sidebar-top-row` sticky; `.project-list-icons .project-item` becomes a single wrap row: `display:flex; flex-wrap: wrap; gap:4px; padding:4px 6px;` with each `.project-item` shrinking to `flex:1` (icon-centered, min-height 32px) instead of the tall vertical entries.
- `.project-menu` dropdown styling (absolute, top-right, `hidden` toggling).
- `.video-filter-bar`, `.video-filter-chips`, `.video-filter-chip` (active state, warns color per chip), `.video-filter-input`.
- `.stage-count-bar` grid 4 columns near `.video-list-actions`/offline area styling; hover/click cursor.
- `.video-step-dots` sizes.
- Remove `.step-list`, `.step-item`, `.step-icon`.

## 5. Error/edge handling

- Debounced search: no request; pure client-side; `renderVideoList` handles empty visible → show a lightweight empty filter state ("没有匹配的视频，清除筛选" button).
- Cleared/empty chips: 全部 chip always present; clicking it resets `stages`.
- Offline videos are filtered out of selectable-only flows but still counted.
- `state.steps` removal: no consumer left after this change (`editor-plan.js` writes removed), keep assignment line for future.
- Sticky header must not cover video rows — test with scroll in desktop window during review.

## 6. Testing

- Vitest: new pure helpers `matchVideoFilter` + cross-view matrix tests (original vs compressed), chip single-select transitions, empty-state search result.
- Adapt existing sidebar-data tests to no `step-list`; add a test that `renderStageCountBar` populates 4 cells with correct counts from a small fixture.
- Frontend manually: `python main.py --serve --no-browser` and verify sticky top, chips filter, count-bar click filters, `.superpowers\brainstorm\` unaffected.

## 7. Out of scope / future

- Virtualized list for 1000+ videos (later).
- Per-group filtering (segmented grouping columns).
- Persisting filter/search across sessions.
- Sorting by stage (explicitly requested NOT to add a sorting control).

## 8. Review plan

1. Implement in one commit: sidebar → `feat(ui): compact sticky sidebar with video filters and accurate stage counts` commit.
2. Update docs/README if needed (none expected; UI-only).
3. Confirm vitest + fast backend tests pass.