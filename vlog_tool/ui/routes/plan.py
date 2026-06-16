"""Route handlers: /api/plan, /api/plans, /api/cut"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from vlog_tool.pipeline import run_cut_all
from vlog_tool.ui.services.file_service import _is_safe_basename, _save_atomic

if TYPE_CHECKING:
    from http.server import BaseHTTPRequestHandler


def handle_get_plans(handler: BaseHTTPRequestHandler, qs: dict) -> None:
    """Handle GET /api/plans."""
    proj_out = handler._get_project_output(qs)
    plans_dir = proj_out / "plans"
    plans = []
    if plans_dir.is_dir():
        for p in sorted(plans_dir.glob("*_plan.json")):
            day_label = p.stem.replace("_plan", "")
            if day_label:
                plans.append({"day_label": day_label, "path": str(p)})
    handler._send_json({"plans": plans})


def handle_get_plan(handler: BaseHTTPRequestHandler, qs: dict) -> None:
    """Handle GET /api/plan."""
    day = qs.get("day", [""])[0]
    if not _is_safe_basename(day) or not day:
        return handler._send_json({"error": "forbidden"}, 403)
    proj_out = handler._get_project_output(qs)
    p = proj_out / "plans" / f"{day}_plan.json"
    if not p.is_file():
        return handler._send_json({"error": f"规划文件不存在: {p}"}, 404)
    handler._send_bytes(p.read_bytes(), "application/json; charset=utf-8")


def handle_put_plan(handler: BaseHTTPRequestHandler, qs: dict, obj: dict) -> None:
    """Handle PUT /api/plan."""
    day = qs.get("day", [""])[0]
    if not _is_safe_basename(day) or not day:
        return handler._send_json({"ok": False, "error": "forbidden"}, 403)
    proj_out = handler._get_project_output(qs)
    p = proj_out / "plans" / f"{day}_plan.json"
    data = json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")
    _save_atomic(p, data)
    handler._send_json({"ok": True, "path": str(p)})


def handle_post_cut(handler: BaseHTTPRequestHandler, qs: dict[str, list[str]], obj: dict) -> None:
    """Handle POST /api/cut."""
    day_label = obj.get("day_label", "day1")
    if not _is_safe_basename(day_label):
        return handler._send_json({"ok": False, "error": "invalid day_label"}, 400)
    source = obj.get("source", "compressed")
    reencode = obj.get("reencode", False)
    out_dir_raw = obj.get("output_dir", None)

    if source not in ("compressed", "original"):
        return handler._send_json({"ok": False, "error": "source must be compressed|original"}, 400)

    out_path = Path(out_dir_raw) if out_dir_raw else None
    proj_input = handler._resolve_project_input(qs)
    cfg = handler._get_config(proj_input)

    try:
        run_cut_all(
            cfg,
            day_label=day_label,
            output_dir=out_path,
            reencode=bool(reencode),
            source=source,
        )
    except Exception as e:
        return handler._send_json({"ok": False, "error": str(e)}, 500)

    actual_out = str(out_path or (handler.output_dir / "cuts" / day_label))
    handler._send_json(
        {
            "ok": True,
            "output_dir": actual_out,
            "day_label": day_label,
        }
    )
