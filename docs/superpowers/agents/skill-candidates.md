# Skill Extraction Candidates

> Use this to decide whether a recurring workflow should become a project skill.

## Existing Project Skills

| Skill | Use when |
| --- | --- |
| `adding-ai-provider` | Adding provider adapters, model capability tags, or provider config examples |
| `adding-new-task` | Adding a new AI task, prompt, pipeline step, or task binding |
| `adding-cli-subcommand` | Adding or changing CLI command registration |
| `vlog-config-split-changes` | Changing global/project config schema, config UI, ownership validation, or examples |
| `vlog-artifact-identity-fixes` | Touching original/compressed/split identity, sidecar matching, or plan/export media resolution |
| `vlog-review-iteration` | Working through a review document or ROADMAP bug item one fix at a time |

## Strong Future Candidates

### `vlog-ui-run-workflows`

Use when changing Run panel behavior, SSE progress, cancellation, selected files, or completion navigation.

Why it helps:

- The workflow crosses `runner.js`, `/api/run/*`, `ProgressTracker`, `ProcessingState`, and pipeline steps.
- Bugs often come from updating the UI but not the route contract, or vice versa.
- It can encode the required verification path: route tests, runner syntax checks, and selected-file behavior.

### `vlog-whisper-model-flow`

Use when changing Whisper install, model cache, transcript generation, or transcript UI.

Why it helps:

- Whisper has separate CLI, UI route, model download, and task execution paths.
- Cancellation/download status must remain safe on Windows and on interrupted network downloads.
- It can route agents to `clio/ui/routes/whisper_*`, `clio/transcribe.py`, `clio/tasks/transcribe.py`, and transcript tests.

## Existing Planned Skills To Revisit

Historical docs already planned these project skills, but they are not currently committed as tracked project files:

- `adding-ai-provider`
- `adding-new-task`
- `adding-cli-subcommand`

Before creating them, run the `writing-skills` process: define pressure scenarios, observe baseline failures, write the minimal skill, validate with realistic tasks, then commit each skill separately.

## Not Worth A Skill Yet

- One-off README wording updates.
- Mechanical formatting commands.
- Generic TDD or generic code review workflow that is not project-specific.
