# Maintenance Instructions for Future AI Agents

> Load this after `AGENTS.md` when planning non-trivial code changes.

## 1. Treat configuration as a two-layer contract

`config.yaml` is global and `project.yaml` is project-local. Relative project paths resolve from the project directory, not from the repo root or global config path.

When changing config behavior, update all relevant surfaces:

- dataclass model in `clio/config/models.py`
- parser/loader path in `clio/config/loader.py` or related config modules
- ownership validation in config routes when a field changes layer
- `config.example.yaml` or `docs/project.example.yaml`
- README/UI docs when user-visible
- tests for merge, path resolution, validation, and auto-upgrade behavior

Do not store API keys in YAML examples. Keep `api_key_env` as an environment variable name.

## 2. Preserve the pipeline step contract end to end

`run_pipeline_steps()` is the shared contract between CLI and UI. When adding or changing a step, keep these inputs coherent through route handlers, preview, orchestration, and task modules:

- `files`
- `overwrite`
- `cancel_event`
- `context_override`
- `task_prompts`
- `tracker`

Do not assume a step only runs from the full pipeline. Rerun, selected-file runs, preview summaries, and cancellation all need to remain consistent.

## 3. Reuse existing artifact matching helpers

The project relies on generated filenames, sidecar JSON files, split segments, compressed stems, index prefixes, `.vmeta`, `.vindex`, and `media_identity`.

Prefer helpers in:

- `clio.identity`
- `clio.vmeta`
- `clio.tasks._helpers`
- `clio.ui.services.file_service`
- `clio.ui.routes.videos`

Always sort filesystem iteration before assigning indices or comparing generated artifacts, because Windows and Linux directory order differs.

## 4. Keep AI provider lifecycle and retry semantics intact

Provider objects are cached in `clio.ai.factory`; tests rely on clearing that cache. `ProviderConfig.retry_attempts` means extra retries, while `with_retry(attempts=...)` means total calls. Convert using `retry_attempts + 1`.

For Gemini video analysis, keep this invariant:

1. upload once
2. wait until the File API object is active
3. pass cancellation into polling
4. call `generate_content`
5. delete the uploaded file in `finally`

Rate limiting should sleep outside shared locks when concurrency is involved.

## 5. Keep tests behavioral

Useful tests call production entry points and assert observable results. Avoid tests that duplicate production loops or only prove "does not raise" unless no observable state exists.

Route-dispatch tests may use mocks, but route/service behavior belongs in route/service tests. Frontend tests require Node 18 or newer; Node 16 fails before Vitest can execute because Vite imports newer `node:fs/promises` APIs.
