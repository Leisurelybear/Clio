"""API handler for Whisper installation check and model download."""

from __future__ import annotations

import json
import os
import sys as _sys
import threading
import time
from pathlib import Path

from vlog_tool.transcribe import _resolve_cache_dir, check_whisper
from vlog_tool.utils import run_subprocess


def handle_get_whisper_check(handler) -> None:
    installed = check_whisper()
    cuda = False
    if installed:
        try:
            from ctranslate2 import get_cuda_device_count

            cuda = get_cuda_device_count() > 0
        except ImportError:
            pass

    cache_path = None
    try:
        from vlog_tool.config import load_config

        cfg = load_config()
        cache_dir = _resolve_cache_dir(cfg)
        if cache_dir.is_dir():
            cache_path = str(cache_dir)
    except Exception:
        pass

    handler._send_json(
        {
            "ok": True,
            "installed": installed,
            "cuda": cuda,
            "cache_path": cache_path,
        }
    )


# ── Whisper model download ──────────────────────────────────────────────────

_INSTALL_LOCK = threading.Lock()
_INSTALL_THREAD: threading.Thread | None = None


def _install_progress_path(handler) -> Path:
    proj_out = handler._get_project_output({})
    return proj_out / ".whisper_install.json"


def _write_install_progress(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = os.urandom(4).hex()
    tmp = path.parent / f"{path.name}.{suffix}.tmp"
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        tmp.unlink(missing_ok=True)


def handle_get_whisper_install_status(handler) -> None:
    path = _install_progress_path(handler)
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {"status": "idle"}
    else:
        data = {"status": "idle"}
    with _INSTALL_LOCK:
        running = _INSTALL_THREAD is not None and _INSTALL_THREAD.is_alive()
    data["running"] = running
    handler._send_json(data)


def handle_post_whisper_install(handler) -> None:
    global _INSTALL_THREAD

    with _INSTALL_LOCK:
        if _INSTALL_THREAD is not None and _INSTALL_THREAD.is_alive():
            handler._send_json({"ok": False, "error": "download is already running"}, 409)
            return
        progress_path = _install_progress_path(handler)

        def _worker():
            try:
                _run_install(handler, progress_path)
            except Exception as e:
                _write_install_progress(
                    progress_path,
                    {
                        "status": "error",
                        "progress_pct": 0,
                        "message": f"安装失败: {e}",
                    },
                )

        _INSTALL_THREAD = threading.Thread(target=_worker, daemon=True)
        _INSTALL_THREAD.start()

    handler._send_json({"ok": True, "message": "whisper install started"})


def _run_install(handler, progress_path: Path) -> None:
    proj_input = handler._resolve_project_input({})
    cfg = handler._get_config(proj_input)

    # Step 1: ensure huggingface_hub is installed
    _write_install_progress(
        progress_path,
        {
            "status": "downloading",
            "progress_pct": 0,
            "message": "检查 huggingface_hub 依赖...",
        },
    )
    try:
        import huggingface_hub  # noqa: F401
    except ImportError:
        r = run_subprocess(
            [_sys.executable, "-m", "pip", "install", "huggingface_hub", "-q"],
            capture_output=True,
            text=True,
        )
        if r.returncode != 0:
            raise RuntimeError(f"安装 huggingface_hub 失败: {r.stderr}")

    from huggingface_hub import hf_hub_download  # noqa

    # Set env vars for China mirror
    if cfg.whisper.hf_endpoint:
        os.environ["HF_ENDPOINT"] = cfg.whisper.hf_endpoint
    if cfg.proxy.enabled and cfg.proxy.url:
        os.environ["HTTP_PROXY"] = cfg.proxy.url
        os.environ["HTTPS_PROXY"] = cfg.proxy.url

    # Step 2: download model
    cache_dir = _resolve_cache_dir(cfg)
    cache_dir.mkdir(parents=True, exist_ok=True)
    model_name = cfg.whisper.model_size
    repo_id = f"Systran/faster-whisper-{model_name}"

    _write_install_progress(
        progress_path,
        {
            "status": "downloading",
            "progress_pct": 0,
            "message": f"正在下载模型 {model_name}...",
        },
    )

    start = time.monotonic()
    last_pct = 0
    last_bytes = 0

    def _callback(current: int, total: int | None) -> None:
        nonlocal last_pct, last_bytes
        if total:
            pct = int(current / total * 100)
            elapsed = time.monotonic() - start
            speed_bps = (current - last_bytes) / max(elapsed, 0.1)
            speed_str = (
                f"{speed_bps / 1024 / 1024:.1f} MB/s" if speed_bps > 1024 * 1024 else f"{speed_bps / 1024:.0f} KB/s"
            )
            eta_sec = int((total - current) / max(speed_bps, 1))
            if pct >= last_pct + 2 or pct == 100:
                _write_install_progress(
                    progress_path,
                    {
                        "status": "downloading",
                        "progress_pct": pct,
                        "message": f"下载模型 {model_name} ({pct}%)",
                        "speed": speed_str,
                        "eta_sec": eta_sec,
                    },
                )
                last_pct = pct
            last_bytes = current

    try:
        hf_hub_download(
            repo_id=repo_id,
            filename="model.bin",
            cache_dir=str(cache_dir),
            resume_download=True,
            local_dir_use_symlinks=False,
            callback=_callback,
        )
    except Exception as e:
        raise RuntimeError(f"模型下载失败: {e}") from e

    _write_install_progress(
        progress_path,
        {
            "status": "done",
            "progress_pct": 100,
            "message": f"模型 {model_name} 下载完成",
        },
    )
