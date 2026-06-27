"""Config cache for the UI server.

Provides a thread-safe LRU cache with mtime-based invalidation.
Extracted from server.py's make_handler closure to support testability.
"""

from __future__ import annotations

import copy
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from vlog_tool.config import AppConfig, load_config


class ConfigCache:
    """Thread-safe LRU cache for project-specific AppConfig instances.

    - Keyed by project input_dir (or '__global__' for no project).
    - mtime-aware: re-reads config files when they change on disk.
    - LRU eviction at maxsize (default 20).
    - Returns deep copies to prevent caller mutation.
    """

    def __init__(self, config_path: Path | None, maxsize: int = 20, on_load: Callable[..., Any] | None = None) -> None:
        self._config_path = config_path
        self._maxsize = maxsize
        self._on_load = on_load
        self._cache: dict[str, AppConfig] = {}
        self._meta: dict[str, tuple[float | None, float | None]] = {}
        self._lock = threading.Lock()

    def get(self, project_input: Path | None = None) -> AppConfig:
        _GLOBAL_KEY = "__global__"
        key = _GLOBAL_KEY if project_input is None else str(project_input.resolve())

        cfg_mtime = self._read_mtime(self._config_path)
        proj_mtime = self._read_mtime(None if project_input is None else project_input / "project.yaml")

        with self._lock:
            if key in self._cache:
                old_cfg_mtime, old_proj_mtime = self._meta.get(key, (0, 0))
                if cfg_mtime == old_cfg_mtime and proj_mtime == old_proj_mtime:
                    return copy.deepcopy(self._cache[key])
                del self._cache[key]
                self._meta.pop(key, None)

            new_config = load_config(self._config_path or "config.yaml", project_dir=project_input)

            if len(self._cache) >= self._maxsize:
                oldest_key = next(iter(self._cache))
                self._cache.pop(oldest_key)
                self._meta.pop(oldest_key, None)

            self._cache[key] = new_config
            self._meta[key] = (cfg_mtime, proj_mtime)
            if self._on_load:
                self._on_load(new_config)
            return copy.deepcopy(new_config)

    def invalidate_all(self) -> None:
        with self._lock:
            self._cache.clear()
            self._meta.clear()

    def invalidate_key(self, key: str) -> None:
        with self._lock:
            self._cache.pop(key, None)
            self._meta.pop(key, None)

    def keys(self) -> list[str]:
        with self._lock:
            return list(self._cache.keys())

    @staticmethod
    def _read_mtime(path: Path | None) -> float:
        if path is None:
            return 0.0
        try:
            return path.stat().st_mtime
        except OSError:
            return 0.0
