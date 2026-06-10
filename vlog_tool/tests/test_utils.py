"""Tests for vlog_tool/utils.py — pure utility functions."""
from __future__ import annotations

from pathlib import Path

import pytest

from vlog_tool.utils import (
    extract_json,
    find_videos,
    format_index,
    mask_if_looks_like_key,
    sanitize_name,
)


# ── extract_json ────────────────────────────────────────────────────

class TestExtractJson:
    def test_plain_json_object(self):
        assert extract_json('{"a": 1}') == {"a": 1}

    def test_json_with_surrounding_text(self):
        text = "Some prefix\n```json\n{\"a\": 1}\n```\nsuffix"
        assert extract_json(text) == {"a": 1}

    def test_nested_json(self):
        text = '{"a": {"b": [1, 2, 3]}}'
        assert extract_json(text) == {"a": {"b": [1, 2, 3]}}

    def test_empty_object(self):
        assert extract_json("{}") == {}

    def test_json_with_unicode(self):
        assert extract_json('{"name": "巴黎"}') == {"name": "巴黎"}

    def test_raises_on_invalid_input(self):
        with pytest.raises(ValueError):
            extract_json("not json at all no braces")

    def test_raises_on_empty_text(self):
        with pytest.raises(ValueError):
            extract_json("")

    def test_brace_in_string_extracted_correctly(self):
        text = '{"key": "value with { inside"}'
        assert extract_json(text) == {"key": "value with { inside"}


# ── mask_if_looks_like_key ──────────────────────────────────────────

class TestMaskIfLooksLikeKey:
    def test_empty_string(self):
        assert mask_if_looks_like_key("") == ""

    def test_sk_short(self):
        assert mask_if_looks_like_key("sk-") == "sk-"

    def test_sk_long(self):
        result = mask_if_looks_like_key("sk-abc123def456")
        assert result == "sk-a***f456"  # first 4 + *** + last 4
        assert len(result) < 20

    def test_aiza_key(self):
        result = mask_if_looks_like_key("AIzaSyFakeKeyForTestPurposesOnly123")
        assert result == "AIza***y123"  # first 4 + *** + last 4

    def test_ghp_token(self):
        result = mask_if_looks_like_key("ghp_xxxxxxxxxxxxxxxxxxxx")
        assert result.startswith("ghp_")
        assert "***" in result

    def test_long_string_without_prefix(self):
        result = mask_if_looks_like_key("a" * 40)
        assert result == f"{'a'*6}***{'a'*4}"

    def test_short_string_without_prefix(self):
        assert mask_if_looks_like_key("hello") == "hello"

    def test_short_string_with_spaces(self):
        assert mask_if_looks_like_key("a normal sentence without key patterns") == "a normal sentence without key patterns"


# ── sanitize_name ───────────────────────────────────────────────────

class TestSanitizeName:
    def test_removes_special_chars(self):
        assert sanitize_name('file:name test') == "filename_test"

    def test_replaces_whitespace(self):
        assert sanitize_name("my clip name") == "my_clip_name"

    def test_truncates_long(self):
        long_name = "a" * 100
        assert len(sanitize_name(long_name)) == 40

    def test_empty_fallback(self):
        assert sanitize_name("") == "clip"

    def test_trim_whitespace(self):
        result = sanitize_name("  hello  ")
        assert result == "hello"
        assert "_" not in result  # single word, no inner spaces after strip

    def test_chinese_chars_preserved(self):
        assert sanitize_name("巴黎铁塔") == "巴黎铁塔"


# ── format_index ────────────────────────────────────────────────────

class TestFormatIndex:
    def test_basic(self):
        assert format_index(1, 3) == "001"

    def test_width_2(self):
        assert format_index(5, 2) == "05"

    def test_large_index(self):
        assert format_index(100, 3) == "100"

    def test_width_4(self):
        assert format_index(42, 4) == "0042"


# ── find_videos ─────────────────────────────────────────────────────

class TestFindVideos:
    def test_empty_directory(self, tmp_path):
        assert find_videos(tmp_path) == []

    def test_finds_mp4_files(self, tmp_path):
        (tmp_path / "clip1.mp4").write_text("fake video")
        (tmp_path / "clip2.mp4").write_text("fake video")
        result = find_videos(tmp_path)
        assert len(result) == 2
        assert all(p.suffix == ".mp4" for p in result)

    def test_ignores_non_video_files(self, tmp_path):
        (tmp_path / "notes.txt").write_text("text")
        (tmp_path / "image.jpg").write_text("image")
        assert find_videos(tmp_path) == []

    def test_recursive_finds_nested(self, tmp_path):
        sub = tmp_path / "subdir"
        sub.mkdir()
        (tmp_path / "root.mp4").write_text("fake")
        (sub / "nested.mov").write_text("fake")
        result = find_videos(tmp_path, recursive=True)
        assert len(result) == 2

    def test_non_recursive_ignores_nested(self, tmp_path):
        sub = tmp_path / "subdir"
        sub.mkdir()
        (sub / "nested.mp4").write_text("fake")
        assert find_videos(tmp_path, recursive=False) == []

    def test_nonexistent_directory_raises(self):
        with pytest.raises(NotADirectoryError):
            find_videos(Path("/nonexistent/path"))

    def test_case_insensitive_extensions(self, tmp_path):
        (tmp_path / "clip.MP4").write_text("fake")
        (tmp_path / "clip.MOV").write_text("fake")
        assert len(find_videos(tmp_path)) == 2

    def test_multiple_extensions(self, tmp_path):
        for ext in [".mp4", ".mov", ".avi", ".mkv"]:
            (tmp_path / f"file{ext}").write_text("fake")
        assert len(find_videos(tmp_path)) == 4
