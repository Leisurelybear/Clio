"""Tests for clio/analyze_windows.py."""

from __future__ import annotations

from pathlib import Path

from clio.analyze_windows import (
    AnalyzeWindow,
    build_analyze_windows,
    cleanup_analyze_windows_dir,
    merge_window_analyses,
    shift_analysis_times,
    slice_window_video,
)


class TestBuildAnalyzeWindows:
    def test_single_when_short(self):
        ws = build_analyze_windows(600, window_max_min=15, overlap_sec=20)
        assert len(ws) == 1
        assert ws[0].start_sec == 0
        assert ws[0].end_sec == 600

    def test_multi_with_overlap(self):
        ws = build_analyze_windows(2400, window_max_min=15, overlap_sec=20)
        assert len(ws) >= 3
        assert ws[0].start_sec == 0
        assert ws[0].end_sec == 900
        assert ws[1].start_sec == 900 - 20
        assert ws[-1].end_sec == 2400
        for a, b in zip(ws, ws[1:]):
            assert b.start_sec < a.end_sec


class TestShiftAndMerge:
    def test_shift_timeline_numeric(self):
        raw = {"title": "t", "summary": "s", "timeline": [{"start": 10, "end": 20, "text": "a"}]}
        out = shift_analysis_times(raw, 100)
        assert out["timeline"][0]["start"] == 110
        assert out["timeline"][0]["end"] == 120
        assert raw["timeline"][0]["start"] == 10

    def test_merge_prefers_title_window0_and_sorts_timeline(self):
        w0 = AnalyzeWindow(0, 0, 900)
        w1 = AnalyzeWindow(1, 880, 1800)
        a0 = {
            "title": "A",
            "summary": "s0",
            "timeline": [{"start": 10, "end": 20, "text": "early"}],
            "highlights": ["h1"],
            "location": "X",
        }
        a1 = {
            "title": "B",
            "summary": "s1",
            "timeline": [{"start": 900, "end": 910, "text": "late"}],
            "highlights": ["h1", "h2"],
            "location": "Y",
        }
        merged = merge_window_analyses([(w0, a0), (w1, a1)], overlap_sec=20)
        assert merged["title"] == "A"
        assert "s0" in merged["summary"] and "s1" in merged["summary"]
        assert len(merged["timeline"]) == 2
        assert merged["timeline"][0]["start"] <= merged["timeline"][1]["start"]
        assert set(merged["highlights"]) == {"h1", "h2"}
        assert len(merged["analyze_windows"]) == 2

    def test_merge_dedupes_overlap_near_duplicates(self):
        w0 = AnalyzeWindow(0, 0, 900)
        w1 = AnalyzeWindow(1, 880, 1800)
        a0 = {
            "title": "A",
            "summary": "s0",
            "timeline": [{"start": 890, "end": 900, "text": "dup"}],
        }
        a1 = {
            "title": "B",
            "summary": "s1",
            "timeline": [{"start": 892, "end": 902, "text": "dup"}],
        }
        merged = merge_window_analyses([(w0, a0), (w1, a1)], overlap_sec=20)
        assert sum(1 for t in merged["timeline"] if t.get("text") == "dup") == 1


class TestSliceWindowVideo:
    def test_slice_window_video_invokes_ffmpeg(self, tmp_path: Path):
        src = tmp_path / "001_GL.mp4"
        src.write_bytes(b"\x00" * 10)
        dest = tmp_path / ".analyze_windows"
        calls = []

        def fake_run(args, ffmpeg, **kw):
            calls.append(args)
            Path(args[-1]).write_bytes(b"x")

        out = slice_window_video(
            source=src,
            window=AnalyzeWindow(0, 0, 60),
            dest_dir=dest,
            ffmpeg="ffmpeg",
            run_ffmpeg=fake_run,
        )
        assert out.is_file()
        assert "w00" in out.name
        assert "-ss" in calls[0]

    def test_cleanup_removes_window_files(self, tmp_path: Path):
        dest = tmp_path / ".analyze_windows"
        dest.mkdir()
        f = dest / "001_GL_w00_0-60.mp4"
        f.write_bytes(b"x")
        other = dest / "keep.txt"
        other.write_text("y", encoding="utf-8")
        cleanup_analyze_windows_dir(dest)
        assert not f.exists()
        assert other.exists()
