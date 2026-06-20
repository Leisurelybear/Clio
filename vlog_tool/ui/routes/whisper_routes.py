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
_INSTALL_CANCEL = threading.Event()


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
    # Detect stale "downloading" state (process killed mid-download)
    if data.get("status") in ("downloading",) and not running:
        data = {"status": "idle", "message": "上次下载中断，可重新开始"}
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


def handle_post_whisper_install_cancel(handler) -> None:
    """POST /api/whisper/install/cancel — cancel ongoing download."""
    global _INSTALL_CANCEL
    _INSTALL_CANCEL.set()
    # Clean up partial progress state
    path = _install_progress_path(handler)
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("status") == "downloading":
                # Mark as cancelled so frontend shows correct state
                _write_install_progress(
                    path,
                    {"status": "idle", "progress_pct": 0, "message": "下载已取消"},
                )
        except (json.JSONDecodeError, OSError):
            pass
    handler._send_json({"ok": True, "message": "cancel requested"})


_KNOWN_MODEL_SIZES: dict[str, int] = {
    "tiny": 151_362_048,
    "base": 290_574_848,
    "small": 483_382_016,
    "medium": 1_536_351_744,
    "large-v2": 3_076_648_960,
    "large-v3": 3_076_648_960,
}


def _get_model_file_size(repo_id: str, cfg) -> int:
    """Get the remote model file size via HEAD request, with known-size fallback."""
    import requests as _req
    from huggingface_hub import hf_hub_url

    proxy_url = cfg.proxy.url if (cfg.proxy.enabled and cfg.proxy.url) else None
    proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None
    try:
        url = hf_hub_url(repo_id, filename="model.bin")
        r = _req.head(url, proxies=proxies, timeout=15, allow_redirects=True)
        r.raise_for_status()
        size = int(r.headers.get("Content-Length", 0))
        if size:
            return size
    except Exception:
        pass
    # Fallback: known model sizes
    for key, sz in _KNOWN_MODEL_SIZES.items():
        if key in repo_id:
            return sz
    return 0


def _download_error_detail(e: Exception, cfg) -> str:
    """Build a user-friendly error message for download failures."""
    proxy_url = cfg.proxy.url if (cfg.proxy.enabled and cfg.proxy.url) else None
    endpoint = cfg.whisper.hf_endpoint or "https://huggingface.co"
    msg = [f"模型下载失败: {e}"]
    msg.append(f"  Endpoint: {endpoint}")
    msg.append(f"  Proxy: {proxy_url or '无'}")
    if "10061" in str(e) or "refused" in str(e).lower():
        msg.append("  提示: 连接被拒绝。请检查:")
        msg.append("    - hf-mirror.com 是否可访问（试试浏览器打开）")
        msg.append("    - 配置文件中 ai.proxy.url 是否正确设置")
        msg.append("    - 如果不需要镜像，删除 config.yaml 中的 ai.whisper.hf_endpoint")
        msg.append("    - 若需代理，在 config.yaml 中配置 proxy: { enabled: true, url: http://127.0.0.1:7890 }")
    return "\n".join(msg)


def _find_model_file(cache_dir: Path, model_name: str) -> Path | None:
    """Scan huggingface cache dir for the model.bin file (including partial downloads)."""
    repo_cache = cache_dir / f"models--Systran--faster-whisper-{model_name}"
    if not repo_cache.is_dir():
        return None
    # Check snapshots first (completed download)
    snapshots = repo_cache / "snapshots"
    if snapshots.is_dir():
        for rev_dir in snapshots.iterdir():
            model_file = rev_dir / "model.bin"
            if model_file.is_file():
                return model_file
    # Check blobs for partial files
    blobs = repo_cache / "blobs"
    if blobs.is_dir():
        for f in blobs.iterdir():
            if f.name.endswith(".incomplete") or f.name.startswith("."):
                return f
            if f.is_file() and f.stat().st_size > 0:
                return f
    return None


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

    # Save and set env vars for download (restore in finally)
    _ENV_KEYS = {"HF_ENDPOINT", "HTTP_PROXY", "HTTPS_PROXY", "HF_HUB_DISABLE_PROGRESS_BARS"}
    _old_env = {k: os.environ.get(k) for k in _ENV_KEYS}
    try:
        if cfg.whisper.hf_endpoint:
            os.environ["HF_ENDPOINT"] = cfg.whisper.hf_endpoint
        elif cfg.proxy.enabled and cfg.proxy.url:
            os.environ["HTTP_PROXY"] = cfg.proxy.url
            os.environ["HTTPS_PROXY"] = cfg.proxy.url
        os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"

        # Step 2: download model
        cache_dir = _resolve_cache_dir(cfg)
        cache_dir.mkdir(parents=True, exist_ok=True)
        model_name = cfg.whisper.model_size
        repo_id = f"Systran/faster-whisper-{model_name}"

        # Get total file size before download
        total_size = _get_model_file_size(repo_id, cfg)

        _write_install_progress(
            progress_path,
            {
                "status": "downloading",
                "progress_pct": 0,
                "message": f"正在下载模型 {model_name} ({_format_bytes(total_size) if total_size else '...'})...",
            },
        )

        from huggingface_hub import hf_hub_download  # noqa

        # hf_hub_download returns the path to the downloaded file.
        # Run in a thread so we can poll file size for progress.
        result: list[Path | None] = [None]
        exc_info: list[BaseException | None] = [None]

        def _dl_thread() -> None:
            try:
                p = hf_hub_download(
                    repo_id=repo_id,
                    filename="model.bin",
                    cache_dir=str(cache_dir),
                    resume_download=True,
                    local_dir_use_symlinks=False,
                )
                result[0] = Path(p)
            except BaseException as e:
                exc_info[0] = e

        import threading as _threading

        _INSTALL_CANCEL.clear()
        t = _threading.Thread(target=_dl_thread, daemon=True)
        t.start()

        start = time.monotonic()
        last_pct = 0
        while t.is_alive():
            if _INSTALL_CANCEL.is_set():
                # Forcibly stop the download thread
                try:
                    import ctypes as _ctypes

                    tid = t.ident
                    if tid:
                        _ctypes.pythonapi.PyThreadState_SetAsyncExc(_ctypes.c_long(tid), _ctypes.py_object(SystemExit))
                except Exception:
                    pass
                # Give it a moment to exit
                t.join(timeout=3)
                # Clean up partial files
                partial = _find_model_file(cache_dir, model_name)
                if partial:
                    try:
                        partial.unlink(missing_ok=True)
                    except OSError:
                        pass
                _write_install_progress(
                    progress_path,
                    {"status": "idle", "progress_pct": 0, "message": "下载已取消"},
                )
                return
            t.join(timeout=1.0)
            elapsed = time.monotonic() - start
            candidate = _find_model_file(cache_dir, model_name) if cache_dir.is_dir() else None
            current = candidate.stat().st_size if candidate and candidate.is_file() else 0
            pct = int(current / total_size * 100) if total_size else 0
            speed_bps = current / max(elapsed, 1.0)
            speed_str = (
                f"{speed_bps / 1024 / 1024:.1f} MB/s"
                if speed_bps > 1024 * 1024
                else f"{speed_bps / 1024:.0f} KB/s"
                if speed_bps
                else ""
            )
            eta_sec = int((total_size - current) / max(speed_bps, 1)) if total_size and speed_bps else None
            if total_size and pct >= last_pct + 2:
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
            elif not total_size:
                _write_install_progress(
                    progress_path,
                    {
                        "status": "downloading",
                        "progress_pct": 0,
                        "message": f"下载模型 {model_name} ({int(elapsed)}s, {_format_bytes(current)} 已下载)",
                    },
                )

        if _INSTALL_CANCEL.is_set():
            # Race: thread exited from SystemExit between loop iterations
            _write_install_progress(
                progress_path,
                {"status": "idle", "progress_pct": 0, "message": "下载已取消"},
            )
            return

        if exc_info[0]:
            raise RuntimeError(_download_error_detail(exc_info[0], cfg)) from exc_info[0]
        model_path = result[0]

        if not model_path or not model_path.is_file():
            raise RuntimeError("模型下载后文件未找到")

        _write_install_progress(
            progress_path,
            {
                "status": "done",
                "progress_pct": 100,
                "message": f"模型 {model_name} 下载完成",
            },
        )
    finally:
        # Restore env vars to avoid polluting the process
        for k, v in _old_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


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
        with open(proj_yaml, encoding="utf-8") as f:
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
