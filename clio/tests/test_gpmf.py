"""Tests for clio/gpmf.py — GoPro GPMF telemetry summary (R-024 MVP)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from clio.gpmf import (
    TelemetrySummary,
    format_telemetry_for_prompt,
    load_telemetry_summary,
    probe_gpmf_marker,
    summarize_from_sidecar,
)


class TestSummarizeFromSidecar:
    def test_parses_speed_peaks_and_elev(self, tmp_path: Path):
        sidecar = tmp_path / "GL010695.gpmf.json"
        sidecar.write_text(
            json.dumps(
                {
                    "duration_sec": 120.0,
                    "speed": [
                        {"t_sec": 12.5, "value": 48.2, "unit": "km/h"},
                        {"t_sec": 63.0, "value": 52.1, "unit": "km/h"},
                        {"t_sec": 20.0, "value": 10.0, "unit": "km/h"},
                    ],
                    "elevation_m": [100.0, 150.0, 220.0],
                }
            ),
            encoding="utf-8",
        )
        summary = summarize_from_sidecar(sidecar)
        assert summary.has_gpmf is True
        assert summary.source == "sidecar"
        assert summary.duration_sec == 120.0
        assert len(summary.speed_peaks) == 2  # top peaks only
        assert summary.speed_peaks[0]["t_sec"] == 63.0
        assert summary.elev_delta_m == pytest.approx(120.0)

    def test_missing_sidecar_returns_empty(self, tmp_path: Path):
        summary = summarize_from_sidecar(tmp_path / "nope.gpmf.json")
        assert summary.has_gpmf is False
        assert summary.source == "none"
        assert summary.speed_peaks == []


class TestProbeGpmfMarker:
    def test_detects_gpmf_ascii_marker(self, tmp_path: Path):
        p = tmp_path / "clip.mp4"
        # Minimal fake: header + GPMF fourcc somewhere in the first 256KB
        p.write_bytes(b"\x00" * 100 + b"GPMF" + b"\x00" * 50)
        assert probe_gpmf_marker(p) is True

    def test_false_on_non_gpmf_file(self, tmp_path: Path):
        p = tmp_path / "plain.mp4"
        p.write_bytes(b"ftypisom" + b"\x00" * 200)
        assert probe_gpmf_marker(p) is False

    def test_false_on_missing_file(self, tmp_path: Path):
        assert probe_gpmf_marker(tmp_path / "missing.mp4") is False


class TestLoadTelemetrySummary:
    def test_prefers_sidecar_over_probe(self, tmp_path: Path):
        video = tmp_path / "GL.MP4"
        video.write_bytes(b"GPMF" + b"\x00" * 20)
        sidecar = tmp_path / "GL.gpmf.json"
        sidecar.write_text(
            json.dumps({"speed": [{"t_sec": 1.0, "value": 30, "unit": "km/h"}]}),
            encoding="utf-8",
        )
        s = load_telemetry_summary(video)
        assert s.source == "sidecar"
        assert s.has_gpmf is True

    def test_probe_only_when_no_sidecar(self, tmp_path: Path):
        video = tmp_path / "GL.MP4"
        video.write_bytes(b"xxxxGPMFyyyy")
        s = load_telemetry_summary(video)
        assert s.has_gpmf is True
        assert s.source == "probe"
        assert s.notes  # explain limited detail

    def test_no_gps_phone_clip_is_silent_empty(self, tmp_path: Path):
        """Most non-GoPro / no-GPS clips: no marker, no sidecar → empty, no error."""
        phone = tmp_path / "IMG_1234.MOV"
        phone.write_bytes(b"ftypqt  " + b"\x00" * 200)
        s = load_telemetry_summary(phone)
        assert s.has_gpmf is False
        assert s.source == "none"
        assert format_telemetry_for_prompt(s) == ""

    def test_none_path_is_safe(self):
        s = load_telemetry_summary(None)  # type: ignore[arg-type]
        assert s.has_gpmf is False
        assert format_telemetry_for_prompt(s) == ""


class TestFormatTelemetryForPrompt:
    def test_empty_when_no_gpmf(self):
        assert format_telemetry_for_prompt(TelemetrySummary(has_gpmf=False, source="none")) == ""

    def test_empty_when_summary_is_none(self):
        assert format_telemetry_for_prompt(None) == ""

    def test_includes_peak_timecodes(self):
        s = TelemetrySummary(
            has_gpmf=True,
            source="sidecar",
            duration_sec=90.0,
            sample_count=100,
            speed_peaks=[
                {"t_sec": 12.5, "value": 48.2, "unit": "km/h"},
                {"t_sec": 63.0, "value": 52.1, "unit": "km/h"},
            ],
            elev_delta_m=120.0,
            notes=[],
        )
        text = format_telemetry_for_prompt(s)
        assert "运动遥测" in text or "GPMF" in text
        assert "00:12" in text
        assert "01:03" in text
        assert "120" in text
