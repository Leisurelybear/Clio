"""API handler for Whisper installation check and model download."""

from __future__ import annotations

import json
import os
import shutil
import sys as _sys
import threading
import time
from pathlib import Path

from vlog_tool.config import WhisperModelSize
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


# ── Whisper model management ─────────────────────────────────────────────────


def _get_cache_dir(handler) -> Path:
    proj_input = handler._resolve_project_input({})
    cfg = handler._get_config(proj_input)
    return _resolve_cache_dir(cfg)


def _list_cached_models(cache_dir: Path) -> list[dict]:
    """Scan cache_dir for downloaded faster-whisper models."""
    if not cache_dir.is_dir():
        return []
    models = []
    for entry in cache_dir.iterdir():
        if not entry.is_dir():
            continue
        name = entry.name
        # HuggingFace cache dirs look like: models--Systran--faster-whisper-{size}
        if "faster-whisper" not in name.lower():
            continue
        snapshots = entry / "snapshots"
        if not snapshots.is_dir():
            continue
        total_size = 0
        model_file_found = False
        for snap_dir in snapshots.iterdir():
            if not snap_dir.is_dir():
                continue
            for f in snap_dir.rglob("*"):
                if f.is_file():
                    try:
                        sz = f.stat().st_size
                        total_size += sz
                        if sz > 100 * 1024 * 1024:
                            model_file_found = True
                    except OSError:
                        pass
        # Extract model size from dir name
        model_size = name.rsplit("-", 1)[-1] if "-" in name else name
        models.append(
            {
                "name": model_size,
                "size_bytes": total_size,
                "size_display": _format_bytes(total_size),
                "valid": model_file_found,
            }
        )
    return models


def _format_bytes(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    elif n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    elif n < 1024 * 1024 * 1024:
        return f"{n / (1024 * 1024):.1f} MB"
    return f"{n / (1024 * 1024 * 1024):.2f} GB"


def handle_get_whisper_models(handler) -> None:
    """GET /api/whisper/models — list cached models and available model sizes."""
    cache_dir = _get_cache_dir(handler)
    cached = _list_cached_models(cache_dir)
    available = list(WhisperModelSize)
    # Get current configured model
    proj_input = handler._resolve_project_input({})
    cfg = handler._get_config(proj_input)
    current_model = cfg.whisper.model_size
    # Disk space info
    free_bytes = 0
    try:
        if cache_dir.is_dir():
            free_bytes = shutil.disk_usage(cache_dir).free
        else:
            free_bytes = shutil.disk_usage(cache_dir.parent).free
    except OSError:
        pass
    handler._send_json(
        {
            "ok": True,
            "cached": cached,
            "available": [{"name": m.value, "label": m.value} for m in available],
            "current_model": current_model,
            "cache_dir": str(cache_dir),
            "free_bytes": free_bytes,
            "free_display": _format_bytes(free_bytes),
        }
    )


def handle_post_whisper_model_delete(handler, qs: dict, obj: dict) -> None:
    """POST /api/whisper/models/delete — delete a cached model."""
    model_name = (obj.get("name") or "").strip()
    if not model_name:
        handler._send_json({"ok": False, "error": "missing model name"}, 400)
        return
    cache_dir = _get_cache_dir(handler)
    if not cache_dir.is_dir():
        handler._send_json({"ok": False, "error": "cache dir not found"}, 404)
        return
    deleted = False
    for entry in cache_dir.iterdir():
        if not entry.is_dir():
            continue
        if model_name.lower() in entry.name.lower() and "faster-whisper" in entry.name.lower():
            try:
                shutil.rmtree(entry)
                deleted = True
            except OSError as e:
                handler._send_json({"ok": False, "error": f"删除失败: {e}"}, 500)
                return
    handler._send_json({"ok": True, "deleted": deleted})


def handle_put_whisper_model(handler, qs: dict, obj: dict) -> None:
    """PUT /api/whisper/model — set active model size."""
    model_name = (obj.get("model_size") or "").strip()
    if not model_name:
        handler._send_json({"ok": False, "error": "missing model_size"}, 400)
        return
    if model_name not in list(WhisperModelSize):
        handler._send_json(
            {
                "ok": False,
                "error": f"invalid model_size, must be one of: {', '.join(WhisperModelSize)}",
            },
            400,
        )
        return
    # Write to project.yaml or global config
    proj_input = handler._resolve_project_input({})
    proj_yaml = proj_input / "project.yaml"
    import yaml

    if proj_yaml.is_file():
        with open(proj_yaml, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        raw.setdefault("whisper", {})["model_size"] = model_name
        suffix = os.urandom(4).hex()
        tmp = proj_yaml.parent / f"{proj_yaml.name}.{suffix}.tmp"
        try:
            tmp.write_text(yaml.dump(raw, allow_unicode=True, default_flow_style=False), encoding="utf-8")
            tmp.replace(proj_yaml)
        except OSError:
            tmp.unlink(missing_ok=True)
            handler._send_json({"ok": False, "error": "写入配置文件失败"}, 500)
            return
    handler._send_json({"ok": True, "model_size": model_name})
