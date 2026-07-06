from __future__ import annotations

from clio.tasks.cover import _normalize_timestamp


class TestNormalizeTimestamp:
    def test_mm_ss(self):
        assert _normalize_timestamp("01:02") == "00:01:02.000"

    def test_hh_mm_ss(self):
        assert _normalize_timestamp("01:02:03.5") == "01:02:03.500"

    def test_invalid(self):
        assert _normalize_timestamp("bad") is None
        assert _normalize_timestamp("-1:02") is None
