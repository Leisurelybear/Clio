# UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete UI redesign with light/dark mode toggle, refined components, and missing style additions (toast, skeleton, empty states).

**Architecture:** Pure CSS custom properties for theming, no build step. `style.css` holds all styles. A small JS module handles theme persistence and toast logic. No dependencies added.

**Tech Stack:** CSS custom properties, vanilla JS (ES modules), stdlib http.server (Python backend unchanged)

---

### Task 1: Update Design Tokens in style.css

**Files:**
- Modify: `clio/ui/static/style.css:1-68`

- [ ] **Step 1: Replace current design tokens with new indigo palette**

Replace the entire `:root {` block (lines 1-68) with:

```css
/* ── Design Tokens ──────────────────────────────────────────── */
:root, .dark-theme {
  --bg-base: #0b0b0f;
  --bg-surface: #131318;
  --bg-surface-2: #1a1a22;
  --bg-surface-3: #22222e;
  --bg-hover: #272735;
  --bg-active: rgba(99, 102, 241, 0.1);

  --border: #2a2a3a;
  --border-light: #3a3a4e;
  --border-focus: #818cf8;

  --text-primary: #ededef;
  --text-secondary: #a1a1aa;
  --text-tertiary: #71717a;
  --text-muted: #52525b;

  --accent: #6366f1;
  --accent-hover: #818cf8;
  --accent-bg: rgba(99, 102, 241, 0.1);
  --accent-glow: 0 0 20px rgba(99, 102, 241, 0.15);

  --red: #e11d48;
  --red-bg: rgba(225, 29, 72, 0.1);
  --success: #22c55e;
  --success-bg: rgba(34, 197, 94, 0.1);
  --success-text: #22c55e;
  --warning: #eab308;
  --warning-bg: rgba(234, 179, 8, 0.1);
  --error: #ef4444;
  --error-bg: rgba(239, 68, 68, 0.1);

  --radius-sm: 6px;
  --radius-md: 8px;
  --radius-lg: 10px;
  --radius-xl: 14px;

  --shadow-sm: 0 1px 3px rgba(0,0,0,0.4);
  --shadow-md: 0 4px 16px rgba(0,0,0,0.5);
  --shadow-lg: 0 8px 40px rgba(0,0,0,0.6);
  --shadow-xl: 0 16px 64px rgba(0,0,0,0.7);

  --font-sans: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Microsoft YaHei', 'PingFang SC', sans-serif;
  --font-mono: 'SF Mono', 'Cascadia Code', 'JetBrains Mono', Consolas, ui-monospace, monospace;

  --text-xs: 11px;
  --text-sm: 12px;
  --text-base: 13px;
  --text-lg: 15px;
  --text-xl: 18px;
  --text-2xl: 24px;

  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 20px;
  --space-6: 24px;
  --space-8: 32px;

  --transition-fast: 150ms ease;
  --transition-base: 200ms ease;
  --transition-slow: 400ms cubic-bezier(0.4, 0, 0.2, 1);

  --sidebar-w: 240px;
  --editor-w: 400px;
  --handle-w: 5px;
}
```

- [ ] **Step 2: Verify no broken references**

```bash
python -c "import re; css = open('clio/ui/static/style.css').read(); vars = re.findall(r'var\(--([^)]+)\)', css); defined = set(re.findall(r'--([\w-]+)\s*:', css)); missing = [v for v in vars if v not in defined and not v.startswith('space')]; print(f'Missing vars: {missing}')"
```
Expected: Empty list (no missing var references, space vars are dynamic)

- [ ] **Step 3: Commit**

```bash
git add clio/ui/static/style.css
git commit -m "feat(ui): update design tokens to indigo palette"
```

---

### Task 2: Add Light Theme Variables

**Files:**
- Modify: `clio/ui/static/style.css` (after Task 1's token block)

- [ ] **Step 1: Add light theme override block after the dark theme variables**

```css
/* ── Light Theme ────────────────────────────────────────────── */
body.light-theme {
  --bg-base: #f8f9fc;
  --bg-surface: #ffffff;
  --bg-surface-2: #f1f3f5;
  --bg-surface-3: #e9ecef;
  --bg-hover: #dee2e6;
  --bg-active: rgba(99, 102, 241, 0.08);

  --border: #e2e4e9;
  --border-light: #d0d3d8;

  --text-primary: #1a1a2e;
  --text-secondary: #52525b;
  --text-tertiary: #8a8a94;
  --text-muted: #b0b0b8;

  --shadow-sm: 0 1px 3px rgba(0,0,0,0.08);
  --shadow-md: 0 4px 16px rgba(0,0,0,0.1);
  --shadow-lg: 0 8px 40px rgba(0,0,0,0.12);
  --shadow-xl: 0 16px 64px rgba(0,0,0,0.15);
}
```

- [ ] **Step 2: Add prefers-color-scheme auto-detection**

Add just after the light theme block:

```css
/* Auto dark mode for light theme users */
@media (prefers-color-scheme: light) {
  body:not(.dark-theme):not(.light-theme) {
    --bg-base: #f8f9fc;
    --bg-surface: #ffffff;
    --bg-surface-2: #f1f3f5;
    --bg-surface-3: #e9ecef;
    --bg-hover: #dee2e6;
    --bg-active: rgba(99, 102, 241, 0.08);
    --border: #e2e4e9;
    --border-light: #d0d3d8;
    --text-primary: #1a1a2e;
    --text-secondary: #52525b;
    --text-tertiary: #8a8a94;
    --text-muted: #b0b0b8;
    --shadow-sm: 0 1px 3px rgba(0,0,0,0.08);
    --shadow-md: 0 4px 16px rgba(0,0,0,0.1);
    --shadow-lg: 0 8px 40px rgba(0,0,0,0.12);
    --shadow-xl: 0 16px 64px rgba(0,0,0,0.15);
  }
}
```

- [ ] **Step 3: Commit**

```bash
git add clio/ui/static/style.css
git commit -m "feat(ui): add light theme CSS variables and prefers-color-scheme detection"
```

---

### Task 3: Add Theme Toggle UI + JS Logic

**Files:**
- Modify: `clio/ui/static/index.html:9-23` (header)
- Modify: `clio/ui/static/src/main.js` (init function)
- Create: `clio/ui/static/src/theme.js`

- [ ] **Step 1: Create theme.js module**

```javascript
// Theme toggle: dark / light mode with localStorage persistence

const STORAGE_KEY = 'vlog_ui_theme';

export function initTheme() {
  const saved = localStorage.getItem(STORAGE_KEY);
  const prefersLight = window.matchMedia('(prefers-color-scheme: light)').matches;

  if (saved === 'light') {
    document.body.classList.add('light-theme');
  } else if (saved === 'dark') {
    document.body.classList.remove('light-theme');
  } else if (prefersLight) {
    document.body.classList.add('light-theme');
  }
}

export function toggleTheme() {
  document.body.classList.toggle('light-theme');
  const isLight = document.body.classList.contains('light-theme');
  localStorage.setItem(STORAGE_KEY, isLight ? 'light' : 'dark');
  return isLight;
}
```

- [ ] **Step 2: Add theme toggle button to header**

Replace the reload button area in `index.html` to add a theme toggle:

```html
<button id="btn-theme" class="btn-icon" title="切换浅色/暗色主题">
  <span class="icon">
    <svg viewBox="0 0 24 24" width="16" height="16">
      <path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/>
    </svg>
  </span>
</button>
<button id="btn-reload" class="btn-icon" title="重新扫描磁盘上的文件">
  <span class="icon"><svg viewBox="0 0 24 24"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/></svg></span>
</button>
```

- [ ] **Step 3: Wire up theme toggle in main.js**

In `init()` function, add after `initLayout()`:

```javascript
import { initTheme, toggleTheme } from './theme.js';

// Inside init(), after initLayout():
initTheme();
document.getElementById('btn-theme').onclick = toggleTheme;
```

- [ ] **Step 4: Commit**

```bash
git add clio/ui/static/src/theme.js clio/ui/static/index.html clio/ui/static/src/main.js
git commit -m "feat(ui): add light/dark theme toggle with localStorage persistence"
```

---

### Task 4: Refactor Header Styles

**Files:**
- Modify: `clio/ui/static/style.css` (header section ~lines 92-104)
- Modify: `clio/ui/static/index.html` (header structure)

- [ ] **Step 1: Update header HTML structure**

Replace the `<header>` block (lines 9-23) in `index.html`:

```html
<header>
  <div class="header-left">
    <div class="brand-mark">V</div>
    <div class="proj">
      <span class="label">PROJECT</span>
      <span id="proj-name" class="value">加载中...</span>
    </div>
  </div>
  <div class="source-toggle">
    <button data-source="compressed" class="active" title="浏览 output/compressed/ 下的 640p 压缩视频">压缩</button>
    <button data-source="original" title="浏览 input_dir 下的原始 4K 视频">原视频</button>
  </div>
  <div class="actions">
    <span id="status" class="status"></span>
    <button id="btn-theme" class="btn-icon" title="切换浅色/暗色主题">
      <span class="icon"><svg viewBox="0 0 24 24" width="16" height="16"><path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/></svg></span>
    </button>
    <button id="btn-reload" class="btn-icon" title="重新扫描磁盘上的文件"><span class="icon"><svg viewBox="0 0 24 24"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/></svg></span></button>
  </div>
</header>
```

- [ ] **Step 2: Replace header CSS**

Replace the entire header section (lines 92-104) with:

```css
/* ── Header ────────────────────────────────────────────────── */
header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-2) var(--space-4);
  background: var(--bg-surface);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
  gap: var(--space-3);
  min-height: 44px;
  -webkit-app-region: drag;
}
header > * { -webkit-app-region: no-drag; }

.header-left {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  min-width: 0;
}

.brand-mark {
  width: 22px;
  height: 22px;
  background: var(--accent);
  color: #fff;
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 11px;
  flex-shrink: 0;
}

.proj { display: flex; align-items: center; gap: var(--space-2); min-width: 0; }
.proj .label { color: var(--text-muted); font-size: 10px; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; white-space: nowrap; }
.proj .value {
  font-family: var(--font-mono);
  color: var(--text-primary);
  font-size: var(--text-sm);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 300px;
}
```

- [ ] **Step 3: Update source-toggle CSS**

Replace the existing source-toggle rules with:

```css
.source-toggle {
  display: flex;
  background: var(--bg-surface-2);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  overflow: hidden;
}
.source-toggle button {
  background: transparent;
  color: var(--text-secondary);
  border: none;
  padding: 5px 14px;
  cursor: pointer;
  font: inherit;
  font-size: var(--text-sm);
  font-weight: 500;
  transition: background var(--transition-fast), color var(--transition-fast);
}
.source-toggle button:hover { background: var(--bg-hover); color: var(--text-primary); }
.source-toggle button.active { background: var(--accent); color: #fff; }
.source-toggle button:focus-visible { outline: 2px solid var(--border-focus); outline-offset: -2px; }
```

- [ ] **Step 4: Update actions CSS**

```css
.actions { display: flex; align-items: center; gap: var(--space-1); }
.btn-icon {
  background: transparent;
  color: var(--text-tertiary);
  border: 1px solid transparent;
  padding: 5px;
  cursor: pointer;
  border-radius: var(--radius-sm);
  font: inherit;
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: var(--text-sm);
  transition: all var(--transition-fast);
  width: 30px;
  height: 30px;
  justify-content: center;
}
.btn-icon:hover { background: var(--bg-hover); color: var(--text-primary); border-color: var(--border); }
.btn-icon:focus-visible { outline: 2px solid var(--border-focus); outline-offset: 2px; }
```

- [ ] **Step 5: Commit**

```bash
git add clio/ui/static/style.css clio/ui/static/index.html
git commit -m "feat(ui): redesign header with brand mark and compact layout"
```

---

### Task 5: Redesign Sidebar Items

**Files:**
- Modify: `clio/ui/static/style.css` (sidebar section ~lines 283-330)

- [ ] **Step 1: Replace sidebar item CSS**

Replace the project-item rules with:

```css
#project-list, #video-list { list-style: none; padding: var(--space-1) 0; margin: 0; }

.project-item {
  padding: var(--space-2) var(--space-3); cursor: pointer;
  display: flex; align-items: center; gap: var(--space-2);
  transition: all var(--transition-fast);
  min-height: 36px;
  border-radius: var(--radius-sm);
  margin: 0 var(--space-1);
}
.project-item:hover { background: var(--bg-hover); }
.project-item.active {
  background: var(--bg-active);
  color: var(--accent);
}
.project-item.active .name { color: var(--accent); font-weight: 600; }
.project-item .name { flex: 1; font-weight: 500; font-size: var(--text-base); }
.project-item .shortcut {
  font-size: 10px;
  color: var(--text-muted);
  background: var(--bg-surface-2);
  padding: 1px 5px;
  border-radius: 3px;
  font-family: var(--font-mono);
}
```

- [ ] **Step 2: Update sidebar section headers**

```css
#sidebar h3 {
  display: flex; align-items: center; gap: var(--space-2);
  padding: var(--space-2) var(--space-3); margin: var(--space-2) 0 0;
  font-size: 10px; color: var(--text-muted);
  text-transform: uppercase; letter-spacing: 0.08em;
  font-weight: 600;
}
#video-count { font-weight: normal; text-transform: none; letter-spacing: 0; font-size: var(--text-sm); color: var(--text-tertiary); }
```

- [ ] **Step 3: Add keyboard shortcut labels to index.html**

Update project items in index.html (~lines 39-58) to add `shortcut` spans:

```html
<li class="project-item" data-entity="plan" title="打开编排 (plan) 面板">
  <span class="icon"><svg viewBox="0 0 24 24"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="9" y1="21" x2="9" y2="9"/></svg></span>
  <span class="name">编排</span>
  <span class="shortcut">⌘1</span>
</li>
<li class="project-item" data-entity="config" title="编辑 config.yaml 配置">
  <span class="icon"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-2 2 2 2 0 01-2-2v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83 0 2 2 0 010-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 01-2-2 2 2 0 012-2h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 010-2.83 2 2 0 012.83 0l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 012-2 2 2 0 012 2v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 0 2 2 0 010 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 012 2 2 2 0 01-2 2h-.09a1.65 1.65 0 00-1.51 1z"/></svg></span>
  <span class="name">设置</span>
  <span class="shortcut">⌘2</span>
</li>
<li class="project-item" data-entity="run" title="运行流水线">
  <span class="icon"><svg viewBox="0 0 24 24"><polygon points="5 3 19 12 5 21 5 3"/></svg></span>
  <span class="name">运行</span>
  <span class="shortcut">⌘3</span>
</li>
<li class="project-item" data-entity="logs" title="查看服务运行日志">
  <span class="icon"><svg viewBox="0 0 24 24"><polyline points="1 12 1 19 23 19 23 12"/><polyline points="22 8 12 3 2 8 2 8"/><rect x="12" y="15" width="2" height="2"/><rect x="8" y="15" width="2" height="2"/><rect x="4" y="15" width="2" height="2"/></svg></span>
  <span class="name">日志</span>
  <span class="shortcut">⌘4</span>
</li>
<li class="project-item" data-entity="tokens" title="AI token 使用统计">
  <span class="icon"><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><line x1="12" y1="8" x2="12" y2="16"/><line x1="8" y1="12" x2="16" y2="12"/></svg></span>
  <span class="name">统计</span>
  <span class="shortcut">⌘5</span>
</li>
```

- [ ] **Step 4: Commit**

```bash
git add clio/ui/static/style.css clio/ui/static/index.html
git commit -m "feat(ui): redesign sidebar items with rounded corners and shortcut labels"
```

---

### Task 6: Redesign Video List Items

**Files:**
- Modify: `clio/ui/static/style.css` (video list section ~lines 337-430)

- [ ] **Step 1: Replace video item CSS**

```css
/* ── Video List ────────────────────────────────────────────── */
.video-item {
  padding: var(--space-2) var(--space-3); cursor: pointer;
  border-bottom: 1px solid var(--border);
  transition: background var(--transition-fast);
  display: flex;
  align-items: center;
  gap: var(--space-2);
}
.video-item:hover { background: var(--bg-hover); }
.video-item.active { background: var(--bg-active); }
.video-item.active .video-name { color: var(--accent); }
.video-item.no-match { opacity: 0.5; }

.video-thumb {
  width: 32px; height: 20px;
  background: var(--bg-surface-2);
  border-radius: 3px;
  display: flex; align-items: center; justify-content: center;
  font-size: 7px; color: var(--text-muted);
  flex-shrink: 0;
  border: 1px solid var(--border);
}

.video-info { flex: 1; min-width: 0; }

.video-name {
  font-weight: 500; word-break: break-all; font-size: var(--text-base);
  display: flex; align-items: center; gap: 6px;
  color: var(--text-primary);
}
.video-title {
  font-size: var(--text-xs); color: var(--text-secondary);
  margin: 0 0 1px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.video-match { margin: 2px 0 0; font-size: var(--text-xs); line-height: 1.4; }
.video-duration {
  font-size: 10px; color: var(--text-tertiary);
  font-family: var(--font-mono);
}
.match-badge {
  display: inline-flex; align-items: center; gap: 3px;
  font-size: 10px; background: var(--success-bg);
  color: var(--success); padding: 1px 6px;
  border-radius: 10px; font-family: var(--font-mono);
  white-space: nowrap; font-weight: 500;
}
.match-badge.miss { background: var(--error-bg); color: var(--error); }
.video-item.active .match-badge { background: var(--accent-bg); color: var(--accent); }

.video-step-badges {
  display: flex;
  gap: 4px;
  margin-top: 2px;
}
.video-step-badge {
  font-size: 9px;
  padding: 1px 5px;
  border-radius: 3px;
  font-weight: 500;
  white-space: nowrap;
}
.video-step-badge.done { background: var(--success-bg); color: var(--success); }
.video-step-badge.pending { background: var(--bg-surface-3); color: var(--text-muted); }
.video-step-badge.running { background: var(--warning-bg); color: var(--warning); }

.video-meta {
  font-size: var(--text-xs); color: var(--text-tertiary);
  margin-top: 3px; display: flex; align-items: center; gap: var(--space-2);
}
.video-meta .has { color: var(--success); display: inline-flex; align-items: center; gap: 3px; }
.video-meta .miss { opacity: 0.35; display: inline-flex; align-items: center; gap: 3px; }
```

- [ ] **Step 2: Update sidebar-data.js to use new video item structure**

Modify `clio/ui/static/src/sidebar-data.js` (the renderVideoList function) to use the new thumbnail + step badges structure. Search for the function and update the template string for each video item.

```javascript
// In renderVideoList(), update the video item template:
const html = v.missing
  ? `<div class="video-item no-match">
       <div class="video-thumb">VID</div>
       <div class="video-info">
         <div class="video-name">${escapeHtml(v.file)}</div>
         <div class="video-title">${v.title ? escapeHtml(v.title) : ''}</div>
         <div class="video-step-badges">${stepBadges}</div>
       </div>
     </div>`
  : `<div class="video-item ${v.file === state.currentVideo ? 'active' : ''}" data-file="${escapeHtml(v.file)}">
       <div class="video-thumb">VID</div>
       <div class="video-info">
         <div class="video-name-row">
           <div class="video-name">${escapeHtml(v.file)}</div>
           ${v.duration ? `<span class="video-duration">${v.duration}</span>` : ''}
         </div>
         <div class="video-step-badges">${stepBadges}</div>
       </div>
     </div>`;
```

- [ ] **Step 3: Commit**

```bash
git add clio/ui/static/style.css clio/ui/static/src/sidebar-data.js
git commit -m "feat(ui): redesign video list with thumbnails and step badges"
```

---

### Task 7: Redesign Editor Tabs

**Files:**
- Modify: `clio/ui/static/style.css` (tabs section ~lines 540-573)
- Modify: `clio/ui/static/index.html` (tabs HTML)

- [ ] **Step 1: Replace tabs HTML**

Replace `<div class="tabs">` block in index.html:

```html
<div class="tabs">
  <button class="tab active" data-tab="texts">分析</button>
  <button class="tab" data-tab="voiceover">口播</button>
  <button class="tab" data-tab="transcript">转录</button>
</div>
```

(The HTML is the same but styles change)

- [ ] **Step 2: Replace tabs CSS**

Replace the entire `.tabs` / `.tab` section:

```css
.tabs {
  display: flex;
  background: var(--bg-surface-2);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
  padding: 3px var(--space-2);
  gap: 2px;
}
.tab {
  flex: 1;
  padding: 7px var(--space-2);
  background: transparent;
  border: none;
  color: var(--text-tertiary);
  cursor: pointer;
  font: inherit;
  font-size: var(--text-sm);
  border-radius: var(--radius-sm);
  transition: all var(--transition-fast);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  font-weight: 500;
}
.tab:hover { background: var(--bg-hover); color: var(--text-secondary); }
.tab.active {
  color: var(--accent);
  background: var(--bg-surface);
  font-weight: 600;
}
```

- [ ] **Step 3: Update entity-specific editor modes CSS**

```css
#editor.entity-plan .tabs { display: none; }
#editor.entity-plan .tab-pane:not(#tab-plan) { display: none; }
#editor.entity-plan #tab-plan { display: block; }
#editor.entity-run .tabs { display: none; }
#editor.entity-run .tab-pane:not(#tab-run) { display: none; }
#editor.entity-run #tab-run { display: block; }
#editor.entity-config .tabs { display: none; }
#editor.entity-config .tab-pane:not(#tab-config) { display: none; }
#editor.entity-config #tab-config { display: block; }
#editor.entity-logs .tabs { display: none; }
#editor.entity-logs .tab-pane:not(#tab-logs) { display: none; }
#editor.entity-logs #tab-logs { display: flex; flex-direction: column; height: 100%; }
#editor.entity-video #tab-plan,
#editor.entity-video #tab-config { display: none; }
#editor.entity-run .editor-actions,
#editor.entity-logs .editor-actions { display: none; }
#editor.entity-tokens .tabs { display: none; }
#editor.entity-tokens .tab-pane:not(#tab-tokens) { display: none; }
#editor.entity-tokens #tab-tokens { display: block; }
#editor.entity-tokens .editor-actions { display: none; }
```

- [ ] **Step 4: Commit**

```bash
git add clio/ui/static/style.css
git commit -m "feat(ui): redesign editor tabs as segmented control"
```

---

### Task 8: Redesign Buttons

**Files:**
- Modify: `clio/ui/static/style.css` (btn-primary, sidebar-btn, etc.)

- [ ] **Step 1: Replace button CSS**

Update `.btn-primary` and `.btn-secondary`:

```css
.btn-primary {
  width: 100%;
  padding: 9px 16px;
  background: var(--accent);
  color: #fff;
  border: none;
  cursor: pointer;
  border-radius: var(--radius-md);
  font: inherit;
  font-weight: 600;
  font-size: var(--text-base);
  transition: all var(--transition-fast);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  box-shadow: 0 0 12px rgba(99, 102, 241, 0.15);
}
.btn-primary:hover { background: var(--accent-hover); box-shadow: 0 0 20px rgba(99, 102, 241, 0.25); }
.btn-primary:active { transform: scale(0.98); }
.btn-primary.dirty { background: var(--warning); animation: pulse-warning 2s infinite; box-shadow: none; }
.btn-primary.dirty:hover { background: #d97706; box-shadow: none; }
.btn-primary:disabled { background: var(--bg-surface-3); color: var(--text-muted); cursor: not-allowed; box-shadow: none; }
.btn-primary:disabled:active { transform: none; }

.btn-secondary {
  background: transparent;
  color: var(--text-secondary);
  border: 1px solid var(--border);
  padding: 8px 16px;
  border-radius: var(--radius-md);
  font: inherit;
  font-size: var(--text-sm);
  cursor: pointer;
  transition: all var(--transition-fast);
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.btn-secondary:hover { background: var(--bg-hover); color: var(--text-primary); border-color: var(--border-light); }
.btn-secondary:focus-visible { outline: 2px solid var(--border-focus); outline-offset: 2px; }
```

- [ ] **Step 2: Update sidebar-btn**

```css
.sidebar-btn {
  background: var(--bg-surface-2);
  color: var(--text-secondary);
  border: 1px solid var(--border);
  padding: 6px 10px;
  border-radius: var(--radius-sm);
  font: inherit;
  font-size: var(--text-sm);
  cursor: pointer;
  transition: all var(--transition-fast);
  display: inline-flex;
  align-items: center;
  gap: 4px;
  flex: 1;
  font-weight: 500;
}
.sidebar-btn:hover { background: var(--bg-hover); color: var(--text-primary); border-color: var(--border-light); }
```

- [ ] **Step 3: Commit**

```bash
git add clio/ui/static/style.css
git commit -m "feat(ui): redesign buttons with indigo glow and rounded corners"
```

---

### Task 9: Add Toast Notification System

**Files:**
- Create: `clio/ui/static/src/toast.js`
- Modify: `clio/ui/static/style.css` (add toast styles)
- Modify: `clio/ui/static/index.html` (add toast container)

- [ ] **Step 1: Add toast CSS**

```css
/* ── Toast Notifications ───────────────────────────────────── */
.toast-container {
  position: fixed;
  bottom: var(--space-4);
  right: var(--space-4);
  z-index: 2000;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  pointer-events: none;
  max-width: 380px;
}
.toast {
  pointer-events: auto;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  color: #fff;
  box-shadow: var(--shadow-lg);
  animation: toastIn 200ms ease;
  min-width: 260px;
}
.toast.removing {
  animation: toastOut 200ms ease forwards;
}
.toast-icon {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: rgba(255,255,255,0.2);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  flex-shrink: 0;
}
.toast-message { flex: 1; line-height: 1.4; }
.toast-close {
  opacity: 0.6;
  cursor: pointer;
  font-size: 16px;
  line-height: 1;
  padding: 2px;
  flex-shrink: 0;
  border: none;
  background: none;
  color: #fff;
  transition: opacity var(--transition-fast);
}
.toast-close:hover { opacity: 1; }

.toast.success { background: #166534; border: 1px solid #22c55e; }
.toast.error { background: #991b1b; border: 1px solid #ef4444; }
.toast.warning { background: #854d0e; border: 1px solid #eab308; }
.toast.info { background: #1e40af; border: 1px solid #60a5fa; }

@keyframes toastIn {
  from { opacity: 0; transform: translateY(12px) scale(0.96); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}
@keyframes toastOut {
  from { opacity: 1; transform: translateX(0); }
  to { opacity: 0; transform: translateX(100%); }
}

@media (prefers-reduced-motion: reduce) {
  .toast { animation: none; }
  .toast.removing { animation: none; opacity: 0; }
}
```

- [ ] **Step 2: Add toast container to index.html**

Add before `</body>`:

```html
<div id="toast-container" class="toast-container"></div>
```

- [ ] **Step 3: Create toast.js**

```javascript
const container = document.getElementById('toast-container');
const MAX_VISIBLE = 3;
let queue = [];

function addToast(message, type = 'info', duration = 4000) {
  if (!container) return;
  
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  
  const icons = { success: '✓', error: '!', warning: '◌', info: 'i' };
  
  toast.innerHTML = `
    <span class="toast-icon">${icons[type] || 'i'}</span>
    <span class="toast-message">${message}</span>
    <button class="toast-close">&times;</button>
  `;
  
  toast.querySelector('.toast-close').onclick = () => removeToast(toast);
  
  const visible = container.children.length;
  if (visible >= MAX_VISIBLE) {
    queue.push(toast);
  } else {
    container.appendChild(toast);
    if (duration > 0) {
      setTimeout(() => removeToast(toast), duration);
    }
  }
}

function removeToast(toast) {
  if (toast.classList.contains('removing')) return;
  toast.classList.add('removing');
  toast.addEventListener('animationend', () => {
    if (toast.parentNode) toast.parentNode.removeChild(toast);
    if (queue.length > 0) {
      const next = queue.shift();
      container.appendChild(next);
      setTimeout(() => removeToast(next), 4000);
    }
  }, { once: true });
}

export { addToast };
```

- [ ] **Step 4: Commit**

```bash
git add clio/ui/static/style.css clio/ui/static/index.html clio/ui/static/src/toast.js
git commit -m "feat(ui): add toast notification system with 4 variants and queue"
```

---

### Task 10: Add Loading Skeleton & Enhanced Empty States

**Files:**
- Modify: `clio/ui/static/style.css` (add skeleton and empty state styles)

- [ ] **Step 1: Add skeleton CSS**

```css
/* ── Loading Skeleton ──────────────────────────────────────── */
@keyframes shimmer {
  0% { background-position: -200% 0; }
  100% { background-position: 200% 0; }
}
.skeleton {
  background: linear-gradient(90deg, var(--bg-surface-2) 25%, var(--bg-hover) 50%, var(--bg-surface-2) 75%);
  background-size: 200% 100%;
  animation: shimmer 1.5s ease-in-out infinite;
  border-radius: var(--radius-sm);
}
.skeleton-line { height: 12px; margin-bottom: var(--space-2); width: 100%; }
.skeleton-line:last-child { width: 60%; }
.skeleton-block { height: 60px; margin-bottom: var(--space-2); border-radius: var(--radius-md); }
.skeleton-circle { width: 32px; height: 32px; border-radius: 50%; flex-shrink: 0; }

@media (prefers-reduced-motion: reduce) {
  .skeleton { animation: none; background: var(--bg-surface-2); }
}
```

- [ ] **Step 2: Enhance empty state CSS**

```css
/* ── Empty State ───────────────────────────────────────────── */
.empty-state {
  padding: var(--space-8) var(--space-4);
  text-align: center;
  color: var(--text-muted);
}
.empty-state-icon {
  display: block;
  margin: 0 auto var(--space-3);
  width: 48px;
  height: 48px;
  color: var(--text-muted);
  opacity: 0.5;
}
.empty-state-icon svg {
  width: 100%;
  height: 100%;
  stroke: currentColor;
  fill: none;
  stroke-width: 1.5;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.empty-state h4 {
  margin: 0 0 var(--space-1);
  color: var(--text-secondary);
  font-size: var(--text-lg);
  font-weight: 600;
}
.empty-state p {
  margin: var(--space-1) 0;
  font-size: var(--text-sm);
  line-height: 1.5;
  max-width: 280px;
  margin-left: auto;
  margin-right: auto;
}
.empty-state .btn-primary {
  display: inline-flex;
  width: auto;
  margin-top: var(--space-3);
  padding: 8px 18px;
}
```

- [ ] **Step 3: Commit**

```bash
git add clio/ui/static/style.css
git commit -m "feat(ui): add loading skeleton and enhanced empty state styles"
```

---

### Task 11: Add Unified Focus Ring

**Files:**
- Modify: `clio/ui/static/style.css`

- [ ] **Step 1: Add global focus-visible style**

Add near the top of the file (after reset section):

```css
/* ── Focus Ring ────────────────────────────────────────────── */
:focus-visible {
  outline: 2px solid var(--border-focus);
  outline-offset: 2px;
}
/* Remove old focus styles that conflict */
button:focus:not(:focus-visible),
input:focus:not(:focus-visible),
select:focus:not(:focus-visible),
textarea:focus:not(:focus-visible) {
  outline: none;
}
```

- [ ] **Step 2: Remove redundant focus styles throughout the file**

Search for existing `:focus` rules on buttons, inputs, selects and ensure they use `outline: none` only for `:focus:not(:focus-visible)`. The individual component focus styles (like input focus with box-shadow) should remain — they enhance the default focus ring, not replace it.

- [ ] **Step 3: Commit**

```bash
git add clio/ui/static/style.css
git commit -m "feat(ui): add unified focus-visible ring across all interactive elements"
```

---

### Task 12: Thinner Scrollbar

**Files:**
- Modify: `clio/ui/static/style.css` (scrollbar section)

- [ ] **Step 1: Replace scrollbar CSS**

```css
/* ── Scrollbar ─────────────────────────────────────────────── */
::-webkit-scrollbar { width: 4px; height: 4px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }
::-webkit-scrollbar-thumb:hover { background: var(--border-light); }
```

- [ ] **Step 2: Commit**

```bash
git add clio/ui/static/style.css
git commit -m "style(ui): thinner scrollbar (4px) with hover highlight"
```

---

### Task 13: Polish Modals

**Files:**
- Modify: `clio/ui/static/style.css` (modal section)

- [ ] **Step 1: Replace modal CSS**

```css
/* ── Modal ─────────────────────────────────────────────────── */
.modal { position: fixed; inset: 0; z-index: 1000; display: flex; align-items: center; justify-content: center; }
.modal-backdrop { position: absolute; inset: 0; background: rgba(0,0,0,0.6); backdrop-filter: blur(6px); }
.modal-dialog {
  position: relative;
  background: var(--bg-surface);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-xl);
  padding: var(--space-5) var(--space-6);
  min-width: 360px;
  max-width: 90vw;
  box-shadow: var(--shadow-xl);
  animation: modalIn 200ms cubic-bezier(0.4, 0, 0.2, 1);
}
@keyframes modalIn {
  from { opacity: 0; transform: translateY(-8px) scale(0.97); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}

.modal-dialog h3 { margin: 0 0 var(--space-4); color: var(--text-primary); font-size: var(--text-lg); font-weight: 600; }
.modal-dialog label { display: block; margin-bottom: var(--space-3); }
.modal-dialog label span { display: block; margin-bottom: var(--space-1); font-size: var(--text-sm); color: var(--text-secondary); font-weight: 500; }
.modal-dialog input[type="text"] {
  width: 100%; background: var(--bg-surface-2); color: var(--text-primary);
  border: 1px solid var(--border); padding: 8px 10px;
  border-radius: var(--radius-sm); font: inherit;
  transition: border-color var(--transition-fast);
}
.modal-dialog input[type="text"]:focus { outline: none; border-color: var(--border-focus); box-shadow: 0 0 0 3px var(--accent-bg); }

.modal-actions { display: flex; justify-content: flex-end; gap: var(--space-2); margin-top: var(--space-4); }
.modal-actions button { padding: 8px 18px; border-radius: var(--radius-md); font: inherit; font-size: var(--text-sm); cursor: pointer; transition: all var(--transition-fast); }
```

- [ ] **Step 2: Commit**

```bash
git add clio/ui/static/style.css
git commit -m "feat(ui): polish modal with blur backdrop and refined animation"
```

---

### Task 14: Refine Resize Handles

**Files:**
- Modify: `clio/ui/static/style.css` (resize-handle section)

- [ ] **Step 1: Update resize handle CSS for cleaner look**

```css
/* ── Resize Handles ────────────────────────────────────────── */
.resize-handle {
  background: transparent;
  cursor: col-resize;
  position: relative;
  z-index: 10;
  transition: background var(--transition-fast);
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: var(--handle-w);
}
.resize-handle::before {
  content: '';
  position: absolute;
  top: 0;
  left: 2px;
  width: 1px;
  height: 100%;
  background: var(--border);
  transition: all var(--transition-fast);
}
.resize-handle:hover::before,
.resize-handle:active::before {
  background: var(--accent);
  width: 2px;
  left: 1.5px;
  box-shadow: 0 0 6px rgba(99, 102, 241, 0.3);
}
.resize-handle:hover {
  background: var(--accent-bg);
}
```

- [ ] **Step 2: Commit**

```bash
git add clio/ui/static/style.css
git commit -m "style(ui): refine resize handle with subtle accent glow"
```

---

### Task 15: Verify All Existing Functionality

**Files:**
- All modified files

- [ ] **Step 1: Start the server and check UI loads**

```bash
python main.py serve --no-browser
```

Visit http://127.0.0.1:8765 and verify:
- [ ] All panels render (sidebar, player, editor)
- [ ] Theme toggle works (header button switches dark/light)
- [ ] Theme persists on page reload
- [ ] Video list shows with correct badges
- [ ] Editor tabs switch correctly
- [ ] Modals open/close with animation
- [ ] Resize handles work
- [ ] Toast system test (call `addToast('test', 'success')` from console)
- [ ] Skeleton classes apply correctly

- [ ] **Step 2: Run Python smoke test**

```bash
python main.py check
```

- [ ] **Step 3: Verify git status is clean**

```bash
git status
```
Expected: only the planned files modified, no accidental changes.

- [ ] **Step 4: Final commit if needed**

```bash
git add -A
git commit -m "fix(ui): polish and verification fixes after redesign"
```

---

## Self-Review Checklist

- [ ] All spec requirements mapped to tasks
- [ ] No TBD/TODO placeholders
- [ ] Types and names consistent across tasks
- [ ] File paths are exact
- [ ] Each step is 2-5 minutes of work
