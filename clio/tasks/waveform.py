"""Lazy audio waveform peaks cache for the player UI.

Peaks are extracted with ffmpeg (mono PCM), binned max-abs, stored under
output/waveforms/<sha1-key>.json. Generation is non-blocking: ensure_waveform
returns ready or pending and may start a daemon job with file locks.
"""

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


def lock_status(project_output: Path, key: str, *, now: float | None = None) -> Literal["none", "pending", "stale"]:
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


def write_lock(project_output: Path, key: str, source_path: Path, *, now: float | None = None) -> None:
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
    ffmpeg_bin = resolve_binary(ffmpeg, "ffmpeg") if ffmpeg else resolve_binary("", "ffmpeg")
    dur = duration_sec
    if dur is None or dur <= 0:
        try:
            ffprobe = resolve_binary("", "ffprobe")
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
            ffmpeg_bin,
        )
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

        write_lock(project_output, key, source_path)
        started_at = time.time()

        def _job() -> None:
            global _active_jobs
            with _jobs_lock:
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
        return {"status": "pending", "started_at": started_at, "key": key}
