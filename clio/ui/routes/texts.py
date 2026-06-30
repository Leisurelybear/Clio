"""Route handlers: /api/texts, /api/voiceover"""

from __future__ import annotations

import json
from http import HTTPStatus
from typing import TYPE_CHECKING, Any

from clio.ui.services.file_service import _save_atomic

if TYPE_CHECKING:
    from clio.ui.handler_protocol import HandlerProtocol


def handle_get_texts(handler: HandlerProtocol, qs: dict[str, Any]) -> None:
    """Handle GET /api/texts."""
    proj_out = handler._get_project_output(qs)
    fname = qs.get("file", [""])[0]
    p = handler._resolve_texts(fname, proj_out)
    if p is None:
        return handler.send_error(HTTPStatus.NOT_FOUND)
    handler._send_bytes(p.read_bytes(), "application/json; charset=utf-8")


def handle_get_voiceover(handler: HandlerProtocol, qs: dict[str, Any]) -> None:
    """Handle GET /api/voiceover."""
    proj_out = handler._get_project_output(qs)
    fname = qs.get("file", [""])[0]
    p = handler._resolve_in("scripts", fname, proj_out)  # type: ignore[attr-defined]  # TODO(phase4): add to Protocol when stable
    if p is None:
        return handler.send_error(HTTPStatus.NOT_FOUND)
    handler._send_bytes(p.read_bytes(), "application/json; charset=utf-8")


def handle_put_texts(handler: HandlerProtocol, qs: dict[str, Any], obj: dict) -> None:
    """Handle PUT /api/texts."""
    proj_out = handler._get_project_output(qs)
    fname = qs.get("file", [""])[0]
    p = handler._resolve_texts(fname, proj_out)
    if p is None:
        return handler._send_json({"ok": False, "error": "forbidden or not found"}, 403)
    data = json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")
    _save_atomic(p, data)
    handler._send_json({"ok": True, "path": str(p)})


def handle_put_voiceover(handler: HandlerProtocol, qs: dict[str, Any], obj: dict) -> None:
    """Handle PUT /api/voiceover."""
    proj_out = handler._get_project_output(qs)
    fname = qs.get("file", [""])[0]
    p = handler._resolve_in("scripts", fname, proj_out)  # type: ignore[attr-defined]  # TODO(phase4): add to Protocol when stable
    if p is None:
        return handler._send_json({"ok": False, "error": "forbidden or not found"}, 403)
    data = json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")
    _save_atomic(p, data)
    handler._send_json({"ok": True, "path": str(p)})
