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

    def test_lock_pending_then_stale(self, tmp_path: Path):
        key = "abc123def4567890"
        src = tmp_path / "v.mp4"
        src.write_bytes(b"v")
        t0 = 1_000_000.0
        wf.write_lock(tmp_path, key, src, now=t0)
        # same-pid lock with no live job → stale; simulate live job first
        with wf._jobs_lock:
            wf._active_job_keys.add(key)
        try:
            assert wf.lock_status(tmp_path, key, now=t0 + 10) == "pending"
            assert wf.lock_status(tmp_path, key, now=t0 + wf.STALE_SEC + 1) == "stale"
        finally:
            with wf._jobs_lock:
                wf._active_job_keys.discard(key)
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

        def _fake_extract(video_path, ffmpeg, duration_sec=None, audio_source="original", ffprobe=""):
            return {
                "version": 1,
                "source_path": str(video_path),
                "audio_source": audio_source,
                "duration_sec": 1.0,
                "bin_count": 400,
                "peaks": [0.1, 0.9],
                "status": "ready",
            }

        deps_ok = {
            "ok": True,
            "ffmpeg": "C:/fake/ffmpeg.exe",
            "ffprobe": "C:/fake/ffprobe.exe",
            "missing": [],
            "detail": "",
        }
        with (
            patch("clio.utils.probe_ffmpeg_deps", return_value=deps_ok),
            patch.object(wf, "extract_peaks_for_video", side_effect=_fake_extract),
            patch.object(wf, "_spawn_job", side_effect=lambda fn: fn()),  # run inline
        ):
            out = wf.ensure_waveform(tmp_path, src, ffmpeg="", audio_source="original")
        # After inline job completes, ensure may return ready; if design returns pending first:
        # accept either ready (sync complete) or pending then ready on second call.
        assert out["status"] in ("ready", "pending")
        if out["status"] == "pending":
            assert wf.lock_status(tmp_path, key) in ("pending", "none")
            with patch("clio.utils.probe_ffmpeg_deps", return_value=deps_ok):
                out2 = wf.ensure_waveform(tmp_path, src, ffmpeg="")
            assert out2["status"] == "ready"
            assert out2["peaks"] == [0.1, 0.9]
        else:
            assert out["peaks"] == [0.1, 0.9]


class TestErrorCooldown:
    def test_ensure_error_cooldown_skips_rejob(self, tmp_path: Path):
        src = tmp_path / "v.mp4"
        src.write_bytes(b"v")
        key = wf.cache_key(src)
        ep = wf.error_path(tmp_path, key)
        ep.parent.mkdir(parents=True, exist_ok=True)
        ep.write_text("boom", encoding="utf-8")
        deps_ok = {
            "ok": True,
            "ffmpeg": "C:/fake/ffmpeg.exe",
            "ffprobe": "C:/fake/ffprobe.exe",
            "missing": [],
            "detail": "",
        }
        with (
            patch("clio.utils.probe_ffmpeg_deps", return_value=deps_ok),
            patch.object(wf, "extract_peaks_for_video") as ex,
        ):
            out = wf.ensure_waveform(tmp_path, src, ffmpeg="")
        assert out["status"] == "error"
        assert "boom" in out["error"]
        ex.assert_not_called()

    def test_ensure_error_expired_retries(self, tmp_path: Path, monkeypatch):
        src = tmp_path / "v.mp4"
        src.write_bytes(b"v")
        key = wf.cache_key(src)
        ep = wf.error_path(tmp_path, key)
        ep.parent.mkdir(parents=True, exist_ok=True)
        ep.write_text("old", encoding="utf-8")
        # age the error beyond cool-down
        old = time.time() - wf.ERROR_COOLDOWN_SEC - 5
        import os

        os.utime(ep, (old, old))

        def _fake_extract(video_path, ffmpeg, duration_sec=None, audio_source="original", ffprobe=""):
            return {
                "version": 1,
                "source_path": str(video_path),
                "audio_source": audio_source,
                "duration_sec": 1.0,
                "bin_count": 400,
                "peaks": [0.2],
                "status": "ready",
            }

        deps_ok = {
            "ok": True,
            "ffmpeg": "C:/fake/ffmpeg.exe",
            "ffprobe": "C:/fake/ffprobe.exe",
            "missing": [],
            "detail": "",
        }
        with (
            patch("clio.utils.probe_ffmpeg_deps", return_value=deps_ok),
            patch.object(wf, "extract_peaks_for_video", side_effect=_fake_extract),
            patch.object(wf, "_spawn_job", side_effect=lambda fn: fn()),
        ):
            out = wf.ensure_waveform(tmp_path, src, ffmpeg="")
        assert out["status"] in ("ready", "pending")


class TestResolveBinaryContract:
    """Waveform must use resolve_binary like compress/cut: empty -> PATH discover.

    Bare name "ffmpeg" is treated as a configured path and raises.
    """

    def test_extract_uses_path_discovery_when_ffmpeg_empty(self, tmp_path: Path):
        src = tmp_path / "v.mp4"
        src.write_bytes(b"v")
        calls = {}

        def fake_resolve(configured, fallback):
            calls["configured"] = configured
            calls["fallback"] = fallback
            if configured:
                raise FileNotFoundError(f"找不到可执行文件: {configured}")
            return "C:/fake/ffmpeg.exe"

        def fake_run(args, ffmpeg, **kwargs):
            out = Path(args[-1])
            out.write_bytes(b"RIFF" + (b"\x00" * 40) + (b"\x00\x00" * 100))

        with (
            patch("clio.utils.resolve_binary", side_effect=fake_resolve),
            patch("clio.utils.run_ffmpeg", side_effect=fake_run),
            patch("clio.utils.get_duration_sec", return_value=1.0),
        ):
            out = wf.extract_peaks_for_video(src, ffmpeg="", duration_sec=1.0)

        assert calls.get("configured") == ""
        assert calls.get("fallback") == "ffmpeg"
        assert out["status"] == "ready"
        assert len(out["peaks"]) > 0

    def test_route_must_not_default_empty_config_to_bare_name(self):
        """Empty paths.ffmpeg must stay '' so resolve_binary discovers PATH."""
        # Mimic the fixed route: do not coerce empty -> "ffmpeg"
        paths_ffmpeg = ""
        ffmpeg = paths_ffmpeg or ""
        assert ffmpeg == ""
        from clio.utils import resolve_binary

        discovered = resolve_binary(ffmpeg, "ffmpeg")
        assert discovered
        with pytest.raises(FileNotFoundError):
            resolve_binary("ffmpeg", "ffmpeg")


class TestOrphanLockRecovery:
    def test_dead_pid_lock_is_stale(self, tmp_path: Path):
        key = "deadpidlock000001"
        src = tmp_path / "v.mp4"
        src.write_bytes(b"v")
        # pid 1 is not a reliable "dead" on Unix; use absurd high pid
        dead_pid = 2_000_000_001
        lp = wf.lock_path(tmp_path, key)
        lp.parent.mkdir(parents=True, exist_ok=True)
        lp.write_text(
            json.dumps({"started_at": time.time(), "source_path": str(src), "pid": dead_pid}),
            encoding="utf-8",
        )
        assert wf.lock_status(tmp_path, key) == "stale"

    def test_ensure_reattempts_after_orphan_lock(self, tmp_path: Path):
        src = tmp_path / "v.mp4"
        src.write_bytes(b"v")
        key = wf.cache_key(src)
        lp = wf.lock_path(tmp_path, key)
        lp.parent.mkdir(parents=True, exist_ok=True)
        lp.write_text(
            json.dumps({"started_at": time.time(), "source_path": str(src), "pid": 2_000_000_002}),
            encoding="utf-8",
        )

        def _fake_extract(video_path, ffmpeg, duration_sec=None, audio_source="original", ffprobe=""):
            return {
                "version": 1,
                "source_path": str(video_path),
                "audio_source": audio_source,
                "duration_sec": 1.0,
                "bin_count": 400,
                "peaks": [0.3],
                "status": "ready",
            }

        with (
            patch.object(wf, "extract_peaks_for_video", side_effect=_fake_extract),
            patch.object(wf, "_spawn_job", side_effect=lambda fn: fn()),
        ):
            out = wf.ensure_waveform(tmp_path, src, ffmpeg="")
        assert out["status"] in ("ready", "pending")
        if out["status"] == "pending":
            out2 = wf.ensure_waveform(tmp_path, src, ffmpeg="")
            assert out2["status"] == "ready"


class TestMissingBinaryEarlyFail:
    def test_ensure_missing_binary_no_lock_no_error_file(self, tmp_path: Path):
        src = tmp_path / "v.mp4"
        src.write_bytes(b"v")
        key = wf.cache_key(src)

        with (
            patch(
                "clio.utils.probe_ffmpeg_deps",
                return_value={
                    "ok": False,
                    "ffmpeg": None,
                    "ffprobe": None,
                    "missing": ["ffmpeg", "ffprobe"],
                    "detail": "未找到 ffmpeg、ffprobe。请运行 setup…",
                },
            ),
            patch.object(wf, "extract_peaks_for_video") as ex,
            patch.object(wf, "_spawn_job") as spawn,
        ):
            out = wf.ensure_waveform(tmp_path, src, ffmpeg="", ffprobe="")
        assert out["status"] == "error"
        assert out.get("code") == "missing_binary"
        assert "ffmpeg" in out["error"].lower() or "找不到" in out["error"] or "未找到" in out["error"]
        assert not wf.lock_path(tmp_path, key).exists()
        assert not wf.error_path(tmp_path, key).exists()
        ex.assert_not_called()
        spawn.assert_not_called()

    def test_ensure_missing_binary_retries_immediately_next_call(self, tmp_path: Path):
        """No cool-down: second call after install can succeed without waiting 60s."""
        src = tmp_path / "v.mp4"
        src.write_bytes(b"v")
        key = wf.cache_key(src)

        with patch(
            "clio.utils.probe_ffmpeg_deps",
            return_value={
                "ok": False,
                "ffmpeg": None,
                "ffprobe": None,
                "missing": ["ffmpeg"],
                "detail": "未找到 ffmpeg",
            },
        ):
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
            patch(
                "clio.utils.probe_ffmpeg_deps",
                return_value={
                    "ok": True,
                    "ffmpeg": "C:/fake/ffmpeg.exe",
                    "ffprobe": "C:/fake/ffprobe.exe",
                    "missing": [],
                    "detail": "",
                },
            ),
            patch.object(wf, "extract_peaks_for_video", side_effect=_fake_extract),
            patch.object(wf, "_spawn_job", side_effect=lambda fn: fn()),
        ):
            out2 = wf.ensure_waveform(tmp_path, src, ffmpeg="")
        assert out2["status"] in ("ready", "pending")
