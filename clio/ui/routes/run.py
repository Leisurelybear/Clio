"""Route handlers: /api/run/start, /api/run/status, /api/rerun"""

from __future__ import annotations

import copy
import json
import re
import threading
import time
import traceback
from pathlib import Path
from typing import TYPE_CHECKING, Any

from clio.pipeline import run_analyze_all, run_compress_all, run_generate_scripts, run_pipeline_steps
from clio.progress import ProgressTracker
from clio.tasks.transcribe import run_transcribe_one
from clio.ui.services.file_service import _find_original_for_compressed, _find_texts_dirs, _is_safe_basename
from clio.ui.services.project_service import _project_output_dir
from clio.ui.services.run_preview import build_run_preview

if TYPE_CHECKING:
    from clio.ui.handler_protocol import HandlerProtocol


def _apply_run_input_dir_override(cfg, input_dir_raw: str | None) -> tuple[Any, str | None]:
    """Return a run-local config copy when the request overrides input_dir."""
    if input_dir_raw is None:
        return cfg, None
    if not isinstance(input_dir_raw, str):
        return cfg, "input_dir must be a string"
    input_dir_raw = input_dir_raw.strip()
    if not input_dir_raw:
        return cfg, None
    input_dir = Path(input_dir_raw).expanduser()
    if not input_dir.is_dir():
        return cfg, f"input_dir not found: {input_dir_raw}"
    run_cfg = copy.deepcopy(cfg)
    try:
        run_cfg.paths.input_dir = input_dir
    except AttributeError:
        if run_cfg.paths._project is not None:
            run_cfg.paths._project.input_dir = input_dir
        else:
            return cfg, "project paths not available for input_dir override"
    return run_cfg, None


def handle_get_run_stream(handler: HandlerProtocol, qs: dict[str, Any]) -> None:
    """GET /api/run/stream — SSE endpoint for real-time run status."""
    proj_input = handler._resolve_project_input(qs)
    state = handler._get_state(str(proj_input.resolve()))
    progress_file = handler._get_project_output(qs) / ".progress.json"

    handler.send_response(200)
    handler.send_header("Content-Type", "text/event-stream")
    handler.send_header("Cache-Control", "no-cache")
    handler.send_header("Connection", "keep-alive")
    handler.send_header("X-Accel-Buffering", "no")
    handler.end_headers()

    last_data = ""
    try:
        while True:
            if progress_file.is_file():
                try:
                    raw = progress_file.read_text(encoding="utf-8")
                except OSError:
                    time.sleep(0.5)
                    continue
                if raw != last_data:
                    try:
                        parsed = json.loads(raw)
                    except json.JSONDecodeError:
                        time.sleep(0.5)
                        continue
                    last_data = raw
                    with state.run_lock:
                        running = state.run_thread is not None and state.run_thread.is_alive()
                    parsed["running"] = running
                    if parsed.get("status") == "running" and not running:
                        parsed["status"] = "idle"
                    msg = json.dumps(parsed, ensure_ascii=False)
                    handler.wfile.write(f"data: {msg}\n\n".encode())
                    handler.wfile.flush()

                    if parsed.get("status") in ("done", "error", "cancelled"):
                        break
            else:
                if last_data != "_idle":
                    last_data = "_idle"
                    handler.wfile.write(b'data: {"status":"idle"}\n\n')
                    handler.wfile.flush()

            time.sleep(0.5)
    except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
        pass  # Client disconnected


def handle_get_run_status(handler: HandlerProtocol, qs: dict[str, Any]) -> None:
    """Handle GET /api/run/status."""
    proj_input = handler._resolve_project_input(qs)
    state = handler._get_state(str(proj_input.resolve()))
    progress_file = handler._get_project_output(qs) / ".progress.json"
    if progress_file.is_file():
        try:
            data = json.loads(progress_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {"status": "unknown"}
    else:
        data = {"status": "idle"}
    with state.run_lock:
        running = state.run_thread is not None and state.run_thread.is_alive()
    data["running"] = running
    if data.get("status") == "running" and not running:
        data["status"] = "idle"
        data["message"] = ""
        try:
            progress_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
    handler._send_json(data)


def handle_post_run_start(handler: HandlerProtocol, qs: dict[str, Any], obj: dict) -> None:
    """Handle POST /api/run/start."""
    day_label = obj.get("day_label", "day1")
    steps = obj.get("steps")
    proj_input = handler._resolve_project_input(qs)
    cfg = handler._get_config(proj_input)
    cfg, cfg_error = _apply_run_input_dir_override(cfg, obj.get("input_dir"))
    if cfg_error:
        return handler._send_json({"ok": False, "error": cfg_error}, 400)
    state = handler._get_state(str(proj_input.resolve()))
    if "use_transcripts" in obj:
        cfg.plan.use_transcripts = obj["use_transcripts"]
    files_list = obj.get("files")
    if files_list is not None and not isinstance(files_list, list):
        return handler._send_json({"ok": False, "error": "files must be a list of video names"}, 400)
    overwrite = obj.get("overwrite", False)
    context_override = obj.get("context_override") or None
    task_prompts = obj.get("task_prompts") or None

    with state.run_lock:
        if state.run_thread is not None and state.run_thread.is_alive():
            return handler._send_json({"ok": False, "error": "pipeline is already running"}, 409)

        # Write initial progress after confirming the run slot is reserved,
        # so a duplicate request cannot clobber .progress.json before the 409.
        pre_tracker = ProgressTracker(cfg.paths.output_dir)
        pre_tracker.update(phase="启动", current=0, total=0, message="流水线启动中...")

        def _run():
            state.cancel_event.clear()
            tracker = ProgressTracker(cfg.paths.output_dir)
            try:
                run_pipeline_steps(
                    cfg,
                    day_label,
                    steps,
                    tracker=tracker,
                    cancel_event=state.cancel_event,
                    files=files_list,
                    overwrite=overwrite,
                    context_override=context_override,
                    task_prompts=task_prompts,
                )
            except Exception:
                tracker.error("pipeline failed")
                traceback.print_exc()
            finally:
                with state.run_lock:
                    state.run_thread = None

        state.run_thread = threading.Thread(target=_run, daemon=True)
        state.run_thread.start()
    label = "+".join(steps) if steps else "all"
    handler._send_json({"ok": True, "message": f"pipeline started ({label})"})


def handle_post_run_preview(handler: HandlerProtocol, qs: dict[str, Any], obj: dict) -> None:
    """Handle POST /api/run/preview."""
    day_label = obj.get("day_label", "day1")
    steps = obj.get("steps")
    files_list = obj.get("files")
    if files_list is not None and not isinstance(files_list, list):
        return handler._send_json({"ok": False, "error": "files must be a list of video names"}, 400)

    proj_input = handler._resolve_project_input(qs)
    cfg = handler._get_config(proj_input)
    preview = build_run_preview(
        cfg,
        steps or [],
        force=bool(obj.get("overwrite", False)),
        use_transcripts=obj.get("use_transcripts", True),
        files=files_list,
        day_label=day_label,
    )
    handler._send_json({"ok": True, "preview": preview})


def handle_post_run_cancel(handler: HandlerProtocol, qs: dict[str, Any], obj: dict) -> None:
    """Handle POST /api/run/cancel."""
    proj_input = handler._resolve_project_input(qs)
    state = handler._get_state(str(proj_input.resolve()))
    state.cancel_event.set()
    handler._send_json({"ok": True, "message": "取消请求已发送"})


def handle_post_rerun(handler: HandlerProtocol, qs: dict[str, Any], obj: dict) -> None:
    """Handle POST /api/rerun."""
    proj_input = handler._resolve_project_input(qs)
    cfg = handler._get_config(proj_input)
    state = handler._get_state(str(proj_input.resolve()))
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
            original_name = _find_original_for_compressed(stem, proj_input, cfg.compressed_dir)
            if not original_name:
                return handler._send_json({"ok": False, "error": f"original video not found: {video_basename}"}, 404)
            original_video = proj_input / original_name
    else:
        original_name = _find_original_for_compressed(stem, proj_input, cfg.compressed_dir)
        if not original_name:
            return handler._send_json({"ok": False, "error": f"no matching original video for {stem}"}, 404)
        original_video = proj_input / original_name

    # Resolve texts JSON path (for voiceover rerun)
    raw_index = obj.get("index") or ""
    index_prefix = (
        re.sub(r"[^a-zA-Z0-9_-]", "", raw_index) if raw_index else (stem.split("_", 1)[0] if "_" in stem else stem)
    )
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
        cancel_event=state.cancel_event,
    ):
        cancel_event.clear()
        # Deep-copy config, force redo (user clicked rerun => regenerate everything)
        cfg = copy.deepcopy(cfg)
        cfg.analyze.skip_existing = False
        tracker = ProgressTracker(proj_out, rerun=True, rerun_video=video_basename)

        def _log(msg: str) -> None:
            print(f"  [rerun] {msg}")
            tracker.log(msg)

        try:
            _log(f"▶ Starting rerun {task} — {video_basename}")
            for step_name, step_fn, step_label in [
                (
                    "compress",
                    lambda: run_compress_all(
                        cfg, tracker=tracker, single_file=original_video, cancel_event=cancel_event
                    ),
                    "压缩视频",
                ),
                (
                    "analyze",
                    lambda: run_analyze_all(
                        cfg, tracker=tracker, single_file=original_video, cancel_event=cancel_event
                    ),
                    "AI 分析",
                ),
                (
                    "voiceover",
                    lambda: run_generate_scripts(
                        cfg, tracker=tracker, single_file=texts_json, cancel_event=cancel_event
                    ),
                    "生成口播",
                ),
            ]:
                if task not in (step_name, "all"):
                    continue
                if cancel_event.is_set():
                    _log(f"✗ 取消: {step_label}")
                    raise RuntimeError(f"rerun 被用户取消（{step_label}）")
                _log(f"Step: {step_label}...")
                step_fn()
                _log(f"✓ {step_label} complete")
            if task in ("transcribe", "all"):
                if cancel_event.is_set():
                    _log("✗ 取消: 转录")
                    raise RuntimeError("rerun 被用户取消（转录）")
                _log("Step: transcribing audio...")
                from clio.transcribe import check_whisper

                if not check_whisper():
                    raise RuntimeError("faster-whisper 未安装。执行: python main.py whisper install")
                _log(f"original_video={original_video}, exists={original_video.is_file()}")
                result = run_transcribe_one(
                    cfg,
                    original_video,
                    cancel_event=cancel_event,
                    progress_callback=lambda pct: tracker.update(
                        phase="transcribe", current=pct, total=100, message=f"{video_basename}: 转录 ({pct}%)"
                    ),
                )
                if "error" in result:
                    _log(f"✗ transcription failed: {result['error']}")
                    raise RuntimeError(result["error"])
                _log(f"✓ transcription complete, output_dir={cfg.paths.output_dir}")
            tracker.done(f"{task} → {video_basename} complete")
            print(f"  [rerun] ✓ {task} -> {video_basename} complete")
        except RuntimeError as e:
            msg = str(e)
            if "被用户取消" in msg:
                tracker.cancelled(msg)
            else:
                tracker.error(f"rerun failed: {e}")
            print(f"  [rerun] ✗ {msg}")
        except Exception as e:
            print(f"  [rerun] ✗ rerun failed: {e}")
            tracker.error(f"rerun failed: {e}")
            traceback.print_exc()
        finally:
            with state.run_lock:
                state.run_thread = None

    with state.run_lock:
        if state.run_thread is not None and state.run_thread.is_alive():
            return handler._send_json({"ok": False, "error": "a task is already running"}, 409)
        state.run_thread = threading.Thread(target=_rerun_worker, daemon=True)
        state.run_thread.start()
    handler._send_json({"ok": True, "message": f"started rerun {task} ({video_basename})"})
