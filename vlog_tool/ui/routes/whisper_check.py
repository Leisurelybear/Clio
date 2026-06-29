"""Whisper installation check handler."""

from __future__ import annotations

from typing import Any

from vlog_tool.transcribe import _resolve_cache_dir, check_whisper
from vlog_tool.ui.handler_protocol import HandlerProtocol


def handle_get_whisper_check(handler: HandlerProtocol, qs: dict[str, Any]) -> None:
    installed = check_whisper()
    cuda = False
    if installed:
        try:
            from ctranslate2 import get_cuda_device_count

            cuda = get_cuda_device_count() > 0
        except ImportError:
            pass

    cache_path = None
    model_cached = False
    try:
        proj_input = handler._resolve_project_input(qs)
        cfg = handler._get_config(proj_input)
        cache_dir = _resolve_cache_dir(cfg)
        if cache_dir.is_dir():
            cache_path = str(cache_dir)
            for entry in cache_dir.iterdir():
                if entry.is_dir():
                    snapshots = entry / "snapshots"
                    if snapshots.is_dir():
                        for snap_dir in snapshots.iterdir():
                            max_size = 0
                            for f in snap_dir.rglob("*"):
                                if f.is_file():
                                    try:
                                        sz = f.stat().st_size
                                    except OSError:
                                        continue
                                    if sz > max_size:
                                        max_size = sz
                            if max_size > 100 * 1024 * 1024:
                                model_cached = True
                                break
                    if model_cached:
                        break
    except Exception:
        pass

    handler._send_json(
        {
            "ok": True,
            "installed": installed,
            "cuda": cuda,
            "cache_path": cache_path,
            "model_cached": model_cached,
        }
    )
