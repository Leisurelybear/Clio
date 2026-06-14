"""API handler for Whisper installation check."""

from __future__ import annotations

from vlog_tool.transcribe import check_whisper


def handle_get_whisper_check(handler) -> None:
    installed = check_whisper()
    cuda = False
    if installed:
        try:
            import torch  # noqa: F811

            cuda = torch.cuda.is_available()
        except ImportError:
            pass

    cache_path = None
    try:
        from vlog_tool.config import load_config
        from vlog_tool.transcribe import _resolve_cache_dir

        cfg = load_config()
        cache_dir = _resolve_cache_dir(cfg)
        if cache_dir.is_dir():
            cache_path = str(cache_dir)
    except Exception:
        pass

    handler._send_json(
        {
            "ok": True,
            "installed": installed,
            "cuda": cuda,
            "cache_path": cache_path,
        }
    )
