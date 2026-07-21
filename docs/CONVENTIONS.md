# Documentation Conventions

Canonical naming and layout rules for files under `docs/`.
See also: design `docs/superpowers/specs/2026-07-22-docs-naming-conventions-design.md`.

## Filename pattern

```text
YYYY-MM-DD-<topic>[-suffix].md
```

| Rule | Convention |
|------|------------|
| Case | All lowercase |
| Word separator | kebab-case (`-`) |
| Date | `YYYY-MM-DD`; required for dated artifacts |
| Language | English in filenames; Chinese OK in body |
| Roadmap ID | Lowercase, no hyphen: `r012` (not `R-012` / `R012`) |
| Project name | Use `clio` in new filenames (not legacy `vlog-editing-helper`) |

## Suffixes by directory

| Directory | Suffix | Example |
|-----------|--------|---------|
| `docs/superpowers/specs/` | required `-design` | `2026-07-19-plan-seg-card-density-design.md` |
| `docs/superpowers/plans/` | required `-plan` | `2026-07-19-plan-seg-card-density-plan.md` |
| `docs/superpowers/reviews/` | none required | `2026-06-14-whisper-transcription-review.md` |
| `docs/analysis/` | none required | `2026-07-20-full-project-review.md` |
| `docs/review/` | none required | keep kebab form |
| `docs/refactor/` | `-plan` when the doc is a plan | `2026-06-12-clio-refactor-plan.md` |
| `docs/archive/` | none required | `2026-07-01-roadmap-archive.md` |
| `docs/` root | stable references may omit date | `cli-reference.md` |
| `docs/superpowers/agents/` | ops notes; date prefix not required | `gotchas.md` |

## New document checklist

1. All-lowercase kebab-case
2. Date prefix (except root stable references and agents ops notes)
3. Correct `-design` / `-plan` suffix when under specs/plans
4. Roadmap IDs as `r012`
5. Prefer `clio` over legacy product names in filenames

## Directory roles (layout unchanged)

| Directory | Purpose |
|-----------|---------|
| `docs/superpowers/specs/` | Feature design specs |
| `docs/superpowers/plans/` | Implementation plans |
| `docs/superpowers/reviews/` | Spec/plan review write-ups |
| `docs/superpowers/agents/` | AI maintenance notes |
| `docs/analysis/` | Point-in-time project reviews / iterations |
| `docs/review/` | Feature-scoped audits |
| `docs/refactor/` | Historical refactor notes |
| `docs/archive/` | Archived roadmap snapshots |
| `docs/screenshots/` | UI screenshots |

## Exemptions

- `docs/cli-reference.md`, `docs/project.example.yaml`
- `docs/superpowers/agents/*` (unless adding a new dated artifact)
- `docs/screenshots/*`
