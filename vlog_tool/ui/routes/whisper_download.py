"""Whisper model download — thread, progress, and install handlers."""

from __future__ import annotations

import json
import os
import sys as _sys
import threading
import time
from pathlib import Path
from typing import Any

import requests as _req

from vlog_tool.transcribe import _resolve_cache_dir
from vlog_tool.ui.handler_protocol import HandlerProtocol
from vlog_tool.utils import run_subprocess

_INSTALL_LOCK = threading.Lock()
_INSTALL_THREAD: threading.Thread | None = None
_INSTALL_CANCEL = threading.Event()


def _install_progress_path(handler: HandlerProtocol, qs: dict[str, Any]) -> Path:
    proj_out = handler._get_project_output(qs)
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


def handle_get_whisper_install_status(handler: HandlerProtocol, qs: dict[str, Any]) -> None:
    path = _install_progress_path(handler, qs)
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {"status": "idle"}
    else:
        data = {"status": "idle"}
    with _INSTALL_LOCK:
        running = _INSTALL_THREAD is not None and _INSTALL_THREAD.is_alive()
    if data.get("status") in ("downloading",) and not running:
        data = {"status": "idle", "message": "上次下载中断，可重新开始"}
    data["running"] = running
    handler._send_json(data)


def handle_post_whisper_install(handler: HandlerProtocol, qs: dict[str, Any]) -> None:
    global _INSTALL_THREAD

    with _INSTALL_LOCK:
        if _INSTALL_THREAD is not None and _INSTALL_THREAD.is_alive():
            handler._send_json({"ok": False, "error": "download is already running"}, 409)
            return
        progress_path = _install_progress_path(handler, qs)

        def _worker() -> None:
            try:
                _run_install(handler, qs, progress_path)
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


def handle_post_whisper_install_cancel(handler: HandlerProtocol, qs: dict[str, Any]) -> None:
    global _INSTALL_CANCEL
    _INSTALL_CANCEL.set()
    path = _install_progress_path(handler, qs)
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("status") == "downloading":
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


def _get_model_file_size(repo_id: str, cfg: Any) -> int:
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
    for key, sz in _KNOWN_MODEL_SIZES.items():
        if key in repo_id:
            return sz
    return 0


def _download_error_detail(e: Exception, cfg: Any) -> str:
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
    repo_cache = cache_dir / f"models--Systran--faster-whisper-{model_name}"
    if not repo_cache.is_dir():
        return None
    snapshots = repo_cache / "snapshots"
    if snapshots.is_dir():
        for rev_dir in snapshots.iterdir():
            model_file = rev_dir / "model.bin"
            if model_file.is_file():
                return model_file
    blobs = repo_cache / "blobs"
    if blobs.is_dir():
        for f in blobs.iterdir():
            if f.name.endswith(".incomplete") or f.name.startswith("."):
                return f
            if f.is_file() and f.stat().st_size > 0:
                return f
    return None


def _run_install(handler: HandlerProtocol, qs: dict[str, Any], progress_path: Path) -> None:
    proj_input = handler._resolve_project_input(qs)
    cfg = handler._get_config(proj_input)

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

    _ENV_KEYS = {"HF_ENDPOINT", "HTTP_PROXY", "HTTPS_PROXY", "HF_HUB_DISABLE_PROGRESS_BARS"}
    _old_env = {k: os.environ.get(k) for k in _ENV_KEYS}
    try:
        if cfg.whisper.hf_endpoint:
            os.environ["HF_ENDPOINT"] = cfg.whisper.hf_endpoint
        elif cfg.proxy.enabled and cfg.proxy.url:
            os.environ["HTTP_PROXY"] = cfg.proxy.url
            os.environ["HTTPS_PROXY"] = cfg.proxy.url
        os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"

        cache_dir = _resolve_cache_dir(cfg)
        cache_dir.mkdir(parents=True, exist_ok=True)
        model_name = cfg.whisper.model_size
        repo_id = f"Systran/faster-whisper-{model_name}"

        total_size = _get_model_file_size(repo_id, cfg)

        _write_install_progress(
            progress_path,
            {
                "status": "downloading",
                "progress_pct": 0,
                "message": f"正在下载模型 {model_name} ({_format_bytes(total_size) if total_size else '...'})...",
            },
        )

        from huggingface_hub import hf_hub_url

        url = hf_hub_url(repo_id, filename="model.bin")
        proxy_url = cfg.proxy.url if (cfg.proxy.enabled and cfg.proxy.url) else None
        proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None

        model_cache_dir = cache_dir / f"models--Systran--faster-whisper-{model_name}"
        snapshots = model_cache_dir / "snapshots" / "downloaded"
        snapshots.mkdir(parents=True, exist_ok=True)
        model_path = snapshots / "model.bin"
        tmp_path = model_path.with_name(model_path.name + ".tmp")

        _INSTALL_CANCEL.clear()
        try:
            response = _req.get(url, stream=True, proxies=proxies, timeout=30, allow_redirects=True)
            response.raise_for_status()
        except _req.exceptions.RequestException as e:
            raise RuntimeError(_download_error_detail(e, cfg)) from e

        total_size = int(response.headers.get("Content-Length", 0)) or total_size

        downloaded = 0
        start = time.monotonic()
        last_report_time = 0.0
        last_pct = 0

        with open(tmp_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if _INSTALL_CANCEL.is_set():
                    tmp_path.unlink(missing_ok=True)
                    _write_install_progress(
                        progress_path,
                        {"status": "idle", "progress_pct": 0, "message": "下载已取消"},
                    )
                    return
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)

                now = time.monotonic()
                if now - last_report_time < 1.0:
                    continue
                last_report_time = now
                pct = int(downloaded / total_size * 100) if total_size else 0
                speed_bps = downloaded / max(now - start, 1.0)
                speed_str = (
                    f"{speed_bps / 1024 / 1024:.1f} MB/s"
                    if speed_bps > 1024 * 1024
                    else f"{speed_bps / 1024:.0f} KB/s"
                    if speed_bps
                    else ""
                )
                eta_sec = int((total_size - downloaded) / max(speed_bps, 1)) if total_size and speed_bps else None
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
                            "message": f"下载模型 {model_name} ({int(now - start)}s, "
                            f"{_format_bytes(downloaded)} 已下载)",
                        },
                    )

        try:
            tmp_path.replace(model_path)
        except OSError as e:
            raise RuntimeError(_download_error_detail(e, cfg)) from e
        _write_install_progress(
            progress_path,
            {
                "status": "done",
                "progress_pct": 100,
                "message": f"模型 {model_name} 下载完成",
            },
        )
    finally:
        for k, v in _old_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _format_bytes(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    elif n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    elif n < 1024 * 1024 * 1024:
        return f"{n / (1024 * 1024):.1f} MB"
    return f"{n / (1024 * 1024 * 1024):.2f} GB"
