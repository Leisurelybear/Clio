"""Route handlers: /api/texts, /api/voiceover"""

from __future__ import annotations

import json
from http import HTTPStatus
from typing import TYPE_CHECKING

from vlog_tool.ui.services.file_service import _save_atomic

if TYPE_CHECKING:
    from http.server import BaseHTTPRequestHandler


def handle_get_texts(handler: BaseHTTPRequestHandler, qs: dict) -> None:
    """Handle GET /api/texts."""
    proj_out = handler._get_project_output(qs)
    fname = qs.get("file", [""])[0]
    p = handler._resolve_texts(fname, proj_out)
    if p is None:
        return handler.send_error(HTTPStatus.NOT_FOUND)
    handler._send_bytes(p.read_bytes(), "application/json; charset=utf-8")


def handle_get_voiceover(handler: BaseHTTPRequestHandler, qs: dict) -> None:
    """Handle GET /api/voiceover."""
    proj_out = handler._get_project_output(qs)
    fname = qs.get("file", [""])[0]
    p = handler._resolve_in("scripts", fname, proj_out)
    if p is None:
        return handler.send_error(HTTPStatus.NOT_FOUND)
    handler._send_bytes(p.read_bytes(), "application/json; charset=utf-8")


def handle_put_texts(handler: BaseHTTPRequestHandler, qs: dict, obj: dict) -> None:
    """Handle PUT /api/texts."""
    proj_out = handler._get_project_output(qs)
    fname = qs.get("file", [""])[0]
    p = handler._resolve_texts(fname, proj_out)
    if p is None:
        return handler._send_json({"ok": False, "error": "forbidden or not found"}, 403)
    data = json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")
    _save_atomic(p, data)
    handler._send_json({"ok": True, "path": str(p)})


def handle_put_voiceover(handler: BaseHTTPRequestHandler, qs: dict, obj: dict) -> None:
    """Handle PUT /api/voiceover."""
    proj_out = handler._get_project_output(qs)
    fname = qs.get("file", [""])[0]
    p = handler._resolve_in("scripts", fname, proj_out)
    if p is None:
        return handler._send_json({"ok": False, "error": "forbidden or not found"}, 403)
    data = json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")
    _save_atomic(p, data)
    handler._send_json({"ok": True, "path": str(p)})
