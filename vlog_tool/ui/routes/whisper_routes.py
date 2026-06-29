"""API handlers for Whisper — re-exported from focused sub-modules."""

from __future__ import annotations

from vlog_tool.ui.routes.whisper_check import handle_get_whisper_check
from vlog_tool.ui.routes.whisper_download import (
    handle_get_whisper_install_status,
    handle_post_whisper_install,
    handle_post_whisper_install_cancel,
)
from vlog_tool.ui.routes.whisper_models import (
    handle_get_whisper_models,
    handle_post_whisper_model_delete,
    handle_put_whisper_model,
)

__all__ = [
    "handle_get_whisper_check",
    "handle_get_whisper_install_status",
    "handle_get_whisper_models",
    "handle_post_whisper_install",
    "handle_post_whisper_install_cancel",
    "handle_post_whisper_model_delete",
    "handle_put_whisper_model",
]
