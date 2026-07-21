# Rename to Clio — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename package `vlog_tool/` → `clio/`, update all imports/mocks/loggers, add `clio` CLI entry point.

**Architecture:** Purely mechanical rename — no functional changes. The old `vlog_tool/` directory becomes `clio/`, all internal imports rewrite, `main.py` becomes a thin wrapper, and `pyproject.toml` gains a console_scripts entry.

**Tech Stack:** Python, pyproject.toml, bash/ps1 scripts, GitHub Actions.

---

### Task 1: Rename Directory + Bulk Import Rewrite

**Files:**
- Rename: `vlog_tool/` → `clio/`
- Modify: all `.py` files referencing `vlog_tool` in imports, mock strings, and logger names
- Modify: `.opencode/start_ui.py`
- Test: no test change needed yet (imports update in same pass)

- [ ] **Step 1: Rename directory**

```bash
# Try git mv first; fallback to Move-Item on Windows
git mv vlog_tool/ clio/
```

If `git mv` fails with "bad source" (Windows quirk), use:

```bash
Move-Item vlog_tool clio
```

- [ ] **Step 2: Bulk replace imports**

Replace all `from vlog_tool` → `from clio` and `import vlog_tool` → `import clio` across all `.py` files:

```bash
Get-ChildItem -Recurse -Filter *.py -Path clio, .opencode | ForEach-Object {
    (Get-Content $_.FullName) -replace 'from vlog_tool', 'from clio' -replace 'import vlog_tool', 'import clio' | Set-Content $_.FullName
}
```

Also apply to `main.py` (will be overwritten later, but clean for now):

```bash
(Get-Content main.py) -replace 'from vlog_tool', 'from clio' -replace 'import vlog_tool', 'import clio' | Set-Content main.py
```

- [ ] **Step 3: Bulk replace mock strings and logger names**

Replace all `"vlog_tool.` → `"clio.` in all `.py` files (covers patch() strings and getLogger() names):

```bash
Get-ChildItem -Recurse -Filter *.py -Path clio, .opencode | ForEach-Object {
    (Get-Content $_.FullName) -replace '"vlog_tool.', '"clio.' | Set-Content $_.FullName
}
```

Also apply to `main.py`:

```bash
(Get-Content main.py) -replace '"vlog_tool.', '"clio.' | Set-Content main.py
```

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor: rename vlog_tool package to clio"
```

---

### Task 2: Add CLI Entry Points

**Files:**
- Create: `clio/__main__.py`
- Modify: `main.py`
- Modify: `.opencode/start_ui.py`

- [ ] **Step 1: Create `clio/__main__.py`**

```python
"""Enable `python -m clio <command>` without pip install."""
from clio.main import main
main()
```

- [ ] **Step 2: Rewrite `main.py` as thin wrapper**

Replace entire `main.py` with:

```python
#!/usr/bin/env python3
"""Thin wrapper — delegate to clio package."""
from clio.main import main

if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Update `.opencode/start_ui.py`**

Change imports:

```python
from clio.config import load_config
from clio.ui import run
```

- [ ] **Step 4: Commit**

```bash
git add clio/__main__.py main.py .opencode/start_ui.py
git commit -m "feat(cli): add clio entry point via __main__.py and pyproject.toml"
```

---

### Task 3: Update pyproject.toml

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add `[project]` section + update testpaths**

Add to `pyproject.toml` (before existing `[tool.pytest.ini_options]`):

```toml
[project]
name = "clio"
version = "0.1.0"
description = "AI preprocessing pipeline for travel vlog editing"
requires-python = ">=3.11"

[project.scripts]
clio = "clio.main:main"
```

Update testpaths:

```toml
[tool.pytest.ini_options]
testpaths = ["clio/tests"]
```

- [ ] **Step 2: Commit**

```bash
git add pyproject.toml
git commit -m "build: register clio console_scripts entry point"
```

---

### Task 4: Update Setup/Serve/Whisper Scripts

**Files:**
- Modify: `setup.ps1`, `setup.sh`, `serve.ps1`, `serve.sh`, `whisper-install.ps1`, `whisper-install.sh`

- [ ] **Step 1: Update `setup.ps1`**

Three changes:
1. Line 1: `# Vlog 工具一键配置脚本（PowerShell）` → `# Clio 一键配置脚本（PowerShell）`
2. Line 8: `"=== Vlog 剪辑辅助工具 - 环境配置 ==="` → `"=== Clio - 环境配置 ==="`
3. Lines 142, 171: `'python main.py whisper install'` → `'python -m clio whisper install'`
4. Line 233: `main.py check` → `-m clio check`

- [ ] **Step 2: Update `setup.sh`**

Two changes:
1. Line 5: `"=== Vlog 剪辑辅助工具 - 环境配置 ==="` → `"=== Clio - 环境配置 ==="`
2. Lines 97, 115: `'python main.py whisper install'` → `'python -m clio whisper install'`
3. Line 180: `main.py check` → `-m clio check`
4. Line 186: `python main.py run --day day1` → `python -m clio run --day day1`

- [ ] **Step 3: Update `serve.ps1`**

Line 12: `main.py serve` → `python -m clio serve`

- [ ] **Step 4: Update `serve.sh`**

Line 11: `main.py serve` → `python -m clio serve`

- [ ] **Step 5: Update `whisper-install.ps1`**

Line 12: `main.py whisper install` → `python -m clio whisper install`

- [ ] **Step 6: Update `whisper-install.sh`**

Line 11: `main.py whisper install` → `python -m clio whisper install`

- [ ] **Step 7: Commit**

```bash
git add setup.ps1 setup.sh serve.ps1 serve.sh whisper-install.ps1 whisper-install.sh
git commit -m "chore(scripts): update references from main.py to clio"
```

---

### Task 5: Update CI Configuration

**Files:**
- Modify: `.github/workflows/test.yml`

- [ ] **Step 1: Update paths in CI**

Three changes in `.github/workflows/test.yml`:

1. mypy path:
   ```
   mypy vlog_tool/config/ vlog_tool/progress.py vlog_tool/export/__init__.py vlog_tool/log.py vlog_tool/schema.py vlog_tool/_str_enum.py
   ```
   → ```
   mypy clio/config/ clio/progress.py clio/export/__init__.py clio/log.py clio/schema.py clio/_str_enum.py
   ```

2. Import check:
   ```
   python -c "import vlog_tool; print('import OK')"
   ```
   → ```
   python -c "import clio; print('import OK')"
   ```

3. Test command:
   ```
   python -m pytest vlog_tool/tests/ --cov=vlog_tool --cov-branch --cov-report=term --cov-report=xml
   ```
   → ```
   python -m pytest clio/tests/ --cov=clio --cov-branch --cov-report=term --cov-report=xml
   ```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/test.yml
git commit -m "ci: update package paths from vlog_tool to clio"
```

---

### Task 6: Update Documentation

**Files:**
- Modify: `README.md`, `README.en.md`, `AGENTS.md`, `ROADMAP.md`, `docs/analysis/*.md`
- Modify: `.opencode/skills/adding-new-task/SKILL.md`

- [ ] **Step 1: Update `README.md`**

Replace references:
- Title: `Vlog 剪辑辅助工具` → `Clio`
- Directory tree: `vlog_tool/` → `clio/`
- Test command: `vlog_tool/tests/` → `clio/tests/`
- Links: `vlog_tool/ui/README.md` → `clio/ui/README.md`

Use PowerShell replace:

```powershell
(Get-Content README.md) -replace 'Vlog 剪辑辅助工具', 'Clio' -replace 'vlog_tool/', 'clio/' | Set-Content README.md
```

- [ ] **Step 2: Update `README.en.md`**

Same replacements (title `Vlog Editing Helper` → `Clio`, `vlog_tool/` → `clio/`):

```powershell
(Get-Content README.en.md) -replace 'Vlog Editing Helper', 'Clio' -replace 'vlog_tool/', 'clio/' | Set-Content README.en.md
```

- [ ] **Step 3: Update `AGENTS.md`**

Replace all `vlog_tool/` → `clio/` (directory tree, test paths, file references):

```powershell
(Get-Content AGENTS.md) -replace 'vlog_tool/', 'clio/' | Set-Content AGENTS.md
```

- [ ] **Step 4: Update `ROADMAP.md`**

Replace code path references `vlog_tool/` → `clio/`:

```powershell
(Get-Content ROADMAP.md) -replace 'vlog_tool/', 'clio/' | Set-Content ROADMAP.md
```

- [ ] **Step 5: Update `docs/analysis/*.md`**

Replace `vlog_tool/` → `clio/` in all analysis docs:

```powershell
Get-ChildItem docs/analysis/*.md | ForEach-Object {
    (Get-Content $_.FullName) -replace 'vlog_tool/', 'clio/' | Set-Content $_.FullName
}
```

- [ ] **Step 6: Update skills**

```powershell
(Get-Content .opencode/skills/adding-new-task/SKILL.md) -replace 'vlog_tool/', 'clio/' | Set-Content .opencode/skills/adding-new-task/SKILL.md
```

- [ ] **Step 7: Commit**

```bash
git add README.md README.en.md AGENTS.md ROADMAP.md docs/analysis/ .opencode/skills/
git commit -m "docs: update references from vlog_tool to clio"
```

---

### Task 7: Verify with Tests

- [ ] **Step 1: Run a quick smoke test**

```bash
python -c "import clio; print('import OK:', clio.__file__)"
```

Expected: prints "import OK: ...\clio\__init__.py"

- [ ] **Step 2: Run pytest** (basic unit tests only, skip integration)

```bash
python -m pytest clio/tests/ -x --timeout=30 -q
```

Expected: tests pass (or known failures unrelated to rename). If import errors, verify the bulk replace caught everything:

```bash
# Find any remaining vlog_tool references
Select-String -Recurse -Pattern "vlog_tool" -Path clio, main.py, .opencode | Where-Object {$_ -notmatch "__pycache__"}
```

- [ ] **Step 3: Run ruff lint + format check**

```bash
ruff check clio/ main.py
ruff format --check clio/ main.py
```

Expected: clean (no errors introduced by rename — pre-existing warnings ignored)

- [ ] **Step 4: Final commit if fixes needed**

```bash
git add -A
git commit -m "fix: clean up remaining vlog_tool references after rename"
```
