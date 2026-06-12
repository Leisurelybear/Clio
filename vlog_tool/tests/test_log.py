"""Tests for vlog_tool/log.py — pure formatting functions and TeeWriter."""

from __future__ import annotations

import io
import logging

from vlog_tool.log import _TeeWriter, format_duration, format_size, setup_logging, teardown_logging

# ── format_size ─────────────────────────────────────────────────────


class TestFormatSize:
    def test_zero_bytes(self):
        assert format_size(0) == "0 B"

    def test_small_bytes(self):
        assert format_size(512) == "512 B"

    def test_kilobytes(self):
        assert format_size(1_024) == "1.0 KB"

    def test_megabytes(self):
        assert format_size(1_024 * 1_024) == "1.00 MB"

    def test_gigabytes(self):
        assert format_size(1_024 * 1_024 * 1_024) == "1.00 GB"

    def test_fractional_kb(self):
        assert format_size(1_500) == "1.5 KB"

    def test_fractional_mb(self):
        assert format_size(1_024 * 1_024 * 2 + 500_000) == "2.48 MB"

    def test_negative(self):
        assert format_size(-100) == "-100 B"


# ── format_duration ─────────────────────────────────────────────────


class TestFormatDuration:
    def test_zero_seconds(self):
        assert format_duration(0) == "0s"

    def test_under_minute(self):
        assert format_duration(45) == "45s"

    def test_one_minute(self):
        assert format_duration(60) == "1m00s"

    def test_minutes_and_seconds(self):
        assert format_duration(83) == "1m23s"

    def test_one_hour(self):
        assert format_duration(3600) == "1h00m00s"

    def test_hours_minutes_seconds(self):
        assert format_duration(3723) == "1h02m03s"

    def test_negative_returns_zero_prefix(self):
        assert format_duration(-10) == "0s"

    def test_large_duration(self):
        assert format_duration(10000) == "2h46m40s"


# ── _TeeWriter ─────────────────────────────────────────────────


class TestTeeWriter:
    def test_writes_to_original(self):
        buf = io.StringIO()
        logger = logging.getLogger("test_tee_w")
        logger.setLevel(logging.INFO)
        tw = _TeeWriter(buf, logger, logging.INFO)
        tw.write("hello")
        tw.flush()
        assert buf.getvalue() == "hello"

    def test_skip_empty_message(self):
        buf = io.StringIO()
        logger = logging.getLogger("test_tee_empty")
        logger.setLevel(logging.INFO)
        tw = _TeeWriter(buf, logger, logging.INFO)
        assert tw.write("") == 0

    def test_isatty_delegates(self):
        buf = io.StringIO()
        logger = logging.getLogger("test_tee_tty")
        logger.setLevel(logging.INFO)
        tw = _TeeWriter(buf, logger, logging.INFO)
        assert tw.isatty() is False

    def test_flush_delegates(self):
        buf = io.StringIO()
        logger = logging.getLogger("test_tee_flush")
        logger.setLevel(logging.INFO)
        tw = _TeeWriter(buf, logger, logging.INFO)
        tw.write("data")
        tw.flush()
        assert buf.getvalue() == "data"


# ── setup_logging / teardown_logging ───────────────────────────


class TestSetupLogging:
    def test_teardown_restores_stdout(self, tmp_path):
        import sys

        original = sys.stdout
        try:
            setup_logging(tmp_path)
            assert sys.stdout is not original
        finally:
            teardown_logging()
        assert sys.stdout is original

    def test_teardown_restores_stderr(self, tmp_path):
        import sys

        original = sys.stderr
        try:
            setup_logging(tmp_path)
            assert sys.stderr is not original
        finally:
            teardown_logging()
        assert sys.stderr is original

    def test_setup_is_idempotent(self, tmp_path):
        setup_logging(tmp_path)
        logger1 = setup_logging(tmp_path)
        teardown_logging()
        assert logger1 is not None

    def test_teardown_before_setup_noop(self):
        teardown_logging()
        teardown_logging()
