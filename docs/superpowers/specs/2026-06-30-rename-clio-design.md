# Design: Rename Product to Clio

## Overview

Rename the existing project from its current identity ("Vlog 剪辑辅助工具", package `vlog_tool`) to **Clio** — a clean, single-word product name. The CLI entry changes from `python main.py <command>` to `clio <command>` (after install) or `python -m clio <command>` (without install).

## Scope

- **Package directory**: `vlog_tool/` → `clio/`
- **All internal imports**: `from vlog_tool.xxx` → `from clio.xxx`
- **CLI entry**: Add `clio` command via `pyproject.toml` + `clio/__main__.py`
- **Backwards compat**: Keep `main.py` as thin wrapper
- **Scripts**: `setup.ps1/sh`, `serve.ps1/sh`, `whisper-install.ps1/sh` — update references
- **CI/Config**: `pyproject.toml`, `.github/workflows/test.yml` — update paths
- **Docs**: `README.md`, `README.en.md`, `AGENTS.md`, `ROADMAP.md`, `docs/analysis/*.md`, docs under `vlog_tool/ui/`
- **Skills**: `.opencode/skills/adding-new-task/SKILL.md` — update package reference
- **Excluded**: Git repo directory name (`vlog-video-analysis/` stays as-is), VSCode config, coverage data, venv, `.githooks/` (no package name ref), `CHANGELOG.md` (historical accuracy)

## Detailed Design

### 1. Package Rename (vlog_tool/ → clio/)

Move the entire `vlog_tool/` directory tree to `clio/`. All imports referencing `vlog_tool` rewrite to `clio`.

```python
# Before
from vlog_tool.config import load_config
# After
from clio.config import load_config
```

Affected files: all `.py` files in `vlog_tool/` (including `vlog_tool/*.py`, `vlog_tool/ai/*.py`, `vlog_tool/config/*.py`, `vlog_tool/export/*.py`, `vlog_tool/tasks/*.py`, `vlog_tool/tests/*.py`, `vlog_tool/ui/*.py`, `vlog_tool/ui/routes/*.py`, `vlog_tool/ui/services/*.py`), plus `main.py` and `.opencode/start_ui.py`.

Strategy: simple find-and-replace `from vlog_tool` → `from clio` and `import vlog_tool` → `import clio`.

### 2. Entry Points

#### `clio/__main__.py` (new)
Enables `python -m clio <command>` without pip install.

```python
from clio.main import main
main()
```

#### `pyproject.toml`
Add `[project]` section with console_scripts entry point for `clio` command:

```toml
[project]
name = "clio"
version = "0.1.0"
description = "AI preprocessing pipeline for travel vlog editing"
requires-python = ">=3.11"

[project.scripts]
clio = "clio.main:main"
```

Update `[tool.pytest.ini_options]`:
```toml
testpaths = ["clio/tests"]
```

#### `main.py` (backwards compat wrapper)
Replace current content with a thin wrapper:

```python
#!/usr/bin/env python3
from clio.main import main
main()
```

#### `.opencode/start_ui.py`
Update import: `from clio.config` / `from clio.ui`.

### 3. Script Updates

Multiple occurrences per file — replace all.

| File | Changes |
|------|--------|
| `setup.ps1` | `"Vlog 剪辑辅助工具"` → `"Clio"`, `"Vlog 工具一键配置脚本"` → `"Clio 一键配置脚本"`, standalone `main.py` → `-m clio` in all command references |
| `setup.sh` | `"Vlog 剪辑辅助工具"` → `"Clio"`, standalone `main.py` → `-m clio` in all command references |
| `serve.ps1` | `main.py serve` → `python -m clio serve` |
| `serve.sh` | `main.py serve` → `python -m clio serve` |
| `whisper-install.ps1` | `main.py whisper install` → `python -m clio whisper install` |
| `whisper-install.sh` | `main.py whisper install` → `python -m clio whisper install` |

### 4. CI Configuration

`.github/workflows/test.yml`:
- `mypy vlog_tool/config/` → `mypy clio/config/`
- `python -c "import vlog_tool"` → `python -c "import clio"`
- `python -m pytest vlog_tool/tests/ --cov=vlog_tool` → `python -m pytest clio/tests/ --cov=clio`

### 5. Documentation

`README.md` / `README.en.md`:
- Title: "Vlog 剪辑辅助工具" → "Clio"
- Directory tree: `vlog_tool/` → `clio/`
- Test commands: `vlog_tool/tests/` → `clio/tests/`
- Links to `vlog_tool/ui/README.md` → `clio/ui/README.md`

`AGENTS.md`:
- Directory tree: `vlog_tool/` → `clio/`
- Test paths: `vlog_tool/tests/` → `clio/tests/`
- All references to `vlog_tool/`

`ROADMAP.md`, `docs/analysis/*.md`:
- Replace `vlog_tool/` with `clio/` where referencing current code paths

`.opencode/skills/adding-new-task/SKILL.md`:
- `vlog_tool/` → `clio/` in all path references

### 6. Test Mock String References

Test files use `unittest.mock.patch("vlog_tool.xxx")` as string arguments (e.g. `patch("vlog_tool.ai.gemini.genai.Client")`, `monkeypatch.setattr("vlog_tool.compress.resolve_binary", ...)`). These strings must also be updated: `"vlog_tool."` → `"clio."` in all `patch()` and `monkeypatch.setattr()` calls.

Affected test files include `test_ai_gemini.py`, `test_ai_openai_compat.py`, `test_analyze_funcs.py`, `test_compress.py`, `test_cut.py`, `test_export.py`, `test_export_routes.py`, `test_fs.py`, `test_helpers.py`, `test_main.py`, `test_pipeline.py`, and others.

Strategy: bulk replace `"vlog_tool.` → `"clio.` across all test `.py` files (same as import replacement).

### 7. Logger Names

Update logger name strings for consistency (cosmetic, but keeps `grep` clean):

- `logging.getLogger("vlog_tool.schema")` → `logging.getLogger("clio.schema")`
- `logging.getLogger("vlog_tool.export.jianying")` → `logging.getLogger("clio.export.jianying")`

### 8. Migration Sequence

The rename touches ~100+ files, but the change is purely mechanical (import path rewrite + name changes). Execution:

1. `git mv vlog_tool/ clio/` (rename directory; use `Move-Item` if `git mv` fails on Windows)
2. Bulk find-and-replace `from vlog_tool` → `from clio` and `import vlog_tool` → `import clio` across all `.py` files
3. Bulk find-and-replace `"vlog_tool.` → `"clio.` in all `.py` files (covers mock `patch()` strings and `getLogger()` names in one pass)
4. Create `clio/__main__.py`
5. Update `pyproject.toml`
6. Update `main.py` as wrapper
7. Update scripts (`setup.*`, `serve.*`, `whisper-install.*`)
8. Update CI (`.github/workflows/test.yml`)
9. Update docs (README, AGENTS, ROADMAP, analysis docs)
10. Update skills
11. Run tests to verify

## Files NOT to Change

- `.git/`, `__pycache__/`, `.venv/`, `node_modules/`
- `.env` / `.env.example` (no project name reference)
- `config.example.yaml` / `config.yaml` (no package name reference)
- `CHANGELOG.md` (historical accuracy — keep old path references as-is)
- `.githooks/` (no package name reference)
- `LICENSE`
- `requirements.txt` (no package name)
- `.gitignore`, `.mypy_cache/`, `.pytest_cache/`, `.ruff_cache/`, `.coverage`
- `projects.json*`, `opencode_session_import.json`
- Node modules / `package.json` / `vitest.config.js`
