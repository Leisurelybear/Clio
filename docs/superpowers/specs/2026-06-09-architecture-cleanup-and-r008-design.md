# Architecture Cleanup & R-008 UI Single-Step Execution

## Overview

Two-phase project to improve code maintainability and add missing functionality:

- **Phase 1**: Split monolithic `server.py` / `app.js`, de-localize machine-specific content, fix known bugs
- **Phase 2**: Implement R-008 (UI single-step pipeline execution with file selection)

---

## Phase 1: Architecture Cleanup + De-localization

### 1.1 server.py Modularization

Current: 940-line monolith with `make_handler()` closure pattern.

Target structure:

```
vlog_tool/ui/
├── server.py           # make_handler skeleton (~80 lines): create closure, register routes
├── services.py         # Shared logic: project resolution, registry, file detection (~200 lines)
│   ├── _project_output_dir()
│   ├── _resolve_project_input()   # (renamed from _resolve_project_dir)
│   ├── _get_project_output()
│   ├── _registry_path() / _add_to_registry()
│   ├── _list_projects()
│   ├── _detect_steps()
│   ├── _find_texts_dirs()
│   ├── _resolve_texts() / _resolve_in()
│   └── _send_video_range()
├── routes/
│   ├── __init__.py
│   ├── config.py       # /api/config, /api/config/raw
│   ├── project.py      # /api/project, /api/projects, /api/project/create, /api/project/add
│   ├── video.py        # /api/videos, /api/video
│   ├── text.py         # /api/texts, /api/voiceover, /api/plans, /api/plan
│   └── pipeline.py     # /api/run/*, /api/cut
```

**Route module pattern**: Each exports `register_routes(handler_class, services)` that attaches methods like `do_GET_config`, `do_PUT_project` etc.

**server.py**: Creates the closure (output_dir, input_dir, static_dir, config, config_path), instantiates services, calls `register_routes()` for each module.

### 1.2 app.js Modularization

Current: 1075-line monolith with global `state` + top-level functions.

Target structure:

```
vlog_tool/ui/static/
├── app.js              # init() + event bindings (~80 lines)
├── state.js            # state object, state management helpers
├── api.js              # api() wrapper + per-endpoint functions
└── viewer.js           # All render functions (video list, plan, texts, voiceover, run)
```

**Module pattern**: Each file assigns to a namespace object (e.g. `window.State`, `window.API`, `window.Viewer`). `app.js` imports these and wires init.

### 1.3 De-localization

| Item | Action |
|------|--------|
| `projects.json` | Add to `.gitignore` |
| `*.bak` files | Add `*.bak` to `.gitignore` |
| `config.example.yaml` | Ensure all paths/IPs are placeholders |
| Local path in code comments | Scan and replace with generic descriptions |
| `VIDEO_EXTS` duplication | Move to shared constant (e.g. `vlog_tool/_constants.py`) |
| Missing `trip_context_2.md` | Either create stub or fix `config.yaml` reference |

### 1.4 Bug Fixes

| Bug | Fix |
|-----|-----|
| Silent exception eating in `do_POST _run()` | Log exception, update progress.json with error status |
| Late import in `do_PUT /api/config/raw` | Move to top-level imports |
| API keys in `.env` (plaintext) | Already gitignored; document in README to use env vars |
| `apply_run_paths` mutates config in-place | Return new config instead of mutating |

---

## Phase 2: R-008 UI Single-Step Execution

### 2.1 Feature Summary

Enable running individual pipeline steps (compress / analyze / voiceover / plan) from the UI with:

- Directory selection (custom input dir, not limited to config)
- File selection (choose specific files within the directory)
- Progress display (reuse R-005's `.progress.json` mechanism)
- Auto-refresh target view on completion

### 2.2 Backend: New / Extend Endpoints

**`POST /api/run/step`**
```json
{
  "step": "compress|analyze|voiceover|plan",
  "input_dir": "E:\\Videos\\MyTrip",       // optional, defaults to config.input_dir
  "files": ["001.mp4", "002.mp4"],          // optional, empty/null = all
  "day_label": "day1"                        // required for plan
}
```

Response: `{ "ok": true, "run_id": "..." }`

**`GET /api/run/status?run_id=..."`** (extend existing)

Returns per-file progress within a step, not just overall progress.

**`POST /api/run/cancel`** (new)

Cancel a running step.

### 2.3 Frontend: Run Panel Revamp

Current: simple step checkboxes + "Run selected" button.

New design:
- Top section: **input directory** (text input + "Browse" placeholder)
- Middle section: **file list** with checkboxes (preview thumbnails optional)
- Step selector: checkboxes for compress/analyze/voiceover/plan
- "Run selected" button
- Progress area: per-file status (pending/running/done/failed) + ETA
- "Cancel" button when running

### 2.4 Data Flow

```
User selects dir → POST /api/run/step/check (scan dir, return file list)
User checks files → UI stores selection
User clicks Run → POST /api/run/step { step, input_dir, files }
Backend runs step in daemon thread, writes progress to .progress.json
UI polls GET /api/run/status every 2 seconds
On completion: auto-switch to relevant view (e.g. analyze done → texts tab)
```

### 2.5 Edge Cases

| Case | Behavior |
|------|----------|
| No files selected | Run all files in directory |
| Directory doesn't exist | Show inline error, don't proceed |
| Step already running | Return 409 Conflict |
| Single file failure | Continue with remaining files, mark failed |
| Cancel mid-run | Set cancel flag, thread checks and stops at next safe point |

---

## Implementation Order

1. **Phase 1a: Security & de-localization** (`.gitignore`, constants, config cleanup)
2. **Phase 1b: server.py modularization** (split into routes/ + services.py)
3. **Phase 1c: app.js modularization** (split into state/api/viewer)
4. **Phase 1d: Bug fixes** (silent exception, late import, in-place mutation)
5. **Phase 2: R-008 backend** (`POST /api/run/step`, extend status, cancel)
6. **Phase 2: R-008 frontend** (run panel revamp, file selection, progress)
7. **Phase 2: Polish** (auto-refresh, error handling, docs)

---

## Non-goals (explicitly out of scope)

- Full rewrite of server.py architecture (e.g., Flask/FastAPI migration)
- Frontend framework migration (React/Vue)
- CLI changes
- Test infrastructure (unless user explicitly requests)
- Docker support
