# Video Player Audio Waveform Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show a scrubbable amplitude waveform under the main player, with lazy ffmpeg peaks cached under `output/waveforms/`, never blocking video load.

**Architecture:** Pure library `clio/tasks/waveform.py` owns cache key, lock/stale, peaks extract, and ensure-async. `GET /api/waveform` resolves media (original-prefer when full file; play-file when split segment), returns 200 ready or 202 pending. Frontend `waveform.js` + bar under `<video>` draws canvas, seeks, polls pending. Mirror cover/video project query params.

**Tech Stack:** Python 3.11, existing ffmpeg via `resolve_binary` / subprocess (same spirit as `clio/tasks/transcribe.py` `_extract_audio`), stdlib `threading`, vanilla JS ES modules, Vitest, pytest + unittest.mock.

**Spec:** `docs/superpowers/specs/2026-07-18-video-waveform-design.md`

## Global Constraints

- No new npm or Python dependencies.
- Never block `player.src` load on waveform generation.
- Peaks prefer **original** for full-file media; for **split segments** (`segment_label` present) use the **currently loaded** file so duration matches (spec §6.4).
- Cache under `{project_output}/waveforms/`; key = `sha1(normalized_abs_path)[:16]`.
- `STALE_SEC = 900` for `.generating` locks; max **2** concurrent ffmpeg waveform jobs.
- Work on `main`; one feature per commit; English commit messages; Chinese UI strings only.
- TDD for pure helpers first; mock ffmpeg in unit tests (no real media required).
- `api()` in `api.js` treats 202 as OK (`r.ok`); body must include `status: "pending"` so the client can branch without reading HTTP status.

## File map

| File | Responsibility |
| --- | --- |
| `clio/tasks/waveform.py` | Cache paths, key, read/write peaks, lock/stale, bin_count, peaks from WAV/path, job kick |
| `clio/tests/test_tasks_waveform.py` | Unit tests for above (mock ffmpeg) |
| `clio/ui/routes/waveform.py` | `handle_get_waveform`, media resolve, optional regenerate |
| `clio/tests/test_routes_waveform.py` | Route tests with MagicMock handler |
| `clio/ui/server.py` | Import + `Route("GET", "/api/waveform", ...)` (+ POST regenerate if Task 5) |
| `clio/ui/static/index.html` | `#waveform-bar` DOM under player |
| `clio/ui/static/style.css` | Waveform bar layout |
| `clio/ui/static/src/waveform.js` | Fetch/poll, canvas draw, scrub math, playhead |
| `clio/ui/static/src/__tests__/waveform.test.js` | Pure helpers |
| `clio/ui/static/src/viewer.js` | Hook select/play + timeupdate |
| `clio/ui/static/src/api.js` | No change if 202 already OK; only change if tests prove otherwise |

---

### Task 1: Peaks cache + compute library (TDD)

**Files:**
- Create: `clio/tasks/waveform.py`
- Create: `clio/tests/test_tasks_waveform.py`

**Interfaces:**
- Produces:
  - `WAVEFORM_VERSION = 1`
  - `STALE_SEC = 900`
  - `MAX_CONCURRENT_JOBS = 2`
  - `cache_key(source_path: Path) -> str`
  - `waveforms_dir(project_output: Path) -> Path`
  - `ready_path(project_output: Path, key: str) -> Path`
  - `lock_path(project_output: Path, key: str) -> Path`
  - `bin_count_for_duration(duration_sec: float) -> int`  # clamp(round(d*2), 400, 2000)
  - `read_peaks(project_output: Path, key: str) -> dict | None`
  - `write_peaks_atomic(project_output: Path, key: str, payload: dict) -> Path`
  - `lock_status(project_output: Path, key: str, *, now: float | None = None) -> Literal["none","pending","stale"]`
  - `write_lock(project_output: Path, key: str, source_path: Path, *, now: float | None = None) -> None`
  - `clear_lock(project_output: Path, key: str) -> None`
  - `peaks_from_pcm_s16le(pcm: bytes, *, bin_count: int) -> list[float]`  # max-abs per bin, normalize 0..1
  - `extract_peaks_for_video(video_path: Path, ffmpeg: str, *, duration_sec: float | None = None) -> dict`  # runs ffmpeg → temp wav → peaks payload (no project write)
  - `ensure_waveform(project_output: Path, source_path: Path, ffmpeg: str, *, duration_sec: float | None = None, audio_source: str = "original") -> dict`  
    Returns either ready payload with `"status": "ready"` or `{"status": "pending", "started_at": ..., "key": ...}`. Side effect: may start daemon thread.

- [ ] **Step 1: Write failing tests**

Create `clio/tests/test_tasks_waveform.py`:

```python
"""Tests for clio/tasks/waveform.py — peaks cache, lock, binning."""

from __future__ import annotations

import json
import struct
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from clio.tasks import waveform as wf


class TestCacheKey:
    def test_stable_and_hex(self, tmp_path: Path):
        p = tmp_path / "GL010695.MP4"
        p.write_bytes(b"x")
        k1 = wf.cache_key(p)
        k2 = wf.cache_key(p.resolve())
        assert k1 == k2
        assert len(k1) == 16
        assert all(c in "0123456789abcdef" for c in k1)

    def test_different_paths_differ(self, tmp_path: Path):
        a = tmp_path / "a.mp4"
        b = tmp_path / "b.mp4"
        a.write_bytes(b"1")
        b.write_bytes(b"2")
        assert wf.cache_key(a) != wf.cache_key(b)


class TestBinCount:
    def test_clamps(self):
        assert wf.bin_count_for_duration(1) == 400
        assert wf.bin_count_for_duration(300) == 600  # 300*2
        assert wf.bin_count_for_duration(10_000) == 2000


class TestPeaksFromPcm:
    def test_silence_is_zero(self):
        pcm = b"\x00\x00" * 1000
        peaks = wf.peaks_from_pcm_s16le(pcm, bin_count=10)
        assert len(peaks) == 10
        assert all(p == 0.0 for p in peaks)

    def test_loud_sample_normalizes(self):
        # one full-scale sample then zeros
        loud = struct.pack("<h", 32767)
        pcm = loud + b"\x00\x00" * 99
        peaks = wf.peaks_from_pcm_s16le(pcm, bin_count=4)
        assert max(peaks) == pytest.approx(1.0)
        assert min(peaks) >= 0.0


class TestLockAndReadWrite:
    def test_write_read_roundtrip(self, tmp_path: Path):
        key = "abc123def4567890"
        payload = {
            "version": 1,
            "source_path": "D:/x.mp4",
            "audio_source": "original",
            "duration_sec": 12.5,
            "bin_count": 400,
            "peaks": [0.1, 0.2, 0.3],
            "status": "ready",
        }
        wf.write_peaks_atomic(tmp_path, key, payload)
        got = wf.read_peaks(tmp_path, key)
        assert got is not None
        assert got["peaks"] == [0.1, 0.2, 0.3]
        assert got["version"] == 1

    def test_lock_pending_then_stale(self, tmp_path: Path, monkeypatch):
        key = "abc123def4567890"
        src = tmp_path / "v.mp4"
        src.write_bytes(b"v")
        t0 = 1_000_000.0
        wf.write_lock(tmp_path, key, src, now=t0)
        assert wf.lock_status(tmp_path, key, now=t0 + 10) == "pending"
        assert wf.lock_status(tmp_path, key, now=t0 + wf.STALE_SEC + 1) == "stale"
        wf.clear_lock(tmp_path, key)
        assert wf.lock_status(tmp_path, key, now=t0) == "none"

    def test_ensure_ready_hit_skips_job(self, tmp_path: Path):
        src = tmp_path / "v.mp4"
        src.write_bytes(b"v")
        key = wf.cache_key(src)
        wf.write_peaks_atomic(
            tmp_path,
            key,
            {
                "version": 1,
                "source_path": str(src),
                "audio_source": "original",
                "duration_sec": 1.0,
                "bin_count": 400,
                "peaks": [0.5],
                "status": "ready",
            },
        )
        with patch.object(wf, "extract_peaks_for_video") as ex:
            out = wf.ensure_waveform(tmp_path, src, ffmpeg="ffmpeg")
        assert out["status"] == "ready"
        assert out["peaks"] == [0.5]
        ex.assert_not_called()

    def test_ensure_missing_returns_pending_and_writes_lock(self, tmp_path: Path):
        src = tmp_path / "v.mp4"
        src.write_bytes(b"v")
        key = wf.cache_key(src)

        def _fake_extract(video_path, ffmpeg, duration_sec=None):
            return {
                "version": 1,
                "source_path": str(video_path),
                "audio_source": "original",
                "duration_sec": 1.0,
                "bin_count": 400,
                "peaks": [0.1, 0.9],
                "status": "ready",
            }

        with (
            patch.object(wf, "extract_peaks_for_video", side_effect=_fake_extract),
            patch.object(wf, "_spawn_job", side_effect=lambda fn: fn()),  # run inline
        ):
            out = wf.ensure_waveform(tmp_path, src, ffmpeg="ffmpeg", audio_source="original")
        # After inline job completes, ensure may return ready; if design returns pending first:
        # accept either ready (sync complete) or pending then ready on second call.
        assert out["status"] in ("ready", "pending")
        if out["status"] == "pending":
            assert wf.lock_status(tmp_path, key) in ("pending", "none")
            out2 = wf.ensure_waveform(tmp_path, src, ffmpeg="ffmpeg")
            assert out2["status"] == "ready"
            assert out2["peaks"] == [0.1, 0.9]
        else:
            assert out["peaks"] == [0.1, 0.9]
```

- [ ] **Step 2: Run tests — expect FAIL (module missing)**

```bash
.venv/Scripts/python -m pytest clio/tests/test_tasks_waveform.py -q --tb=line
```

Expected: `ModuleNotFoundError` or collection errors.

- [ ] **Step 3: Implement `clio/tasks/waveform.py`**

Minimal implementation notes:

```python
# clio/tasks/waveform.py
from __future__ import annotations

import hashlib
import json
import os
import struct
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable, Literal

WAVEFORM_VERSION = 1
STALE_SEC = 900
MAX_CONCURRENT_JOBS = 2
_MIN_BINS, _MAX_BINS = 400, 2000

_jobs_lock = threading.Lock()
_active_jobs = 0
_key_locks: dict[str, threading.Lock] = {}
_key_locks_guard = threading.Lock()


def cache_key(source_path: Path) -> str:
    resolved = str(Path(source_path).resolve()).replace("\\", "/").lower()
    return hashlib.sha1(resolved.encode("utf-8")).hexdigest()[:16]


def waveforms_dir(project_output: Path) -> Path:
    return Path(project_output) / "waveforms"


def ready_path(project_output: Path, key: str) -> Path:
    return waveforms_dir(project_output) / f"{key}.json"


def lock_path(project_output: Path, key: str) -> Path:
    return waveforms_dir(project_output) / f"{key}.generating"


def bin_count_for_duration(duration_sec: float) -> int:
    d = max(0.0, float(duration_sec or 0.0))
    return max(_MIN_BINS, min(_MAX_BINS, int(round(d * 2))))


def peaks_from_pcm_s16le(pcm: bytes, *, bin_count: int) -> list[float]:
    n = len(pcm) // 2
    if n <= 0 or bin_count <= 0:
        return [0.0] * max(bin_count, 0)
    samples = struct.unpack("<" + "h" * n, pcm[: n * 2])
    peaks = [0.0] * bin_count
    for i, s in enumerate(samples):
        b = min(bin_count - 1, int(i * bin_count / n))
        a = abs(s) / 32768.0
        if a > peaks[b]:
            peaks[b] = a
    m = max(peaks) if peaks else 0.0
    if m > 0:
        peaks = [p / m for p in peaks]
    return peaks


def read_peaks(project_output: Path, key: str) -> dict[str, Any] | None:
    p = ready_path(project_output, key)
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if data.get("version") != WAVEFORM_VERSION or not isinstance(data.get("peaks"), list):
        return None
    data.setdefault("status", "ready")
    return data


def write_peaks_atomic(project_output: Path, key: str, payload: dict[str, Any]) -> Path:
    d = waveforms_dir(project_output)
    d.mkdir(parents=True, exist_ok=True)
    dest = ready_path(project_output, key)
    tmp = dest.with_suffix(".json.tmp")
    body = dict(payload)
    body["status"] = "ready"
    body["version"] = WAVEFORM_VERSION
    tmp.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, dest)
    return dest


def lock_status(
    project_output: Path, key: str, *, now: float | None = None
) -> Literal["none", "pending", "stale"]:
    lp = lock_path(project_output, key)
    if not lp.is_file():
        return "none"
    try:
        data = json.loads(lp.read_text(encoding="utf-8"))
        started = float(data.get("started_at") or 0)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return "stale"
    t = time.time() if now is None else now
    if t - started > STALE_SEC:
        return "stale"
    return "pending"


def write_lock(
    project_output: Path, key: str, source_path: Path, *, now: float | None = None
) -> None:
    d = waveforms_dir(project_output)
    d.mkdir(parents=True, exist_ok=True)
    payload = {
        "started_at": time.time() if now is None else now,
        "source_path": str(source_path),
        "pid": os.getpid(),
    }
    lock_path(project_output, key).write_text(json.dumps(payload), encoding="utf-8")


def clear_lock(project_output: Path, key: str) -> None:
    lock_path(project_output, key).unlink(missing_ok=True)


def _key_lock(key: str) -> threading.Lock:
    with _key_locks_guard:
        if key not in _key_locks:
            _key_locks[key] = threading.Lock()
        return _key_locks[key]


def _spawn_job(fn: Callable[[], None]) -> None:
    t = threading.Thread(target=fn, daemon=True)
    t.start()


def extract_peaks_for_video(
    video_path: Path,
    ffmpeg: str,
    *,
    duration_sec: float | None = None,
    audio_source: str = "original",
) -> dict[str, Any]:
    """Extract mono s16le via temp wav (8kHz is enough for amplitude peaks)."""
    from clio.utils import get_duration_sec, resolve_binary, run_ffmpeg

    video_path = Path(video_path)
    ffmpeg = resolve_binary(ffmpeg, "ffmpeg") if ffmpeg else resolve_binary("", "ffmpeg")
    dur = duration_sec
    if dur is None or dur <= 0:
        try:
            from clio.utils import resolve_binary as rb

            # ffprobe optional — if missing, estimate from sample count later
            ffprobe = rb("", "ffprobe")
            dur = get_duration_sec(video_path, ffprobe)
        except Exception:
            dur = 0.0
    bins = bin_count_for_duration(dur if dur and dur > 0 else 60.0)
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    tmp_path = Path(tmp.name)
    try:
        run_ffmpeg(
            [
                "-y",
                "-i",
                str(video_path),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "8000",
                "-acodec",
                "pcm_s16le",
                str(tmp_path),
            ],
            ffmpeg,
        )
        # skip WAV header 44 bytes if present
        raw = tmp_path.read_bytes()
        pcm = raw[44:] if len(raw) > 44 and raw[:4] == b"RIFF" else raw
        peaks = peaks_from_pcm_s16le(pcm, bin_count=bins)
        return {
            "version": WAVEFORM_VERSION,
            "source_path": str(video_path.resolve()),
            "audio_source": audio_source,
            "duration_sec": float(dur or 0.0),
            "bin_count": bins,
            "peaks": peaks,
            "status": "ready",
        }
    finally:
        tmp_path.unlink(missing_ok=True)


def ensure_waveform(
    project_output: Path,
    source_path: Path,
    ffmpeg: str,
    *,
    duration_sec: float | None = None,
    audio_source: str = "original",
) -> dict[str, Any]:
    source_path = Path(source_path)
    key = cache_key(source_path)
    with _key_lock(key):
        ready = read_peaks(project_output, key)
        if ready is not None:
            return ready
        st = lock_status(project_output, key)
        if st == "stale":
            clear_lock(project_output, key)
            st = "none"
        if st == "pending":
            try:
                data = json.loads(lock_path(project_output, key).read_text(encoding="utf-8"))
                started = float(data.get("started_at") or time.time())
            except Exception:
                started = time.time()
            return {"status": "pending", "started_at": started, "key": key}

        # start job
        write_lock(project_output, key, source_path)

        def _job() -> None:
            global _active_jobs
            with _jobs_lock:
                # simple global cap: wait-spin is OK for daemon
                while _active_jobs >= MAX_CONCURRENT_JOBS:
                    time.sleep(0.2)
                _active_jobs += 1
            try:
                payload = extract_peaks_for_video(
                    source_path,
                    ffmpeg,
                    duration_sec=duration_sec,
                    audio_source=audio_source,
                )
                write_peaks_atomic(project_output, key, payload)
            except Exception as e:
                try:
                    err = waveforms_dir(project_output) / f"{key}.error"
                    err.write_text(str(e)[:500], encoding="utf-8")
                except OSError:
                    pass
            finally:
                clear_lock(project_output, key)
                with _jobs_lock:
                    _active_jobs = max(0, _active_jobs - 1)

        _spawn_job(_job)
        return {"status": "pending", "started_at": time.time(), "key": key}
```

Adjust `extract_peaks_for_video` ffprobe wiring to match project helpers cleanly (prefer `resolve_binary(config…)` only at route layer; tests mock `extract_peaks_for_video` entirely).

- [ ] **Step 4: Run tests — expect PASS**

```bash
.venv/Scripts/python -m pytest clio/tests/test_tasks_waveform.py -q --tb=short
```

Expected: all passed. Fix until green.

- [ ] **Step 5: Commit**

```bash
git add clio/tasks/waveform.py clio/tests/test_tasks_waveform.py
git commit -m "$(cat <<'EOF'
feat(waveform): peaks cache, lock, and lazy ensure job

Add output/waveforms JSON peaks with stale lock recovery and
non-blocking ensure_waveform for the player API.
EOF
)"
```

---

### Task 2: GET /api/waveform route

**Files:**
- Create: `clio/ui/routes/waveform.py`
- Create: `clio/tests/test_routes_waveform.py`
- Modify: `clio/ui/server.py` (import + Route registration)

**Interfaces:**
- Consumes: `ensure_waveform`, `cache_key`, `read_peaks` from Task 1; `handler._resolve_project_dir`, `_get_project_output`, `_get_config`; video path rules similar to `handle_get_video`.
- Produces: `handle_get_waveform(handler, qs) -> None`
- Query params: `file`, `source` (`compressed`|`original`), `abspath` optional, `is_segment` optional (`"1"`/`"true"`), project params as usual.

**Media resolution rules (implement exactly):**

1. If `source == "compressed"` and `file` safe basename:
   - `compressed_path = proj_out / "compressed" / file`
2. If `abspath` present and file exists and suffix in `VIDEO_EXTENSIONS`:
   - `original_path = Path(abspath).resolve()` (still require membership in `videos.json` selection when checking original for play parity — same as `handle_get_video`)
3. **Peaks source selection:**
   - If `is_segment` is true → use **player file**: compressed_path if source compressed else original_path; `audio_source` = that kind.
   - Else if original_path exists → use original; `audio_source="original"`.
   - Else if compressed_path exists → use compressed; `audio_source="compressed"`.
   - Else → 404 JSON `{"ok": false, "error": "no media"}`.

4. Call `ensure_waveform(proj_out, peaks_path, ffmpeg, audio_source=...)`.
5. If result `status=="ready"` → `_send_json(result)` (200).
6. If `status=="pending"` → `_send_json(result, 202)`.

Note: confirm `Handler._send_json` accepts status code as second arg (used elsewhere as `_send_json(..., 400)`).

- [ ] **Step 1: Write failing route tests**

```python
# clio/tests/test_routes_waveform.py
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from clio.ui.routes.waveform import handle_get_waveform


def _handler(tmp_path: Path) -> MagicMock:
    h = MagicMock()
    proj = tmp_path / "proj"
    out = tmp_path / "out"
    proj.mkdir()
    out.mkdir()
    h._resolve_project_dir.return_value = proj
    h._get_project_output.return_value = out
    h._get_config.return_value = SimpleNamespace(
        paths=SimpleNamespace(ffmpeg="ffmpeg", ffprobe="ffprobe")
    )
    h._send_json = MagicMock()
    return h


class TestHandleGetWaveform:
    def test_ready_returns_peaks(self, tmp_path: Path):
        h = _handler(tmp_path)
        out = h._get_project_output.return_value
        comp = out / "compressed"
        comp.mkdir()
        vid = comp / "001_a.mp4"
        vid.write_bytes(b"x")
        payload = {
            "status": "ready",
            "version": 1,
            "peaks": [0.1, 0.2],
            "duration_sec": 1.0,
            "bin_count": 2,
            "audio_source": "compressed",
            "source_path": str(vid),
        }
        with patch("clio.ui.routes.waveform.ensure_waveform", return_value=payload) as en:
            handle_get_waveform(
                h,
                {"file": ["001_a.mp4"], "source": ["compressed"], "is_segment": ["1"]},
            )
        en.assert_called_once()
        h._send_json.assert_called_once()
        args = h._send_json.call_args
        assert args[0][0]["status"] == "ready"
        # 200 default — no status or status 200
        if len(args[0]) > 1:
            assert args[0][1] == 200

    def test_pending_returns_202(self, tmp_path: Path):
        h = _handler(tmp_path)
        out = h._get_project_output.return_value
        comp = out / "compressed"
        comp.mkdir()
        (comp / "001_a.mp4").write_bytes(b"x")
        with patch(
            "clio.ui.routes.waveform.ensure_waveform",
            return_value={"status": "pending", "started_at": 1.0, "key": "k"},
        ):
            handle_get_waveform(
                h, {"file": ["001_a.mp4"], "source": ["compressed"], "is_segment": ["1"]}
            )
        args = h._send_json.call_args
        assert args[0][0]["status"] == "pending"
        assert args[0][1] == 202

    def test_no_media_404(self, tmp_path: Path):
        h = _handler(tmp_path)
        handle_get_waveform(h, {"file": ["missing.mp4"], "source": ["compressed"]})
        args = h._send_json.call_args
        assert args[0][1] == 404
```

- [ ] **Step 2: Run — FAIL (import/route missing)**

```bash
.venv/Scripts/python -m pytest clio/tests/test_routes_waveform.py -q --tb=line
```

- [ ] **Step 3: Implement route + register**

`clio/ui/routes/waveform.py` — resolve paths; call `ensure_waveform`.

In `clio/ui/server.py`:

```python
from clio.ui.routes.waveform import handle_get_waveform
# in route table near /api/cover:
Route("GET", "/api/waveform", "handle_get_waveform"),
```

Ensure the handler method name is bound the same way as other route handlers (local import namespace / getattr pattern already used by Route list).

- [ ] **Step 4: Run route tests + Task 1 tests**

```bash
.venv/Scripts/python -m pytest clio/tests/test_tasks_waveform.py clio/tests/test_routes_waveform.py -q --tb=short
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add clio/ui/routes/waveform.py clio/tests/test_routes_waveform.py clio/ui/server.py
git commit -m "$(cat <<'EOF'
feat(ui): GET /api/waveform with lazy peaks generation

Resolve original-prefer vs segment play-file, return 200 ready or
202 pending using ensure_waveform.
EOF
)"
```

---

### Task 3: Frontend pure helpers + bar chrome (TDD)

**Files:**
- Create: `clio/ui/static/src/waveform.js`
- Create: `clio/ui/static/src/__tests__/waveform.test.js`
- Modify: `clio/ui/static/index.html` (insert bar)
- Modify: `clio/ui/static/style.css`

**Interfaces:**
- Produces (export):
  - `timeFromClientX(clientX, barRect, duration) -> number`  # seconds, clamped
  - `playheadRatio(currentTime, duration) -> number`  # 0..1
  - `buildWaveformQuery(video, { source, project handled by api }) -> URLSearchParams fields object`  
    Returns `{ file, source, abspath?, is_segment? }` for query string.
  - `drawWaveform(canvas, peaks, { playheadRatio, width, height, dpr })` (optional pure enough to smoke-test with jsdom/canvas mock — if canvas hard in vitest, only test math + query builder)

**Query builder rules:**

```js
export function buildWaveformQuery(v, source) {
  const isSegment = Boolean(v?.segment_label);
  const params = { source, file: v.file };
  if (isSegment) {
    params.is_segment = '1';
    if (source === 'original' && v.abs_path) params.abspath = v.abs_path;
    // compressed segment: file is compressed name as listed
    if (source === 'original' && v.match?.file) {
      // when UI source is original but peaks should follow play file:
      // playVideoSegment still loads original for non-compressed mode;
      // if segment_matches compressed, prefer compressed file for peaks:
      params.source = 'compressed';
      params.file = v.match.file;
      delete params.abspath;
    }
  } else {
    // full file: prefer original abs if online
    const orig = v.abs_path || v.match?.abs_path;
    const origMissing = v.missing || v.match?.missing;
    if (orig && !origMissing) {
      params.abspath = orig;
      // keep source as-is; server prefers original when abspath exists & not segment
    }
  }
  return params;
}
```

Refine against actual `state.videos` shapes from `/api/videos` (compressed entries have `match.abs_path`; original entries have `abs_path` + `match.file`). Adjust so **non-segment** always sends original `abspath` when available; **segment** sends the compressed segment basename with `source=compressed` + `is_segment=1`.

- [ ] **Step 1: Failing vitest**

```js
// clio/ui/static/src/__tests__/waveform.test.js
import { describe, it, expect } from 'vitest';
import { timeFromClientX, playheadRatio, buildWaveformQuery } from '../waveform.js';

describe('timeFromClientX', () => {
  const rect = { left: 100, width: 200 };
  it('maps left edge to 0', () => {
    expect(timeFromClientX(100, rect, 50)).toBe(0);
  });
  it('maps right edge to duration', () => {
    expect(timeFromClientX(300, rect, 50)).toBe(50);
  });
  it('clamps outside', () => {
    expect(timeFromClientX(0, rect, 50)).toBe(0);
    expect(timeFromClientX(999, rect, 50)).toBe(50);
  });
  it('returns 0 if duration invalid', () => {
    expect(timeFromClientX(150, rect, NaN)).toBe(0);
  });
});

describe('playheadRatio', () => {
  it('clamps', () => {
    expect(playheadRatio(5, 10)).toBe(0.5);
    expect(playheadRatio(-1, 10)).toBe(0);
    expect(playheadRatio(99, 10)).toBe(1);
    expect(playheadRatio(1, 0)).toBe(0);
  });
});

describe('buildWaveformQuery', () => {
  it('segment uses compressed play file', () => {
    const q = buildWaveformQuery(
      { file: '001_GL_seg01.mp4', segment_label: '1/2', match: { file: '001_GL_seg01.mp4' } },
      'compressed',
    );
    expect(q.is_segment).toBe('1');
    expect(q.source).toBe('compressed');
    expect(q.file).toContain('seg');
  });

  it('full file prefers original abspath', () => {
    const q = buildWaveformQuery(
      { file: '001_GL.mp4', match: { abs_path: 'D:/GL.MP4', missing: false } },
      'compressed',
    );
    expect(q.abspath).toBe('D:/GL.MP4');
    expect(q.is_segment).toBeUndefined();
  });
});
```

- [ ] **Step 2: Run vitest — FAIL**

```bash
cd clio/ui/static && npm test -- --run src/__tests__/waveform.test.js
```

- [ ] **Step 3: Implement helpers + DOM + CSS**

`waveform.js` — export pure functions first; also export:

```js
export function requestWaveformForVideo(v, source) { /* api GET builder */ }
export function mountWaveformBar() { /* no-op if missing */ }
export function setWaveformPeaks(peaksPayload) {}
export function setWaveformStatus(text) {}
export function updateWaveformPlayhead(player) {}
export function bindWaveformScrub(player) {}
export function resetWaveform() {}
export function loadWaveformForCurrentVideo() {}
```

HTML insert in `index.html` after `</div>` of `.player-wrap` (before `#player-info`):

```html
    <div id="waveform-bar" class="waveform-bar" hidden>
      <canvas id="waveform-canvas" aria-hidden="true"></canvas>
      <div class="waveform-playhead" id="waveform-playhead" hidden></div>
      <div class="waveform-status" id="waveform-status" aria-live="polite"></div>
    </div>
```

CSS sketch:

```css
.waveform-bar {
  position: relative;
  height: 32px;
  margin: 0 0 4px;
  background: var(--bg-surface-2);
  border: 1px solid var(--border);
  border-radius: 3px;
  cursor: pointer;
  user-select: none;
}
.waveform-bar[hidden] { display: none !important; }
.waveform-bar canvas {
  display: block;
  width: 100%;
  height: 100%;
}
.waveform-playhead {
  position: absolute;
  top: 0; bottom: 0;
  width: 2px;
  background: var(--accent);
  pointer-events: none;
  transform: translateX(-1px);
}
.waveform-status {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  color: var(--text-muted);
  pointer-events: none;
}
.waveform-bar.has-peaks .waveform-status { display: none; }
```

- [ ] **Step 4: Vitest PASS**

```bash
cd clio/ui/static && npm test -- --run src/__tests__/waveform.test.js
```

- [ ] **Step 5: Commit**

```bash
git add clio/ui/static/src/waveform.js clio/ui/static/src/__tests__/waveform.test.js clio/ui/static/index.html clio/ui/static/style.css
git commit -m "$(cat <<'EOF'
feat(ui): waveform bar helpers and player chrome

Pure scrub math + query builder; canvas bar DOM/CSS under video.
EOF
)"
```

---

### Task 4: Wire load, poll, scrub, playhead

**Files:**
- Modify: `clio/ui/static/src/waveform.js` (full behavior)
- Modify: `clio/ui/static/src/viewer.js` (`playVideoSegment`, `setupPlayer`)
- Modify: `clio/ui/static/src/api.js` only if 202 handling needs a `raw` fetch (prefer using `api()` and `status` field)

**Behavior checklist:**

1. `playVideoSegment` after setting `player.src` / seek: call `loadWaveformForCurrentVideo()`.
2. `loadWaveformForCurrentVideo`:
   - `resetWaveform()` cancel poll timer (`_pollToken++`).
   - If no `state.currentVideo`, hide bar.
   - Show bar, status `波形生成中…` until ready.
   - `api('GET', '/api/waveform?' + params)` — **note** `api()` already appends project; build query with file/source/abspath/is_segment only.
   - If `status==='ready'` or body has `peaks`: `setWaveformPeaks`, draw, clear status, `has-peaks` class.
   - If `status==='pending'`: keep status; start poll every 2500ms, max 120 times or until token changes; on ready draw.
   - On throw (404/500): status short error, flat bar.
3. Scrub: pointer events on `#waveform-bar` → `timeFromClientX` → `player.currentTime`.
4. `setupPlayer` `ontimeupdate` also calls `updateWaveformPlayhead(player)`.
5. `ResizeObserver` on bar redraws last peaks.

**api() 202:** `r.ok` is true for 202; JSON returns. If any middleware treats 202 as error, use:

```js
// only if needed
export async function apiRaw(method, url) { ... return { status: r.status, body } }
```

- [ ] **Step 1: Implement wiring in `viewer.js`**

```js
import { loadWaveformForCurrentVideo, updateWaveformPlayhead, bindWaveformScrub, resetWaveform } from './waveform.js';

// end of playVideoSegment success path:
loadWaveformForCurrentVideo();

// setupPlayer:
bindWaveformScrub(player);
// inside ontimeupdate:
updateWaveformPlayhead(player);
```

Implement remaining functions in `waveform.js` using `api` from `./api.js` and `state` from `./state.js`.

- [ ] **Step 2: Manual smoke (local UI)**

1. Start UI server as usual for this project.
2. Open a project with online original + analysis.
3. Select a video: video plays immediately; waveform pending then fills.
4. Click/drag bar seeks.
5. Switch video: old poll stops; new request starts.
6. Kill server mid-generate, restart, reselect: stale lock regenerates (wait up to STALE only if lock young — for test, manually age `.generating` or delete ready).

- [ ] **Step 3: Regression tests**

```bash
.venv/Scripts/python -m pytest clio/tests/test_tasks_waveform.py clio/tests/test_routes_waveform.py -q
cd clio/ui/static && npm test -- --run src/__tests__/waveform.test.js
```

- [ ] **Step 4: Commit**

```bash
git add clio/ui/static/src/waveform.js clio/ui/static/src/viewer.js
git commit -m "$(cat <<'EOF'
feat(ui): load, poll, and scrub audio waveform under player

Non-blocking GET /api/waveform with pending poll; canvas draw and
playhead sync on timeupdate.
EOF
)"
```

---

### Task 5 (optional P1): Regenerate menu + docs touch

**Skip if timeboxed; only if Task 4 stable and menu hook is one-liner.**

**Files:**
- Modify: `clio/ui/routes/waveform.py` — `handle_post_waveform_regenerate`
- Modify: `clio/ui/server.py` — POST route
- Modify: `clio/ui/static/src/video-menu.js` — item “重新生成波形”
- Modify: `docs/superpowers/specs/2026-07-18-video-waveform-design.md` status → Implemented
- Optional one line in `clio/ui/README.md` if it documents player features

**POST body:** same identity fields as GET; delete ready+lock+error for key; `ensure_waveform` again; 202.

- [ ] **Step 1: Implement + test delete-and-kick**
- [ ] **Step 2: Commit**

```bash
git commit -m "feat(ui): regenerate waveform action and docs note"
```

---

## Spec coverage checklist

| Spec item | Task |
| --- | --- |
| Lazy peaks cache under `output/waveforms/` | 1 |
| Key sha1 path, JSON schema version 1 | 1 |
| Lock + stale 900s + no double job | 1 |
| Background thread, max 2 concurrent | 1 |
| GET 200/202, never block video | 2, 4 |
| Original prefer / segment play-file | 2, 3 |
| Canvas bar under video, scrub, playhead | 3, 4 |
| Pending poll, cancel on video change | 4 |
| Optional regenerate | 5 |
| Unit tests mock ffmpeg | 1, 2 |
| Vitest scrub math | 3 |
| No new deps | Global |

## Placeholder / consistency self-review

- No TBD left in task steps.
- `ensure_waveform` return shape used consistently: `status` ready|pending.
- HTTP 202 body includes `status: "pending"` for `api()` consumers.
- Segment query builder must match server `is_segment` handling — both Task 2 and 3.

---

## Execution handoff

Plan saved to `docs/superpowers/plans/2026-07-18-video-waveform-plan.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks  
2. **Inline Execution** — this session with executing-plans and checkpoints  

Which approach?
