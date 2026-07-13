"""Token usage API routes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from clio.ai.token_usage import FileTokenUsageStore
from clio.ui.handler_protocol import HandlerProtocol
from clio.ui.services.project_service import _project_output_dir


def handle_get_token_usage(handler: HandlerProtocol, qs: dict[str, Any]) -> None:
    proj_dir = Path(handler._resolve_project_dir(qs))
    proj_out = _project_output_dir(proj_dir)
    if proj_out is None:
        return handler._send_json({"ok": False, "error": "no project"})
    store = FileTokenUsageStore(str(proj_out))
    stats = store.get_stats()
    handler._send_json(stats)
