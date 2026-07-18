"""Tests for clio/tasks/waveform.py — peaks cache, lock, binning."""

from __future__ import annotations

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


class TestErrorCooldown:
    def test_ensure_error_cooldown_skips_rejob(self, tmp_path: Path):
        src = tmp_path / "v.mp4"
        src.write_bytes(b"v")
        key = wf.cache_key(src)
        ep = wf.error_path(tmp_path, key)
        ep.parent.mkdir(parents=True, exist_ok=True)
        ep.write_text("boom", encoding="utf-8")
        with patch.object(wf, "extract_peaks_for_video") as ex:
            out = wf.ensure_waveform(tmp_path, src, ffmpeg="ffmpeg")
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

        with (
            patch.object(wf, "extract_peaks_for_video", side_effect=_fake_extract),
            patch.object(wf, "_spawn_job", side_effect=lambda fn: fn()),
        ):
            out = wf.ensure_waveform(tmp_path, src, ffmpeg="ffmpeg")
        assert out["status"] in ("ready", "pending")
