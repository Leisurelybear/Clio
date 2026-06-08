from __future__ import annotations

import json
import threading
import time
from pathlib import Path


class ProgressTracker:
    """Thread-safe progress tracker that writes to output/.progress.json.

    Fields written:
      phase        — "compress" | "analyze" | "voiceover" | "plan" | "label" | "done" | "error"
      current      — items completed within current phase
      total        — total items in current phase
      message      — human-readable status line
      status       — "running" | "done" | "error"
      started_at   — ISO timestamp
      eta_sec      — estimated remaining seconds
    """

    def __init__(self, output_dir: Path):
        self._path = output_dir / ".progress.json"
        self._lock = threading.Lock()
        self._start = time.monotonic()
        self._data = {
            "phase": "",
            "current": 0,
            "total": 0,
            "message": "",
            "status": "running",
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "eta_sec": None,
        }
        self._flush()

    def _flush(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".progress.tmp")
        tmp.write_text(json.dumps(self._data, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self._path)

    def update(self, *, phase: str | None = None, current: int | None = None,
               total: int | None = None, message: str | None = None,
               status: str | None = None) -> None:
        with self._lock:
            if phase is not None:
                self._data["phase"] = phase
                self._data["current"] = 0
            if current is not None:
                self._data["current"] = current
            if total is not None:
                self._data["total"] = total
            if message is not None:
                self._data["message"] = message
            if status is not None:
                self._data["status"] = status
            if self._data["total"] > 0 and self._data["current"] > 0:
                elapsed = time.monotonic() - self._start
                rate = self._data["current"] / elapsed if elapsed > 0 else 0
                remaining = self._data["total"] - self._data["current"]
                self._data["eta_sec"] = round(remaining / rate) if rate > 0 else None
            self._flush()

    def next(self, *, message: str | None = None) -> None:
        """Advance current by 1."""
        with self._lock:
            self._data["current"] += 1
            if message is not None:
                self._data["message"] = message
            if self._data["total"] > 0 and self._data["current"] > 0:
                elapsed = time.monotonic() - self._start
                rate = self._data["current"] / elapsed if elapsed > 0 else 0
                remaining = self._data["total"] - self._data["current"]
                self._data["eta_sec"] = round(remaining / rate) if rate > 0 else None
            self._flush()

    def done(self, message: str = "") -> None:
        self.update(phase="done", current=0, total=0, message=message or "完成", status="done")

    def error(self, message: str) -> None:
        self.update(status="error", message=message)
