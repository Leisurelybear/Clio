# 2026-08-01 Desktop Single-Instance Design

## Problem

Launching `clio.exe` twice (or `python -m clio.desktop`) starts two independent
processes that share `config.yaml`, `projects.json`, `desktop-state.json`, and the
output dir. Concurrent writes to these files can corrupt state, and users expect a
double-click to bring up the existing window instead of a second copy.

Separately, when the web UI (`python main.py serve`, port 8765) is already running,
launching the desktop exe silently starts a parallel server — the user should be
asked before proceeding.

## Goal

1. **Single instance (desktop):** the second desktop launch focuses the existing
   window and exits; a stale lock (crashed first instance) is taken over.
2. **Web/desktop coexistence:** when the web UI is detected on the default port,
   the desktop launch prompts "网页版正在运行，是否继续启动桌面版？" and honors
   the choice (default continue, never blocks on dialog failure).

## Approach

Scope is per **config dir** (the dir holding `config.yaml` — `dist\clio` for the exe,
repo root for dev). Scope is **not** global across projects.

### New module `clio/desktop/single_instance.py`

- `lock_path(config_dir)` → `config_dir / "clio.lock"`
- `read_lock(config_dir)` / `write_lock(config_dir, port, pid)` / `remove_lock(config_dir)`
  — JSON `{"port": int, "pid": int}`; corrupt/missing → `None`.
- `focus_first_instance(host, port, timeout=3.0)` → POST `/api/desktop/focus`.
  **Probe-authoritative liveness:** any HTTP response (200, or 5xx while the first
  window is still starting) proves the first instance is alive → the caller exits.
  Only a connection error (`OSError`/`URLError`) means the lock is stale → takeover.
  PID is stored for diagnostics only; PID-based liveness is avoided because
  `os.kill(pid, 0)` / `OpenProcess` are unreliable on Windows.
- `is_web_running(host="127.0.0.1", port=8765, timeout=2.0)` → GET `/`, returns True
  only when status 200 and the body contains the `Vlog` marker (avoids false positives
  from unrelated services on that port).

### Focus endpoint in `clio/ui/server.py`

- Module-level registry: `_desktop_focus_callback` + `set_desktop_focus_callback(cb)`.
- Handler `handle_post_desktop_focus(handler, qs, obj)`:
  - callback `None` → `503 {"ok": false}` (web-only mode, no window attached);
  - callback raises → `500 {"ok": false}` (window not fully started);
  - otherwise → `200 {"ok": true}`.
- Route `POST /api/desktop/focus` with `auth_required=False` (must be reachable by a
  second instance that does not know the API token; localhost-only in practice).

### `clio/desktop/app.py` wiring

Order in `main()`:

1. `read_lock(config_dir)`; if lock exists and `focus_first_instance(port)` is True →
   print "Clio 已在运行，已聚焦原窗口" and exit 0 (before starting a server).
2. `is_web_running()` → prompt via tkinter `askyesno`; decline → exit 0.
3. `start_server(...)` (random port), `set_desktop_focus_callback(_focus_window)`
   where `_focus_window` = `window.restore(); window.show()` (winforms
   `Show()`+`Activate()` brings the window to front).
4. `write_lock(config_dir, handle.port, os.getpid())`.
5. `webview.start()`; `finally:` → `remove_lock(config_dir)` + `stop_server(handle)`.

## Behavior Matrix

| Scenario | Result |
| --- | --- |
| No lock file | First instance starts, writes lock |
| Lock + first alive (focus 200) | Second exits, first window focused |
| Lock + first alive but window starting (focus 5xx) | Second exits (HTTP response = alive) |
| Lock + first crashed / connection refused | Second takes over lock, starts normally |
| Web UI on 8765 + user declines | Desktop exits, web untouched |
| Web UI on 8765 + user accepts | Desktop starts alongside web |
| Web UI elsewhere (non-8765 / non-Clio) | Not detected; desktop starts normally |

## Non-Goals

- Global cross-config-dir single instance (each config dir is a separate app instance).
- Tray/mutex-based native single-instance (Windows-only, adds no focus capability).
- Behavior changes to the web `serve` mode.

## Tests

- `clio/tests/test_desktop_single_instance.py` — lock read/write/remove, corrupt lock,
  focus probe (unreachable / HTTPError / 200 / request shape), web detection
  (unreachable / Clio marker / unrelated server / non-200).
- `clio/tests/test_server.py::TestDesktopFocusCallback` — 503 / 200 / 500 paths;
  `TestAuth::test_focus_unauthenticated*` — route reachable with and without token.
- `clio/tests/test_desktop_app.py` — main() wiring: web-declined exits, web-accepted
  continues, existing instance focuses+exits, stale lock takeover, callback shows the
  window, lock removed on close.
