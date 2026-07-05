# Skill Extraction Candidates

> Source: 2026-07-05 iteration on `docs/analysis/2026-07-04-current-project-review.md`.
> Purpose: track repeatable project workflows that could become skills to reduce rediscovery and token use.

## Strong Candidates

### `vlog-review-iteration`

Use when continuing remediation from a project review document such as `docs/analysis/YYYY-MM-DD-current-project-review.md`.

Why it helps:
- The workflow repeats: read review item, verify whether it is still current, write a failing test, implement one narrow fix, update `ROADMAP.md`, run targeted verification, commit one change.
- It prevents stale-review work, because the first step is to confirm the issue still exists in current code.
- It preserves the user's commit preference: one feature/fix per commit, no push without explicit approval.

Suggested skill contents:
- Required inputs: review document path, target priority band.
- Checklist: current-state verification, RED test, minimal fix, docs update, targeted tests, commit.
- Common traps: review item already fixed, pre-commit formatting leaves empty working-tree status noise, mixing docs cleanup with code fixes.

### `vlog-artifact-identity-fixes`

Use when modifying selected-video execution, split segment mapping, recursive original lookup, sidecar matching, or plan/export resolution.

Why it helps:
- The project has multiple identity layers: filename stem, index prefix, `.vmeta`, `.vindex`, and `media_identity`.
- Many bugs come from comparing the wrong identifier across compressed videos, analysis JSON, scripts, transcripts, and plans.
- A skill can point agents to the canonical helpers and required realistic test names before they edit routing or task code.

Suggested skill contents:
- Canonical contract: prefer `media_identity` and compressed/original stems over generated JSON filenames.
- Required tests: realistic compressed filename such as `002_GL010684.mp4` with AI-generated JSON title filename.
- Files to inspect first: `clio/identity.py`, `clio/vmeta.py`, `clio/ui/routes/videos.py`, `clio/tasks/_helpers.py`.

### `vlog-config-split-changes`

Use when changing config schema, defaults, UI config editing, examples, or migration behavior.

Why it helps:
- The V2 config split has strict global/project ownership.
- Missing example updates or ownership validation can leak API keys or make UI saves fail later.
- A skill can route agents directly to `GlobalConfig`, `ProjectConfig`, config route ownership sets, examples, and tests.

Suggested skill contents:
- Global-only vs project-only ownership table.
- Required updates: `config.example.yaml`, `docs/project.example.yaml`, README docs when user-visible.
- Required tests: config V2 load/migration plus route ownership tests.

## Existing Planned Skills To Revisit

Historical docs already planned these project skills, but they are not currently committed as tracked project files:

- `adding-ai-provider`
- `adding-new-task`
- `adding-cli-subcommand`

Before creating them, run the `writing-skills` process: define pressure scenarios, observe baseline failures, write the minimal skill, validate with realistic tasks, then commit each skill separately.

## Not Worth A Skill Yet

- One-off review notes that only touch a single constant or README line.
- Mechanical formatting commands; keep these in quick references instead.
- Generic TDD or verification workflow; existing superpowers skills already cover those.
