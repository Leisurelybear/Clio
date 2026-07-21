# Docs Naming Conventions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Standardize all `docs/` filenames to lowercase kebab-case with date prefixes and type suffixes, document the rules, and fix in-repo markdown links.

**Architecture:** Pure documentation work. Write `docs/CONVENTIONS.md`, batch-`git mv` non-conforming files per the approved rename map, then grep-and-replace path references. Directory layout stays unchanged. One final commit.

**Tech Stack:** git, bash/rg, markdown. No application code changes. No tests suite runs required beyond filesystem + link grep checks.

**Spec:** `docs/superpowers/specs/2026-07-22-docs-naming-conventions-design.md`

## Global Constraints

- Filenames: all lowercase kebab-case, English only
- Date prefix: `YYYY-MM-DD-` (except root stable refs and `docs/superpowers/agents/*`)
- Roadmap IDs in filenames: `r012` form (lowercase, no hyphen)
- Specs: must end with `-design.md`; plans: must end with `-plan.md`
- Do not restructure directories; do not rewrite doc bodies except path strings
- Do not force-push or rewrite history
- Single commit at the end: `docs: standardize docs naming conventions`
- Leave rename-map tables in the design spec as historical record (old names stay there on purpose)

## File map

| Path | Role |
|------|------|
| Create `docs/CONVENTIONS.md` | Canonical naming rules for humans + AI |
| Modify `AGENTS.md` §4 | One-line pointer to CONVENTIONS |
| `git mv` under `docs/analysis/`, `docs/refactor/`, `docs/superpowers/plans/`, `docs/superpowers/specs/` | Apply rename map |
| Modify path strings in `ROADMAP.md`, `CHANGELOG.md`, `AGENTS.md`, and various `docs/**/*.md` | Fix broken links |
| Leave alone | `docs/screenshots/*`, `docs/superpowers/agents/*` (except link text if they point at renamed files), root `cli-reference.md`, `project.example.yaml` |

---

### Task 1: Write conventions doc + AGENTS pointer

**Files:**
- Create: `docs/CONVENTIONS.md`
- Modify: `AGENTS.md` (after §4 header / new subsection)

- [ ] **Step 1: Create `docs/CONVENTIONS.md`**

Write exactly:

```markdown
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
```

Note: the outer file uses a fenced `text` block inside markdown; write the file with a single nested fence carefully (outer markdown, inner `text` fence closed properly).

- [ ] **Step 2: Add AGENTS pointer**

In `AGENTS.md`, after the `## 4. Key Conventions` heading (before `### 4.1 Commit`), insert:

```markdown
### 4.0 Docs naming

- All files under `docs/` follow `docs/CONVENTIONS.md` (date + kebab-case; specs `-design`, plans `-plan`).
```

- [ ] **Step 3: Sanity-check files exist**

Run:

```bash
test -f docs/CONVENTIONS.md && rg -n "CONVENTIONS" AGENTS.md
```

Expected: file exists; AGENTS shows the new subsection line.

Do **not** commit yet (single commit at Task 5).

---

### Task 2: Rename analysis + refactor files

**Files:**
- `git mv` under `docs/analysis/` and `docs/refactor/`

- [ ] **Step 1: Rename analysis files**

From repo root (bash / Git Bash):

```bash
git mv docs/analysis/2026-06-14-vlog-editing-helper-Review.md \
       docs/analysis/2026-06-14-clio-review.md
git mv docs/analysis/2026-06-17-vlog-editing-helper-full-analysis.md \
       docs/analysis/2026-06-17-clio-full-analysis.md
git mv docs/analysis/2026-06-18-vlog-editing-helper-review.md \
       docs/analysis/2026-06-18-clio-review.md
git mv docs/analysis/2026-06-20-REVIEW-part1.md \
       docs/analysis/2026-06-20-review-part1.md
git mv docs/analysis/2026-06-21-review_part2.md \
       docs/analysis/2026-06-21-review-part2.md
git mv docs/analysis/2026-06-24-claude_review.md \
       docs/analysis/2026-06-24-claude-review.md
git mv docs/analysis/2026-06-28-vlog-editing-helper-review.md \
       docs/analysis/2026-06-28-clio-review.md
```

- [ ] **Step 2: Rename refactor files**

```bash
git mv docs/refactor/UT-improvement.md \
       docs/refactor/2026-06-13-ut-improvement.md
git mv docs/refactor/UT-progress.md \
       docs/refactor/2026-06-13-ut-progress.md
git mv "docs/refactor/vlog-editing-helper-重构规划.md" \
       docs/refactor/2026-06-12-clio-refactor-plan.md
git mv docs/refactor/vmeta-implementation-plan.md \
       docs/refactor/2026-06-26-vmeta-implementation-plan.md
```

- [ ] **Step 3: Verify analysis/refactor filenames**

```bash
ls docs/analysis/
ls docs/refactor/
```

Expected:
- No uppercase letters, no `_`, no Chinese characters in those directories
- New names match the map above
- Unchanged files still present (`2026-06-18-review-fix-result.md`, `2026-07-04-current-project-review.md`, `2026-07-06-ut-review.md`, `2026-07-16-iteration.md`, `2026-07-16-iteration-wave2.md`, `2026-07-20-full-project-review.md`)

---

### Task 3: Rename superpowers plans + specs

**Files:**
- `git mv` under `docs/superpowers/plans/` and `docs/superpowers/specs/`

- [ ] **Step 1: Rename plans (add `-plan`, normalize r-ids)**

```bash
git mv docs/superpowers/plans/2026-06-10-r003-cli-selective-processing.md \
       docs/superpowers/plans/2026-06-10-r003-cli-selective-processing-plan.md
git mv docs/superpowers/plans/2026-06-14-whisper-transcription.md \
       docs/superpowers/plans/2026-06-14-whisper-transcription-plan.md
git mv docs/superpowers/plans/2026-06-18-R012-preview-progress-bar-plan.md \
       docs/superpowers/plans/2026-06-18-r012-preview-progress-bar-plan.md
git mv docs/superpowers/plans/2026-06-21-config-descriptions-and-test-expansion.md \
       docs/superpowers/plans/2026-06-21-config-descriptions-and-test-expansion-plan.md
git mv docs/superpowers/plans/2026-06-22-config-auto-upgrade.md \
       docs/superpowers/plans/2026-06-22-config-auto-upgrade-plan.md
git mv docs/superpowers/plans/2026-06-22-r014-token-usage.md \
       docs/superpowers/plans/2026-06-22-r014-token-usage-plan.md
git mv docs/superpowers/plans/2026-06-22-r018-multi-video-selection.md \
       docs/superpowers/plans/2026-06-22-r018-multi-video-selection-plan.md
git mv docs/superpowers/plans/2026-06-25-jianying-export.md \
       docs/superpowers/plans/2026-06-25-jianying-export-plan.md
git mv docs/superpowers/plans/2026-06-27-media-identity-implementation.md \
       docs/superpowers/plans/2026-06-27-media-identity-plan.md
git mv docs/superpowers/plans/2026-06-27-phase4-type-hardening.md \
       docs/superpowers/plans/2026-06-27-phase4-type-hardening-plan.md
git mv docs/superpowers/plans/2026-06-30-rename-clio.md \
       docs/superpowers/plans/2026-06-30-rename-clio-plan.md
git mv docs/superpowers/plans/2026-07-02-model-registry.md \
       docs/superpowers/plans/2026-07-02-model-registry-plan.md
git mv docs/superpowers/plans/2026-07-04-quality-stability-fixes.md \
       docs/superpowers/plans/2026-07-04-quality-stability-fixes-plan.md
git mv docs/superpowers/plans/2026-07-04-ui-redesign.md \
       docs/superpowers/plans/2026-07-04-ui-redesign-plan.md
git mv docs/superpowers/plans/2026-07-05-project-output-dir-source.md \
       docs/superpowers/plans/2026-07-05-project-output-dir-source-plan.md
git mv docs/superpowers/plans/2026-07-06-provider-connection-test.md \
       docs/superpowers/plans/2026-07-06-provider-connection-test-plan.md
git mv docs/superpowers/plans/2026-07-06-run-preview-summary.md \
       docs/superpowers/plans/2026-07-06-run-preview-summary-plan.md
git mv docs/superpowers/plans/2026-07-10-route-registry.md \
       docs/superpowers/plans/2026-07-10-route-registry-plan.md
git mv docs/superpowers/plans/2026-07-17-plan-domain-edit-readiness.md \
       docs/superpowers/plans/2026-07-17-plan-domain-edit-readiness-plan.md
git mv docs/superpowers/plans/2026-07-17-plan-reorder-feedback.md \
       docs/superpowers/plans/2026-07-17-plan-reorder-feedback-plan.md
git mv docs/superpowers/plans/2026-07-18-ffmpeg-handling-phase-a.md \
       docs/superpowers/plans/2026-07-18-ffmpeg-handling-phase-a-plan.md
git mv docs/superpowers/plans/2026-07-18-remove-physical-split.md \
       docs/superpowers/plans/2026-07-18-remove-physical-split-plan.md
git mv docs/superpowers/plans/2026-07-18-video-waveform.md \
       docs/superpowers/plans/2026-07-18-video-waveform-plan.md
git mv docs/superpowers/plans/2026-07-19-plan-global-preview-timeline.md \
       docs/superpowers/plans/2026-07-19-plan-global-preview-timeline-plan.md
git mv docs/superpowers/plans/2026-07-19-plan-preview-chrome-waveform.md \
       docs/superpowers/plans/2026-07-19-plan-preview-chrome-waveform-plan.md
git mv docs/superpowers/plans/2026-07-19-plan-seg-card-density.md \
       docs/superpowers/plans/2026-07-19-plan-seg-card-density-plan.md
```

Already correct (do **not** rename):  
`2026-06-24-agents-docs-optimization-plan.md`, `2026-07-11-project-video-manager-plan.md`, and this plan file once named with `-plan`.

- [ ] **Step 2: Rename specs (add `-design`, normalize r-ids / topic)**

```bash
git mv docs/superpowers/specs/2026-06-13-config-hot-reload-audit.md \
       docs/superpowers/specs/2026-06-13-config-hot-reload-audit-design.md
git mv docs/superpowers/specs/2026-06-14-whisper-transcription-enhancements.md \
       docs/superpowers/specs/2026-06-14-whisper-transcription-enhancements-design.md
git mv docs/superpowers/specs/2026-06-18-R012-preview-progress-bar-design.md \
       docs/superpowers/specs/2026-06-18-r012-preview-progress-bar-design.md
git mv docs/superpowers/specs/2026-06-20-R016-whisper-model-ui-download.md \
       docs/superpowers/specs/2026-06-20-r016-whisper-model-ui-download-design.md
git mv docs/superpowers/specs/2026-06-30-rename-to-clio.md \
       docs/superpowers/specs/2026-06-30-rename-clio-design.md
git mv docs/superpowers/specs/2026-07-03-security-hardening-docs-maintenance.md \
       docs/superpowers/specs/2026-07-03-security-hardening-docs-maintenance-design.md
git mv docs/superpowers/specs/2026-07-04-ui-redesign.md \
       docs/superpowers/specs/2026-07-04-ui-redesign-design.md
```

- [ ] **Step 3: Verify plans/specs naming**

```bash
# every plan ends with -plan.md
ls docs/superpowers/plans/ | grep -v -- '-plan\.md$' || true
# every spec ends with -design.md
ls docs/superpowers/specs/ | grep -v -- '-design\.md$' || true
# no uppercase R0xx leftovers
ls docs/superpowers/plans/ docs/superpowers/specs/ | grep -E 'R0|R1' || true
```

Expected: both `grep -v` commands print nothing; no `R0`/`R1` uppercase ID filenames.

---

### Task 4: Fix in-repo path references

**Files (known hits before rename; re-grep after):**
- Modify: `ROADMAP.md`
- Modify: `CHANGELOG.md`
- Modify: `AGENTS.md`
- Modify: `docs/analysis/2026-06-18-review-fix-result.md`
- Modify: `docs/refactor/2026-06-13-ut-progress.md`
- Modify: `docs/analysis/2026-06-14-clio-review.md`
- Modify: `docs/superpowers/agents/optimization-plan.md`
- Modify: `docs/superpowers/plans/2026-06-24-agents-docs-optimization-plan.md`
- Modify: any plan/spec that embeds its **own** old path string in the body
- Do **not** rewrite the rename tables inside `docs/superpowers/specs/2026-07-22-docs-naming-conventions-design.md` (historical map)

- [ ] **Step 1: Inventory remaining old basenames**

```bash
rg -n --glob '*.md' \
  'vlog-editing-helper-Review|vlog-editing-helper-full-analysis|vlog-editing-helper-review|REVIEW-part1|review_part2|claude_review|UT-improvement|UT-progress|vmeta-implementation-plan\.md|R012-preview|R016-whisper|rename-to-clio|media-identity-implementation|config-hot-reload-audit\.md|whisper-transcription-enhancements\.md|security-hardening-docs-maintenance\.md|重构规划' \
  .
```

Also catch plan paths that lost the new `-plan` suffix:

```bash
rg -n --glob '*.md' \
  'docs/superpowers/plans/2026-07-19-plan-seg-card-density\.md|docs/superpowers/plans/2026-07-18-remove-physical-split\.md|docs/superpowers/plans/2026-07-18-ffmpeg-handling-phase-a\.md|docs/superpowers/plans/2026-07-17-plan-domain-edit-readiness\.md|docs/superpowers/plans/2026-07-02-model-registry\.md|docs/superpowers/plans/2026-07-05-project-output-dir-source\.md|docs/superpowers/plans/2026-07-17-plan-reorder-feedback\.md|docs/superpowers/plans/2026-07-18-video-waveform\.md|docs/superpowers/plans/2026-07-19-plan-global-preview-timeline\.md|docs/superpowers/plans/2026-07-19-plan-preview-chrome-waveform\.md' \
  .
```

Record every hit outside the design rename table.

- [ ] **Step 2: Apply known reference fixes**

Replace strings (path only; leave surrounding prose):

| Location | Old substring | New substring |
|----------|---------------|---------------|
| `ROADMAP.md` | `docs/analysis/2026-06-20-REVIEW-part1.md` | `docs/analysis/2026-06-20-review-part1.md` |
| `ROADMAP.md` | `docs/analysis/2026-06-21-review_part2.md` | `docs/analysis/2026-06-21-review-part2.md` |
| `ROADMAP.md` | `docs/analysis/2026-06-24-claude_review.md` | `docs/analysis/2026-06-24-claude-review.md` |
| `ROADMAP.md` | `docs/superpowers/specs/2026-06-13-config-hot-reload-audit.md` | `docs/superpowers/specs/2026-06-13-config-hot-reload-audit-design.md` |
| `ROADMAP.md` | `docs/superpowers/plans/2026-07-19-plan-seg-card-density.md` | `docs/superpowers/plans/2026-07-19-plan-seg-card-density-plan.md` |
| `ROADMAP.md` | `docs/superpowers/plans/2026-07-18-remove-physical-split.md` | `docs/superpowers/plans/2026-07-18-remove-physical-split-plan.md` |
| `ROADMAP.md` | `docs/superpowers/plans/2026-07-17-plan-domain-edit-readiness.md` | `docs/superpowers/plans/2026-07-17-plan-domain-edit-readiness-plan.md` |
| `CHANGELOG.md` | `docs/superpowers/plans/2026-07-18-remove-physical-split.md` | `docs/superpowers/plans/2026-07-18-remove-physical-split-plan.md` |
| `CHANGELOG.md` | `docs/superpowers/plans/2026-07-18-ffmpeg-handling-phase-a.md` | `docs/superpowers/plans/2026-07-18-ffmpeg-handling-phase-a-plan.md` |
| `AGENTS.md` | `docs/superpowers/plans/2026-07-02-model-registry.md` | `docs/superpowers/plans/2026-07-02-model-registry-plan.md` |
| `docs/analysis/2026-06-18-review-fix-result.md` | `` `2026-06-18-vlog-editing-helper-review.md` `` | `` `2026-06-18-clio-review.md` `` |
| `docs/refactor/2026-06-13-ut-progress.md` | `docs/refactor/UT-improvement.md` | `docs/refactor/2026-06-13-ut-improvement.md` |
| `docs/analysis/2026-06-14-clio-review.md` | `docs/superpowers/specs/2026-06-13-config-hot-reload-audit.md` | `docs/superpowers/specs/2026-06-13-config-hot-reload-audit-design.md` |
| `docs/superpowers/agents/optimization-plan.md` | `docs/analysis/2026-06-20-REVIEW-part1.md` | `docs/analysis/2026-06-20-review-part1.md` |
| `docs/superpowers/plans/2026-06-24-agents-docs-optimization-plan.md` | `docs/analysis/2026-06-20-REVIEW-part1.md` | `docs/analysis/2026-06-20-review-part1.md` |

For each plan file that was renamed, update **self-path** strings in its body (footer lines like `Plan complete and saved to \`docs/superpowers/plans/<old>.md\`` and any `git add docs/superpowers/plans/<old>.md` examples) to the new `-plan.md` path. Same for any plan that references a sibling plan path that was renamed.

Use targeted search-replace per file; do not blanket-replace bare words like `UT-progress` in CHANGELOG history sentences that are not file paths (archive line `docs: UT-progress v2...` is a **commit subject**, leave it).

- [ ] **Step 3: Re-run inventory; require clean outside design**

```bash
rg -n --glob '*.md' \
  'vlog-editing-helper-Review|vlog-editing-helper-full-analysis|vlog-editing-helper-review\.md|REVIEW-part1|review_part2|claude_review|docs/refactor/UT-|R012-preview|R016-whisper|rename-to-clio\.md|media-identity-implementation|config-hot-reload-audit\.md[^a-z-]|whisper-transcription-enhancements\.md|security-hardening-docs-maintenance\.md|重构规划' \
  . || true
```

Expected: hits only inside:
- `docs/superpowers/specs/2026-07-22-docs-naming-conventions-design.md` (rename tables)
- optionally this plan file if it still lists old names as instructions (acceptable)

Also confirm no dangling plan paths without `-plan`:

```bash
# list plan files
ls docs/superpowers/plans/ > /tmp/plans.txt
# any markdown link to plans/ that does not end in -plan.md
rg -n --glob '*.md' 'docs/superpowers/plans/[0-9]{4}-[0-9]{2}-[0-9]{2}-[^`\])\s"]+' . \
  | grep -v -- '-plan\.md' \
  | grep -v 'docs-naming-conventions' \
  || true
```

Expected: empty (or only design/plan instruction tables).

---

### Task 5: Final verification + commit

**Files:** all changes from Tasks 1–4

- [ ] **Step 1: Filename quality checks**

```bash
# analysis/refactor: no uppercase, no underscore, no non-ascii names
find docs/analysis docs/refactor -maxdepth 1 -type f -name '*.md' | while read f; do
  b=$(basename "$f")
  echo "$b" | grep -qE '^[a-z0-9][a-z0-9.-]*\.md$' || echo "BAD: $b"
done

# plans all *-plan.md
find docs/superpowers/plans -maxdepth 1 -type f -name '*.md' ! -name '*-plan.md' -print
# specs all *-design.md
find docs/superpowers/specs -maxdepth 1 -type f -name '*.md' ! -name '*-design.md' -print
```

Expected: no `BAD:` lines; both finds print nothing.

- [ ] **Step 2: Confirm CONVENTIONS + AGENTS**

```bash
test -f docs/CONVENTIONS.md
rg -n 'docs/CONVENTIONS.md' AGENTS.md
```

Expected: file present; AGENTS references it.

- [ ] **Step 3: Review git status**

```bash
git status
git diff --stat
```

Expected: only docs + `AGENTS.md` (and renames). No code under `clio/`.

- [ ] **Step 4: Single commit**

```bash
git add docs/CONVENTIONS.md AGENTS.md docs/analysis docs/refactor docs/superpowers ROADMAP.md CHANGELOG.md
git status
git commit -m "$(cat <<'EOF'
docs: standardize docs naming conventions

EOF
)"
git status
```

Expected: clean working tree; commit message as above.

---

## Self-review (plan author)

1. **Spec coverage:** Naming rules → Task 1. analysis/refactor renames → Task 2. plans/specs renames → Task 3. Reference fixes + exemptions → Task 4. Verification + single commit → Task 5. Non-goals (no dir merge, no body rewrite, no history rewrite) respected.
2. **Placeholders:** None; every `git mv` pair and known reference row is explicit.
3. **Consistency:** New basenames match the design rename map (`media-identity-plan`, `rename-clio-design`, `r012`/`r016`).
4. **Note:** Historical commit subjects and design rename tables intentionally retain old names.
