"""Route handlers: /api/prompts."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from clio.prompts import PROMPT_DEFAULTS, load_prompt
from clio.ui.services.file_service import _save_atomic

if TYPE_CHECKING:
    from clio.ui.handler_protocol import HandlerProtocol


def _normalize_prompt_name(name: str) -> str | None:
    prompt_name = name.strip().upper()
    if prompt_name not in PROMPT_DEFAULTS:
        return None
    return prompt_name


def _project_prompt_path(handler: HandlerProtocol, qs: dict[str, Any], name: str):
    proj_input = handler._resolve_project_input(qs)
    return proj_input / "templates" / "prompts" / f"{name}.md"


def handle_get_prompts(handler: HandlerProtocol, qs: dict[str, Any]) -> None:
    """Handle GET /api/prompts."""
    proj_input = handler._resolve_project_input(qs)
    prompts = []
    for name, default in PROMPT_DEFAULTS.items():
        override_path = _project_prompt_path(handler, qs, name)
        override = override_path.read_text(encoding="utf-8") if override_path.is_file() else None
        prompts.append(
            {
                "name": name,
                "default": default,
                "content": load_prompt(name, default, proj_input),
                "override": override,
                "has_override": override is not None,
                "override_path": str(override_path),
            }
        )
    handler._send_json({"prompts": prompts, "override_dir": str(proj_input / "templates" / "prompts")})


def handle_put_prompt(handler: HandlerProtocol, qs: dict[str, Any], obj: dict, name: str) -> None:
    """Handle PUT /api/prompts/{name}."""
    prompt_name = _normalize_prompt_name(name)
    if prompt_name is None:
        return handler._send_json({"ok": False, "error": "unknown prompt"}, 404)

    content = obj.get("content")
    if not isinstance(content, str):
        return handler._send_json({"ok": False, "error": "content must be a string"}, 400)
    if not content.strip():
        return handler._send_json({"ok": False, "error": "content cannot be empty"}, 400)

    target = _project_prompt_path(handler, qs, prompt_name)
    target.parent.mkdir(parents=True, exist_ok=True)
    _save_atomic(target, content.encode("utf-8"))
    handler._send_json({"ok": True, "name": prompt_name, "path": str(target)})
