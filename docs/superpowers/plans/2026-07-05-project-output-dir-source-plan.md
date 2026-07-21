# Project Output Directory Source Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `project.yaml` the primary source for project `paths.output_dir`, while keeping `project.json.output_dir` as a legacy fallback.

**Architecture:** Centralize project output resolution in `clio/ui/services/project_service.py`. Project UI state remains in `project.json`; pipeline/config paths remain in `project.yaml`. Creation helpers write both files only for compatibility, but readers prefer `project.yaml`.

**Tech Stack:** Python 3.11+, PyYAML, stdlib `json`, existing pytest suite.

---

### Task 1: Prefer `project.yaml` for Project Output Resolution

**Files:**
- Modify: `clio/ui/services/project_service.py`

- [ ] **Step 1: Inspect `_project_output_dir` callers**

Run: `rg -n "_project_output_dir\\(" clio`

Expected: Callers use the helper for UI project listing, routes, and output paths.

- [ ] **Step 2: Update `_project_output_dir`**

Change `_project_output_dir(proj_input_dir)` so it resolves output directory in this order:

1. `project.yaml` field `paths.output_dir`
2. legacy `project.json` field `output_dir`
3. default `"output"`

Relative paths must remain relative to `proj_input_dir`, matching current behavior.

- [ ] **Step 3: Run targeted verification**

Run: `python -m pytest clio/tests/test_routes_config.py clio/tests/test_routes_projects.py -q`

Expected: existing project/config route tests pass.

### Task 2: Keep New Project Writes Compatible

**Files:**
- Modify: `clio/ui/routes/projects.py`
- Modify: `ROADMAP.md`

- [ ] **Step 1: Review project creation paths**

Run: `rg -n "output_dir|_create_project_yaml|project.json" clio/ui/routes/projects.py clio/ui/services/file_service.py`

Expected: `handle_post_project_create` and `handle_post_project_add` create `project.json` and call `_create_project_yaml`.

- [ ] **Step 2: Keep `project.json.output_dir` as compatibility metadata**

Do not remove `output_dir` from `project.json` write payloads in this iteration. Readers now prefer `project.yaml`, so old UI state remains harmless and old consumers keep working.

- [ ] **Step 3: Update `ROADMAP.md`**

Mark `A-005` as addressed with a note that `project.yaml.paths.output_dir` is now authoritative and `project.json.output_dir` is legacy fallback.

- [ ] **Step 4: Verify no unrelated files changed**

Run: `git diff --check` and `git status --short`

Expected: only `project_service.py`, `ROADMAP.md`, and this plan file changed.

### Task 3: Commit

**Files:**
- Commit: `clio/ui/services/project_service.py`
- Commit: `ROADMAP.md`
- Commit: `docs/superpowers/plans/2026-07-05-project-output-dir-source-plan.md`

- [ ] **Step 1: Commit one focused change**

Run:

```bash
git add clio/ui/services/project_service.py ROADMAP.md docs/superpowers/plans/2026-07-05-project-output-dir-source-plan.md
git commit -m "fix(project): prefer project yaml output dir"
```

Expected: one local commit, no push.
