from __future__ import annotations

from unittest.mock import patch

import pytest

from vlog_tool.ratelimit import RateLimiter, make_rate_limiter


class TestRateLimiterInit:
    def test_negative_raises(self):
        with pytest.raises(ValueError, match="must be > 0"):
            RateLimiter(0)
        with pytest.raises(ValueError, match="must be > 0"):
            RateLimiter(-1)

    def test_sets_interval(self):
        rl = RateLimiter(60)
        assert rl._interval == 1.0

    def test_interval_120_rpm(self):
        rl = RateLimiter(120)
        assert rl._interval == 0.5


class TestRateLimiterContext:
    def test_first_call_no_wait(self):
        rl = RateLimiter(60)
        with patch("vlog_tool.ratelimit.time.monotonic", return_value=100.0):
            with patch("vlog_tool.ratelimit.time.sleep") as mock_sleep:
                with rl:
                    pass
        mock_sleep.assert_not_called()
        assert rl._next_at == 101.0

    def test_second_call_within_interval_waits(self):
        rl = RateLimiter(60)
        rl._next_at = 105.0
        with patch("vlog_tool.ratelimit.time.monotonic", return_value=100.0):
            with patch("vlog_tool.ratelimit.time.sleep") as mock_sleep:
                with rl:
                    pass
        mock_sleep.assert_called_once_with(5.0)
        assert rl._next_at == 106.0

    def test_exact_interval_no_wait(self):
        rl = RateLimiter(60)
        rl._next_at = 100.0
        with patch("vlog_tool.ratelimit.time.monotonic", return_value=100.0):
            with patch("vlog_tool.ratelimit.time.sleep") as mock_sleep:
                with rl:
                    pass
        mock_sleep.assert_not_called()
        assert rl._next_at == 101.0

    def test_logs_rate_limit_message(self, capsys):
        rl = RateLimiter(10)
        rl._next_at = 200.0
        with patch("vlog_tool.ratelimit.time.monotonic", return_value=100.0):
            with patch("vlog_tool.ratelimit.time.sleep"):
                with rl:
                    pass
        captured = capsys.readouterr()
        assert "限流" in captured.out

    def test_only_logs_once_per_wait(self, capsys):
        rl = RateLimiter(10)
        rl._next_at = 200.0
        with patch("vlog_tool.ratelimit.time.monotonic", return_value=100.0):
            with patch("vlog_tool.ratelimit.time.sleep"):
                with rl:
                    pass
        captured = capsys.readouterr()
        assert "限流" in captured.out

        # Second rate-limited call should NOT log again (flag stays True)
        rl._next_at = 300.0
        with patch("vlog_tool.ratelimit.time.monotonic", return_value=100.0):
            with patch("vlog_tool.ratelimit.time.sleep"):
                with rl:
                    pass
        captured2 = capsys.readouterr()
        assert "限流" not in captured2.out

    def test_logged_remains_true_while_rate_limited(self):
        rl = RateLimiter(10)
        rl._next_at = 200.0
        assert rl._logged is False
        with patch("vlog_tool.ratelimit.time.monotonic", return_value=100.0):
            with patch("vlog_tool.ratelimit.time.sleep"):
                with rl:
                    pass
        assert rl._logged is True

    def test_resets_logged_flag_when_not_rate_limited(self):
        rl = RateLimiter(10)
        rl._next_at = 0.0
        assert rl._logged is False
        with patch("vlog_tool.ratelimit.time.monotonic", return_value=100.0):
            with rl:
                pass
        assert rl._logged is False


class TestMakeRateLimiter:
    def test_zero_returns_none(self):
        assert make_rate_limiter(0) is None

    def test_negative_returns_none(self):
        assert make_rate_limiter(-1) is None

    def test_positive_returns_instance(self):
        rl = make_rate_limiter(10)
        assert isinstance(rl, RateLimiter)
        assert rl._interval == 6.0
