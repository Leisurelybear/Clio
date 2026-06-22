# R-018: Multi-Video Selection + Step Execution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Add "selection mode" to the UI sidebar — user clicks "Select Videos" → checkboxes appear → select videos → steps run only on selected files. Idempotent (same output filenames as full run).

**Architecture:** `selectionMode` + `selectedFiles` in frontend state → `files[]` filter passed to backend API → each pipeline task filters its file discovery by the provided basenames. Existing `single_file` param is separate (for rerun); `files` is a new optional filter applied at the collection point.

**Tech Stack:** Python 3.11, ES modules (vanilla JS), http.server, ffmpeg

---

### Task 1: Add `files` + `overwrite` to backend pipeline + route

**Files:**
- Modify: `vlog_tool/ui/routes/run.py:39-63`
- Modify: `vlog_tool/pipeline.py:72-118`

- [ ] **Step 1: Update `handle_post_run_start` to extract `files` and `overwrite` from request body**

In `vlog_tool/ui/routes/run.py:handle_post_run_start`, add after `cfg.plan.use_transcripts`:
```python
    files_list = obj.get("files")
    overwrite = obj.get("overwrite", False)
```

Pass them to `run_pipeline_steps`:
```python
            run_pipeline_steps(cfg, day_label, steps, tracker=tracker,
                               cancel_event=handler.__class__._cancel_event,
                               files=files_list, overwrite=overwrite)
```

- [ ] **Step 2: Update `run_pipeline_steps` to accept and propagate `files` + `overwrite`**

In `vlog_tool/pipeline.py:run_pipeline_steps`, add `files` and `overwrite` parameters. Propagate via kwargs:
```python
def run_pipeline_steps(
    config: AppConfig,
    day_label: str = "day1",
    steps: list[str] | None = None,
    tracker: ProgressTracker | None = None,
    cancel_event: threading.Event | None = None,
    files: list[str] | None = None,
    overwrite: bool = False,
) -> None:
```

When calling each step function, pass `files` and `overwrite` alongside `cancel_event`:
```python
                kwargs: dict = {}
                if cancel_event:
                    kwargs["cancel_event"] = cancel_event
                if files is not None:
                    kwargs["files"] = files
                if overwrite:
                    kwargs["overwrite"] = True
```

- [ ] **Step 3: Commit**

```bash
git add vlog_tool/ui/routes/run.py vlog_tool/pipeline.py
git commit -m "feat(run): accept files filter + overwrite flag in API and pipeline"
```

---

### Task 2: Add `files` filter to each pipeline task function

**Files:**
- Modify: `vlog_tool/tasks/compress.py:20-32`
- Modify: `vlog_tool/tasks/analyze.py:78-110`
- Modify: `vlog_tool/tasks/transcribe.py` (find discovery point)
- Modify: `vlog_tool/tasks/scripts.py:20-34`
- Modify: `vlog_tool/tasks/refine.py` (find discovery point)

- [ ] **Step 1: Add filter to `run_compress_all`**

In `vlog_tool/tasks/compress.py`, add `files: list[str] | None = None` param. After `videos = find_videos(...)`, filter:

```python
    if single_file:
        videos = [single_file]
    else:
        videos = find_videos(config.paths.input_dir, recursive=config.paths.recursive)
    if files is not None:
        allowed = {f.lower() for f in files}
        videos = [v for v in videos if v.stem.lower() in allowed]
```

- [ ] **Step 2: Add filter to `run_analyze_all`**

In `vlog_tool/tasks/analyze.py`, find where compressed files are discovered (around line 93):
```python
def run_analyze_all(
    config: AppConfig,
    tracker: ProgressTracker | None = None,
    single_file: Path | None = None,
    cancel_event: threading.Event | None = None,
    files: list[str] | None = None,
    overwrite: bool = False,
) -> list[ClipRecord]:
```

Find the line where `compressed_files` is built (likely `sorted(config.compressed_dir.glob("*.mp4"))`) and add filter:
```python
    compressed_files = sorted(config.compressed_dir.glob("*.mp4"))
    if files is not None:
        allowed = {f.lower() for f in files}
        compressed_files = [f for f in compressed_files if f.stem.lower() in allowed]
```

Also pass `overwrite` to override `skip_existing`. At each `skip_existing` check, use `overwrite`:
```python
    if not overwrite and config.analyze.skip_existing and out_path.exists():
```

- [ ] **Step 3: Add filter to `run_transcribe_all`**

In `vlog_tool/tasks/transcribe.py:run_transcribe_all`, line 128:
```python
    videos = find_videos(config.paths.input_dir, recursive=config.paths.recursive)
```
Add `files: list[str] | None = None` param. After this line, filter:
```python
    videos = find_videos(config.paths.input_dir, recursive=config.paths.recursive)
    if files is not None:
        allowed = {f.lower() for f in files}
        videos = [v for v in videos if v.stem.lower() in allowed]
```
Also pass `overwrite` to override `skip_existing` at line 142:
```python
    if not overwrite and config.analyze.skip_existing and out_path.exists():
```

- [ ] **Step 4: Add filter to `run_generate_scripts`**

In `vlog_tool/tasks/scripts.py`, after `files = sorted(config.texts_dir.glob("*.json"))`:
```python
    if files_list is not None:
        allowed = {f.lower() for f in files_list}
        files = [f for f in files if f.stem.lower() in allowed]
```
(Use a different param name to avoid shadowing; e.g. `selected_files` or rename the existing `files` var.)

- [ ] **Step 5: Add filter to `run_refine_texts` / `run_refine_scripts`**

In `vlog_tool/tasks/refine.py`, both functions use `_collect_target_files(path, dir)` which globs `dir/*.json`. Add `files: list[str] | None = None` param to both `run_refine_texts` and `run_refine_scripts`. After `files = _collect_target_files(...)`:
```python
    files = _collect_target_files(path, config.texts_dir)
    if files_list is not None:
        allowed = {f.lower() for f in files_list}
        files = [f for f in files if f.stem.lower() in allowed]
```

Also add `overwrite: bool = False` param; apply at skip_existing checks similarly to other tasks.

- [ ] **Step 6: Commit**

```bash
git add vlog_tool/tasks/compress.py vlog_tool/tasks/analyze.py vlog_tool/tasks/transcribe.py vlog_tool/tasks/scripts.py vlog_tool/tasks/refine.py
git commit -m "feat(tasks): add files filter param to all pipeline steps"
```

---

### Task 3: Add `selectionMode` + `selectedFiles` to frontend state

**Files:**
- Modify: `vlog_tool/ui/static/src/state.js`
- Modify: `vlog_tool/ui/static/src/main.js`

- [ ] **Step 1: Add state fields**

In `vlog_tool/ui/static/src/state.js`, add:
```js
  selectionMode: false,
  selectedFiles: [],
  _selectAllCheckbox: null,  // ref for "select all" indeterminate state
```

Add a `clearSelection()` helper:
```js
function clearSelection() {
  state.selectionMode = false;
  state.selectedFiles = [];
}
export { state, clearSelection };
```

- [ ] **Step 2: Wire source-switch to clear selection**

In `vlog_tool/ui/static/src/main.js`, find the `setSource` calls and add `clearSelection()` when source changes. In `main.js:setSource`, call before `saveProject()`:
```js
if (source !== state.source) {
  state.selectionMode = false;
  state.selectedFiles = [];
}
```

- [ ] **Step 3: Commit**

```bash
git add vlog_tool/ui/static/src/state.js vlog_tool/ui/static/src/main.js
git commit -m "feat(ui): add selectionMode + selectedFiles to state, clear on source switch"
```

---

### Task 4: Render selection mode in sidebar

**Files:**
- Modify: `vlog_tool/ui/static/src/sidebar.js`
- Modify: `vlog_tool/ui/static/style.css`

- [ ] **Step 1: Add "Select Videos" button in sidebar header**

In `vlog_tool/ui/static/src/sidebar.js`, find the `renderVideoList()` function or the sidebar header. Add a "Select Videos" button that toggles `state.selectionMode`.

Create a new function `toggleSelection()`:
```js
function toggleSelection() {
  state.selectionMode = !state.selectionMode;
  if (!state.selectionMode) {
    state.selectedFiles = [];
  }
  renderVideoList();
}
```

Add the button in the video header (in `loadVideos` or the HTML template). When `selectionMode` is true, show "Cancel" instead.

- [ ] **Step 2: Update `renderVideoItem` for selection mode**

In `renderVideoItem()` (sidebar.js line 103):
- When `state.selectionMode` is true, prepend a checkbox to the item
- When checked, `state.selectedFiles` contains the item's `v.file`
- When the item is in `state.selectedFiles`, apply a highlight class (`video-item.selected`)
- When `state.selectionMode` is false, no checkbox, no highlight

```js
// At start of renderVideoItem, add checkbox if in selection mode:
let checkboxHtml = '';
let selectedClass = '';
if (state.selectionMode) {
  const isSelected = state.selectedFiles.includes(v.file);
  selectedClass = isSelected ? ' selected' : '';
  checkboxHtml = `<input type="checkbox" class="video-checkbox" data-file="${escapeHtml(v.file)}" ${isSelected ? 'checked' : ''}>`;
}

// Modify the li.className line:
li.className = 'video-item' + selectedClass;
if (state.currentVideo === v.file) li.classList.add('active');
if (!v.match) li.classList.add('no-match');

// Add checkboxHtml at the start of innerHTML:
li.innerHTML = `
  ${checkboxHtml}
  <div class="video-name">...
```

Add checkbox change handler:
```js
// In renderVideoItem, after setting innerHTML:
if (state.selectionMode) {
  const cb = li.querySelector('.video-checkbox');
  if (cb) {
    cb.addEventListener('change', () => {
      if (cb.checked) {
        if (!state.selectedFiles.includes(v.file)) state.selectedFiles.push(v.file);
      } else {
        state.selectedFiles = state.selectedFiles.filter(f => f !== v.file);
      }
      renderVideoList();  // re-render to update highlights
    });
  }
}
```

- [ ] **Step 3: Add Select All / Deselect All in selection mode header**

In `loadVideos()` or `renderVideoList()`, when `state.selectionMode` is true, show "Select All" / "Deselect All" links above the list:

```js
// In renderVideoList(), after clearing ul.innerHTML:
if (state.selectionMode) {
  const headerDiv = document.createElement('div');
  headerDiv.className = 'selection-header';
  const allSelected = state.selectedFiles.length === state.videos.length && state.videos.length > 0;
  headerDiv.innerHTML = `
    <span class="selection-count">Selected: ${state.selectedFiles.length}/${state.videos.length}</span>
    <span class="selection-action" data-action="all">${allSelected ? 'Deselect All' : 'Select All'}</span>
    <span class="selection-action" data-action="cancel" style="color:var(--warn)">Cancel</span>
  `;
  headerDiv.querySelector('[data-action="all"]').onclick = () => {
    if (allSelected) {
      state.selectedFiles = [];
    } else {
      state.selectedFiles = state.videos.map(v => v.file);
    }
    while (ul.firstChild) ul.removeChild(ul.firstChild);
    renderVideoList();
  };
  headerDiv.querySelector('[data-action="cancel"]').onclick = () => {
    state.selectionMode = false;
    state.selectedFiles = [];
    while (ul.firstChild) ul.removeChild(ul.firstChild);
    renderVideoList();
  };
  ul.appendChild(headerDiv);
}
```

- [ ] **Step 4: Add CSS for selection mode**

In `vlog_tool/ui/static/style.css`, add:
```css
.video-item.selected {
  background: rgba(79, 195, 247, 0.08);
  border-left: 3px solid var(--accent);
}
.video-checkbox {
  margin: 0 8px 0 4px;
  flex-shrink: 0;
}
.selection-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  font-size: var(--text-sm);
  color: var(--text-secondary);
  border-bottom: 1px solid var(--border);
}
.selection-count {
  flex: 1;
}
.selection-action {
  cursor: pointer;
  color: var(--accent);
  padding: 2px 6px;
  border-radius: var(--radius-sm);
}
.selection-action:hover {
  background: rgba(79, 195, 247, 0.1);
}
```

- [ ] **Step 5: Commit**

```bash
git add vlog_tool/ui/static/src/sidebar.js vlog_tool/ui/static/style.css
git commit -m "feat(ui): add selection mode with checkboxes, select all/cancel in sidebar"
```

---

### Task 5: Wire selection to runner panel

**Files:**
- Modify: `vlog_tool/ui/static/src/runner.js`
- Modify: `vlog_tool/ui/static/src/sidebar.js` (export `toggleSelection`)

- [ ] **Step 1: Update "Run" button text when selection active**

In `runner.js:renderRun()`, after building the run button, check `state.selectionMode`:
```js
  const runBtn = $('btn-run-start');
  if (state.selectionMode && state.selectedFiles.length === 0) {
    runBtn.disabled = true;
    runBtn.innerHTML = `${icon('play', 16)} 请先选择视频`;
  } else if (state.selectionMode) {
    runBtn.innerHTML = `${icon('play', 16)} 运行选中步骤 (${state.selectedFiles.length} videos)`;
  }
```

- [ ] **Step 2: Send `files` and `overwrite` in startRun**

In `startRun()` (line 130), modify the API call payload to include `files` when in selection mode:
```js
    const payload = {
      day_label: _lastRunDay,
      steps: checked,
      use_transcripts: $('run-use-transcripts').checked,
    };
    if (state.selectionMode && state.selectedFiles.length > 0) {
      payload.files = state.selectedFiles;
    }
    const overwriteCb = $('run-overwrite');
    if (overwriteCb?.checked) {
      payload.overwrite = true;
    }
    const r = await api('POST', '/api/run/start', payload);
```

- [ ] **Step 3: Add "Overwrite existing" checkbox to run panel**

In `renderRun()`, add after the steps section:
```js
    <div class="run-options">
      <label class="run-option-check">
        <input type="checkbox" id="run-overwrite">
        <span>覆盖已有文件（不跳过）</span>
      </label>
    </div>
```

- [ ] **Step 4: Export `toggleSelection` and expose to main.js**

Add to sidebar.js exports:
```js
  toggleSelection,
```

In `main.js`, add the button handler. Find the video header area in index.html or create a button that calls `toggleSelection`. The "Select Videos" button should appear in the sidebar header area.

- [ ] **Step 5: Commit**

```bash
git add vlog_tool/ui/static/src/runner.js vlog_tool/ui/static/src/sidebar.js vlog_tool/ui/static/src/main.js
git commit -m "feat(ui): wire selection to run panel with overwrite checkbox"
```

---

### Task 6: Verify and clean up

**Files:**
- Run full test suite

- [ ] **Step 1: Run tests**

```bash
python -m pytest vlog_tool/tests/ -v -x
```
Expected: all 612 tests pass.

- [ ] **Step 2: Manual smoke test**

```bash
python main.py serve --no-browser
```
1. Open UI → sidebar shows no checkboxes by default
2. Click "Select Videos" → checkboxes appear
3. Select 2 videos → count shows "Selected: 2/4"
4. Go to Run tab → button shows "Run (2 videos)"
5. Click Run → pipeline processes only those 2 files
6. Progress shows selected count, not total
7. Click "Cancel" in selection mode → checkboxes disappear, selection cleared
8. Switch source (compressed↔original) → selection cleared

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "test: add tests for files filter param and selection mode"
```
