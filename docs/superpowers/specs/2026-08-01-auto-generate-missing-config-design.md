# 2026-08-01 Auto-Generate Missing Config Design

## Problem

When `clio.exe` (or `python main.py`) starts without a `config.yaml` in the working
directory, `load_global_config` raises `FileNotFoundError` and the app dies instantly.

The packaged desktop exe (`dist\clio`) does **not** bundle `config.example.yaml`, so a
first-time user has no template to copy from — they must fetch the example from git.

## Goal

If the target `config.yaml` does not exist at load time, auto-generate it from a bundled
`config.example.yaml` template instead of crashing. Applies to both CLI and desktop
(loader layer, per user decision).

## Approach

Add `_ensure_global_config(config_file)` in `clio/config/loader.py`:

1. If `config_file.is_file()` → no-op.
2. Otherwise resolve the example template (see below). If found, `mkdir(parents=True)`
   on the parent dir and copy template → `config_file`. Print a Chinese notice.
3. If template resolution fails or the write raises `OSError`, swallow it and let the
   normal `open()` raise `FileNotFoundError` (existing behavior preserved as fallback).

Template resolution order (same `__file__`-relative pattern as `STATIC_DIR` in
`clio/ui/server.py:129`):

1. `Path(__file__).parent / "config.example.yaml"` — packaged state (`_internal/clio/config/`)
2. `Path(__file__).resolve().parent.parent.parent / "config.example.yaml"` — repo root
   (dev tree; `clio/config/loader.py` → up 3 → repo root)

## Packaging Change

`packaging/clio.spec` datas: add

```python
(str(ROOT / "config.example.yaml"), "clio/config"),
```

so the template lands at `_internal/clio/config/config.example.yaml`, matching
resolution rule 1.

## Behavior Notes

- Generation happens for **any** missing path, not just the default `config.yaml`
  (consistent with existing auto-upgrade / V1→V2 migration philosophy).
- Generated file content == `config.example.yaml` (comments + gemini/openai/deepseek
  presets). No API keys included — keys still come from `.env`.
- Generation failure (unwritable dir, no template) → silent fallback to the existing
  `FileNotFoundError` so no existing caller regresses.

## Test Changes

- `clio/tests/test_config.py:321 test_missing_file_raises` currently uses
  `/nonexistent/config.yaml`, which on this Windows machine resolves to `G:\nonexistent`
  and would be *created* by the new logic. Change it to a guaranteed-unwritable path
  (e.g. `C:\$SystemRoot\...` style) so the fallback still raises `FileNotFoundError`.
- Add new test: missing config in a writable dir → file is created, content equals the
  example, load succeeds.

## Out of Scope

- Generating `project.yaml` (per-project; only needed when a project is opened).
- UI wizard for first-run configuration.
