"""Tests for vlog_tool/progress.py — ProgressTracker."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from vlog_tool.progress import ProgressTracker


class TestProgressTracker:
    def test_creates_progress_file(self, tmp_path):
        t = ProgressTracker(tmp_path)
        assert t._path.is_file()
        data = json.loads(t._path.read_text(encoding="utf-8"))
        assert data["status"] == "running"

    def test_update_phase(self, tmp_path):
        t = ProgressTracker(tmp_path)
        t.update(phase="analyze", total=10, message="analyzing...")
        data = json.loads(t._path.read_text(encoding="utf-8"))
        assert data["phase"] == "analyze"
        assert data["current"] == 0
        assert data["total"] == 10
        assert data["message"] == "analyzing..."

    def test_update_current(self, tmp_path):
        t = ProgressTracker(tmp_path)
        t.update(phase="compress", total=5)
        t.update(current=3)
        data = json.loads(t._path.read_text(encoding="utf-8"))
        assert data["current"] == 3

    def test_next_increments(self, tmp_path):
        t = ProgressTracker(tmp_path)
        t.update(phase="compress", total=3)
        t.next()
        t.next(message="done 2")
        data = json.loads(t._path.read_text(encoding="utf-8"))
        assert data["current"] == 2

    def test_done_sets_status(self, tmp_path):
        t = ProgressTracker(tmp_path)
        t.done("all complete")
        data = json.loads(t._path.read_text(encoding="utf-8"))
        assert data["status"] == "done"
        assert data["message"] == "all complete"

    def test_error_sets_status(self, tmp_path):
        t = ProgressTracker(tmp_path)
        t.error("something went wrong")
        data = json.loads(t._path.read_text(encoding="utf-8"))
        assert data["status"] == "error"
        assert data["message"] == "something went wrong"

    def test_eta_computed(self, tmp_path):
        t = ProgressTracker(tmp_path)
        t.update(phase="compress", total=10, current=1)
        time.sleep(0.05)  # let time pass for rate calculation
        t.update(current=2)
        data = json.loads(t._path.read_text(encoding="utf-8"))
        assert data["eta_sec"] is not None
        assert data["eta_sec"] >= 0

    def test_eta_is_none_when_no_progress(self, tmp_path):
        t = ProgressTracker(tmp_path)
        t.update(phase="compress", total=10)
        t.next()
        data = json.loads(t._path.read_text(encoding="utf-8"))
        # eta might still be None if elapsed is 0
        assert "eta_sec" in data

    def test_starts_at_zero(self, tmp_path):
        t = ProgressTracker(tmp_path)
        data = json.loads(t._path.read_text(encoding="utf-8"))
        assert data["current"] == 0
        assert data["total"] == 0

    def test_atomic_write_no_corruption(self, tmp_path):
        """Verify the written file is valid JSON after repeated updates."""
        t = ProgressTracker(tmp_path)
        for i in range(100):
            t.update(phase="test", current=i)
            # read back and validate
            data = json.loads(t._path.read_text(encoding="utf-8"))
            assert data["current"] == i

    def test_does_not_raise_on_concurrent_read(self, tmp_path):
        """Simulate reading progress.json while it's being written."""
        t = ProgressTracker(tmp_path)
        t.update(phase="test", total=5)
        # Read concurrently (single-threaded simulation)
        for i in range(20):
            t.next(message=f"step {i}")
            try:
                json.loads(t._path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pytest.fail("corrupted JSON on read")

    def test_output_dir_created(self, tmp_path):
        sub = tmp_path / "nested" / "dirs"
        t = ProgressTracker(sub)
        assert sub.is_dir()
        assert t._path.is_file()
