"""Route handlers: /api/plan, /api/plans, /api/cut"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from clio.pipeline import run_cut_all
from clio.plan_model import Plan
from clio.schema import add_schema_version
from clio.ui.services.file_service import _is_safe_basename, _save_atomic

if TYPE_CHECKING:
    from clio.ui.handler_protocol import HandlerProtocol


def handle_get_plans(handler: HandlerProtocol, qs: dict[str, Any]) -> None:
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


def handle_get_plan(handler: HandlerProtocol, qs: dict[str, Any]) -> None:
    """Handle GET /api/plan."""
    day = qs.get("day", [""])[0]
    if not _is_safe_basename(day) or not day:
        return handler._send_json({"error": "forbidden"}, 403)
    proj_out = handler._get_project_output(qs)
    p = proj_out / "plans" / f"{day}_plan.json"
    if not p.is_file():
        return handler._send_json({"error": f"规划文件不存在: {p}"}, 404)
    handler._send_bytes(p.read_bytes(), "application/json; charset=utf-8")


def handle_put_plan(handler: HandlerProtocol, qs: dict[str, Any], obj: dict) -> None:
    """Handle PUT /api/plan."""
    day = qs.get("day", [""])[0]
    if not _is_safe_basename(day) or not day:
        return handler._send_json({"ok": False, "error": "forbidden"}, 403)
    proj_out = handler._get_project_output(qs)
    p = proj_out / "plans" / f"{day}_plan.json"
    plan = Plan.from_dict(obj if isinstance(obj, dict) else {})
    issues = plan.validate_for_save()
    if issues:
        return handler._send_json(
            {
                "ok": False,
                "error": issues[0].message,
                "issues": [i.to_dict() for i in issues],
            },
            400,
        )
    data = add_schema_version(plan.to_dict())
    payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    p.parent.mkdir(parents=True, exist_ok=True)
    _save_atomic(p, payload)
    handler._send_json({"ok": True, "path": str(p)})


def handle_post_cut(handler: HandlerProtocol, qs: dict[str, list[str]], obj: dict) -> None:
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
    proj_dir = handler._resolve_project_dir(qs)
    cfg = handler._get_config(proj_dir)

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
