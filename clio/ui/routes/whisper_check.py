"""Whisper installation check handler."""

from __future__ import annotations

from typing import Any

from clio.transcribe import _resolve_cache_dir, check_cublas, check_whisper
from clio.ui.handler_protocol import HandlerProtocol
from clio.whisper_cache import is_model_cache_complete


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
        proj_dir = handler._resolve_project_dir(qs)
        cfg = handler._get_config(proj_dir)
        cache_dir = _resolve_cache_dir(cfg)
        if cache_dir.is_dir():
            cache_path = str(cache_dir)
            model_cached = is_model_cache_complete(cache_dir, cfg.whisper.model_size)
    except Exception:
        pass

    handler._send_json(
        {
            "ok": True,
            "installed": installed,
            "cublas": check_cublas(),
            "cuda": cuda,
            "cache_path": cache_path,
            "model_cached": model_cached,
        }
    )
