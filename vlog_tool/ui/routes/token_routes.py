"""Token usage API routes."""

from __future__ import annotations

from vlog_tool.ai.token_usage import FileTokenUsageStore


def handle_get_token_usage(handler, qs):
    proj_out = handler._project_output_dir(qs)
    if proj_out is None:
        return handler._send_json({"ok": False, "error": "no project"})
    store = FileTokenUsageStore(str(proj_out))
    stats = store.get_stats()
    return handler._send_json(stats)
