"""Route handlers: /api/prompts."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from clio.prompts import (
    PROMPT_DEFAULTS,
    find_prompt_override,
    load_prompt,
    prompt_override_candidates,
    prompt_override_dir,
)
from clio.ui.services.file_service import _save_atomic

if TYPE_CHECKING:
    from clio.ui.handler_protocol import HandlerProtocol


def _normalize_prompt_name(name: str) -> str | None:
    prompt_name = name.strip().upper()
    if prompt_name not in PROMPT_DEFAULTS:
        return None
    return prompt_name


def _project_prompt_path(handler: HandlerProtocol, qs: dict[str, Any], name: str):
    proj_dir = handler._resolve_project_dir(qs)
    return prompt_override_dir(proj_dir) / f"{name}.md"


def handle_get_prompts(handler: HandlerProtocol, qs: dict[str, Any]) -> None:
    """Handle GET /api/prompts."""
    proj_dir = handler._resolve_project_dir(qs)
    prompts = []
    for name, default in PROMPT_DEFAULTS.items():
        override = find_prompt_override(name, proj_dir)
        save_path = _project_prompt_path(handler, qs, name)
        prompts.append(
            {
                "name": name,
                "default": default,
                "content": load_prompt(name, default, proj_dir),
                "override": override.content if override else None,
                "has_override": override is not None,
                "override_path": str(save_path),
                "source_path": str(override.path) if override else None,
            }
        )
    handler._send_json({"prompts": prompts, "override_dir": str(prompt_override_dir(proj_dir))})


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


def handle_delete_prompt(handler: HandlerProtocol, qs: dict[str, Any], name: str) -> None:
    """Handle DELETE /api/prompts/{name}."""
    prompt_name = _normalize_prompt_name(name)
    if prompt_name is None:
        return handler._send_json({"ok": False, "error": "unknown prompt"}, 404)

    proj_dir = handler._resolve_project_dir(qs)
    deleted: list[str] = []
    seen: set = set()
    for candidate in prompt_override_candidates(prompt_name, proj_dir):
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if candidate.is_file():
            candidate.unlink()
            deleted.append(str(candidate))

    handler._send_json({"ok": True, "name": prompt_name, "deleted": deleted})
