"""Video editing software draft export."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from clio.export.jianying import export_plan_to_jianying

FORMAT_REGISTRY: dict[str, Callable[..., Path]] = {"jianying": export_plan_to_jianying}


def export_plan(
    format: str,
    plan_path: Path,
    output_dir: Path,
    media_dir: Path | None = None,
    day_label: str = "day1",
    *,
    project_dir: Path | None = None,
    input_dir: Path | None = None,
    **kwargs,
) -> Path:
    """Export plan to the specified format.

    Preferred: pass project_dir= (reads videos.json).
    Legacy: 4th positional / input_dir= is a media directory scanned with find_videos
    when project_dir is not set.

    Returns path to the output draft directory.
    """
    exporter = FORMAT_REGISTRY.get(format)
    if exporter is None:
        raise ValueError(f"Unknown export format: {format}. Available: {list(FORMAT_REGISTRY)}")
    legacy_media = input_dir if input_dir is not None else media_dir
    return exporter(
        plan_path,
        output_dir,
        legacy_media,
        day_label,
        project_dir=project_dir,
        **kwargs,
    )
