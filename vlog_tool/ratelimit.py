from __future__ import annotations

import threading
import time


class RateLimiter:
    """每分钟固定次数限流器，线程安全。"""

    def __init__(self, requests_per_minute: int) -> None:
        if requests_per_minute <= 0:
            raise ValueError("requests_per_minute must be > 0")
        self._interval = 60.0 / requests_per_minute
        self._lock = threading.Lock()
        self._next_at = 0.0

    def __enter__(self) -> None:
        with self._lock:
            now = time.monotonic()
            if now < self._next_at:
                time.sleep(self._next_at - now)
            self._next_at = time.monotonic() + self._interval

    def __exit__(self, *exc_info) -> None:
        pass


def make_rate_limiter(requests_per_minute: int) -> RateLimiter | None:
    """若启用了限流则返回 RateLimiter，否则返回 None。"""
    if requests_per_minute <= 0:
        return None
    return RateLimiter(requests_per_minute)
