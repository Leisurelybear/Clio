from __future__ import annotations

import threading
import time
from typing import Any

_logs: list[dict[str, Any]] = []
_lock = threading.Lock()
_MAX = 10000


def write(line: str) -> None:
    entry = {"ts": time.time(), "text": line}
    with _lock:
        _logs.append(entry)
        if len(_logs) > _MAX:
            del _logs[: len(_logs) - _MAX]


def read(offset: int = 0) -> dict[str, Any]:
    with _lock:
        return {"logs": list(_logs[offset:]), "total": len(_logs)}


def clear() -> None:
    with _lock:
        _logs.clear()
