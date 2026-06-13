"""Tests for vlog_tool/tasks/_helpers.py and related pure logic."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from vlog_tool.tasks._helpers import (
    ClipRecord,
    _build_stem,
    _eta_line,
    _next_index,
    _rewrite_script_md,
    _rewrite_text_file,
    _write_csv,
    _write_text_file,
)


def _fake_config(index_width: int = 3) -> SimpleNamespace:
    return SimpleNamespace(
        naming=SimpleNamespace(index_width=index_width),
        paths=SimpleNamespace(ffprobe=""),
    )


class TestNextIndex:
    def test_nonexistent_dir_returns_one(self):
        assert _next_index(Path("/nonexistent")) == 1

    def test_empty_dir_returns_one(self, tmp_path: Path):
        assert _next_index(tmp_path) == 1

    def test_finds_max_index(self, tmp_path: Path):
        (tmp_path / "001_foo.mp4").write_bytes(b"")
        (tmp_path / "003_bar.mp4").write_bytes(b"")
        (tmp_path / "002_baz.mp4").write_bytes(b"")
        assert _next_index(tmp_path) == 4

    def test_ignores_no_underscore(self, tmp_path: Path):
        (tmp_path / "foo.mp4").write_bytes(b"")
        assert _next_index(tmp_path) == 1

    def test_ignores_non_digit_prefix(self, tmp_path: Path):
        (tmp_path / "abc_foo.mp4").write_bytes(b"")
        assert _next_index(tmp_path) == 1

    def test_mixed_valid_and_invalid(self, tmp_path: Path):
        (tmp_path / "001_foo.mp4").write_bytes(b"")
        (tmp_path / "bar.mp4").write_bytes(b"")
        (tmp_path / "abc_baz.mp4").write_bytes(b"")
        assert _next_index(tmp_path) == 2

    def test_large_index(self, tmp_path: Path):
        (tmp_path / "999_foo.mp4").write_bytes(b"")
        assert _next_index(tmp_path) == 1000

    def test_custom_width(self, tmp_path: Path):
        (tmp_path / "0001_foo.mp4").write_bytes(b"")
        (tmp_path / "0003_bar.mp4").write_bytes(b"")
        assert _next_index(tmp_path, 4) == 4


class TestBuildStem:
    def test_basic(self):
        result = _build_stem(1, "Hello World", _fake_config())
        assert result == "001_Hello_World"

    def test_sanitizes_title(self):
        result = _build_stem(42, "Great: View!", _fake_config())
        assert result == "042_Great_View!"


class TestEtaLine:
    def test_first_item_no_eta(self):
        line = _eta_line("分析", 1, 5, "test.mp4", 0, 0.0)
        assert line == "[分析 1/5] test.mp4"

    def test_with_eta(self):
        line = _eta_line("压缩", 3, 10, "vid.mp4", 2, 10.0)
        assert "剩余" in line
        assert "平均" in line
        assert "[压缩 3/10]" in line


class TestWriteTextFile:
    def test_writes_basic_structure(self, tmp_path: Path):
        out = tmp_path / "001_test.txt"
        analysis = {
            "title": "My Video",
            "summary": "A nice clip",
            "location": "Paris",
            "mood": "happy",
            "suggested_use": "opening",
            "timeline": [{"start": "0:00", "end": "1:30", "description": "intro"}],
            "highlights": ["great shot"],
        }
        _write_text_file(out, analysis, tmp_path / "source.mp4", tmp_path / "compressed.mp4")
        text = out.read_text(encoding="utf-8")
        assert "My Video" in text
        assert "A nice clip" in text
        assert "Paris" in text
        assert "0:00 - 1:30" in text
        assert "great shot" in text

    def test_empty_analysis(self, tmp_path: Path):
        out = tmp_path / "001_test.txt"
        _write_text_file(out, {}, tmp_path / "source.mp4", tmp_path / "compressed.mp4")
        text = out.read_text(encoding="utf-8")
        assert "未命名" in text


class TestRewriteTextFile:
    def test_rewrites_without_changelog(self, tmp_path: Path):
        out = tmp_path / "001_test.txt"
        analysis = {"title": "Updated", "summary": "New summary", "location": "Tokyo", "mood": "calm", "suggested_use": "b-roll", "source_file": "source.mp4"}
        _rewrite_text_file(out, analysis)
        text = out.read_text(encoding="utf-8")
        assert "Updated" in text
        assert "New summary" in text

    def test_rewrites_with_changelog(self, tmp_path: Path):
        out = tmp_path / "001_test.txt"
        analysis = {"title": "Fixed", "summary": "x", "location": "?",
                     "mood": "", "suggested_use": "", "source_file": "s.mp4",
                     "_changelog": ["fixed typo", "updated title"]}
        _rewrite_text_file(out, analysis)
        text = out.read_text(encoding="utf-8")
        assert "本次 refine 改动" in text
        assert "fixed typo" in text
        assert "updated title" in text


class TestRewriteScriptMd:
    def test_basic_rewrite(self, tmp_path: Path):
        out = tmp_path / "001_test.md"
        script = {"title": "Script Title", "voiceover": "Hello world", "edit_tip": "cut at 1:00"}
        _rewrite_script_md(out, script)
        text = out.read_text(encoding="utf-8")
        assert "Script Title" in text
        assert "Hello world" in text
        assert "cut at 1:00" in text

    def test_rewrite_with_changelog(self, tmp_path: Path):
        out = tmp_path / "001_test.md"
        script = {"title": "Fixed", "voiceover": "Hello", "edit_tip": "tip",
                   "_changelog": ["corrected date"]}
        _rewrite_script_md(out, script)
        text = out.read_text(encoding="utf-8")
        assert "本次 refine 改动" in text
        assert "corrected date" in text


class TestWriteCsv:
    def test_writes_csv_with_records(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("vlog_tool.tasks._helpers.probe_video_info",
                            lambda *a, **kw: {"duration_sec": 120, "size_mb": 50.0})
        out = tmp_path / "summary.csv"
        src = tmp_path / "s.mp4"
        src.write_bytes(b"x")
        records = [
            ClipRecord(index=1, stem="001_test", source_path=src,
                       compressed_path=tmp_path / "c.mp4", text_path=tmp_path / "t.txt",
                       analysis={"title": "Test", "summary": "A vid", "location": "Paris"}),
        ]
        _write_csv(out, records, _fake_config())
        assert out.exists()
        text = out.read_text(encoding="utf-8-sig")
        assert "001" in text
        assert "Test" in text
        assert "Paris" in text

    def test_empty_records(self, tmp_path: Path):
        out = tmp_path / "empty.csv"
        _write_csv(out, [], _fake_config())
        assert out.exists()
        assert out.read_text(encoding="utf-8-sig").strip() != ""
