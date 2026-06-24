# Agents Docs Optimization: AGENTS.md Slimming + Skills Extraction

## Background

AGENTS.md has grown to **695 lines / 49KB** — far beyond its original purpose as a "quick reference." An AI agent taking over must read the entire document before doing anything useful. Two critical issues:

1. **Information density problem** — 187 lines of §7 changelog + 147 lines of §9 gotchas + 45 lines of §11 optimization plan. Much is stale or irrelevant to a new agent.
2. **No on-demand loading** — everything is monolithic. There's no way for an agent to skip irrelevant sections.
3. **No skill extraction** — procedural guides like "how to add an AI provider" are repeated workflows that could be automated through opencode skills.

## Goals

| # | Goal | Metric |
|---|------|--------|
| 1 | Reduce AGENTS.md to essential rules only | <12KB / ~150 lines |
| 2 | Extract changelog to separate file | CHANGELOG.md |
| 3 | Extract gotchas to on-demand reference | docs/superpowers/agents/gotchas.md |
| 4 | Extract how-to guides as opencode skills | `.opencode/skills/*/SKILL.md` |
| 5 | All existing info preserved, just relocated | No data loss |

## Design

### Document Architecture

```
AGENTS.md (~12KB, always loaded)
├── §1~§4 — Core project identity, tech stack, conventions
├── §5 — User preferences (must-know rules)
├── §6 — AI transfer protocol (what to do on takeover)
├── §7 — Quick reference (test commands, verify flow)
└── §8 — Load-on-demand index (what file/skill to read when)

External files (loaded on demand):
├── CHANGELOG.md                          ← from old §7
├── docs/superpowers/agents/gotchas.md    ← from old §9
├── docs/superpowers/agents/optimization-plan.md  ← from old §11
└── docs/superpowers/agents/directory-tree.md     ← from old §3 (verbose tree)

Project skills (auto-loaded by opencode):
├── .opencode/skills/adding-ai-provider/SKILL.md    ← from old §5.1
├── .opencode/skills/adding-new-task/SKILL.md        ← from old §5.2
└── .opencode/skills/adding-cli-subcommand/SKILL.md  ← from old §5.5
```

### AGENTS.md New Structure

```
§1 一句话简介      (stay)
§2 技术栈           (stay)
§3 目录结构         (simplified tree, no file-level comments)
§4 关键约定         (pruned: keep only active rules, remove stale refs)
§5 用户偏好         (stay, must-know)
§6 AI 接手协议      (from old §12: what to do on takeover)
§7 快速参考         (test commands + verify flow, compact)
§8 按需加载索引     (NEW: a decision table of what to read when)
```

Key conventions to keep:
- Commit conventions (4.1 — actively used)
- Code style rules (4.3 — active)
- Config conventions (4.4 — active)
- Prompt conventions (4.5 — active)
- Pipeline planning workflow (4.2 — active)

Key conventions to trim:
- 4.6 Future Refactoring Directions — most completed or tracked in ROADMAP.md
- Phase 1/Phase 2 details — reference only, no inline text

### On-Demand Loading Index (AGENTS.md §8)

A decision table that tells the AI what to read for specific tasks:

| If you need to... | Load this |
|---|---|
| Understand the project quickly | AGENTS.md itself (already loaded) |
| See project history and what's changed | CHANGELOG.md |
| Know about known pitfalls and traps | docs/superpowers/agents/gotchas.md |
| Check active optimization/refactoring items | docs/superpowers/agents/optimization-plan.md |
| See full directory tree with file-level annotations | docs/superpowers/agents/directory-tree.md |
| Add a new AI provider | skill: `adding-ai-provider` |
| Add a new AI task | skill: `adding-new-task` |
| Add a new CLI subcommand | skill: `adding-cli-subcommand` |
| Configure AI model for refine stage | (inline in AGENTS.md §5) |
| Use targeted fix mode for refine | (inline in AGENTS.md §5) |

### Skills Design

Each skill follows the `agentskills.io/specification` format:
- YAML frontmatter with `name` and `description`
- `description` starts with "Use when..." describing triggering conditions
- NO workflow summary in description (avoids shortcut-taking)
- Skill body: overview, steps, code examples, common mistakes

Three skills to extract:

**1. `adding-ai-provider`**
- Trigger: "adding new AI provider, registering model, configuring API access"
- Content: implement provider class → register in factory → add config example → update README

**2. `adding-new-task`**
- Trigger: "adding new AI task (not refine), creating pipeline step, defining new prompt"
- Content: TaskName enum → prompt constant → analyze fn → pipeline fn → CLI subcommand → README
- Note: Refine configuration (§5.3, §5.4) stays inline in AGENTS.md as small config snippets

**3. `adding-cli-subcommand`**
- Trigger: "adding new CLI command, registering subcommand parser"
- Content: add_parser → dispatch branch → _add_io_args → skip_existing

### File Locations

```
.opencode/skills/adding-ai-provider/SKILL.md
.opencode/skills/adding-new-task/SKILL.md
.opencode/skills/adding-cli-subcommand/SKILL.md
```

OpenCode auto-discovers skills from `.opencode/skills/*/SKILL.md`. No config needed.

### CHANGELOG.md Format

Follows [Keep a Changelog](https://keepachangelog.com/) format:

```markdown
# Changelog

## [Unreleased]

### Added
- R-018 multi-video selection + step execution
- Token usage tracking (R-014)

## [2026-06-22]

### Changed
- Config auto-upgrade: inject missing dataclass defaults on load

### Fixed
- Various review findings (see commit log)
```

### Migration Strategy

1. Create external files first (so nothing is lost)
2. Rewrite AGENTS.md, cross-referencing external files
3. Create skill files
4. Verify: `git diff --stat` shows no data loss
5. Commit: one commit per logical change

## Files to Create/Change

| File | Action | Content source |
|------|--------|----------------|
| `AGENTS.md` | Rewrite (trim) | Old AGENTS.md sections 1-6, 8.1, 10, 12 |
| `CHANGELOG.md` | **Create** | Old AGENTS.md §7 history |
| `docs/superpowers/agents/gotchas.md` | **Create** | Old AGENTS.md §9 |
| `docs/superpowers/agents/optimization-plan.md` | **Create** | Old AGENTS.md §11 |
| `docs/superpowers/agents/directory-tree.md` | **Create** | Old AGENTS.md §3 (verbose tree) |
| `.opencode/skills/adding-ai-provider/SKILL.md` | **Create** | Old AGENTS.md §5.1 |
| `.opencode/skills/adding-new-task/SKILL.md` | **Create** | Old AGENTS.md §5.2 |
| `.opencode/skills/adding-cli-subcommand/SKILL.md` | **Create** | Old AGENTS.md §5.5 |

## Non-Goals

- ROADMAP.md is NOT modified (already large, but separately tracked)
- README.md / README.en.md are NOT modified
- No changes to test code or application logic
- No modification to config.example.yaml or .env.example
