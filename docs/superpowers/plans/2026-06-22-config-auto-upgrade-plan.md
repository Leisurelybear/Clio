# Config Auto-Upgrade Implementation Plan

> **For agentic workers:** Implementation steps use checkbox (`- [ ]`) syntax.

**Goal:** Automatically inject missing dataclass field defaults into `config.yaml` / `project.yaml` on every `load_config()` call.

**Architecture:** Add `_upgrade_config_file()` to `loader.py` that reads YAML, compares each section against dataclass field definitions, writes back only when something changed. Called before normal config loading.

**Tech Stack:** Python 3.11+, PyYAML, dataclasses introspection

---

### Task 1: Add `_upgrade_config_file` to `loader.py`

**Files:**
- Modify: `vlog_tool/config/loader.py` (add function + call from `load_config`)

- [ ] **Step 1: Add imports and `_SECTION_DC_MAP`**

Add to imports in `loader.py`:
```python
import dataclasses
import typing
```

After the existing imports (line 28), add the section-to-dataclass mapping:

```python
_SECTION_DC_MAP: dict[str, type] = {
    "paths": PathsConfig,
    "proxy": ProxyConfig,
    "ai": AIConfig,
    "compress": CompressConfig,
    "analyze": AnalyzeConfig,
    "naming": NamingConfig,
    "script": ScriptConfig,
    "plan": PlanConfig,
    "whisper": WhisperConfig,
}

_MISSING = object()
```

- [ ] **Step 2: Add `_resolve_field_default` and `_upgrade_config_file`**

Add after `deep_merge()` (after line 67):

```python
def _resolve_field_default(fd: dataclasses.Field):
    if fd.default is not dataclasses.MISSING:
        return fd.default
    if fd.default_factory is not dataclasses.MISSING:
        return fd.default_factory()
    return _MISSING
```

```python
def _upgrade_config_file(yaml_path: Path) -> None:
    if not yaml_path.is_file():
        return
    try:
        with yaml_path.open(encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    except Exception:
        return  # skip unreadable/invalid YAML

    if not isinstance(raw, dict):
        return

    added: list[str] = []
    changed = False

    # 1. Top-level sections (paths, proxy, ai, compress, etc.)
    for section_name, dc_type in _SECTION_DC_MAP.items():
        section = raw.get(section_name)
        if not isinstance(section, dict):
            continue
        for fd in dc_type.__dataclass_fields__.values():
            if typing.get_origin(fd.type) is dict:
                continue  # sub-dicts handled separately (ai.providers, ai.tasks)
            if fd.name in section:
                continue
            val = _resolve_field_default(fd)
            if val is _MISSING:
                continue
            section[fd.name] = val
            added.append(f"{section_name}.{fd.name}")
            changed = True

    # 2. ai.providers.* — each provider entry against ProviderConfig
    providers = raw.get("ai", {}).get("providers", {})
    if isinstance(providers, dict):
        for pname, pcfg in providers.items():
            if not isinstance(pcfg, dict):
                continue
            for fd in ProviderConfig.__dataclass_fields__.values():
                if fd.name in pcfg:
                    continue
                val = _resolve_field_default(fd)
                if val is _MISSING:
                    continue
                pcfg[fd.name] = val
                added.append(f"ai.providers.{pname}.{fd.name}")
                changed = True

    # 3. ai.tasks.* — each task entry against TaskConfig
    tasks = raw.get("ai", {}).get("tasks", {})
    if isinstance(tasks, dict):
        for tname, tcfg in tasks.items():
            if not isinstance(tcfg, dict):
                continue
            for fd in TaskConfig.__dataclass_fields__.values():
                if fd.name in tcfg:
                    continue
                val = _resolve_field_default(fd)
                if val is _MISSING:
                    continue
                tcfg[fd.name] = val
                added.append(f"ai.tasks.{tname}.{fd.name}")
                changed = True

    if not changed:
        return

    text = yaml.dump(raw, default_flow_style=False, allow_unicode=True, sort_keys=False)
    yaml_path.write_text(text, encoding="utf-8")
    print(f"[配置] {yaml_path.name} 已自动补全 {len(added)} 个新配置项: {', '.join(added)}")
```

- [ ] **Step 3: Wire into `load_config()`**

Find the project_dir handling block in `load_config()` (currently lines 120-125):

```python
    if project_dir is not None:
        project_yaml = Path(project_dir).resolve() / "project.yaml"
        if project_yaml.is_file():
            with project_yaml.open(encoding="utf-8") as f:
                project_raw: dict[str, Any] = yaml.safe_load(f) or {}
            raw = deep_merge(raw, project_raw)
```

Change to:
```python
    if project_dir is not None:
        project_yaml = Path(project_dir).resolve() / "project.yaml"
        _upgrade_config_file(project_yaml)
        if project_yaml.is_file():
            with project_yaml.open(encoding="utf-8") as f:
                project_raw: dict[str, Any] = yaml.safe_load(f) or {}
            raw = deep_merge(raw, project_raw)
```

And add `_upgrade_config_file(config_file)` after `_load_dotenv(base)`:

```python
    if project_dir is not None:
        project_yaml = Path(project_dir).resolve() / "project.yaml"
        _upgrade_config_file(project_yaml)
        if project_yaml.is_file():
            with project_yaml.open(encoding="utf-8") as f:
                project_raw: dict[str, Any] = yaml.safe_load(f) or {}
            raw = deep_merge(raw, project_raw)
```

- [ ] **Step 4: Run tests to verify no regression**

```bash
.\.venv\Scripts\python.exe -m pytest vlog_tool/tests/ --tb=short 2>&1 | Select-Object -Last 5
```

Expected: 612 passed

- [ ] **Step 5: Commit**

```bash
git add vlog_tool/config/loader.py
git commit -m "feat(config): auto-inject missing dataclass field defaults into config YAML

On every load_config(), _upgrade_config_file() detects fields in
dataclass definitions that are missing from the on-disk config YAML
and injects their Python defaults. Handles top-level sections,
ai.providers.*, and ai.tasks.* independently for both config.yaml
and project.yaml."
```
