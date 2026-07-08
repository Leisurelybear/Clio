---
name: vlog-config-split-changes
description: Use when changing Clio config schema, global/project ownership, config auto-upgrade, config UI forms, provider/task bindings, examples, or validation for config.yaml/project.yaml.
---

# Vlog Config Split Changes

## Core Contract

`config.yaml` is global. `project.yaml` is project-local. Do not add the same setting to both layers.

Global examples belong in `config.example.yaml`; project examples belong in `docs/project.example.yaml`.

## Workflow

1. Read `clio/config/models.py`, `clio/config/loader.py`, and `clio/config/validators.py`.
2. Decide ownership before coding:
   - Global: providers, API key env names, ffmpeg/ffprobe paths, logs, proxy, provider defaults.
   - Project: input/output paths, task bindings, context, compress target/splitting, analyze/script/plan/export/whisper behavior.
3. Update model defaults and parsing/auto-upgrade together.
4. Update route ownership sets in `clio/ui/routes/config_routes.py` when field ownership changes.
5. Update UI config rendering only if the field needs custom behavior; generic fields usually render from the raw config tree.
6. Update examples and docs. Never put local paths, proxy IPs, or API keys in committed examples.
7. Add tests for load/merge, validation, route save, and auto-upgrade behavior.

## Verification

```bash
python -m pytest clio/tests/test_config_v2.py clio/tests/test_routes_config.py clio/tests/test_config_cache.py -q
python -m pytest clio/tests/ -q
```

## Common Mistakes

- Updating dataclasses but not auto-upgrade defaults.
- Allowing project config to contain provider/API-key metadata.
- Updating examples but not README/UI docs for user-visible fields.
- Resolving project-relative paths from the repo root instead of the project directory.
