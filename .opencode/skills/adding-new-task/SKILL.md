---
name: adding-new-task
description: Use when adding a new Clio AI task, prompt, pipeline step, task binding, run-panel step, or generated artifact type in the vlog preprocessing pipeline.
---

# Adding a New AI Task

## Workflow

1. Define the task contract in `clio/ai/base.py` if it needs provider routing.
2. Add prompt constants in `clio/prompts.py`; keep AI output JSON-compatible for `extract_json()`.
3. Add AI-call helpers in `clio/analyze.py`, reusing context wrapping and token usage plumbing.
4. Add a task module or function under `clio/tasks/` when batch processing is needed.
5. Wire orchestration through `clio/pipeline.py` and keep these inputs consistent:
   - `files`
   - `overwrite`
   - `cancel_event`
   - `context_override`
   - `task_prompts`
   - `tracker`
6. Update CLI dispatch in `clio/main.py` and UI run-panel behavior when user-facing.
7. Update examples/docs and add focused tests.

## Required Checks

Use existing task modules as patterns:

- `clio/tasks/analyze.py`
- `clio/tasks/scripts.py`
- `clio/tasks/plan.py`
- `clio/tasks/transcribe.py`

Run focused tests for changed layers, then full regression:

```bash
python -m pytest clio/tests/test_pipeline.py clio/tests/test_routes_run.py -q
python -m pytest clio/tests/ -q
```

## Common Mistakes

- Writing trip context manually instead of using the existing context path.
- Returning free-form text where downstream code expects JSON.
- Forgetting selected-file, overwrite, cancellation, or rerun behavior.
- Creating a new skip toggle instead of using the shared `analyze.skip_existing`.
