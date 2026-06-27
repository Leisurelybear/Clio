from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from vlog_tool.schema import ARTIFACT_SCHEMA_VERSION

_STEPS = ["compress", "analyze", "voiceover", "transcribe", "plan", "label"]


class ProcessingState:
    """Per-file pipeline state matrix, persisted to output/.processing.json.

    Schema:
      version   — 1
      steps     — ordered step list
      files     — {original_stem: {step: status|null}}
    """

    def __init__(self, output_dir: Path):
        self._path = output_dir / ".processing.json"
        self._lock = threading.Lock()
        self._data = self._load()

    def _load(self) -> dict:
        if self._path.is_file():
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
                data.setdefault("_schema_version", ARTIFACT_SCHEMA_VERSION)
                return data
            except (json.JSONDecodeError, OSError):
                pass
        return {"_schema_version": ARTIFACT_SCHEMA_VERSION, "version": 1, "steps": list(_STEPS), "files": {}}

    def _flush(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        suffix = os.urandom(4).hex()
        tmp = self._path.parent / f"{self._path.name}.{suffix}.tmp"
        tmp.write_text(json.dumps(self._data, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self._path)

    def mark(self, file_stem: str, step: str, status: str) -> None:
        with self._lock:
            files = self._data.setdefault("files", {})
            if file_stem not in files:
                files[file_stem] = {s: None for s in _STEPS}
            files[file_stem][step] = status
            self._flush()

    def reset_step(self, step: str) -> None:
        with self._lock:
            for entry in self._data.setdefault("files", {}).values():
                if step in entry:
                    entry[step] = None
            self._flush()

    def get_state(self) -> dict:
        with self._lock:
            return json.loads(json.dumps(self._data))
