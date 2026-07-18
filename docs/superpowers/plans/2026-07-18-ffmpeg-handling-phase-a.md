# ffmpeg Missing-Path Handling — Phase A Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When ffmpeg/ffprobe is missing, surface a warning banner, soft-disable the highest-traffic media entry points, and fail waveform generation without lock/error cool-down storms — without blocking serve or auto-installing.

**Architecture:** Pure `probe_ffmpeg_deps` reuses `resolve_binary`/`discover_ffmpeg_bin`. `GET /api/deps/ffmpeg` exposes it. Frontend stores `state.deps`, feeds `runtime-warnings` (warning level), `buildVideoMenuItems`, runner start guard, and waveform short-circuit. Waveform backend early-returns `missing_binary` before any lock.

**Tech Stack:** Python 3.11+, pytest, existing UI (vanilla JS + vitest), `clio.utils.resolve_binary`

**Spec:** `docs/superpowers/specs/2026-07-18-ffmpeg-handling-design.md` (Phase A)

## Global Constraints

- Empty config path stays `""` — never coerce to bare `"ffmpeg"`.
- Chinese UI copy; English commits.
- No download/install code in Phase A.
- Soft-disable only: menu compress/transcribe (+ label if present), runner start for `{compress,label,transcribe}`, waveform client short-circuit. Cover/cut/reindex rely on backend errors.
- Banner level is **`warning`**, not `danger`.
- Waveform missing binary: **no** `.generating`, **no** `.error` cool-down file.
- Work on `main`; one logical commit per task; ask before push.

## File map

| Path | Role |
| --- | --- |
| `clio/utils.py` | Add `probe_ffmpeg_deps` next to `resolve_binary` |
| `clio/tests/test_utils.py` | Probe unit tests (or `clio/tests/test_deps.py` if preferred) |
| `clio/ui/routes/deps.py` | `handle_get_deps_ffmpeg` |
| `clio/tests/test_routes_deps.py` | Route tests |
| `clio/ui/server.py` | Import + register `GET /api/deps/ffmpeg` |
| `clio/tasks/waveform.py` | Early missing-binary path in `ensure_waveform` |
| `clio/tests/test_tasks_waveform.py` | Assert no lock/error files |
| `clio/ui/static/src/state.js` | `deps: null` |
| `clio/ui/static/src/runtime-warnings.js` | ffmpeg-missing warning |
| `clio/ui/static/src/__tests__/runtime-warnings.test.js` | Banner cases |
| `clio/ui/static/src/video-menu.js` | `deps` param force-disable |
| `clio/ui/static/src/__tests__/video-menu.test.js` | Menu cases |
| `clio/ui/static/src/sidebar-data.js` | Pass `state.deps` into menu |
| `clio/ui/static/src/main.js` | Fetch deps; refresh banner with deps |
| `clio/ui/static/src/sidebar-data.js` or `main.js` | `loadDeps` after config |
| `clio/ui/static/src/runner.js` | Start guard + pure helper |
| `clio/ui/static/src/waveform.js` | Short-circuit when `!state.deps?.ok` |
| `clio/ui/static/src/__tests__/runner-deps.test.js` (new) or extend runner tests | Guard unit tests |

---

### Task 1: `probe_ffmpeg_deps` helper

**Files:**
- Modify: `clio/utils.py` (after `resolve_binary`)
- Test: `clio/tests/test_utils.py` (append class) or Create: `clio/tests/test_deps.py`

**Interfaces:**
- Consumes: `resolve_binary(configured, fallback)`
- Produces: `probe_ffmpeg_deps(ffmpeg_configured: str = "", ffprobe_configured: str = "") -> dict`

- [ ] **Step 1: Write the failing tests**

```python
# clio/tests/test_deps.py (or TestProbeFfmpegDeps in test_utils.py)
from pathlib import Path
from unittest.mock import patch

from clio.utils import probe_ffmpeg_deps


class TestProbeFfmpegDeps:
    def test_both_found(self, tmp_path: Path):
        ff = tmp_path / "ffmpeg.exe"
        fp = tmp_path / "ffprobe.exe"
        ff.write_bytes(b"x")
        fp.write_bytes(b"x")
        out = probe_ffmpeg_deps(str(ff), str(fp))
        assert out["ok"] is True
        assert out["ffmpeg"] == str(ff)
        assert out["ffprobe"] == str(fp)
        assert out["missing"] == []
        assert out["detail"] == ""

    def test_neither_found_empty_config(self):
        with patch("clio.utils.discover_ffmpeg_bin", return_value=None):
            out = probe_ffmpeg_deps("", "")
        assert out["ok"] is False
        assert set(out["missing"]) == {"ffmpeg", "ffprobe"}
        assert out["ffmpeg"] is None and out["ffprobe"] is None
        assert "ffmpeg" in out["detail"] and "ffprobe" in out["detail"]

    def test_only_ffmpeg_found(self, tmp_path: Path):
        ff = tmp_path / "ffmpeg.exe"
        ff.write_bytes(b"x")
        with patch("clio.utils.discover_ffmpeg_bin", side_effect=lambda n: str(ff) if n == "ffmpeg" else None):
            # configured empty for both → discover path
            out = probe_ffmpeg_deps("", "")
        # side_effect only for empty discover; better explicit:
        def fake_resolve(configured, fallback):
            if fallback == "ffmpeg":
                return str(ff)
            raise FileNotFoundError(fallback)

        with patch("clio.utils.resolve_binary", side_effect=fake_resolve):
            out = probe_ffmpeg_deps("", "")
        assert out["ok"] is False
        assert out["missing"] == ["ffprobe"]
        assert out["ffmpeg"] == str(ff)
        assert "ffprobe" in out["detail"]

    def test_bad_configured_path(self, tmp_path: Path):
        out = probe_ffmpeg_deps(str(tmp_path / "nope.exe"), str(tmp_path / "nope2.exe"))
        assert out["ok"] is False
        assert "ffmpeg" in out["missing"]
        assert "ffprobe" in out["missing"]

    def test_empty_not_coerced_to_bare_name(self):
        calls = []

        def fake_resolve(configured, fallback):
            calls.append((configured, fallback))
            raise FileNotFoundError(fallback)

        with patch("clio.utils.resolve_binary", side_effect=fake_resolve):
            probe_ffmpeg_deps("", "")
        assert calls == [("", "ffmpeg"), ("", "ffprobe")]
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
pytest clio/tests/test_deps.py -v
# or: pytest clio/tests/test_utils.py -k ProbeFfmpeg -v
```

Expected: `ImportError` or `AttributeError: probe_ffmpeg_deps`

- [ ] **Step 3: Implement `probe_ffmpeg_deps`**

Add to `clio/utils.py` immediately after `resolve_binary`:

```python
def probe_ffmpeg_deps(
    ffmpeg_configured: str = "",
    ffprobe_configured: str = "",
) -> dict:
    """Report ffmpeg/ffprobe availability without raising.

    Returns:
        ok: True only if both resolve.
        ffmpeg / ffprobe: resolved path or None.
        missing: list of missing tool names.
        detail: Chinese message for UI (empty when ok).
    """
    found: dict[str, str | None] = {"ffmpeg": None, "ffprobe": None}
    missing: list[str] = []
    for name, configured in (
        ("ffmpeg", ffmpeg_configured or ""),
        ("ffprobe", ffprobe_configured or ""),
    ):
        try:
            found[name] = resolve_binary(configured, name)
        except FileNotFoundError:
            found[name] = None
            missing.append(name)

    if not missing:
        return {
            "ok": True,
            "ffmpeg": found["ffmpeg"],
            "ffprobe": found["ffprobe"],
            "missing": [],
            "detail": "",
        }

    setup = "setup.ps1" if os.name == "nt" else "setup.sh"
    labels = "、".join(missing)
    detail = (
        f"未找到 {labels}。请运行 {setup}，或在 config.yaml 的 paths.ffmpeg / paths.ffprobe 中填写路径。"
        " 压缩 / 裁剪 / 转录抽音 / 波形等功能不可用。"
    )
    return {
        "ok": False,
        "ffmpeg": found["ffmpeg"],
        "ffprobe": found["ffprobe"],
        "missing": missing,
        "detail": detail,
    }
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
pytest clio/tests/test_deps.py -v
```

- [ ] **Step 5: Commit**

```bash
git add clio/utils.py clio/tests/test_deps.py
# or test_utils.py if tests live there
git commit -m "feat(deps): probe_ffmpeg_deps for UI availability check"
```

---

### Task 2: `GET /api/deps/ffmpeg` route

**Files:**
- Create: `clio/ui/routes/deps.py`
- Modify: `clio/ui/server.py` (import + Route list)
- Test: Create `clio/tests/test_routes_deps.py`

**Interfaces:**
- Consumes: `probe_ffmpeg_deps`, `handler._resolve_project_dir`, `handler._get_config`
- Produces: `handle_get_deps_ffmpeg(handler, qs) -> None` → JSON body of probe dict

- [ ] **Step 1: Write failing route test**

```python
# clio/tests/test_routes_deps.py
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from clio.ui.routes.deps import handle_get_deps_ffmpeg


def _handler(tmp_path: Path) -> MagicMock:
    h = MagicMock()
    proj = tmp_path / "proj"
    proj.mkdir()
    h._resolve_project_dir.return_value = proj
    h._get_config.return_value = SimpleNamespace(
        paths=SimpleNamespace(ffmpeg="", ffprobe="")
    )
    h._send_json = MagicMock()
    return h


class TestHandleGetDepsFfmpeg:
    def test_returns_probe_payload(self, tmp_path: Path):
        h = _handler(tmp_path)
        payload = {
            "ok": False,
            "ffmpeg": None,
            "ffprobe": None,
            "missing": ["ffmpeg", "ffprobe"],
            "detail": "未找到 ffmpeg、ffprobe。…",
        }
        with patch("clio.ui.routes.deps.probe_ffmpeg_deps", return_value=payload) as probe:
            handle_get_deps_ffmpeg(h, {})
        probe.assert_called_once_with("", "")
        h._send_json.assert_called_once_with(payload)

    def test_uses_config_paths(self, tmp_path: Path):
        h = _handler(tmp_path)
        ff = tmp_path / "ffmpeg.exe"
        fp = tmp_path / "ffprobe.exe"
        ff.write_bytes(b"x")
        fp.write_bytes(b"x")
        h._get_config.return_value = SimpleNamespace(
            paths=SimpleNamespace(ffmpeg=str(ff), ffprobe=str(fp))
        )
        with patch("clio.ui.routes.deps.probe_ffmpeg_deps") as probe:
            probe.return_value = {"ok": True, "ffmpeg": str(ff), "ffprobe": str(fp), "missing": [], "detail": ""}
            handle_get_deps_ffmpeg(h, {})
        probe.assert_called_once_with(str(ff), str(fp))
```

- [ ] **Step 2: Run — expect FAIL (import)**

```bash
pytest clio/tests/test_routes_deps.py -v
```

- [ ] **Step 3: Implement route + register**

`clio/ui/routes/deps.py`:

```python
"""Dependency availability endpoints (ffmpeg/ffprobe)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from clio.utils import probe_ffmpeg_deps

if TYPE_CHECKING:
    from clio.ui.handler_protocol import HandlerProtocol


def handle_get_deps_ffmpeg(handler: HandlerProtocol, qs: dict[str, Any]) -> None:
    """GET /api/deps/ffmpeg — probe ffmpeg/ffprobe without side effects."""
    proj_dir = handler._resolve_project_dir(qs)
    cfg = handler._get_config(proj_dir)
    paths = getattr(cfg, "paths", None)
    ffmpeg = getattr(paths, "ffmpeg", "") or ""
    ffprobe = getattr(paths, "ffprobe", "") or ""
    handler._send_json(probe_ffmpeg_deps(ffmpeg, ffprobe))
```

In `clio/ui/server.py`:

1. Add import: `from clio.ui.routes.deps import handle_get_deps_ffmpeg`
2. Add route near other GETs (after whisper check is fine):

```python
Route("GET", "/api/deps/ffmpeg", "handle_get_deps_ffmpeg"),
```

Ensure the handler is resolvable the same way as other `handle_*` imports (module-level import already lists them).

- [ ] **Step 4: Run tests PASS**

```bash
pytest clio/tests/test_routes_deps.py -v
```

- [ ] **Step 5: Commit**

```bash
git add clio/ui/routes/deps.py clio/ui/server.py clio/tests/test_routes_deps.py
git commit -m "feat(ui): GET /api/deps/ffmpeg availability endpoint"
```

---

### Task 3: Waveform early-fail without lock/error files

**Files:**
- Modify: `clio/tasks/waveform.py` (`ensure_waveform`)
- Test: `clio/tests/test_tasks_waveform.py`

**Interfaces:**
- Consumes: `resolve_binary` (or `probe_ffmpeg_deps`)
- Produces: early return  
  `{"status":"error","error": str, "code":"missing_binary","key": key}`  
  with **no** lock file and **no** `.error` file

- [ ] **Step 1: Write failing tests**

```python
class TestMissingBinaryEarlyFail:
    def test_ensure_missing_binary_no_lock_no_error_file(self, tmp_path: Path):
        src = tmp_path / "v.mp4"
        src.write_bytes(b"v")
        key = wf.cache_key(src)

        def boom(configured, fallback):
            raise FileNotFoundError(f"找不到 {fallback}。请运行 setup…")

        with (
            patch("clio.utils.resolve_binary", side_effect=boom),
            patch.object(wf, "extract_peaks_for_video") as ex,
            patch.object(wf, "_spawn_job") as spawn,
        ):
            out = wf.ensure_waveform(tmp_path, src, ffmpeg="", ffprobe="")
        assert out["status"] == "error"
        assert out.get("code") == "missing_binary"
        assert "ffmpeg" in out["error"].lower() or "找不到" in out["error"]
        assert not wf.lock_path(tmp_path, key).exists()
        assert not wf.error_path(tmp_path, key).exists()
        ex.assert_not_called()
        spawn.assert_not_called()

    def test_ensure_missing_binary_retries_immediately_next_call(self, tmp_path: Path):
        """No cool-down: second call after install can succeed without waiting 60s."""
        src = tmp_path / "v.mp4"
        src.write_bytes(b"v")
        key = wf.cache_key(src)

        with patch("clio.utils.resolve_binary", side_effect=FileNotFoundError("找不到 ffmpeg")):
            out1 = wf.ensure_waveform(tmp_path, src, ffmpeg="")
        assert out1["status"] == "error"
        assert not wf.error_path(tmp_path, key).exists()

        def _fake_extract(video_path, ffmpeg, duration_sec=None, audio_source="original", ffprobe=""):
            return {
                "version": 1,
                "source_path": str(video_path),
                "audio_source": audio_source,
                "duration_sec": 1.0,
                "bin_count": 400,
                "peaks": [0.5],
                "status": "ready",
            }

        with (
            patch("clio.utils.resolve_binary", return_value="C:/fake/ffmpeg.exe"),
            patch.object(wf, "extract_peaks_for_video", side_effect=_fake_extract),
            patch.object(wf, "_spawn_job", side_effect=lambda fn: fn()),
        ):
            out2 = wf.ensure_waveform(tmp_path, src, ffmpeg="")
        assert out2["status"] in ("ready", "pending")
```

Note: early-fail should call `resolve_binary` **before** checking `recent_error` is not required, but must run **before** `write_lock`. Prefer checking missing binary after ready-cache hit (cache hit still returns ready without binary).

Order inside `ensure_waveform` (with `_key_lock`):

1. `read_peaks` → return if ready  
2. **probe/resolve binaries** → if missing, return `missing_binary` (no cool-down path)  
3. `recent_error` cool-down  
4. lock pending/stale  
5. write lock + spawn  

- [ ] **Step 2: Run tests — expect FAIL**

```bash
pytest clio/tests/test_tasks_waveform.py::TestMissingBinaryEarlyFail -v
```

- [ ] **Step 3: Implement early-fail in `ensure_waveform`**

Inside `ensure_waveform`, after ready hit, before `recent_error`:

```python
        # Missing binary is an environment issue — do not lock or cool-down.
        try:
            from clio.utils import resolve_binary

            resolve_binary(ffmpeg or "", "ffmpeg")
            # ffprobe optional for peaks if duration_sec provided, but compress/cut need both;
            # require ffprobe too so UI deps and waveform agree.
            resolve_binary(ffprobe or "", "ffprobe")
        except FileNotFoundError as e:
            return {
                "status": "error",
                "error": str(e),
                "code": "missing_binary",
                "key": key,
            }
```

Alternatively use `probe_ffmpeg_deps(ffmpeg or "", ffprobe or "")` and if not ok return `detail` as error — preferred for consistent messaging:

```python
        from clio.utils import probe_ffmpeg_deps

        deps = probe_ffmpeg_deps(ffmpeg or "", ffprobe or "")
        if not deps["ok"]:
            return {
                "status": "error",
                "error": deps["detail"] or "找不到 ffmpeg/ffprobe",
                "code": "missing_binary",
                "key": key,
            }
```

Route already maps `status == "error"` → 503 JSON; keep that.

- [ ] **Step 4: Run full waveform tests**

```bash
pytest clio/tests/test_tasks_waveform.py clio/tests/test_routes_waveform.py -v
```

- [ ] **Step 5: Commit**

```bash
git add clio/tasks/waveform.py clio/tests/test_tasks_waveform.py
git commit -m "fix(waveform): missing ffmpeg returns early without lock or cooldown"
```

---

### Task 4: Frontend `state.deps` + runtime-warnings banner

**Files:**
- Modify: `clio/ui/static/src/state.js`
- Modify: `clio/ui/static/src/runtime-warnings.js`
- Modify: `clio/ui/static/src/__tests__/runtime-warnings.test.js`
- Modify: `clio/ui/static/src/main.js` (and/or `sidebar-data.js` for `loadDeps`)

**Interfaces:**
- Produces: `state.deps = null | { ok, ffmpeg, ffprobe, missing, detail }`
- `buildRuntimeWarnings({ ..., ffmpegDeps })` adds warning when `ffmpegDeps?.ok === false`
- `loadFfmpegDeps()` fetches GET `/api/deps/ffmpeg` and updates state + banner

- [ ] **Step 1: Write failing vitest for warnings**

```js
// in runtime-warnings.test.js
  it('warns when ffmpeg deps are missing', () => {
    const warnings = buildRuntimeWarnings({
      config: {},
      hostname: '127.0.0.1',
      hasToken: true,
      ffmpegDeps: {
        ok: false,
        missing: ['ffmpeg', 'ffprobe'],
        detail: '未找到 ffmpeg、ffprobe。请运行 setup.ps1。',
      },
    });
    const w = warnings.find((x) => x.id === 'ffmpeg-missing');
    expect(w).toBeTruthy();
    expect(w.level).toBe('warning');
    expect(w.text).toMatch(/ffmpeg|setup/i);
    expect(w.action).toBeUndefined(); // Phase A: no install button
  });

  it('does not warn when ffmpeg deps ok', () => {
    const warnings = buildRuntimeWarnings({
      config: {},
      hostname: '127.0.0.1',
      hasToken: true,
      ffmpegDeps: { ok: true, missing: [], detail: '' },
    });
    expect(warnings.some((x) => x.id === 'ffmpeg-missing')).toBe(false);
  });
```

- [ ] **Step 2: Run vitest — expect FAIL**

```bash
cd clio/ui/static && npm test -- --run src/__tests__/runtime-warnings.test.js
```

- [ ] **Step 3: Implement state + warnings + load**

`state.js` — add field:

```js
  deps: null,  // { ok, ffmpeg, ffprobe, missing, detail } from GET /api/deps/ffmpeg
```

`runtime-warnings.js` — extend `buildRuntimeWarnings`:

```js
function buildRuntimeWarnings({
  config = {},
  hostname = '',
  hasToken = false,
  orphanedCutBackups = null,
  ffmpegDeps = null,
} = {}) {
  const warnings = [];
  // ... existing debug / lan / orphaned ...

  if (ffmpegDeps && ffmpegDeps.ok === false) {
    warnings.push({
      id: 'ffmpeg-missing',
      level: 'warning',
      text:
        ffmpegDeps.detail ||
        '未找到 ffmpeg/ffprobe。压缩 / 裁剪 / 转录抽音 / 波形等功能不可用。请运行 setup 脚本或配置 paths.ffmpeg。',
    });
  }

  return warnings;
}
```

Update `updateRuntimeWarnings` to accept `ffmpegDeps`:

```js
function updateRuntimeWarnings(config, opts = {}) {
  const container = document.getElementById('runtime-warnings');
  const warnings = buildRuntimeWarnings({
    config,
    hostname: window.location.hostname,
    hasToken: Boolean(sessionStorage.getItem('api_token')),
    orphanedCutBackups: opts.orphanedCutBackups,
    ffmpegDeps: opts.ffmpegDeps ?? null,
  });
  renderRuntimeWarnings(container, warnings, { onAction: opts.onAction });
}
```

`main.js` — load deps and pass into banner:

```js
async function loadFfmpegDeps() {
  try {
    state.deps = await api('GET', '/api/deps/ffmpeg');
  } catch {
    state.deps = null; // do not false-alarm if probe fails
  }
}

async function refreshRuntimeWarningsBanner() {
  try {
    const r = await api('GET', '/api/cut/orphaned-backups');
    _orphanedCutBackups = r.items || [];
  } catch {
    _orphanedCutBackups = [];
  }
  updateRuntimeWarnings(state.config, {
    orphanedCutBackups: _orphanedCutBackups,
    ffmpegDeps: state.deps,
    onAction: handleRuntimeWarningAction,
  });
}
```

In `init()` after `loadConfig()` (find existing call site):

```js
  await loadConfig();
  await loadFfmpegDeps();
  await refreshRuntimeWarningsBanner();
```

Also re-fetch deps after config save if there is a single save success path that reloads config (search `loadConfig()` after put); at minimum call `loadFfmpegDeps` + `refreshRuntimeWarningsBanner` when global/project config is saved successfully. If that path is hard to find, call from `selectConfig` reload after save in editor-config — implementer greps `PUT /api/config` success handlers.

Export `loadFfmpegDeps` only if other modules need it; otherwise keep local to main and re-render list when deps change:

```js
// after deps load, if video list already rendered:
import { renderVideoList } from './sidebar.js'; // or sidebar-data
// renderVideoList() if videos present
```

- [ ] **Step 4: Run vitest PASS**

```bash
cd clio/ui/static && npm test -- --run src/__tests__/runtime-warnings.test.js
```

- [ ] **Step 5: Commit**

```bash
git add clio/ui/static/src/state.js clio/ui/static/src/runtime-warnings.js \
  clio/ui/static/src/__tests__/runtime-warnings.test.js clio/ui/static/src/main.js
git commit -m "feat(ui): warn when ffmpeg/ffprobe missing via runtime banner"
```

---

### Task 5: Soft-disable video menu + runner + waveform client

**Files:**
- Modify: `clio/ui/static/src/video-menu.js`
- Modify: `clio/ui/static/src/__tests__/video-menu.test.js`
- Modify: `clio/ui/static/src/sidebar-data.js` (`buildVideoMenuItems(v, state.source, state.deps)`)
- Modify: `clio/ui/static/src/runner.js`
- Modify: `clio/ui/static/src/waveform.js`
- Optional Create: `clio/ui/static/src/__tests__/ffmpeg-deps-guard.test.js` for pure helpers

**Interfaces:**
- `buildVideoMenuItems(video, source, deps = null)`
- `mediaStepsNeedFfmpeg(steps: string[]) -> boolean` (export pure)
- `loadWaveformForCurrentVideo` checks `state.deps`

- [ ] **Step 1: Write failing tests**

```js
// video-menu.test.js
  it('disables compress and transcribe when ffmpeg deps missing', () => {
    const deps = { ok: false, detail: '未找到 ffmpeg' };
    const items = buildVideoMenuItems({ missing: false, file: 'a.mp4' }, 'original', deps);
    expect(items.find((i) => i.action === 'compress')?.disabled).toBe(true);
    expect(items.find((i) => i.action === 'transcribe')?.disabled).toBe(true);
    expect(items.find((i) => i.action === 'compress')?.title).toMatch(/ffmpeg|未找到/);
    // remove still enabled
    expect(items.find((i) => i.action === 'remove')?.disabled).toBe(false);
  });

  it('leaves compress enabled when deps ok on original online', () => {
    const items = buildVideoMenuItems(
      { missing: false, file: 'a.mp4' },
      'original',
      { ok: true, missing: [] }
    );
    expect(items.find((i) => i.action === 'compress')?.disabled).toBe(false);
  });
```

```js
// ffmpeg-deps-guard.test.js (new)
import { describe, it, expect } from 'vitest';
import { mediaStepsNeedFfmpeg } from '../runner.js'; // or from a tiny deps-guard.js

describe('mediaStepsNeedFfmpeg', () => {
  it('true for compress/label/transcribe', () => {
    expect(mediaStepsNeedFfmpeg(['analyze', 'compress'])).toBe(true);
    expect(mediaStepsNeedFfmpeg(['label'])).toBe(true);
    expect(mediaStepsNeedFfmpeg(['transcribe'])).toBe(true);
  });
  it('false for analyze/voiceover/plan only', () => {
    expect(mediaStepsNeedFfmpeg(['analyze', 'voiceover', 'plan'])).toBe(false);
  });
});
```

- [ ] **Step 2: Run — expect FAIL**

```bash
cd clio/ui/static && npm test -- --run src/__tests__/video-menu.test.js src/__tests__/ffmpeg-deps-guard.test.js
```

- [ ] **Step 3: Implement**

**video-menu.js** — after building the items array for each branch, apply:

```js
const FFMPEG_MENU_ACTIONS = new Set(['compress', 'transcribe', 'label']);

export function buildVideoMenuItems(video, source, deps = null) {
  // ... existing logic returns `items` ...
  if (deps && deps.ok === false) {
    const reason = deps.detail || '需要 ffmpeg/ffprobe';
    for (const item of items) {
      if (item.action && FFMPEG_MENU_ACTIONS.has(item.action)) {
        item.disabled = true;
        item.title = reason;
      }
    }
  }
  return items;
}
```

Cleaner: build items then call `_applyFfmpegDeps(items, deps)` before return in every exit path — or single return at end. Prefer build then one apply at each return, or refactor to `let items = ...; return applyFfmpegMenuDeps(items, deps)`.

**sidebar-data.js**:

```js
const menuHtml = videoMenuItemsToHtml(buildVideoMenuItems(v, state.source, state.deps));
```

**runner.js** — export pure helper + guard in `startRun`:

```js
const FFMPEG_RUN_STEPS = new Set(['compress', 'label', 'transcribe']);

export function mediaStepsNeedFfmpeg(steps) {
  return (Array.isArray(steps) ? steps : []).some((s) => FFMPEG_RUN_STEPS.has(s));
}

async function startRun() {
  // ... existing selection checks ...
  const options = collectRunOptions();
  if (!options.steps.length) { /* existing */ }

  if (state.deps && state.deps.ok === false && mediaStepsNeedFfmpeg(options.steps)) {
    const msg = state.deps.detail || '需要 ffmpeg/ffprobe 才能运行所选步骤';
    setStatus(msg, 'warn');
    addToast(msg, 'warning', 6000);
    updateRunStartButtonState();
    return;
  }
  // ... rest of startRun
}
```

Ensure `export { ..., mediaStepsNeedFfmpeg }` if other exports are named at bottom — match file style.

**waveform.js** — at start of `loadWaveformForCurrentVideo` after file check:

```js
  if (state.deps && state.deps.ok === false) {
    setWaveformStatus(state.deps.detail || '需要 ffmpeg');
    return;
  }
```

Import `state` already present.

- [ ] **Step 4: Run tests**

```bash
cd clio/ui/static && npm test -- --run src/__tests__/video-menu.test.js src/__tests__/ffmpeg-deps-guard.test.js src/__tests__/waveform.test.js src/__tests__/runtime-warnings.test.js
pytest clio/tests/test_deps.py clio/tests/test_routes_deps.py clio/tests/test_tasks_waveform.py -v
```

- [ ] **Step 5: Commit**

```bash
git add clio/ui/static/src/video-menu.js clio/ui/static/src/__tests__/video-menu.test.js \
  clio/ui/static/src/sidebar-data.js clio/ui/static/src/runner.js clio/ui/static/src/waveform.js \
  clio/ui/static/src/__tests__/ffmpeg-deps-guard.test.js
git commit -m "feat(ui): soft-disable media actions when ffmpeg missing"
```

---

### Task 6: Smoke + self-review checklist

- [ ] **Step 1: Full automated suite for touched areas**

```bash
pytest clio/tests/test_deps.py clio/tests/test_routes_deps.py clio/tests/test_tasks_waveform.py clio/tests/test_utils.py -k "Probe or Resolve or deps or waveform or Waveform" -v
cd clio/ui/static && npm test -- --run
```

- [ ] **Step 2: Manual smoke (if local env allows)**

1. With ffmpeg available: open UI — no `ffmpeg-missing` banner; menu compress works on original; waveform loads.
2. Temporarily break discovery (e.g. set `paths.ffmpeg` / `paths.ffprobe` to nonexistent paths in config, reload): banner appears; compress/transcribe disabled; runner with compress blocked; waveform status shows need ffmpeg; no new files under `output/waveforms/*.generating` from that attempt.
3. Restore paths / clear bad config: re-fetch deps (reload or config save path) — banner gone.

- [ ] **Step 3: Spec coverage check**

Confirm Phase A success criteria in the design doc all map to Tasks 1–5. Gaps → fix before calling A done.

- [ ] **Step 4: No Phase B/C code**

Grep for download URLs / install endpoints — should not exist yet.

```bash
rg "deps/ffmpeg/install|Gyan|btbn" clio -i || true
```

- [ ] **Step 5: Final commit only if smoke fixes needed**; otherwise stop. Ask user before push.

---

## Self-review (plan vs spec)

| Spec requirement | Task |
| --- | --- |
| `probe_ffmpeg_deps` | Task 1 |
| `GET /api/deps/ffmpeg` | Task 2 |
| Waveform no lock/error on missing binary | Task 3 |
| Banner warning level | Task 4 |
| `state.deps` | Task 4 |
| Menu soft-disable compress/transcribe | Task 5 |
| Runner block media steps only | Task 5 |
| Waveform client short-circuit | Task 5 |
| No install (B/C) | Task 6 guard |
| Empty config not bare name | Task 1 test |

**Placeholder scan:** none intentional; static-build URLs deferred to B.

**Type consistency:** `state.deps` matches probe/API dict; `code: "missing_binary"` on waveform error only.

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-18-ffmpeg-handling-phase-a.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks  
2. **Inline Execution** — this session with executing-plans, batch with checkpoints  

Which approach?
