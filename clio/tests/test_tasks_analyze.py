"""Tests for clio/tasks/analyze.py — run_analyze_all."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from clio.tasks.analyze import run_analyze_all


def _cfg(tmp_path: Path) -> SimpleNamespace:
    cfg = SimpleNamespace(
        paths=SimpleNamespace(
            output_dir=tmp_path / "output",
            ffmpeg="ffmpeg",
            ffprobe="ffprobe",
        ),
        compressed_dir=tmp_path / "output" / "compressed",
        texts_dir=tmp_path / "output" / "texts",
        summary_csv=tmp_path / "output" / "summary.csv",
        naming=SimpleNamespace(index_width=3),
        analyze=SimpleNamespace(
            skip_existing=False,
            max_analyze_duration_min=30,
            window_max_min=15,
            window_overlap_sec=20,
            max_workers=1,
        ),
        ai=SimpleNamespace(context=""),
        compress=SimpleNamespace(split_max_min=0, splits_subdir="splits"),
        plan=SimpleNamespace(max_clips_per_day=10, target_duration_sec=300),
        script=SimpleNamespace(target_words=150),
        project_dir=tmp_path / "project",
    )
    Path(cfg.project_dir).mkdir(parents=True, exist_ok=True)
    cfg.compressed_dir.mkdir(parents=True, exist_ok=True)
    cfg.texts_dir.mkdir(parents=True, exist_ok=True)
    return cfg


def _add_original(cfg, name: str = "GL010695.mp4"):
    from clio.tasks._video_loader import load_selected_videos, save_selected_videos

    Path(cfg.project_dir).mkdir(parents=True, exist_ok=True)
    src = Path(cfg.project_dir) / name
    src.write_bytes(b"\x00" * 1000)
    existing = load_selected_videos(cfg.project_dir)
    if src.resolve() not in {p.resolve() for p in existing}:
        existing.append(src)
    save_selected_videos(cfg.project_dir, existing)
    return src


def _common_mocks(monkeypatch):
    """Shared mocks for analyz tests — resolve_binary, probe_video_info."""
    # _write_csv (in _helpers.py) calls resolve_binary + probe_video_info
    monkeypatch.setattr("clio.tasks._helpers.resolve_binary", lambda *a: "ffprobe")
    monkeypatch.setattr("clio.tasks._helpers.probe_video_info", lambda *a, **kw: {})
    # run_analyze_all (in analyze.py) also calls resolve_binary for duration gate
    monkeypatch.setattr("clio.tasks.analyze.resolve_binary", lambda *a: "ffprobe")
    # Prevent AI calls
    monkeypatch.setattr("clio.tasks.analyze._build_stem", lambda idx, title, cfg: f"{idx:03d}_{title}")
    monkeypatch.setattr("clio.tasks.analyze._write_text_file", lambda *a: None)


class TestRunAnalyzeAll:
    def test_analyze_single_file(self, monkeypatch, tmp_path: Path):
        cfg = _cfg(tmp_path)
        _add_original(cfg, "GL010695.mp4")
        comp = cfg.compressed_dir / "001_GL010695.mp4"
        comp.write_bytes(b"\x00" * 100)

        _common_mocks(monkeypatch)
        monkeypatch.setattr("clio.tasks.analyze.get_duration_sec", lambda *a: 60.0)
        monkeypatch.setattr(
            "clio.tasks.analyze.analyze_video",
            lambda *a, **kw: {
                "title": "Test Clip",
                "summary": "A test",
                "location": "Paris",
                "source_file": "GL010695.mp4",
            },
        )

        records = run_analyze_all(cfg)
        assert len(records) == 1
        assert records[0].index == 1

    def test_skip_existing(self, monkeypatch, tmp_path: Path):
        cfg = _cfg(tmp_path)
        _add_original(cfg, "GL010695.mp4")
        comp = cfg.compressed_dir / "001_GL010695.mp4"
        comp.write_bytes(b"\x00" * 100)
        existing_json = cfg.texts_dir / "001_Test_Clip.json"
        existing_json.write_text(
            json.dumps({"title": "Test Clip", "summary": "A test", "source_file": "GL010695.mp4"}), encoding="utf-8"
        )

        _common_mocks(monkeypatch)
        analyze_called = False

        def _analyze(*a):
            nonlocal analyze_called
            analyze_called = True
            return {"title": "New"}

        monkeypatch.setattr("clio.tasks.analyze.analyze_video", _analyze)

        cfg.analyze.skip_existing = True
        records = run_analyze_all(cfg)
        assert len(records) == 1
        assert analyze_called is False

    def test_duration_gate_skips_long_video(self, monkeypatch, tmp_path: Path):
        cfg = _cfg(tmp_path)
        _add_original(cfg, "GL010695.mp4")
        comp = cfg.compressed_dir / "001_GL010695.mp4"
        comp.write_bytes(b"\x00" * 100)

        _common_mocks(monkeypatch)
        monkeypatch.setattr("clio.tasks.analyze.get_duration_sec", lambda *a: 3600.0)
        analyze_called = False

        def _analyze(*a):
            nonlocal analyze_called
            analyze_called = True
            return {"title": "Should not be called"}

        monkeypatch.setattr("clio.tasks.analyze.analyze_video", _analyze)

        cfg.analyze.max_analyze_duration_min = 30
        records = run_analyze_all(cfg)
        assert len(records) == 0
        assert analyze_called is False

    def test_duration_gate_allows_short_video(self, monkeypatch, tmp_path: Path):
        cfg = _cfg(tmp_path)
        _add_original(cfg, "GL010695.mp4")
        comp = cfg.compressed_dir / "001_GL010695.mp4"
        comp.write_bytes(b"\x00" * 100)

        _common_mocks(monkeypatch)
        monkeypatch.setattr("clio.tasks.analyze.get_duration_sec", lambda *a: 60.0)
        monkeypatch.setattr(
            "clio.tasks.analyze.analyze_video",
            lambda *a, **kw: {"title": "Short Clip", "summary": "A short test", "location": "Paris"},
        )

        cfg.analyze.max_analyze_duration_min = 30
        records = run_analyze_all(cfg)
        assert len(records) == 1
        assert records[0].index == 1

    def test_no_matching_original(self, monkeypatch, tmp_path: Path):
        cfg = _cfg(tmp_path)
        comp = cfg.compressed_dir / "001_NOMATCH.mp4"
        comp.write_bytes(b"\x00" * 100)

        _common_mocks(monkeypatch)
        analyze_called = False

        def _analyze(*a):
            nonlocal analyze_called
            analyze_called = True
            return {"title": "x"}

        monkeypatch.setattr("clio.tasks.analyze.analyze_video", _analyze)

        records = run_analyze_all(cfg)
        assert len(records) == 0
        assert analyze_called is False

    def test_empty_compressed_dir(self, monkeypatch, tmp_path: Path):
        cfg = _cfg(tmp_path)
        _common_mocks(monkeypatch)
        records = run_analyze_all(cfg)
        assert len(records) == 0

    def test_files_filter(self, monkeypatch, tmp_path: Path):
        cfg = _cfg(tmp_path)
        pairs = [("GL010683", "001_GL010683"), ("GL010684", "002_GL010684"), ("GL010685", "003_GL010685")]
        for orig_stem, comp_stem in pairs:
            _add_original(cfg, f"{orig_stem}.mp4")
            (cfg.compressed_dir / f"{comp_stem}.mp4").write_bytes(b"\x00" * 100)
        _common_mocks(monkeypatch)
        monkeypatch.setattr("clio.tasks.analyze.get_duration_sec", lambda *a: 60.0)
        monkeypatch.setattr(
            "clio.tasks.analyze.analyze_video",
            lambda *a, **kw: {"title": "x", "summary": "x", "location": "x"},
        )

        records = run_analyze_all(cfg, files=["002_GL010684"])
        assert len(records) == 1
        assert records[0].compressed_path.name == "002_GL010684.mp4"

    def test_single_file_with_vindex_includes_all_segments(self, monkeypatch, tmp_path: Path):
        cfg = _cfg(tmp_path)
        src = _add_original(cfg, "GL010695.mp4")
        comp1 = cfg.compressed_dir / "001_GL010695_seg01.mp4"
        comp1.write_bytes(b"\x00" * 100)
        comp2 = cfg.compressed_dir / "002_GL010695_seg02.mp4"
        comp2.write_bytes(b"\x00" * 100)

        from clio.vmeta import SegmentEntry, VideoIndex

        segs = [
            SegmentEntry(
                index="001",
                filename="001_GL010695_seg01.mp4",
                offset_sec=0.0,
                duration_sec=30.0,
                segment_number=1,
                total_segments=2,
            ),
            SegmentEntry(
                index="002",
                filename="002_GL010695_seg02.mp4",
                offset_sec=30.0,
                duration_sec=30.0,
                segment_number=2,
                total_segments=2,
            ),
        ]
        vindex = VideoIndex.build(source=src, source_duration=60.0, segments=segs)
        vindex.write(cfg.compressed_dir)

        _common_mocks(monkeypatch)
        monkeypatch.setattr("clio.tasks.analyze.get_duration_sec", lambda *a: 30.0)
        monkeypatch.setattr(
            "clio.tasks.analyze.analyze_video",
            lambda *a, **kw: {"title": "Seg", "summary": "x", "location": "x", "source_file": "GL010695.mp4"},
        )

        records = run_analyze_all(cfg, single_file=src)
        assert len(records) == 2
        assert records[0].compressed_path.name == "001_GL010695_seg01.mp4"
        assert records[1].compressed_path.name == "002_GL010695_seg02.mp4"

    def test_overwrite_flag(self, monkeypatch, tmp_path: Path):
        cfg = _cfg(tmp_path)
        _add_original(cfg, "GL010695.mp4")
        comp = cfg.compressed_dir / "001_GL010695.mp4"
        comp.write_bytes(b"\x00" * 100)
        existing = cfg.texts_dir / "001_Test.json"
        existing.write_text(
            json.dumps({"title": "x", "summary": "x", "location": "x", "source_file": "GL010695.mp4"}),
            encoding="utf-8",
        )
        _common_mocks(monkeypatch)
        monkeypatch.setattr("clio.tasks.analyze.get_duration_sec", lambda *a: 60.0)
        analyze_called = False

        def _analyze(*a, **kw):
            nonlocal analyze_called
            analyze_called = True
            return {"title": "overwritten"}

        monkeypatch.setattr("clio.tasks.analyze.analyze_video", _analyze)

        cfg.analyze.skip_existing = True
        records = run_analyze_all(cfg, overwrite=True)
        assert len(records) == 1
        assert analyze_called is True

    def test_multi_window_merges_and_writes_one_json(self, monkeypatch, tmp_path: Path):
        cfg = _cfg(tmp_path)
        cfg.analyze.max_analyze_duration_min = 0
        cfg.analyze.window_max_min = 15
        cfg.analyze.window_overlap_sec = 20
        _add_original(cfg, "GL010695.mp4")
        comp = cfg.compressed_dir / "001_GL010695.mp4"
        comp.write_bytes(b"\x00" * 100)

        _common_mocks(monkeypatch)
        monkeypatch.setattr("clio.tasks.analyze.get_duration_sec", lambda *a: 2400.0)
        monkeypatch.setattr("clio.tasks.analyze.is_legacy_split_path", lambda p: False)

        def fake_slice(*, source, window, dest_dir, ffmpeg, run_ffmpeg=None, cancel_event=None):
            dest_dir.mkdir(parents=True, exist_ok=True)
            out = dest_dir / f"{source.stem}_w{window.index:02d}.mp4"
            out.write_bytes(b"x")
            return out

        monkeypatch.setattr("clio.tasks.analyze.slice_window_video", fake_slice)

        call_paths: list[str] = []

        def _analyze(path, *a, **kw):
            call_paths.append(str(path))
            return {
                "title": f"W{len(call_paths)}",
                "summary": f"sum{len(call_paths)}",
                "timeline": [{"start": 5, "end": 10, "text": f"e{len(call_paths)}"}],
                "location": "X",
            }

        monkeypatch.setattr("clio.tasks.analyze.analyze_video", _analyze)

        records = run_analyze_all(cfg)
        assert len(records) == 1
        assert len(call_paths) >= 3
        assert records[0].analysis is not None
        assert records[0].analysis["title"] == "W1"
        assert len(records[0].analysis.get("analyze_windows", [])) >= 3
        texts = list(cfg.texts_dir.glob("*.json"))
        assert len(texts) == 1
        data = json.loads(texts[0].read_text(encoding="utf-8"))
        assert data["timeline"][0]["start"] == 5
        assert any(t["start"] >= 880 for t in data["timeline"])

    def test_window_failure_writes_nothing(self, monkeypatch, tmp_path: Path):
        cfg = _cfg(tmp_path)
        cfg.analyze.max_analyze_duration_min = 0
        cfg.analyze.window_max_min = 15
        cfg.analyze.window_overlap_sec = 20
        _add_original(cfg, "GL010695.mp4")
        comp = cfg.compressed_dir / "001_GL010695.mp4"
        comp.write_bytes(b"\x00" * 100)

        _common_mocks(monkeypatch)
        monkeypatch.setattr("clio.tasks.analyze.get_duration_sec", lambda *a: 2400.0)
        monkeypatch.setattr("clio.tasks.analyze.is_legacy_split_path", lambda p: False)

        def fake_slice(*, source, window, dest_dir, ffmpeg, run_ffmpeg=None, cancel_event=None):
            dest_dir.mkdir(parents=True, exist_ok=True)
            out = dest_dir / f"{source.stem}_w{window.index:02d}.mp4"
            out.write_bytes(b"x")
            return out

        monkeypatch.setattr("clio.tasks.analyze.slice_window_video", fake_slice)

        n = 0

        def _analyze(path, *a, **kw):
            nonlocal n
            n += 1
            if n >= 2:
                raise RuntimeError("boom")
            return {"title": "ok", "summary": "s", "timeline": [], "location": "X"}

        monkeypatch.setattr("clio.tasks.analyze.analyze_video", _analyze)

        import pytest

        with pytest.raises(RuntimeError, match="失败"):
            run_analyze_all(cfg)
        assert list(cfg.texts_dir.glob("*.json")) == []
