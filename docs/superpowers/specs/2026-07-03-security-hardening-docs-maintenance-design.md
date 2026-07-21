# Security Hardening & Documentation Maintenance

**Date**: 2026-07-03
**Source**: ROADMAP.md Phase 3-4, U-008a/b/c

## Scope

Three small-bounded changes across 5 files + ROADMAP updates:

### 1. Configurable fs_root (U-008a)

- `clio/config/models.py`: Add `fs_root: str | None = None` to `ServerConfig`
- `clio/ui/server.py`: `make_handler` passes `fs_root` to Handler class as `_fs_root`
- `clio/ui/routes/fs.py`: `_is_allowed_path(resolved, fs_root=None)` checks `fs_root` first, falls back to `Path.home()`

### 2. UI_TOKEN env var (U-008b)

- `clio/ui/server.py:run()`: Insert `os.environ.get("UI_TOKEN")` between `api_token` (CLI) and `config.server.api_token`
- Priority: `--token` CLI > `UI_TOKEN` env > `server.api_token` config > auto-generate

### 3. Security docs (Phase 3-4 + U-008c)

- `clio/ui/README.md`: Expand security section with auth system docs, `--token`/`?token=` usage, reverse proxy guidance
- `config.example.yaml`: Add `server:` section with `api_token` and `fs_root` fields
- `ROADMAP.md`: Mark Phase 3-4, U-008a/b/c as done

## Non-goals

- Adding more GET routes to sensitive set (scope creep)
- Symbolic link hardening in `_is_allowed_path`
- Independent security guide document (keep in README)

## Risk Assessment

- `fs_root` change: backward compatible (None = old behavior)
- `UI_TOKEN` change: env var only checked when `--token` is not provided
- Doc changes: no runtime impact
