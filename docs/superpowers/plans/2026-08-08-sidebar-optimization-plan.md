# Sidebar Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the web-UI left sidebar so the top task area is fixed/compact, the video list scales to many videos via search + status chips, and the coarse 流水线 indicator is replaced by an accurate per-file count bar.

**Architecture:** Frontend-only (`clio/ui/static`). New pure helper module `sidebar-video-filter.js` for stage/search predicates (unit-testable), consumed by `sidebar-data.js`. `index.html` is restructured: project action buttons move into a header dropdown, entity nav becomes one compact icon row and the nav row is `position:sticky`; search + chips added above the list; the bottom `流水线` block is replaced by a clickable 4-cell count bar. `renderSteps` is removed and its four call sites updated.

**Tech Stack:** ES modules + vanilla CSS (`static/index.html`, `static/style.css`, `static/src/*.js`), Vitest; `npm test` for frontend.

**Spec:** `docs/superpowers/specs/2026-08-08-sidebar-optimization-design.md`

---

## File structure

| File | Responsibility | Change |
|---|---|---|
| `clio/ui/static/src/sidebar-video-filter.js` | NEW: pure stage-status / search-match helpers | Create (unit-testable) |
| `clio/ui/static/src/__tests__/sidebar-video-filter.test.js` | NEW: unit tests | Create |
| `clio/ui/static/src/sidebar-data.js` | list render applies filters; chips/count-bar/X render | Modify |
| `clio/ui/static/src/sidebar.js` | re-export surface, drop `renderSteps` | Modify |
| `clio/ui/static/src/state.js` | add `videoFilter` | Modify |
| `clio/ui/static/src/main.js` | drop `renderSteps`, wire project dropdown + filter bar | Modify |
| `clio/ui/static/src/runner.js` | `renderSteps()` call site | Modify |
| `clio/ui/static/src/sidebar-rerun.js` | import + call site | Modify |
| `clio/ui/static/src/editor-plan.js` | `state.steps.cut` / `renderSteps()` cleanup | Modify |
| `clio/ui/static/index.html` | sidebar structure | Modify |
| `clio/ui/static/style.css` | new classes, drop `step-list` | Modify |
| `clio/ui/static/src/__tests__/sidebar-select-video.test.js` | mocked export list still valid (renderSteps leftover harmless) | No change |

---

## Task 1: Pure helpers module (TDD)

**Files:**
- Create: `clio/ui/static/src/sidebar-video-filter.js`
- Test: `clio/ui/static/src/__tests__/sidebar-video-filter.test.js`

- [ ] **Step 1: Write failing tests**

`clio/ui/static/src/__tests__/sidebar-video-filter.test.js`:

```js
import { describe, expect, it } from 'vitest';
import {
  STAGE_CELLS,
  videoStageDone,
  videoMissingStage,
  buildVideoStageStatuses,
  chipDefsForSource,
  countChipStates,
  countStageSummary,
  matchVideoSearch,
} from '../sidebar-video-filter.js';

const onlineCompressed = { file: 'GX010195.mp4', index: '1', title: '凡尔赛', text_json: 't.json', script_json: 's.json', transcript_file: 'tr.json' };

describe('videoStageDone', () => {
  it('compressed view: compress done unless missing', () => {
    expect(videoStageDone(onlineCompressed, 'compressed', 'compress')).toBe(true);
    expect(videoStageDone({ ...onlineCompressed, missing: true }, 'compressed', 'compress')).toBe(false);
  });
  it('original view: compress done only when matched', () => {
    expect(videoStageDone({ ...onlineCompressed, match: { file: 'x.mp4', missing: false } }, 'original', 'compress')).toBe(true);
    expect(videoStageDone({ ...onlineCompressed, match: null }, 'original', 'compress')).toBe(false);
  });
  it('analyze/voiceover/transcribe map from artifact fields', () => {
    expect(videoStageDone({ text_json: 't' }, 'compressed', 'analyze')).toBe(true);
    expect(videoStageDone({}, 'compressed', 'analyze')).toBe(false);
    expect(videoStageDone({ script_json: 's' }, 'compressed', 'voiceover')).toBe(true);
    expect(videoStageDone({ transcript_path: 'x' }, 'compressed', 'transcribe')).toBe(true);
  });
});

describe('videoMissingStage', () => {
  it('offline key reflects missing flag', () => {
    expect(videoMissingStage({ missing: true }, 'compressed', 'offline')).toBe(true);
  });
  it('inverts done for file stages', () => {
    expect(videoMissingStage({}, 'compressed', 'analyze')).toBe(true);
  });
});

describe('buildVideoStageStatuses', () => {
  it('contains one key per STAGE_CELL', () => {
    const s = buildVideoStageStatuses(onlineCompressed, 'compressed');
    expect(STAGE_CELLS.map(c => c.key)).toEqual(['compress', 'analyze', 'voiceover', 'transcribe']);
    expect(s).toEqual({ compress: true, analyze: true, voiceover: true, transcribe: true });
  });
});

describe('chipDefsForSource / countChipStats', () => {
  it('non-compress chip (缺压缩) only in original view', () => {
    const orig = chipDefsForSource('original').map(c => c.key);
    expect(orig).toContain('compress');
    expect(chipDefsForSource('compressed').map(c => c.key)).not.toContain('compress');
  });
  it('counts chips over a list', () => {
    const list = [
      { missing: false },
      { missing: true },
      { text_json: 1 },
      { script_json: 1, transcript_path: 1 },
    ];
    const stats = countChipStats(list, 'compressed');
    const byKey = Object.fromEntries(stats.map(s => [s.key, s.count]));
    expect(byKey.offline).toBe(1);      // #1 only
    expect(byKey.analyze).toBe(2);      // #0,#3 missing text_json
    expect(byKey.voiceover).toBe(3);    // #0,#1,#2
    expect(byKey.transcribe).toBe(3);   // #0,#1,#2
  });
});

describe('countStageSummary', () => {
  it('per-stage done/total cells', () => {
    const sum = countStageSummary([{ ...onlineCompressed }, { ... onlineCompressed, missing: true }], 'compressed');
    const by = Object.fromEntries(sum.map(s => [s.key, s]));
    expect(by.compress.done).toBe(1);
    expect(by.compress.total).toBe(2);
    expect(by.analyze.done).toBe(2);
  });
});

describe('matchVideoSearch', () => {
  const v = { index: '001', file: 'GG063.HQ.mp4' };
  it('matches index / name / title case-insensitively', () => {
    expect(matchVideoSearch({ ...v, title: '凡尔赛' }, '凡尔赛')).toBe(true);
    expect(matchVideoSearch({ ...v, title: ''' }, 'GG063')).toBe(true);
    expect(matchVideoSearch({ ...v }, 'no-such')).toBe(false);
  });
  it('treats empty query as match-all', () => {
    expect(matchVideoSearch(v, '')).toBe(true);
  });
});
```

Fix the test typo in my draft: the `matchVideoSearch` example used get `{ title: 'GG063'` — use a valid object. When writing the real file use:

```js
expect(matchVideoSearch({ index: '001', file: 'GG063.HQ', title: 'test' }, 'gg063')).toBe(true);
```

- [ ] **Step 2: Run and confirm FAIL**

Run: `npm test -- clio/ui/static/src/__tests__/sidebar-video-filter.test.js`
Expected: FAIL — `Cannot find module '../sidebar-video-filter.js'`

- [ ] **Step 3: Create the module**

`clio/ui/static/src/sidebar-video-filter.js`:

```js
import { isCompressStepDone } from './video-menu.js';

// exact 4 per-file stages shown in rows, chips, and the bottom count bar
export const STAGE_CELLS = [
  { key: 'compress', label: '压缩' },
  { key: 'analyze', label: '分析' },
  { key: 'voiceover', label: '口播' },
  { key: 'transcribe', label: '转录' },
];

/** True if the given per-file stage is complete for `video` in `source`. */
export function videoStageDone(video, source, key) {
  if (video.missing) return false;
  switch (key) {
    case 'compress':
      return source === 'compressed' ? true : isCompressStepDone(video, 'original');
    case 'analyze':
      return !!video.text_json;
    case 'voiceover':
      return !!video.script_json;
    case 'transcribe':
      return !!video.transcript_path;
    default:
      return false;
  }
}

/** Map of stage key → done flag. */
export function buildVideoStageStatuses(video, source) {
  const out = {};
  for (const c of STAGE_CELLS) out[c.key] = videoStageDone(video, source, c.key);
  return out;
}

/** True when `video` is missing stage `key` (or offline for key==='offline'). */
export function videoMissingStage(video, source, key) {
  if (key === 'offline') return !!video.missing;
  return !videoStageDone(video, source, key);
}

const CHIP_DEFS = {
  original: [
    { key: 'compress', label: '未压缩' },
    { key: 'analyze', label: '缺分析' },
    { key: 'voiceover', label: '缺口播' },
    { key: 'transcribe', label: '缺转录' },
    { key: 'offline', label: '离线' },
  ],
  compressed: [
    { key: 'analyze', label: '缺分析' },
    { key: 'voiceover', label: '缺口播' },
    { key: 'transcribe', label: '缺转录' },
    { key: 'offline', label: '离线' },
  ],
};

/** Chip definitions valid for a source view (未压缩 only exists for original). */
export function chipDefsForSource(source) {
  return source === 'original' ? CHIP_DEFS.original : CHIP_DEFS.compressed;
}

/** [{ key, label, count }] over a full video list (counts always match the whole view). */
export function countChipStats(videos, source) {
  return chipDefsForSource(source).map((d) => ({
    key: d.key,
    label: d.label,
    count: videos.filter((v) => videoMissingStage(v, source, d.key)).length,
  }));
}

/** 4 cells { key,label,done,total } for the bottom count bar. */
export function countStageSummary(videos, source) {
  const total = videos.length;
  return STAGE_CELLS.map((c) => ({
    key: c.key,
    label: c.label,
    done: videos.filter((v) => videoStageDone(v, source, c.key)).length,
    total,
  }));
}

/** True when a query needle (trimmed-lowercased) appears in index/name/title. */
export function matchVideoSearch(video, q) {
  const needle = String(q || '').trim().toLowerCase();
  if (!needle) return true;
  const hay = [
    String(video?.index ?? ''),
    String(video?.file ?? '').replace(/^\d+_/, ''),
    String(video?.title ?? ''),
  ].join(' ').toLowerCase();
  return hay.includes(needle);
}
```

- [ ] **Step 4: Run and confirm PASS**

Run: `npm test -- --re-run clio/ui/static/src/__tests__/sidebar-video-filter.test.js`
Expected: all green. (If `--re-run` unsupported, use `npm test -- clio/ui/static/src/__tests__/sidebar-video-filter.test.js`.)

- [ ] **Step 5: Commit**

```bash
git add clio/ui/static/src/sidebar-video-filter.js clio/ui/static/src/__tests__/sidebar-video-filter.test.js
git commit -m "feat(ui): pure sidebar video filter helpers"
```

---

## Task 2: `index.html` structure

**Files:**
- Modify: `clio/ui/static/index.html`

- [ ] **Step 1: Replace the whole `#sidebar .sidebar-scroll` block**

Current block (lines 36-92) — replace from `<aside id="sidebar">` through `</aside>` (line 92) with:

```html
<aside id="sidebar">
  <div class="panel-header">
    <div class="panel-header-left">
      <span class="panel-header-icon"><svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg></span>
      <span id="proj-name-sidebar" class="value" title="当前项目名">加载中...</span>
    </div>
    <div class="sidebar-project">
      <button id="btn-project-menu" class="sidebar-btn compact" type="button" title="打开 / 新建 / 切换项目">打开项目 ▾</button>
      <div id="project-menu" class="project-menu" hidden>
        <button id="btn-open-project" class="project-menu-item" type="button" title="打开已有项目">打开项目</button>
        <button id="btn-new-project" class="project-menu-item" type="button" title="新建项目">新建项目</button>
        <button id="btn-reveal-project-sidebar" class="project-menu-item" type="button" title="在资源管理器中打开当前项目目录">打开目录</button>
      </div>
    </div>
  </div>
  <div class="sidebar-scroll">
    <ul id="project-list" class="project-list-icons">
      <li class="project-item" data-entity="plan" title="打开编排 (plan) 面板">
        <span class="icon"><svg viewBox="0 0 24 24"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="9" y1="21" x2="9" y2="9"/></svg></span>
        <span class="name">编排</span><span class="shortcut">1</span>
      </li>
      <li class="project-item" data-entity="config" title="编辑 config.yaml 配置">
        <span class="icon"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-2 2 2 2 0 01-2-2v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83 0 2 2 0 010-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 01-2-2 2 2 0 012-2h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 010-2.83 2 2 0 012.83 0l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 012-2 2 2 0 012 2v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 0 2 2 0 010 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 012 2 2 2 0 01-2 2h-.09a1.65 1.65 0 00-1.51 1z"/></svg></span>
        <span class="name">设置</span><span class="shortcut">2</span>
      </li>
      <li class="project-item" data-entity="run" title="运行流水线: 压缩→分析→口播→vlog 剪辑规划→标号">
        <span class="icon"><svg viewBox="0 0 24 24"><polygon points="5 3 19 12 5 21 5 3"/></svg></span>
        <span class="name">运行</span><span class="shortcut">3</span>
      </li>
      <li class="project-item" data-entity="logs" title="查看服务运行日志">
        <span class="icon"><svg viewBox="0 0 24 24"><polyline points="1 12 1 19 23 19 23 12"/><polyline points="22 8 12 3 2 8 2 8"/><rect x="12" y="15" width="2" height="2"/><rect x="8" y="15" width="2" height="2"/><rect x="4" y="15" width="2" height="2"/></svg></span>
        <span class="name">日志</span><span class="shortcut">4</span>
      </li>
      <li class="project-item" data-entity="tokens" title="AI token 使用统计">
        <span class="icon"><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><line x1="12" y1="8" x2="12" y2="16"/><line x1="8" y1="12" x2="16" y2="12"/></svg></span>
        <span class="name">统计</span><span class="shortcut">5</span>
      </li>
    </ul>

    <h3>视频 <span id="video-count" class="muted"></span></h3>
    <div class="video-list-actions">
      <button id="btn-add-videos" class="sidebar-btn" title="从文件夹选择视频文件添加到项目">
        <span class="icon"><svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg></span>
        添加视频
      </button>
      <button id="btn-select-videos" class="sidebar-btn" style="display:none" title="选择部分视频运行">
        <span class="icon"><svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"/></svg></span>
        选择视频
      </button>
    </div>
    <div id="offline-summary" class="offline-summary" hidden></div>

    <div id="video-filter-bar" class="video-filter-bar">
      <input id="video-filter-input" type="text" placeholder="搜索 index / 文件名 / 标题…" autocomplete="off">
      <div id="video-filter-chips" class="video-filter-chips"></div>
    </div>

    <ul id="video-list"></ul>

    <div id="stage-count-bar" class="stage-count-bar" aria-label="各阶段完成计数"></div>
  </div>
</aside>
```

Note: the ORIGINAL project-action triple buttons + `#project-list` (5 rows) + `流水线` heading + `#step-list` are gone; the three action buttons moved inside `.project-menu`, their **IDs unchanged**.

- [ ] **Step 2: Verify no `流水线` / `step-list` references remain in `index.html`**

`Get-Content clio/ui/static/index.html | Select-String "step-list|流水线|project-actions"`
Expected: empty.

- [ ] **Step 3: Commit**

```bash
git add clio/ui/static/index.html
git commit -m "feat(ui): sidebar html — sticky dropdown header, filter row, stage count bar"
```

---

## Task 3: `style.css`

**Files:**
- Modify: `clio/ui/static/style.css`

- [ ] **Step 1: Replace the old step-list / project-actions chunks**

Remove these blocks:
```css
#project-actions { padding: var(--space-2) var(--space-3); display: flex; flex-wrap: wrap; gap: var(--space-2); }
#project-list, #video-list { list-style: none; padding: var(--space-1) 0; margin: 0; }
/* ── Step Pipeline List ──────── */
.step-list { ... }
.step-item { ... }
.step-item .step-icon { ... }
.step-item.done .step-icon { ... }
.step-item .step-label { ... }
.step-item.done .step-label { ... }
```

- [ ] **Step 2: Add the new sidebar structure styles**

Insert after the `.panel-header` / `.sidebar-scroll` block (around line 531):

```css
/* Sticky header: project dropdown in the panel bar */
.panel-header { position: relative; }
.sidebar-project { position: relative; margin-left: auto; }
#btn-project-menu { font-size: var(--text-xs); padding: 3px 9px; }
.project-menu {
  position: absolute; right: 0; top: calc(100% + 4px); z-index: 30;
  background: var(--bg-surface-2); border: 1px solid var(--border);
  border-radius: var(--radius-sm); padding: 4px; min-width: 150px;
  box-shadow: 0 6px 18px rgba(0,0,0,.4);
}
.project-menu-item {
  display: block; width: 100%; text-align: left;
  padding: 7px 10px; background: none; border: none; cursor: pointer;
  font: inherit; font-size: var(--text-sm); color: var(--text-primary);
  border-radius: var(--radius-sm);
}
.project-menu-item:hover { background: var(--bg-hover); }

/* Sidebar top: compact sticky nav row */
#project-list.project-list-icons {
  list-style: none; margin: 0; padding: 6px 6px 4px;
  display: flex; gap: 4px; flex-wrap: wrap;
  position: sticky; top: 0; z-index: 20;
  background: var(--bg-surface);
  border-bottom: 1px solid var(--border);
}
#project-list.project-list-icons .project-item {
  flex: 1; min-width: 34px; min-height: 30px;
  flex-direction: column; gap: 1px; padding: 3px 2px; margin: 0;
}
#project-list.project-list-icons .project-item .name { display: none; }
#project-list.project-list-icons .project-item .shortcut { font-size: 8px; padding: 0 3px; }
#project-list.project-list-icons .project-item .icon { width: 16px; height: 16px; }

/* Video filter bar */
.video-filter-bar { padding: 4px 8px 6px; }
#video-filter-input {
  width: 100%; box-sizing: border-box;
  background: var(--bg-input, var(--bg-surface-2));
  border: 1px solid var(--border); border-radius: var(--radius-sm);
  color: var(--text-primary); padding: 5px 8px; font: inherit; font-size: var(--text-sm);
}
#video-filter-input:focus { outline: none; border-color: var(--border-focus); }
.video-filter-chips {
  display: flex; gap: 4px; flex-wrap: wrap; margin-top: 4px;
}
.video-filter-chip {
  font-size: 10px; padding: 2px 8px; border-radius: 10px; cursor: pointer;
  background: var(--bg-surface-2); color: var(--text-secondary);
  border: 1px solid var(--border-light);
}
.video-filter-chip.active { background: var(--accent-bg); color: var(--accent); border-color: var(--accent); }

/* Video rows: step indicators → compact 4 dots */
.video-step-dots {
  display: flex; gap: 3px; margin-top: 2px; align-items: center;
}
.video-step-dot {
  width: 8px; height: 8px; border-radius: 50%;
  background: var(--bg-surface-3); display: inline-block;
}
.video-step-dot.done { background: var(--success); }
.video-step-dot.pending { background: var(--bg-surface-3); }

/* Bottom stage count bar */
.stage-count-bar {
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 4px;
  padding: 6px 8px; border-top: 1px solid var(--border);
  background: var(--bg-surface);
}
.stage-count-cell {
  text-align: center; font-size: 10px; color: var(--text-secondary);
  background: var(--bg-surface-3); border: 1px solid var(--border-light);
  border-radius: var(--radius-sm); padding: 4px 2px; cursor: pointer;
  line-height: 1.35;
}
.stage-count-cell .num { font-weight: 700; font-size: 12px; display: block; }
.stage-count-cell.active { border-color: var(--accent); color: var(--accent); }
.stage-count-cell:hover { border-color: var(--border-focus); }
```

- [ ] **Step 3: Manual visual check + commit**

Run `python main.py serve --no-browser`, open the URL — the sidebar shows: header bar with 打开项目 ▾ dropdown; one icon nav row at top (5 icons); search + chips; 4-cell count bar at the bottom. No old 打开项目/新建/打开目录 3-button row.

```bash
git add clio/ui/static/style.css
git commit -m "feat(ui): sidebar styles — sticky compact nav, chips, step dots, count bar"
```

---

## Task 4: Filter + count bar rendering (`sidebar-data.js`)

**Files:**
- Modify: `clio/ui/static/src/sidebar-data.js`
- Modify: `clio/ui/static/src/state.js`

- [ ] **Step 1: Add filter state**

`state.js` — append to the object:

```js
  videoFilter: { q: '', stage: '' },  // stage: '' | 'compress' | 'analyze' | 'voiceover' | 'transcribe' | 'offline'
  _filterDebounce: null,
```

- [ ] **Step 2: Import helpers and add rendering**

At top of `sidebar-data.js` import:

```js
import {
  chipDefsForSource,
  countChipStats,
  countStageSummary,
  matchVideoSearch,
  videoMissingStage,
  STAGE_CELLS,
} from './video-filter.js';   // path: ./sidebar-video-filter.js
```

(The import path is `./sidebar-video-filter.js`.)

Add after `loadVideos`:

```js
let _filterInputBound = false;
export function initVideoFilterBar() {
  if (_filterInputBound) return;
  _filterInputBound = true;
  const input = $('video-filter-input');
  if (!input) return;
  input.addEventListener('input', () => {
    clearTimeout(state._filterDebounce);
    state._filterDebounce = setTimeout(() => {
      state.videoFilter.q = input.value;
      renderVideoList();
    }, 150);
  });
}
```

- [ ] **Step 3: Wire filtering into `renderVideoList`**

Edit `renderVideoList()` (replaces the pre-loop body). After the existing `if (!ul) return;` and before loops, the first `renderOfflineSummary();` stays; **insert** the filter + render chips:

```js
  const q = state.videoFilter?.q || '';
  const stage = state.videoFilter?.stage || '';
  const visible = state.videos.filter((v) =>
    matchVideoSearch(v, q) && (!stage || videoMissingStage(v, state.source, stage))
  );

  const countEl = $('video-count');
  if (countEl) countEl.textContent = `(${visible.length}/${state.videos.length})`;

  renderFilterChips();
  renderStageCountBar();
```

Then change all the collection loops from `state.videos` to `visible`:
- group building: `for (const v of state.videos.filter(...))` → `for (const v of visible.filter(...))`
- top-level loop: `for (const v of state.videos)` → `for (const v of visible)`
- `if (!state.videos.length)` → keep as is (empty check before computing `visible` is fine, but the empty-state branch must remain; keep the whole `#videos.length === 0` early-return branch **before** the filter code).

Implementation order inside `renderVideoList` after empty-check block:

```js
  const visible = state.videos.filter(...);
  updateVideoCount(visible.length);
  renderFilterChips();
  renderStageCountBar();

  // groups built from `visible`
  ...
```

Avoid name collision with existing `groups`/`renderedGroups`.

- [ ] **Step 4: Add `renderFilterChips` + `renderStageCountBar` + `updateVideoCount`**

Add these functions at bottom of `sidebar-data.js`:

```js
function renderFilterChips() {
  const box = $('video-filter-chips');
  if (!box) return;
  const all = state.videos.length;
  const stats = countChipStats(state.videos, state.source);
  box.innerHTML = '';
  const allBtn = document.createElement('button');
  allBtn.type = 'button';
  allBtn.className = 'video-filter-chip' + (!state.videoFilter.stage ? ' active' : '');
  allBtn.textContent = `全部 ${state.videos.length}`;
  allBtn.onclick = () => { state.videoFilter.stage = ''; renderVideoList(); };
  box.appendChild(allBtn);
  for (const s of stats) {
    if (s.count === 0) continue;
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'video-filter-chip' + (state.videoFilter.stage === s.key ? ' active' : '');
    b.textContent = `${s.label} ${s.count}`;
    b.onclick = () => {
      state.videoFilter.stage = state.videoFilter.stage === s.key ? '' : s.key;
      renderVideoList();
    };
    box.appendChild(b);
  }
}

function renderStageCountBar() {
  const box = $('stage-count-bar');
  if (!box) return;
  box.innerHTML = '';
  if (!state.videos.length) {
    box.hidden = true;
    return;
  }
  box.hidden = false;
  const summary = countStageSummary(state.videos, state.source);
  for (const s of summary) {
    const cell = document.createElement('div');
    cell.className = 'stage-count-cell' + (state.videoFilter.stage === s.key ? ' active' : '');
    cell.title = s.done === s.total ? `${s.label}: 全部完成` : `${s.label}: 缺 ${s.total - s.done} 个`;
    cell.innerHTML = `<span class="stage-count-num">${s.done}/${s.total}</span>${s.label}`;
    cell.onclick = () => {
      const key = state.videoFilter.stage === s.key ? '' : s.key;
      state.videoFilter.stage = key;
      renderVideoList();
    };
    box.appendChild(cell);
  }
}
```

Also remove the now-redundant `const countEl = $('video-count'); countEl.textContent = ...` that currently lives in `loadVideos()` (line ~143-144) — it is replaced by `updateVideoCount` inside `renderVideoList`.

- [ ] **Step 5: Empty filter state**

In `renderVideoList`, last extra branch: after the existing `if (!state.videos.length) {...}` early return, add BEFORE the filter generation loop a guard for a nonzero total but zero visible:

```js
  if (visible.length === 0 && state.videos.length > 0) {
    const li = document.createElement('li');
    li.className = 'empty-state';
    li.innerHTML = `
      <p class="hint">没有匹配的视频，试试清除筛选</p>
      <button type="button" class="sidebar-btn" id="btn-clear-video-filter" style="...;">清除筛选</button>
    `;
    li.querySelector('#btn-clear-video-filter').onclick = () => {
      state.videoFilter.q = '';
      state.videoFilter.stage = '';
      if ($('video-filter-input')) $('video-filter-input').value = '';
      renderVideoList();
    };
    ul.appendChild(li);
    return;
  }
```

- [ ] **Step 6: Test + commit**

Run `npm test` — full Vitest suite still green (old `loadVideos` count assertion covered by the same-sidebar tests). Create/refresh any failing test expectations against the new `visible/total` label if present.

```bash
git add clio/ui/static/src/sidebar-data.js clio/ui/static/src/state.js
git commit -m "feat(ui): wire video filters, chips and stage count bar into sidebar"
```

---

## Task 5: Row step badges → compact dots

**Files:**
- Modify: `clio/ui/static/src/sidebar-data.js`

- [ ] **Step 1: In `renderVideoItem`, replace the badge block**

Replace:

```js
  const stepBadges = buildVideoStepBadges(v, state.source)
    .map(s => `<span class="video-step-badge ${s.done ? 'done' : 'pending'}">${s.label}</span>`)
    .join('');
```

with:

```js
  const stepStatuses = buildVideoStageStatuses(v, state.source);
  const stepDots = STAGE_CELLS
    .map(c => `<span class="video-step-dot ${stepStatuses[c.key] ? 'done' : 'pending'}" title="${c.label}: ${stepStatuses[c.key] ? '完成' : '待处理'}"></span>`)
    .join('');
```

And in the `li.innerHTML`, replace:

```html
<div class="video-step-badges">${stepBadges}</div>
```

with:

```html
<div class="video-step-dots">${stepDots}</div>
```

- [ ] **Step 2: Fix imports**

`sidebar-data.js` currently imports `buildVideoStepBadges` from `./video-menu.js` — if it becomes unused after the change, drop it from the import; keep `isCompressStepDone`-based helpers only if actually used. (Count bar/chips use `./sidebar-video-filter.js`, which internally imports `isCompressStepDone` from `video-menu.js`.)

- [ ] **Step 3: Run tests + commit**

Run: `npm test` — green.
Commit:
```bash
git add clio/ui/static/src/sidebar-data.js
git commit -m "feat(ui): render per-video stage dots instead of text badges"
```

---

## Task 6: Remove `renderSteps` and update call sites

**Files:**
- Modify: `clio/ui/static/src/sidebar-data.js`, `clio/ui/static/src/sidebar.js`, `clio/ui/static/src/main.js`, `clio/ui/static/src/runner.js`, `clio/ui/static/src/sidebar-rerun.js`, `clio/ui/static/src/editor-plan.js`

- [ ] **Step 1: Delete `renderSteps`**

In `sidebar-data.js` remove the whole function (lines ~189-201) including `export function renderSteps()`.

- [ ] **Step 2: Update `sidebar.js`**

Remove `renderSteps` from the import from `./sidebar-data.js` and from the `export { ... }` list.

- [ ] **Step 3: Update `main.js`**

- Remove `renderSteps` from the import block (line 18).
- Delete the two `renderSteps();` calls at lines 391 and 530.
- Add `initVideoFilterBar` wiring: in the `init()` function right after the `btn-add-videos` handler binding (line 427), add:

```js
  const { initVideoFilterBar } = await import('./sidebar-data.js');
  initVideoFilterBar();
```

- Also add the project dropdown toggle next to it:

```js
  document.getElementById('btn-project-menu')?.addEventListener('click', (e) => {
    e.stopPropagation();
    const menu = document.getElementById('project-menu');
    if (menu) menu.hidden = !menu.hidden;
  });
  document.addEventListener('click', (e) => {
    if (!e.target.closest('.sidebar-project')) {
      const menu = document.getElementById('project-menu');
      if (menu) menu.hidden = true;
    }
  });
```

- [ ] **Step 4: Update `runner.js`**

Replace `import('./sidebar.js').then(mod => mod.renderSteps());` (line 517) with `import('./sidebar.js').then(mod => mod.renderVideoList());`.

- [ ] **Step 5: Update `sidebar-rerun.js`**

Replace the import on line 5:

```js
import { loadVideos, renderSteps } from './sidebar-data.js';
```

with

```js
import { loadVideos, renderVideoList } from './sidebar-data.js';
```

And line 160 `renderSteps();` → `renderVideoList();`.

- [ ] **Step 6: Update `editor-plan.js`**

Remove lines 861-862:

```js
    state.steps.cut = true;
    import('./sidebar.js').then(mod => mod.renderSteps());
```

(keep the following `saveProject` call).

- [ ] **Step 7: Verify no stragglers + commit**

```bash
Get-ChildItem clio/ui/static/src -Filter *.js | Select-String -Pattern "renderSteps"
```
Expected: empty (except maybe mock/test fixtures that still name it — those are harmless).

```bash
git add clio/ui/static/src/sidebar-data.js clio/ui/static/src/sidebar.js clio/ui/static/src/main.js clio/ui/static/src/runner.js clio/ui/static/src/sidebar-rerun.js clio/ui/static/src/editor-plan.js
git commit -m "refactor(ui): drop renderSteps system; call sites move to renderVideoList"
```

---

## Task 7: Tests — adapt existing mocks

**Files:**
- Check: `clio/ui/static/src/__tests__/sidebar-select-video.test.js`

- [ ] **Step 1: Confirm mock still valid**

That test mocks `./sidebar.js` exporting `renderSteps: vi.fn()`. Extra keys in a vi.fn() map are harmless. Run full suite: `npm test`. If anything asserts on `renderSteps` **being defined on the real module** (e.g., `toEqual(Object.keys(...))`), update e.g.:

```js
expect(Object.keys(sidebarMock)).toEqual([...]) // → remove 'renderSteps' from expected array if present
```

- [ ] **Step 2: Commit**

```bash
git add clio/ui/static/src/__tests__
git commit -m "test(ui): keep mock surface in sync with removed renderSteps" || echo "no test changes needed"
```

---

## Task 8: Full verification

- [ ] **Step 1: Vitest**

```bash
npm test
```
Expected: all pass (new `sidebar-video-filter` + existing `video-menu`, `sidebar-*`, `runtime-warnings`).

- [ ] **Step 2: Backend tests**

```bash
python -m pytest clio/tests/ -q
```
Expected: pass (no backend changes).

- [ ] **Step 3: Lint**

```bash
ruff format clio  # only if touched python (none) — skip
ruff check clio/tests/  # none changed — skip
```

Nothing changed on Python side; skip ruff.

- [ ] **Step 4: Manual UI check**

`python main.py --serve --no-browser`, open URL:
- top header shows compact `打开项目 ▾` dropdown (3 actions), no old 3-button row;
- nav icon row sticks while scrolling the list;
- chips appear with counts; clicking a chip filters; count bar cells click to filter; search narrows by index/name/title;
- each row shows thumbnail/badge/title/⋯ menu as before;
- 分观众 bottom `流水线` list is gone.

- [ ] **Step 5: Commit final (if any leftovers)**