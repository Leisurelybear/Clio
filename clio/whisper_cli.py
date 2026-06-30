from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Any

from clio.config import load_config
from clio.transcribe import PROJECT_ROOT, _resolve_cache_dir
from clio.utils import run_subprocess

_snapshot_download: Any
try:
    from huggingface_hub import snapshot_download as _snapshot_download
except ImportError:
    _snapshot_download = None


def run_whisper_install(config_path: str | Path = "config.yaml") -> int:
    print("正在安装 faster-whisper...")

    cfg = load_config(config_path)
    import os

    if cfg.whisper.hf_endpoint:
        os.environ["HF_ENDPOINT"] = cfg.whisper.hf_endpoint
        print(f"HF_ENDPOINT 已设置为: {cfg.whisper.hf_endpoint}")
    else:
        print("HF_ENDPOINT: 使用 HuggingFace 官方默认地址")
        if cfg.proxy.enabled and isinstance(cfg.proxy.url, str) and cfg.proxy.url.strip():
            os.environ["HTTP_PROXY"] = cfg.proxy.url
            os.environ["HTTPS_PROXY"] = cfg.proxy.url

    req = PROJECT_ROOT / "requirements-whisper.txt"
    if not req.is_file():
        print(f"未找到依赖文件: {req}")
        return 1
    result = run_subprocess(
        [sys.executable, "-m", "pip", "install", "-r", str(req)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print("安装失败:", result.stderr)
        return 1
    print("faster-whisper 安装完成")

    try:
        from ctranslate2 import get_cuda_device_count

        cuda_avail = get_cuda_device_count() > 0
    except (ImportError, OSError):
        cuda_avail = False
    if cuda_avail:
        import shutil

        cuda_size_mb = 2800
        tmp_free = shutil.disk_usage(tempfile.gettempdir()).free // (1024 * 1024)
        if tmp_free < cuda_size_mb:
            print(f"  [跳过] 磁盘空间不足（临时目录剩余 {tmp_free} MB，需要 ~{cuda_size_mb} MB），CUDA 加速跳过")
            print("  [提示] 如需 CUDA 加速，请手动执行: pip install nvidia-cublas-cu12 nvidia-cudnn-cu12")
        else:
            print("检测到 NVIDIA GPU，安装 CUDA 运行时加速...")
            r = run_subprocess(
                [sys.executable, "-m", "pip", "install", "nvidia-cublas-cu12", "nvidia-cudnn-cu12", "-q"],
            )
            if r.returncode == 0:
                print("CUDA 运行时安装完成")
            else:
                print(f"  [警告] CUDA 运行时安装失败（返回码 {r.returncode}），将使用 CPU 运行")
    else:
        print("CUDA: 不可用（使用 CPU）")

    model_name = cfg.whisper.model_size
    cache_dir = _resolve_cache_dir(cfg)
    cache_dir.mkdir(parents=True, exist_ok=True)

    if _model_in_cache(cache_dir, model_name):
        print(f"模型 '{model_name}' 已在缓存中，跳过下载")
        return 0

    repo_id = f"Systran/faster-whisper-{model_name}"
    print(f"正在预下载模型 '{model_name}' 到 {cache_dir}...")
    print(f"  模型仓库: {repo_id}")
    print("  模型大小约 1~2 GB，下载时间取决于网络速度")
    if _snapshot_download is None:
        print("  [错误] huggingface_hub 未安装，无法下载模型")
        return 1

    try:
        _snapshot_download(
            repo_id=repo_id,
            cache_dir=str(cache_dir),
            resume_download=True,
            local_dir_use_symlinks=False,
            ignore_patterns=["*.h5", "*.ot", "*.pt"],
        )
    except Exception as e:
        print(f"  [错误] 下载失败: {e}")
        print("  [提示] 检查 hf_endpoint 配置或网络连接")
        return 1

    print(f"模型 '{model_name}' 已就绪")
    return 0


def _model_in_cache(cache_dir: Path, model_name: str) -> bool:
    """Check if a model is completely cached and valid."""
    if not cache_dir.is_dir():
        return False
    for entry in cache_dir.iterdir():
        if not entry.is_dir():
            continue
        name = entry.name.lower()
        if "whisper" in name and model_name.lower() in name:
            snapshots = entry / "snapshots"
            if not snapshots.is_dir():
                continue
            for snap_dir in snapshots.iterdir():
                if not snap_dir.is_dir():
                    continue
                model_file_size = _find_model_file_size(snap_dir)
                if model_file_size > 100 * 1024 * 1024:
                    return True
                print(f"  缓存不完整（{snap_dir.name}: 模型文件仅 {model_file_size // 1024 // 1024} MB），重新下载")
    return False


def _find_model_file_size(dir_path: Path) -> int:
    """Find the largest file in a directory (likely the model binary)."""
    max_size = 0
    for f in dir_path.rglob("*"):
        if f.is_file():
            try:
                sz = f.stat().st_size
                if sz > max_size:
                    max_size = sz
            except OSError:
                pass
    return max_size


def run_whisper_check(config_path: str | Path = "config.yaml") -> int:
    print("=== Whisper 环境检测 ===")
    try:
        import faster_whisper

        print(f"faster-whisper: {faster_whisper.__version__}  ✔")
    except ImportError:
        print("faster-whisper: 未安装  ✘（请执行 python main.py whisper install）")
        return 1

    try:
        from ctranslate2 import get_cuda_device_count

        cuda_avail = get_cuda_device_count() > 0
    except (ImportError, OSError):
        cuda_avail = False
    print(f"CUDA: {'可用 ✔' if cuda_avail else '不可用（使用 CPU）'}")

    cfg = load_config(config_path)
    cache_dir = _resolve_cache_dir(cfg)
    if cache_dir.is_dir():
        models = [d.name for d in cache_dir.iterdir() if d.is_dir()]
        if models:
            print(f"已缓存模型: {', '.join(models)}")
        else:
            print("模型缓存: 空（尚无缓存模型）")
    ep = cfg.whisper.hf_endpoint
    print(f"HF_ENDPOINT: {ep or 'HuggingFace 官方默认地址'}")
    return 0
