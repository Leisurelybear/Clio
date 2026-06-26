# AGENTS.md — AI Maintenance Manual & Project Memory

> Quick reference for **AI assistants taking over maintenance**.
> User preference: Chinese for conversation, **English** for commit messages and this document.

## 1. Project in One Sentence

An **AI preprocessing pipeline**: raw travel vlog footage → ffmpeg compression → Gemini reviews video + DeepSeek writes script → JianYing (CapCut) manual editing.

## 2. Tech Stack

- **Python 3.11+** (PEP 604 `X | None`, dataclass)
- **ffmpeg / ffprobe** (video processing; GoPro 4K → 640p 5MB compressed)
- **google-genai** (Gemini 2.5 Flash video File API)
- **httpx** (DeepSeek / OpenAI compatible calls)
- **PyYAML** (config parsing)
- **pytest** (unit tests, auto-run in CI; **643 test cases**)

Dependencies in `requirements.txt`; `setup.ps1`/`setup.sh` creates venv + installs ffmpeg + copies `.env` in one click.

## 3. Directory Structure (Simplified)

```
vlog-video-analysis/
├── main.py                    CLI entry
├── vlog_tool/
│   ├── config/                AppConfig + load_config (config package)
│   ├── shutdown.py            beforeStop hook
│   ├── pipeline.py            High-level pipeline orchestration
│   ├── analyze.py             AI interaction functions
│   ├── compress.py            ffmpeg wrapper
│   ├── prompts.py             All prompt templates
│   ├── transcribe.py          Whisper ASR core
│   ├── whisper_cli.py         Whisper CLI
│   ├── utils.py               ffmpeg discovery, file IO, extract_json
│   ├── log.py                 Logging (hourly rotating, TeeWriter)
│   ├── cut.py                 Segment cutting (ffmpeg wrapper)
│   ├── split.py               Long video splitter
│   ├── vmeta.py               .vmeta/.vindex sidecar metadata
│   ├── progress.py            Progress tracker (used by UI + CLI)
│   ├── tasks/                 Pipeline steps (per-step modules)
│   ├── ui/                    Web UI (stdlib http.server)
│   │   ├── server.py          HTTP server
│   │   ├── routes/            Route handlers (refine, transcripts, whisper)
│   │   └── static/            Frontend (no build step, ES modules)
│   └── ai/                    AI providers
│       ├── base.py            TaskName enum, Provider Protocol
│       ├── factory.py         Provider lookup by name
│       ├── gemini.py          Gemini multimodal
│       └── openai_compat.py   DeepSeek / OpenAI / Tongyi / Moonshot
├── templates/                  vlog_template.md, trip_context.md
├── config.example.yaml / .env.example
├── requirements.txt / requirements-locked.txt
├── .github/workflows/test.yml
└── vlog_tool/tests/            pytest unit tests (643 cases)
```

> See `docs/superpowers/agents/directory-tree.md` for full tree with file-level annotations and test coverage details.

## 4. Key Conventions

### 4.1 Commit

- **English** message, **Conventional Commits**: `type(scope): subject`
- **Each commit as small as possible** — one independent feature/fix per commit
- Types: `feat` / `fix` / `refactor` / `docs` / `chore`
- History rewriting: use `git rebase -i --root`; on Windows use byte-level Python filter (see gotchas.md §9.2)

### 4.2 Workflow

- **Plan first, then implement**: record in ROADMAP.md, confirm approach, then code
- **Document new modules**: README.md for users, AGENTS.md for AI (purpose, entry, conventions)

### 4.3 Code Style

- No comments unless explaining **why** (WHAT is self-evident)
- Chinese for user-facing copy (CLI prompts, error messages)
- Default `skip_existing=True` shared by all steps (controlled by `analyze` toggle)
- AI-returned JSON uses `extract_json()`: first `json.loads`, then regex `{}`

### 4.4 Configuration

- Repo commits `config.example.yaml` / `.env.example`; real files gitignored
- No local paths, proxy IPs, API keys in examples (use placeholders)
- After config changes, update both example and READMEs

### 4.5 Prompts

- All in `vlog_tool/prompts.py` as constants
- Trip context injected via `_wrap_with_context()` before all prompts
- Output format: JSON (for `extract_json()` parsing)

### 4.6 Refine Special Modes

**Changing AI for refine stage:** `refine_text` falls back to `video_analyze` by default. To use a cheaper pure-text model:

```yaml
ai:
  tasks:
    refine_text:
      provider: deepseek
      model: deepseek-chat
```

**Targeted fix mode (`--fix`):** For known errors (place names, numbering), more reliable than free review:
- Use with `-i` specifying a **single** json file
- Switches to "Targeted fix based on user feedback" prompt
- `_changelog` first entry always "Modified XXX per user feedback"
- Implemented in `prompts.py`: `REFINE_TEXT_FIX_PROMPT` / `REFINE_SCRIPT_FIX_PROMPT`

## 5. User Preferences

- Language: Chinese for conversation, **English** for commits/docs/AGENTS.md
- Commit granularity: one feature per commit, **do not batch**
- History rewriting: force-push accepted
- **No** API keys / local paths in config files
- **No** test code (unless explicitly requested)
- **Push must be explicitly confirmed**. Local commits fine, `git push` requires user approval.

## 6. AI Transfer Protocol

Upon taking over, the AI should:

1. `git log --oneline -10` — recent changes
2. `git status` — uncommitted changes
3. Read `config.example.yaml` — config structure
4. Read `templates/trip_context.md` — current trip background
5. Read `docs/superpowers/agents/gotchas.md` — known pitfalls (only if modifying affected modules)
6. Read `CHANGELOG.md` — project history (only if needed)
7. Ask the user what they want to do

For new features: **discuss plan first → user confirms → implement → one commit → confirm before push**.

## 7. Quick Reference

### Running Tests

```bash
# Full run
python -m pytest vlog_tool/tests/ -v
# Single module
python -m pytest vlog_tool/tests/test_utils.py -v
```

GitHub Actions runs tests on Python 3.11/3.12 (Ubuntu + Windows).

### Code Formatting

```bash
ruff format .
ruff check .
```

Pre-commit hook auto-runs ruff on staged `.py` files (`.githooks/pre-commit`).

### Verification Flow

```bash
python main.py check                           # Environment check
python main.py analyze --force                 # Run everything once
python main.py analyze                         # Verify skip works
python main.py refine                          # Verify trip context injection
python main.py serve --no-browser              # Verify UI starts
```

### Dependency Locking

`requirements.txt` (loose) for daily dev; `requirements-locked.txt` (pinned) for CI.

## 8. On-Demand Loading Index

| If you need to... | Load this |
|---|---|
| Understand the project quickly | AGENTS.md (already loaded) |
| See project history and recent changes | `CHANGELOG.md` |
| Know known pitfalls and traps | `docs/superpowers/agents/gotchas.md` |
| Check active refactoring items | `docs/superpowers/agents/optimization-plan.md` |
| See full directory tree with annotations | `docs/superpowers/agents/directory-tree.md` |
| Add a new AI provider | Skill: `adding-ai-provider` |
| Add a new AI task | Skill: `adding-new-task` |
| Add a new CLI subcommand | Skill: `adding-cli-subcommand` |
