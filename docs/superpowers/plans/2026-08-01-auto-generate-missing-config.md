# Auto-Generate Missing Config Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Auto-generate a `config.yaml` from the bundled `config.example.yaml` template when the target config file is missing at load time, instead of crashing with `FileNotFoundError`.

**Architecture:** Add `_example_config_path()` (template resolution: PyInstaller `_internal` bundle path, then repo root) and `_ensure_global_config()` (mkdir + copy template, or silent fallback) to `clio/config/loader.py`, called from `load_global_config`. Bundle `config.example.yaml` in `packaging/clio.spec` datas.

**Tech Stack:** Python 3.11+, PyYAML, pytest, PyInstaller spec.

**Spec:** `docs/superpowers/specs/2026-08-01-auto-generate-missing-config-design.md`

---

### Task 1: Add `_example_config_path` template resolver

**Files:**
- Modify: `clio/config/loader.py` (add helper near `_load_dotenv`, ~line 86)
- Test: `clio/tests/test_config.py`

- [ ] **Step 1: Write the failing test**

Append inside `TestLoadConfig` class (after line ~323) in `clio/tests/test_config.py`:

```python
def test_example_config_path_resolves_repo_root(self):
    from clio.config.loader import _example_config_path

    path = _example_config_path()
    assert path is not None
    assert path.is_file()
    assert path.name == "config.example.yaml"
    assert "ai:" in path.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest clio/tests/test_config.py::TestLoadConfig::test_example_config_path_resolves_repo_root -v`
Expected: FAIL with `ImportError: cannot import name '_example_config_path'`

- [ ] **Step 3: Implement `_example_config_path`**

Add after `_load_dotenv` in `clio/config/loader.py`:

```python
def _example_config_path() -> Path | None:
    """Locate the bundled config.example.yaml template.

    Resolution order: PyInstaller _internal bundle (clio/config/), then the
    repo root in the dev tree (up three levels from clio/config/loader.py).
    Returns None when neither exists.
    """
    for base in (Path(__file__).parent, Path(__file__).resolve().parent.parent.parent):
        candidate = base / "config.example.yaml"
        if candidate.is_file():
            return candidate
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest clio/tests/test_config.py::TestLoadConfig::test_example_config_path_resolves_repo_root -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add clio/config/loader.py clio/tests/test_config.py
git commit -m "feat(config): add bundled example template resolver"
```

---

### Task 2: Add `_ensure_global_config` and wire into `load_global_config`

**Files:**
- Modify: `clio/config/loader.py:430-437` (call site inside `load_global_config`)
- Test: `clio/tests/test_config.py`

- [ ] **Step 1: Write the failing test**

Append inside `TestLoadConfig` (after the test from Task 1):

```python
def test_auto_generates_missing_config(self, tmp_path):
    target = tmp_path / "nested" / "config.yaml"
    cfg = load_config(target)
    assert target.is_file()
    assert "ai:" in target.read_text(encoding="utf-8")
    assert cfg.compress.fps == 15
    assert cfg.proxy.enabled is False

def test_missing_file_raises_when_generation_blocked(self, tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    missing = blocker / "config.yaml"
    with pytest.raises(FileNotFoundError):
        load_config(missing)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest clio/tests/test_config.py::TestLoadConfig::test_auto_generates_missing_config clio/tests/test_config.py::TestLoadConfig::test_missing_file_raises_when_generation_blocked -v`
Expected:
- `test_auto_generates_missing_config` FAILs with `FileNotFoundError`
- `test_missing_file_raises_when_generation_blocked` PASSes already (it matches current behavior)

- [ ] **Step 3: Implement `_ensure_global_config` and call it**

Add after `_example_config_path` in `clio/config/loader.py`:

```python
def _ensure_global_config(config_file: Path) -> None:
    """Create config.yaml from the bundled example template when missing.

    Failures (no template, unwritable dir) are swallowed so the normal
    open() in load_global_config raises FileNotFoundError as before.
    """
    if config_file.is_file():
        return
    example = _example_config_path()
    if example is None:
        return
    try:
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"[config] 未找到 {config_file.name}，已从示例生成默认配置: {config_file}")
    except OSError:
        return
```

In `load_global_config`, insert the call after `_load_dotenv(base)` (currently line 434):

```python
    _load_dotenv(base)
    _ensure_global_config(config_file)
```

- [ ] **Step 4: Replace the old missing-file test**

In `clio/tests/test_config.py`, replace `test_missing_file_raises` (lines 321-323):

```python
    def test_missing_file_raises(self, tmp_path):
        blocker = tmp_path / "blocker"
        blocker.write_text("x", encoding="utf-8")
        missing = blocker / "config.yaml"
        with pytest.raises(FileNotFoundError):
            load_config(missing)
```

This keeps the test deterministic: a file where the config dir should be blocks `mkdir`, so generation is skipped and `open()` raises `FileNotFoundError`.

- [ ] **Step 5: Run the config test module**

Run: `python -m pytest clio/tests/test_config.py -v`
Expected: ALL PASS (including the two new tests and the replaced one)

- [ ] **Step 6: Run the full loader-adjacent suite**

Run: `python -m pytest clio/tests/test_config.py clio/tests/test_config_v2.py clio/tests/test_config_cache.py -q`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add clio/config/loader.py clio/tests/test_config.py
git commit -m "feat(config): auto-generate missing config.yaml from example"
```

---

### Task 3: Bundle `config.example.yaml` in the PyInstaller spec

**Files:**
- Modify: `packaging/clio.spec:19-22` (datas list)

- [ ] **Step 1: Add the datas entry**

In `packaging/clio.spec`, add a line to the `datas` list:

```python
    datas=[
        (str(ROOT / "clio" / "ui" / "static"), "clio/ui/static"),
        (str(ROOT / "templates"), "templates"),
        (str(ROOT / "config.example.yaml"), "clio/config"),
    ],
```

- [ ] **Step 2: Rebuild the onedir (optional but recommended)**

Run: `python -m PyInstaller packaging/clio.spec --noconfirm --clean`
Expected: build succeeds; verify `dist/clio/_internal/clio/config/config.example.yaml` exists.

- [ ] **Step 3: Verify smoke launch with no config**

In a fresh empty temp dir, run: `G:\Coding_Project\IdeaProjects\vlog-video-analysis\dist\clio\clio.exe`
Expected: `config.yaml` is auto-created next to the exe; app window opens.

- [ ] **Step 4: Commit**

```bash
git add packaging/clio.spec
git commit -m "build(desktop): bundle config.example.yaml template in onedir"
```

---

### Task 4: Full verification

- [ ] **Step 1: Run full test suite**

Run: `python -m pytest clio/tests/ -q`
Expected: ALL PASS (1200+ cases)

- [ ] **Step 2: Run ruff**

Run: `ruff check clio main.py` and `ruff format clio main.py`
Expected: no errors

- [ ] **Step 3: Update README-desktop.md**

In `packaging/README-desktop.md`, under the "运行前置" section, add a line noting the app auto-creates a default `config.yaml` from the bundled example on first launch.

- [ ] **Step 4: Commit**

```bash
git add packaging/README-desktop.md
git commit -m "docs(desktop): note auto-generated config on first launch"
```

---

## Self-Review Notes

- Spec coverage: template resolution (Task 1), generation + silent fallback (Task 2), packaging (Task 3), test updates for `test_missing_file_raises` (Task 2 Step 4), docs (Task 4 Step 3).
- No placeholders; all code and commands concrete.
- Type consistency: `_example_config_path` returns `Path | None`, used by `_ensure_global_config`; both named consistently across tasks.
- Out of scope per spec: `project.yaml` generation, first-run wizard.
