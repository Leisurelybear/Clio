"""Route handlers: /api/run/start, /api/run/status, /api/rerun"""

from __future__ import annotations

import copy
import json
import threading
import traceback
from pathlib import Path
from typing import TYPE_CHECKING

from vlog_tool.pipeline import run_analyze_all, run_compress_all, run_generate_scripts, run_pipeline_steps
from vlog_tool.tasks.transcribe import run_transcribe_one
from vlog_tool.progress import ProgressTracker
from vlog_tool.ui.services.file_service import _find_original_for_compressed, _find_texts_dirs, _is_safe_basename
from vlog_tool.ui.services.project_service import _project_output_dir

if TYPE_CHECKING:
    from http.server import BaseHTTPRequestHandler


def handle_get_run_status(handler: BaseHTTPRequestHandler, qs: dict) -> None:
    """Handle GET /api/run/status."""
    progress_file = handler._get_project_output(qs) / ".progress.json"
    if progress_file.is_file():
        try:
            data = json.loads(progress_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {"status": "unknown"}
    else:
        data = {"status": "idle"}
    with handler.__class__._run_lock:
        running = handler._run_thread is not None and handler._run_thread.is_alive()
    data["running"] = running
    handler._send_json(data)


def handle_post_run_start(handler: BaseHTTPRequestHandler, qs: dict, obj: dict) -> None:
    """Handle POST /api/run/start."""
    day_label = obj.get("day_label", "day1")
    steps = obj.get("steps")
    proj_input = handler._resolve_project_input(qs)
    cfg = handler._get_config(proj_input)
    if "use_transcripts" in obj:
        cfg.plan.use_transcripts = obj["use_transcripts"]

    def _run():
        tracker = ProgressTracker(cfg.paths.output_dir)
        try:
            run_pipeline_steps(cfg, day_label, steps, tracker=tracker)
        except Exception:
            tracker.error("pipeline failed")
            traceback.print_exc()

    with handler.__class__._run_lock:
        if handler._run_thread is not None and handler._run_thread.is_alive():
            return handler._send_json({"ok": False, "error": "pipeline is already running"}, 409)
        handler._run_thread = threading.Thread(target=_run, daemon=True)
        handler._run_thread.start()
    label = "+".join(steps) if steps else "all"
    handler._send_json({"ok": True, "message": f"pipeline started ({label})"})


def handle_post_rerun(handler: BaseHTTPRequestHandler, qs: dict, obj: dict) -> None:
    """Handle POST /api/rerun."""
    proj_input = handler._resolve_project_input(qs)
    cfg = handler._get_config(proj_input)
    proj_out = _project_output_dir(proj_input)

    video_basename = (obj.get("video") or "").strip()
    task = (obj.get("task") or "").strip()
    if not video_basename or not _is_safe_basename(video_basename):
        return handler._send_json({"ok": False, "error": "invalid video filename"}, 400)
    if task not in ("compress", "analyze", "texts", "voiceover", "transcribe", "all"):
        return handler._send_json(
            {
                "ok": False,
                "error": "requires video (filename) and task (compress|analyze|texts|voiceover|transcribe|all)",
            },
            400,
        )
    # 向后兼容
    if task == "texts":
        task = "analyze"

    stem = Path(video_basename).stem

    # Resolve original video path
    source_view = obj.get("source", "compressed")
    if source_view == "original":
        original_video = proj_input / video_basename
        if not original_video.is_file():
            # Maybe frontend sent a compressed filename with source:original
            # (e.g. from original view where v.file is actually compressed name).
            # Try resolving via _find_original_for_compressed as fallback.
            original_name = _find_original_for_compressed(stem, proj_input)
            if not original_name:
                return handler._send_json({"ok": False, "error": f"original video not found: {video_basename}"}, 404)
            original_video = proj_input / original_name
    else:
        original_name = _find_original_for_compressed(stem, proj_input)
        if not original_name:
            return handler._send_json({"ok": False, "error": f"no matching original video for {stem}"}, 404)
        original_video = proj_input / original_name

    # Resolve texts JSON path (for voiceover rerun)
    index_prefix = obj.get("index") or (stem.split("_", 1)[0] if "_" in stem else stem)
    texts_json = None
    if task in ("voiceover", "all"):
        for td in _find_texts_dirs(proj_out):
            candidates = sorted(td.glob(f"{index_prefix}_*.json"))
            if candidates:
                texts_json = candidates[0]
                break
        if texts_json is None:
            return handler._send_json({"ok": False, "error": f"no analysis result found for {stem}"}, 404)

    def _rerun_worker(
        cfg=cfg,
        task=task,
        video_basename=video_basename,
        original_video=original_video,
        texts_json=texts_json,
        proj_out=proj_out,
    ):
        # Deep-copy config, force redo (user clicked rerun => regenerate everything)
        cfg = copy.deepcopy(cfg)
        cfg.analyze.skip_existing = False
        tracker = ProgressTracker(proj_out, rerun=True, rerun_video=video_basename)

        def _log(msg: str) -> None:
            print(f"  [rerun] {msg}")
            tracker.log(msg)

        try:
            _log(f"▶ Starting rerun {task} — {video_basename}")
            if task in ("compress", "all"):
                _log("Step: compressing video...")
                run_compress_all(cfg, tracker=tracker, single_file=original_video)
                _log("✓ compression complete")
            if task in ("analyze", "all"):
                _log("Step: AI analyzing video...")
                run_analyze_all(cfg, tracker=tracker, single_file=original_video)
                _log("✓ analysis complete")
            if task in ("voiceover", "all"):
                _log("Step: generating voiceover script...")
                run_generate_scripts(cfg, tracker=tracker, single_file=texts_json)
                _log("✓ voiceover generation complete")
            if task in ("transcribe", "all"):
                _log("Step: transcribing audio...")
                from vlog_tool.transcribe import check_whisper

                if not check_whisper():
                    raise RuntimeError("faster-whisper 未安装。执行: python main.py whisper install")
                _log(f"original_video={original_video}, exists={original_video.is_file()}")
                result = run_transcribe_one(cfg, original_video)
                if "error" in result:
                    _log(f"✗ transcription failed: {result['error']}")
                    raise RuntimeError(result["error"])
                _log(f"✓ transcription complete, output_dir={cfg.paths.output_dir}")
            tracker.done(f"{task} → {video_basename} complete")
            print(f"  [rerun] ✓ {task} -> {video_basename} complete")
        except Exception as e:
            print(f"  [rerun] ✗ rerun failed: {e}")
            tracker.error(f"rerun failed: {e}")
            traceback.print_exc()

    with handler.__class__._run_lock:
        if handler._run_thread is not None and handler._run_thread.is_alive():
            return handler._send_json({"ok": False, "error": "a task is already running"}, 409)
        handler._run_thread = threading.Thread(target=_rerun_worker, daemon=True)
        handler._run_thread.start()
    handler._send_json({"ok": True, "message": f"started rerun {task} ({video_basename})"})
