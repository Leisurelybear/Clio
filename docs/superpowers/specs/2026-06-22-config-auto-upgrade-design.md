# Config Auto-Upgrade: Missing Fields Injection from Dataclass Defaults

## Problem

When the user updates the codebase (git pull), new config fields are added to Python
dataclasses (e.g. `reencode_split`, `debug_print_prompt`). The user's local
`config.yaml` / `project.yaml` does not know about these fields. Although in-memory
dataclass defaults work correctly, the on-disk file stays stale — the user never
discovers new features through their config file.

## Requirements

- On every `load_config()` call, detect missing fields in each config file
- Inject defaults from the Python dataclass `field(default=...)` definitions
- Write back to disk only when something changed
- Print a summary of what was added
- Handle all config sections: `paths`, `proxy`, `compress`, `analyze`, `naming`,
  `plan`, `script`, `whisper`, `ai.providers.*`, `ai.tasks.*`

## Non-Requirements

- Does NOT validate or fix type mismatches (existing values are left untouched)
- Does NOT remove unknown fields (that's already handled by `_filter_dc()`)
- Does NOT regenerate or reformat `config.example.yaml`

## Design

### Entry Point: `load_config()` in `loader.py`

Add a pre-load step at the very beginning of `load_config()`, before the file is
read for normal processing:

```python
def load_config(config_path, project_dir=None):
    base = Path(config_path).parent
    _load_dotenv(base)

    # NEW: upgrade config files before loading
    _upgrade_config_file(config_path)
    if project_dir is not None:
        proj_yaml = Path(project_dir).resolve() / "project.yaml"
        if proj_yaml.is_file():
            _upgrade_config_file(proj_yaml)

    # Original flow continues unchanged below
    with open(config_path) as f:
        raw = yaml.safe_load(f) or {}
    ...
```

This ensures:
- Global `config.yaml` is upgraded independently
- `project.yaml` (if exists) is upgraded independently
- The upgrade happens BEFORE the deep merge, so each file is self-consistent

### Core Function: `_upgrade_config_file(yaml_path)`

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

def _resolve_field_default(fd: dataclasses.Field):
    if fd.default is not dataclasses.MISSING:
        return fd.default
    if fd.default_factory is not dataclasses.MISSING:
        return fd.default_factory()
    raise ValueError(f"Field {fd.name} has no default")
```

Algorithm:
1. Read YAML file → dict
2. For each `(section_name, dataclass_type)` in `_SECTION_DC_MAP`:
   - If the section exists and is a dict:
     - For each field in `dataclass_type.__dataclass_fields__`:
       - If field type is `dict` → skip (sub-sections like `ai.providers` handled separately)
       - If field name is NOT in section dict → inject with `_resolve_field_default()`
3. Handle `ai.providers.*` — iterate each provider dict against `ProviderConfig`
4. Handle `ai.tasks.*` — iterate each task dict against `TaskConfig`
5. Handle `paths` against `PathsConfig` (with special handling for `_path()`)
6. Handle `script` against `ScriptConfig`
7. If any field was injected → write file via `yaml.dump()` → print summary

### Skip Conditions

- Section does not exist in YAML → skip (don't create new sections)
- Section exists but is not a dict → skip
- Field already exists in YAML → skip (respect user's explicit value)
- Field has no default (`dataclasses.MISSING`) → skip

### Write-back

```python
if changed:
    text = yaml.dump(raw, default_flow_style=False, allow_unicode=True, sort_keys=False)
    yaml_path.write_text(text, encoding="utf-8")
    print(f"[配置] {yaml_path.name} 已自动补全 {n} 个新配置项: {', '.join(added)}")
```

YAML writing has one trade-off: **PyYAML does not preserve comments**. Existing
comments in the config file will be lost on write. This is acceptable because:
- It only happens when new fields are detected (rare — once per field addition)
- The terminal message tells the user exactly what was added
- The project already follows this pattern in `file_service.py:_migrate_project_configs()`

### Special Cases

**`PathsConfig`** — has a `_path()` transformation:
```python
def _path(value: str, base: Path) -> str:
    return str((base / value).resolve()) if not Path(value).is_absolute() else value
```
The field defaults in the dataclass are raw strings (`"."`, `"./output"`).
We inject the raw default (not `_path()` transformed) — it's just a default
value, the transformation happens during dataclass construction.

**`AIConfig`** — has `providers: dict` and `tasks: dict` fields with
`default_factory=dict`. These fields have type `dict`, so they are skipped
by the generic loop. The `ai.providers.*` and `ai.tasks.*` sub-iteration
handles each entry individually. Scalar fields like `debug_print_prompt: bool`
and `context: str` are injected normally.

**`ScriptConfig`** — constructed via explicit kwargs in `load_config()`, but
dataclass fields still have defaults. We introspect the dataclass as usual.

**`ProviderConfig`** — `api_key` field has no default (`MISSING`), skip it.
`api_key_env` defaults to `""` — inject as empty string (harmless, environment
lookup will find nothing).

**`TaskConfig`** — `provider` and `model` both have no defaults (`MISSING`),
skip both. Tasks without explicit provider/model would fail validation anyway.

### Example Output

```
[配置] config.yaml 已自动补全 2 个新配置项: compress.reencode_split, ai.debug_print_prompt
```

Or when no changes:

```
(no output — file is already up-to-date)
```

## Files Changed

| File | Change |
|------|--------|
| `vlog_tool/config/loader.py` | Add `_upgrade_config_file()`, `_resolve_field_default()`, `_SECTION_DC_MAP`; call from `load_config()` |
| `vlog_tool/tests/test_config.py` | Add tests for `_upgrade_config_file` |

## Test Plan

1. **Valid YAML file with a section missing some fields** — injects missing fields,
   leaves existing untouched
2. **Valid YAML file with no missing fields** — no changes, no write
3. **Empty/None YAML** — no crash
4. **Section exists but not a dict** — skip gracefully
5. **`ai.providers.*` providers missing fields** — injects per-provider
6. **`ai.tasks.*` tasks missing fields** — injects per-task
7. **File has a field without dataclass default (`MISSING`)** — skipped
8. **Both config.yaml and project.yaml** — each upgraded independently
9. **Write-back preserves existing fields, only adds new ones** — verified via
   round-trip test (read → upgrade → read → compare)

## Open Questions

- None — design approved in brainstorming (2026-06-22)
