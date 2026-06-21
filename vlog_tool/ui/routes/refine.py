"""Route handler: POST /api/refine"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from vlog_tool.analyze import refine_script, refine_text
from vlog_tool.tasks.refine import _load_analysis_for_script
from vlog_tool.ui.services.file_service import _is_safe_basename, _save_atomic

if TYPE_CHECKING:
    from http.server import BaseHTTPRequestHandler


def handle_post_refine(handler: BaseHTTPRequestHandler, qs: dict, obj: dict) -> None:
    """Handle POST /api/refine.

    Body: {file: str, type: "texts"|"scripts", context?: str}
    Refines the given texts/scripts file via AI and saves it back.
    """
    fname = obj.get("file", "")
    ftype = obj.get("type", "")
    context_override = obj.get("context") or None

    if not fname or ftype not in ("texts", "scripts"):
        return handler._send_json({"ok": False, "error": "missing or invalid file/type"}, 400)
    if not _is_safe_basename(Path(fname).stem):
        return handler._send_json({"ok": False, "error": "forbidden"}, 403)

    proj_out = handler._get_project_output(qs)
    if ftype == "texts":
        p = handler._resolve_texts(fname, proj_out)
    else:
        p = handler._resolve_in("scripts", fname, proj_out)

    if p is None:
        return handler._send_json({"ok": False, "error": "forbidden or not found"}, 404)

    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        return handler._send_json({"ok": False, "error": f"failed to read file: {e}"}, 500)

    config = handler._get_config(proj_out)

    try:
        if ftype == "texts":
            refined = refine_text(data, config, context_override=context_override)
        else:
            analysis = _load_analysis_for_script(p, config.texts_dir)
            refined = refine_script(data, analysis, config, context_override=context_override)
    except Exception as e:
        return handler._send_json({"ok": False, "error": f"refine failed: {e}"}, 500)

    raw = json.dumps(refined, ensure_ascii=False, indent=2).encode("utf-8")
    _save_atomic(p, raw)

    handler._send_json({"ok": True, "data": refined})
