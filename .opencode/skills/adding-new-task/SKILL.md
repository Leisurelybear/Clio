---
name: adding-new-task
description: Use when adding a new AI task (e.g. subtitle translation), creating a pipeline step, defining a new prompt for the AI analysis pipeline
---

# Adding a New AI Task

## Overview

A new AI task touches the prompt constants, analysis function, pipeline orchestration, and CLI registration.

## Implementation

1. `clio/ai/base.py` — add enum value to `TaskName`
2. `clio/prompts.py` — add prompt constant
3. `clio/analyze.py` — add `task_xxx()` function, reuse `_wrap_with_context()`
4. `clio/pipeline.py` — add `run_xxx_all()` with `cancel_event` propagation
5. `main.py` — register subcommand, reuse `_add_io_args()`
6. Update READMEs

## Common Mistakes

- Writing trip context manually instead of using `_wrap_with_context()`
- Output not in JSON format — breaks `extract_json()` parsing
- Forgetting `cancel_event` propagation — add to pipeline.py's event list
- Skipping `skip_existing` integration — consistent with other steps
