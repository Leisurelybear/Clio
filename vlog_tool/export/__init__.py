"""Video editing software draft export."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from vlog_tool.export.jianying import export_plan_to_jianying

FORMAT_REGISTRY: dict[str, Callable[..., Path]] = {"jianying": export_plan_to_jianying}


def export_plan(
    format: str,
    plan_path: Path,
    output_dir: Path,
    input_dir: Path,
    day_label: str = "day1",
    **kwargs,
) -> Path:
    """Export plan to the specified format.

    Returns path to the output draft directory.
    """
    exporter = FORMAT_REGISTRY.get(format)
    if exporter is None:
        raise ValueError(f"Unknown export format: {format}. Available: {list(FORMAT_REGISTRY)}")
    return exporter(plan_path, output_dir, input_dir, day_label, **kwargs)
