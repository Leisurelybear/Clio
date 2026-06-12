"""Pipeline orchestration — imports all task functions from vlog_tool/tasks/.
All public symbols are re-exported for backward compatibility."""

from __future__ import annotations

# Keep these orchestration-specific items in pipeline.py
from vlog_tool.config import AppConfig
from vlog_tool.log import timed
from vlog_tool.progress import ProgressTracker

# Re-export everything for backward compatibility (imported by main.py, ui)
from vlog_tool.tasks._helpers import (
    ClipRecord,  # noqa: F401
    _build_stem,  # noqa: F401
    _eta_line,  # noqa: F401
    _next_index,  # noqa: F401
    _rewrite_script_md,  # noqa: F401
    _rewrite_text_file,  # noqa: F401
    _write_csv,  # noqa: F401
    _write_text_file,  # noqa: F401
)
from vlog_tool.tasks.analyze import run_analyze_all  # noqa: F401
from vlog_tool.tasks.compress import run_compress_all  # noqa: F401
from vlog_tool.tasks.cut import run_cut_all  # noqa: F401
from vlog_tool.tasks.label import run_label_videos  # noqa: F401
from vlog_tool.tasks.plan import run_plan_vlog  # noqa: F401
from vlog_tool.tasks.refine import run_refine_scripts, run_refine_texts  # noqa: F401
from vlog_tool.tasks.scripts import run_generate_scripts  # noqa: F401


def run_full_pipeline(config: AppConfig, day_label: str = "day1") -> None:
    config.paths.output_dir.mkdir(parents=True, exist_ok=True)
    with timed("=== 1/5 压缩原视频 ==="):
        run_compress_all(config)
    with timed("=== 2/5 AI 分析素材 ==="):
        run_analyze_all(config)
    with timed("=== 3/5 生成口播文案 ==="):
        run_generate_scripts(config)
    with timed("=== 4/5 vlog 剪辑规划 ==="):
        run_plan_vlog(config, day_label)
    with timed("=== 5/5 烧录序号标注 ==="):
        run_label_videos(config)
    print("\n完成！输出目录:", config.paths.output_dir)


_STEP_LABELS = {
    "compress": "压缩原视频",
    "analyze": "AI 分析素材",
    "voiceover": "生成口播文案",
    "plan": "vlog 剪辑规划",
    "label": "烧录序号标注",
}

_STEP_FUNCS = {
    "compress": run_compress_all,
    "analyze": run_analyze_all,
    "voiceover": run_generate_scripts,
    "plan": run_plan_vlog,
    "label": run_label_videos,
}

_STEP_DAY_ARG = {"plan"}


def run_pipeline_steps(
    config: AppConfig,
    day_label: str = "day1",
    steps: list[str] | None = None,
    tracker: ProgressTracker | None = None,
) -> None:
    """运行指定步骤列表（可选的进度跟踪）。

    steps 取值: analyze, voiceover, plan, label（默认全部）。
    """
    config.paths.output_dir.mkdir(parents=True, exist_ok=True)
    if not steps:
        steps = list(_STEP_FUNCS.keys())

    if tracker is None:
        tracker = ProgressTracker(config.paths.output_dir)

    try:
        for step in steps:
            label = _STEP_LABELS.get(step, step)
            if tracker:
                tracker.update(phase=step, current=0, total=1, message=f"{label}...")
            with timed(f"=== {label} ==="):
                fn = _STEP_FUNCS[step]
                if step in _STEP_DAY_ARG:
                    fn(config, day_label, tracker)
                else:
                    fn(config, tracker)
        tracker.done(f"完成！输出目录: {config.paths.output_dir}")
    except Exception as e:
        tracker.error(str(e))
        raise
