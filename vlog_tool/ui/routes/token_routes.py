"""Token usage API routes."""

from __future__ import annotations

from pathlib import Path

from vlog_tool.ai.token_usage import FileTokenUsageStore
from vlog_tool.ui.services.project_service import _project_output_dir


def handle_get_token_usage(handler, qs):
    proj_input = Path(handler._resolve_project_input(qs))
    proj_out = _project_output_dir(proj_input)
    if proj_out is None:
        return handler._send_json({"ok": False, "error": "no project"})
    store = FileTokenUsageStore(str(proj_out))
    stats = store.get_stats()
    return handler._send_json(stats)
