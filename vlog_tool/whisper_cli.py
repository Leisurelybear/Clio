from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from vlog_tool.config import load_config
from vlog_tool.transcribe import PROJECT_ROOT, _resolve_cache_dir


def run_whisper_install() -> int:
    print("正在安装 faster-whisper...")
    req = PROJECT_ROOT / "requirements-whisper.txt"
    if not req.is_file():
        print(f"未找到依赖文件: {req}")
        return 1
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", str(req)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print("安装失败:", result.stderr)
        return 1
    print("faster-whisper 安装完成")

    from ctranslate2 import get_cuda_device_count

    cuda_avail = get_cuda_device_count() > 0
    print(f"CUDA: {'可用' if cuda_avail else '不可用（使用 CPU）'}")

    cfg = load_config()
    model_name = cfg.whisper.model_size
    cache_dir = _resolve_cache_dir(cfg)
    cache_dir.mkdir(parents=True, exist_ok=True)
    print(f"正在预下载模型 '{model_name}' 到 {cache_dir}...")
    from faster_whisper import WhisperModel

    WhisperModel(model_name, device="cpu", download_root=str(cache_dir))
    print(f"模型 '{model_name}' 已就绪")
    return 0


def run_whisper_check() -> int:
    print("=== Whisper 环境检测 ===")
    try:
        import faster_whisper

        print(f"faster-whisper: {faster_whisper.__version__}  ✔")
    except ImportError:
        print("faster-whisper: 未安装  ✘（请执行 python main.py whisper install）")
        return 1

    from ctranslate2 import get_cuda_device_count

    cuda_avail = get_cuda_device_count() > 0
    print(f"CUDA: {'可用 ✔' if cuda_avail else '不可用（使用 CPU）'}")

    cfg = load_config()
    cache_dir = _resolve_cache_dir(cfg)
    if cache_dir.is_dir():
        models = [d.name for d in cache_dir.iterdir() if d.is_dir()]
        if models:
            print(f"已缓存模型: {', '.join(models)}")
        else:
            print("模型缓存: 空（尚无缓存模型）")
    return 0
