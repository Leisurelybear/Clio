# Config Hot-Reload Audit

Investigation into whether config changes take effect without restarting the server.

## Summary

**Partial hot-reload exists, but only for project-level config via the UI.** Global `config.yaml` saves and any external file edits require a full server restart.

| Scenario | Reloads? | Mechanism |
|---|---|---|
| Save `project.yaml` via UI editor | **Yes — immediate** | `_config_cache.pop()` in `config_routes.py:106` |
| Save `config.yaml` via UI editor | **No — restart required** | File written, cache not invalidated (bug) |
| Edit any config file externally | **No — restart required** | No file-watching or mtime checks |
| Pipeline run (`/api/run/start`, etc.) | Uses cached config | `_get_config()` key-existence check only |

## Key Findings

### Architecture

- `load_config()` (config.py:276) is a stateless pure function — always re-reads from disk.
- `_config_cache` (server.py:98-99) is a `dict[str, AppConfig]` with a `Lock` — no TTL, no mtime check, no size limit.
- `_get_config()` (server.py:103-112) checks only `if key not in cache` — no file staleness detection.

### Bug: Global config save skips cache invalidation

`config_routes.py:108-132` writes `config.yaml` to disk and validates it via `load_config(tmp_path)`, but never calls `_config_cache.pop(...)`. All existing project cache entries remain stale. Pipeline runs reuse the old config.

### False "restart required" message in UI

`editor.js:275` always shows `"需重启服务生效"` after any config save, even though `project.yaml` saves take effect immediately. Only global `config.yaml` saves actually need a restart.

## Next Steps (R-009)

1. Fix global `config.yaml` save — `_config_cache.clear()` after write
2. Add mtime check to `_get_config()` — compare file mtime on every cache hit
3. Update UI status message — differentiate project vs global save feedback
4. Add `_config_cache` size limit (LRU or max-entries) to prevent memory leak
5. (Optional) Add file-watcher thread for external edits

Filed as R-009 in ROADMAP.md.
