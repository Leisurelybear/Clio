from __future__ import annotations

from typing import Any

from clio.ui.handler_protocol import HandlerProtocol
from clio.ui.services.ai_test_service import test_provider_connection


def handle_post_ai_test(handler: HandlerProtocol, qs: dict[str, Any], obj: dict[str, Any]) -> None:
    raw_provider = obj.get("provider")
    if raw_provider is None:
        return handler._send_json({"ok": False, "error": "provider is required"}, 400)
    if not isinstance(raw_provider, str):
        return handler._send_json({"ok": False, "error": "provider must be a string"}, 400)

    provider = raw_provider.strip()
    if not provider:
        return handler._send_json({"ok": False, "error": "provider is required"}, 400)

    raw_model = obj.get("model")
    if raw_model is None:
        model = ""
    elif isinstance(raw_model, str):
        model = raw_model.strip()
    else:
        return handler._send_json({"ok": False, "error": "model must be a string"}, 400)

    proj_dir = handler._resolve_project_dir(qs)
    cfg = handler._get_config(proj_dir)
    result = test_provider_connection(cfg, provider_name=provider, model=model)
    return handler._send_json(result)
