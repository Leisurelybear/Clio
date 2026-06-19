from __future__ import annotations

import sys
from pathlib import Path

from vlog_tool.config import load_config
from vlog_tool.transcribe import PROJECT_ROOT, _resolve_cache_dir
from vlog_tool.utils import run_subprocess


def run_whisper_install(config_path: str | Path = "config.yaml") -> int:
    print("正在安装 faster-whisper...")

    cfg = load_config(config_path)
    import os

    if cfg.whisper.hf_endpoint:
        os.environ["HF_ENDPOINT"] = cfg.whisper.hf_endpoint
        print(f"HF_ENDPOINT 已设置为: {cfg.whisper.hf_endpoint}")
    else:
        print("HF_ENDPOINT: 使用 HuggingFace 官方默认地址")

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
    print(f"正在预下载模型 '{model_name}' 到 {cache_dir}...")
    from faster_whisper import WhisperModel

    WhisperModel(model_name, device="cpu", download_root=str(cache_dir))
    print(f"模型 '{model_name}' 已就绪")
    return 0


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
