# R-018: Multi-Video Selection + Step Execution

## Background

The current run panel allows step selection and running all videos, or rerunning a single video. There is no "select multiple videos → choose steps → run only selected videos" interaction. Users want to select videos in the sidebar, then run the pipeline on only the selected items.

## Principles

1. **Default invisible** — no checkboxes shown by default. User explicitly enters "selection mode" via a button.
2. **Idempotent** — running 1 video or all videos produces the same output filenames. Output filenames are determined by source filenames, not by selection scope.
3. **Per-entry independent** — each sidebar entry (parent video + each `_segNN` split segment) has its own checkbox. Selecting parent does not auto-select segments.
4. **Backend filters by basename** — the pipeline processes the same way as "run all", but filters input by the provided `files[]` list. No pipeline logic changes.

## Architecture

### State

```js
state.selectionMode = false     // toggle by "Select Videos" button
state.selectedFiles = []        // basenames like ["001_巴黎铁塔", "002_卢浮宫"]
```

Switching video source (compressed ↔ original) clears selection.

### Frontend Components

**Sidebar (`sidebar.js`)**:
- Normal state: video list as-is, no checkboxes
- Selection mode header: `[Select All] [Deselect All] [Cancel]` + `Selected: N/M`
- Entry: `☑ basename` with highlight styling when selected
- Exit selection mode: click "Cancel" button, clear all selections

**Run panel (`runner.js`)**:
- Reads `state.selectedFiles` when `state.selectionMode` is true
- Button text: `▶ Run (N videos)` or `▶ Run (全部)`
- Disabled with hint when in selection mode but nothing selected

### Backend API

`POST /api/run/start` — extended payload:

```json
{
  "steps": ["compress", "analyze", "transcribe", "voiceover", "plan", "refine"],
  "files": ["001_巴黎铁塔", "001_GL010683_seg01"],
  "overwrite": false
}
```

- `files` — optional array. Empty or absent → process all videos (existing behavior).
- `overwrite` — optional bool. When true, force overwrite existing output files (overrides `skip_existing`).

In `handle_post_run_start`, pass `files` and `overwrite` to the pipeline entry function.

### Pipeline Changes

**`tasks/run.py` or `pipeline.py`**:

In `run_analyze_all` (and similar for compress/transcribe/scripts/plan):
- Accept an optional `files: list[str]` parameter
- When present, filter the file discovery (e.g., `find_videos()`) to only include matching basenames
- Pipeline loops over the same items, just fewer of them

This is the key insight for **idempotency**: we don't change what happens to each file. We only change which files we iterate over. The output of processing `001_巴黎铁塔.mp4` is identical whether you run it alone or in batch.

**Filtering strategy per step**:

| Step | Discovery | Filter by basename |
|------|-----------|-------------------|
| compress | `find_videos(input_dir)` → compress candidates | intersect with `files` |
| analyze | `find_videos(compressed_dir)` → existing `.mp4` | intersect with `files` |
| transcribe | `find_videos(compressed_dir)` → existing `.mp4` | intersect with `files` |
| scripts | `glob(texts_dir, *.json)` | intersect stem with `files` |
| refine | `glob(texts_dir, *.json)` + `glob(scripts_dir, *.json)` | intersect stem with `files` |
| plan | full project plan (not per-video) | no filtering (plan always runs on all data) |

**Split segments**: Segments like `001_GL010683_seg01` appear as their own entries in the sidebar. In the pipeline, each segment is processed independently — it resolves back to the original source video with the appropriate offset from the split manifest. Selection filtering works identically on segments since they have their own basename.

### Conflict / Overwrite Handling

User config `analyze.skip_existing` controls default behavior (default: skip).

Two override mechanisms:
1. `POST /api/run/start` `overwrite: true` parameter — API-level force overwrite
2. Run panel "Overwrite existing" checkbox (sends `overwrite: true`)

When conflict detected & no override set:
- UI shows confirmation dialog: "N files already exist. Overwrite / Skip / Cancel"
- "Overwrite" → sets `overwrite: true` and re-sends
- "Skip" → proceeds with `overwrite: false` (skip_existing handles it)
- "Cancel" → no-op

This is a UI-only pattern: the confirmation dialog is just a frontend loop that retries with the user's choice. The backend is stateless.

### Progress Display

Progress count reflects the actual number of videos being processed (selected set), not total project videos.

Example:
- Project has 50 videos
- User selects 3
- Progress shows: `[3/3] Compressing 002_卢浮宫...` (not `[3/50]`)

### Error Handling

- If `files[]` contains entries not found in the current project directory, log a warning and skip (don't fail the whole run)
- If `files[]` is empty while `selectionMode=true`, show error in Run panel: "No videos selected"
- The `overwrite` flag is per-run, not persisted

## Files to Change

| File | Change |
|------|--------|
| `ui/static/src/state.js` | Add `selectionMode`, `selectedFiles`, `clearSelection()` |
| `ui/static/src/sidebar.js` | Render checkbox when `selectionMode`, Select All/Cancel buttons |
| `ui/static/src/runner.js` | Read selected files, show count in button, overwrite checkbox, conflict dialog |
| `ui/static/src/main.js` | Wire "Select Videos" button toggle |
| `ui/static/style.css` | Selection mode highlight style |
| `ui/routes/run.py` | Accept `files` + `overwrite` in `handle_post_run_start` |
| `vlog_tool/pipeline.py` | Pass `files` filter to each step's `run_*_all()` |
| `vlog_tool/tasks/compress.py` | Accept `files` filter parameter |
| `vlog_tool/tasks/analyze.py` | Accept `files` filter parameter |
| `vlog_tool/tasks/transcribe.py` | Accept `files` filter parameter |
| `vlog_tool/tasks/scripts.py` | Accept `files` filter parameter |
| `vlog_tool/tasks/refine.py` | Accept `files` filter parameter |

## Non-Goals

- Plan step is not affected (always runs on full project data)
- No change to CLI behavior (CLI continues to support `-i` for single file)
- No change to rerun single video flow (existing `POST /api/rerun` unchanged)
- No change to how output files are named or stored
