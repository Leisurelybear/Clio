# Docs Naming Conventions — Design

Date: 2026-07-22  
Status: approved for planning  
Scope: standardize `docs/` file naming + batch rename existing files + fix in-repo references. Directory layout is **not** restructured.

## Goal

Make every document under `docs/` follow one predictable naming scheme so humans and AI agents can find, link, and create docs without guessing. Deliver:

1. A written convention (`docs/CONVENTIONS.md`)
2. A single bulk rename of non-conforming files
3. Updated in-repo markdown links
4. A pointer from `AGENTS.md` §4

## Non-goals

- Merging or deleting directories (`analysis/`, `review/`, `refactor/`, etc.)
- Rewriting document bodies (except path references)
- Renaming screenshots, `docs/superpowers/agents/*` ops notes, or root stable references (`cli-reference.md`, `project.example.yaml`)
- Git history rewrite / force-push

## Naming rules

### General pattern

```text
YYYY-MM-DD-<topic>[-suffix].md
```

| Rule | Convention |
|------|------------|
| Case | All lowercase |
| Word separator | kebab-case (`-`) |
| Date | `YYYY-MM-DD`; if missing, use file mtime or earliest date in content |
| Language | English in filenames; Chinese OK in body |
| Roadmap ID | Lowercase, no hyphen: `r012` (not `R-012` / `R012`) |
| Legacy project name | Filename `vlog-editing-helper` → `clio` |

### Suffixes by directory

| Directory | Suffix | Example |
|-----------|--------|---------|
| `docs/superpowers/specs/` | required `-design` | `2026-07-19-plan-seg-card-density-design.md` |
| `docs/superpowers/plans/` | required `-plan` | `2026-07-19-plan-seg-card-density-plan.md` |
| `docs/superpowers/reviews/` | none required | `2026-06-14-whisper-transcription-review.md` |
| `docs/analysis/` | none required | `2026-07-20-full-project-review.md` |
| `docs/review/` | none required | existing form kept if already kebab |
| `docs/refactor/` | `-plan` when the doc is a plan | `2026-06-12-clio-refactor-plan.md` |
| `docs/archive/` | none required | `2026-07-01-roadmap-archive.md` |
| `docs/` root | stable references may omit date | `cli-reference.md` |

### New-doc checklist

1. All-lowercase kebab-case
2. Date prefix (except root stable references)
3. Correct suffix for specs/plans
4. Roadmap IDs as `r012`

## Rename map

### `docs/analysis/`

| Old | New |
|-----|-----|
| `2026-06-14-vlog-editing-helper-Review.md` | `2026-06-14-clio-review.md` |
| `2026-06-17-vlog-editing-helper-full-analysis.md` | `2026-06-17-clio-full-analysis.md` |
| `2026-06-18-vlog-editing-helper-review.md` | `2026-06-18-clio-review.md` |
| `2026-06-20-REVIEW-part1.md` | `2026-06-20-review-part1.md` |
| `2026-06-21-review_part2.md` | `2026-06-21-review-part2.md` |
| `2026-06-24-claude_review.md` | `2026-06-24-claude-review.md` |
| `2026-06-28-vlog-editing-helper-review.md` | `2026-06-28-clio-review.md` |

Unchanged when already conforming (e.g. `2026-06-18-review-fix-result.md`, `2026-07-20-full-project-review.md`).

### `docs/refactor/`

| Old | New |
|-----|-----|
| `UT-improvement.md` | `2026-06-13-ut-improvement.md` |
| `UT-progress.md` | `2026-06-13-ut-progress.md` |
| `vlog-editing-helper-重构规划.md` | `2026-06-12-clio-refactor-plan.md` |
| `vmeta-implementation-plan.md` | `2026-06-26-vmeta-implementation-plan.md` |

Dates for formerly undated files come from file mtime.

### `docs/superpowers/plans/`

Every plan must end with `-plan.md`. Roadmap IDs normalized to `r012` form.

| Old | New |
|-----|-----|
| `2026-06-10-r003-cli-selective-processing.md` | `2026-06-10-r003-cli-selective-processing-plan.md` |
| `2026-06-14-whisper-transcription.md` | `2026-06-14-whisper-transcription-plan.md` |
| `2026-06-18-R012-preview-progress-bar-plan.md` | `2026-06-18-r012-preview-progress-bar-plan.md` |
| `2026-06-21-config-descriptions-and-test-expansion.md` | `2026-06-21-config-descriptions-and-test-expansion-plan.md` |
| `2026-06-22-config-auto-upgrade.md` | `2026-06-22-config-auto-upgrade-plan.md` |
| `2026-06-22-r014-token-usage.md` | `2026-06-22-r014-token-usage-plan.md` |
| `2026-06-22-r018-multi-video-selection.md` | `2026-06-22-r018-multi-video-selection-plan.md` |
| `2026-06-25-jianying-export.md` | `2026-06-25-jianying-export-plan.md` |
| `2026-06-27-media-identity-implementation.md` | `2026-06-27-media-identity-plan.md` |
| `2026-06-27-phase4-type-hardening.md` | `2026-06-27-phase4-type-hardening-plan.md` |
| `2026-06-30-rename-clio.md` | `2026-06-30-rename-clio-plan.md` |
| `2026-07-02-model-registry.md` | `2026-07-02-model-registry-plan.md` |
| `2026-07-04-quality-stability-fixes.md` | `2026-07-04-quality-stability-fixes-plan.md` |
| `2026-07-04-ui-redesign.md` | `2026-07-04-ui-redesign-plan.md` |
| `2026-07-05-project-output-dir-source.md` | `2026-07-05-project-output-dir-source-plan.md` |
| `2026-07-06-provider-connection-test.md` | `2026-07-06-provider-connection-test-plan.md` |
| `2026-07-06-run-preview-summary.md` | `2026-07-06-run-preview-summary-plan.md` |
| `2026-07-10-route-registry.md` | `2026-07-10-route-registry-plan.md` |
| `2026-07-17-plan-domain-edit-readiness.md` | `2026-07-17-plan-domain-edit-readiness-plan.md` |
| `2026-07-17-plan-reorder-feedback.md` | `2026-07-17-plan-reorder-feedback-plan.md` |
| `2026-07-18-ffmpeg-handling-phase-a.md` | `2026-07-18-ffmpeg-handling-phase-a-plan.md` |
| `2026-07-18-remove-physical-split.md` | `2026-07-18-remove-physical-split-plan.md` |
| `2026-07-18-video-waveform.md` | `2026-07-18-video-waveform-plan.md` |
| `2026-07-19-plan-global-preview-timeline.md` | `2026-07-19-plan-global-preview-timeline-plan.md` |
| `2026-07-19-plan-preview-chrome-waveform.md` | `2026-07-19-plan-preview-chrome-waveform-plan.md` |
| `2026-07-19-plan-seg-card-density.md` | `2026-07-19-plan-seg-card-density-plan.md` |

Already correct (keep): `2026-06-24-agents-docs-optimization-plan.md`, `2026-07-11-project-video-manager-plan.md`.

### `docs/superpowers/specs/`

Every spec must end with `-design.md`. Roadmap IDs normalized.

| Old | New |
|-----|-----|
| `2026-06-13-config-hot-reload-audit.md` | `2026-06-13-config-hot-reload-audit-design.md` |
| `2026-06-14-whisper-transcription-enhancements.md` | `2026-06-14-whisper-transcription-enhancements-design.md` |
| `2026-06-18-R012-preview-progress-bar-design.md` | `2026-06-18-r012-preview-progress-bar-design.md` |
| `2026-06-20-R016-whisper-model-ui-download.md` | `2026-06-20-r016-whisper-model-ui-download-design.md` |
| `2026-06-30-rename-to-clio.md` | `2026-06-30-rename-clio-design.md` |
| `2026-07-03-security-hardening-docs-maintenance.md` | `2026-07-03-security-hardening-docs-maintenance-design.md` |
| `2026-07-04-ui-redesign.md` | `2026-07-04-ui-redesign-design.md` |

Other `*-design.md` files with lowercase r-ids stay as-is.

### Unchanged intentionally

- `docs/review/2026-06-16-feat-whisper-full-audit.md`
- `docs/archive/2026-07-01-roadmap-archive.md`
- `docs/cli-reference.md`, `docs/project.example.yaml`
- `docs/superpowers/agents/*`
- `docs/screenshots/*`

## Reference fix scope

After `git mv`, grep the whole repo for old basenames and paths. Update at least:

- `README.md`, `README.en.md`, `AGENTS.md`, `ROADMAP.md`, `CHANGELOG.md`
- Cross-links inside `docs/**/*.md`

Do not change non-docs code strings unless they are clearly docs paths.

## Delivery

1. Create `docs/CONVENTIONS.md` with the naming rules (and optional short history note; full rename map lives in this design or commit message).
2. Add a one-line pointer under `AGENTS.md` §4 Key Conventions.
3. Apply all renames via `git mv`.
4. Fix references.
5. Single commit: `docs: standardize docs naming conventions`.

## Verification

- No uppercase / underscore / Chinese filenames under `docs/` except where this design explicitly exempts (agents, screenshots, root stable refs).
- All files in `superpowers/plans/` end with `-plan.md`.
- All files in `superpowers/specs/` end with `-design.md`.
- Repo-wide search for old basenames returns no hits outside this design / CONVENTIONS history notes.
- `git status` shows only docs + AGENTS changes for this work.

## Implementation approach

Lightweight list-driven renames (Approach 1 from brainstorming):

- Conventions live in `docs/CONVENTIONS.md` (user-facing).
- `AGENTS.md` links to it (AI-facing).
- One atomic commit with `git mv` + link fixes for auditability and easy revert.
