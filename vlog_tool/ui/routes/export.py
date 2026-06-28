"""Export routes for plan to video editing software drafts."""

from __future__ import annotations

from vlog_tool.export import export_plan
from vlog_tool.ui.handler_protocol import HandlerProtocol


def handle_post_export(
    handler: HandlerProtocol,
    qs: dict[str, list[str]],
    obj: dict,
) -> None:
    """POST /api/export — export plan to JianYing draft."""
    day = obj.get("day", "day1")
    fmt = obj.get("format", "jianying")

    proj_input = handler._resolve_project_input(qs)
    cfg = handler._get_config(proj_input)

    plan_path = cfg.plans_dir / f"{day}_plan.json"
    if not plan_path.is_file():
        handler._send_json({"ok": False, "error": f"plan 文件不存在: {plan_path}"}, 404)
        return

    out_dir = cfg.paths.output_dir / "export" / f"{day}_{fmt}"
    try:
        result_path = export_plan(
            fmt,
            plan_path,
            out_dir,
            cfg.paths.input_dir,
            day,
            ffprobe=cfg.paths.ffprobe,
            texts_dir=cfg.texts_dir,
            canvas_ratio=cfg.export.canvas_ratio,
        )
    except (FileNotFoundError, ValueError) as e:
        handler._send_json({"ok": False, "error": str(e)}, 400)
        return

    handler._send_json({"ok": True, "path": str(result_path)})
