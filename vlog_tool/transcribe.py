from __future__ import annotations

import os
import threading
from collections.abc import Callable
from pathlib import Path

from vlog_tool.config import AppConfig


def check_whisper() -> bool:
    try:
        import faster_whisper  # noqa: F401

        return True
    except ImportError:
        return False


PROJECT_ROOT = Path(__file__).resolve().parent.parent

try:
    from faster_whisper import WhisperModel
except ImportError:
    WhisperModel = None  # type: ignore[assignment]

_whisper_model = None
_whisper_cache_key: str | None = None
_env_lock = threading.Lock()


def _clear_model_cache() -> None:
    global _whisper_model, _whisper_cache_key
    _whisper_model = None
    _whisper_cache_key = None


def _resolve_cache_dir(config: AppConfig) -> Path:
    if config.whisper.cache_dir:
        return Path(config.whisper.cache_dir).resolve()
    return PROJECT_ROOT / "models"


def _resolve_device(config: AppConfig) -> str:
    if config.whisper.device == "auto":
        try:
            from ctranslate2 import get_cuda_device_count

            return "cuda" if get_cuda_device_count() > 0 else "cpu"
        except (ImportError, OSError, RuntimeError):
            return "cpu"
    return config.whisper.device


def _resolve_compute_types(device: str) -> list[str]:
    if device == "cuda":
        return ["int8_float16", "float16", "default"]
    return ["int8", "default"]


def _get_model(config: AppConfig):
    global _whisper_model, _whisper_cache_key
    if WhisperModel is None:
        raise ImportError("faster-whisper is not installed. Run: pip install faster-whisper")

    _ENV_KEYS = {"HF_ENDPOINT", "HTTP_PROXY", "HTTPS_PROXY", "OMP_NUM_THREADS", "MKL_NUM_THREADS"}
    with _env_lock:
        saved = {k: os.environ.get(k) for k in _ENV_KEYS}
        try:
            os.environ.setdefault("OMP_NUM_THREADS", "4")
            os.environ.setdefault("MKL_NUM_THREADS", "4")
            if config.whisper.hf_endpoint:
                os.environ["HF_ENDPOINT"] = config.whisper.hf_endpoint
            else:
                if config.proxy.enabled and isinstance(config.proxy.url, str) and config.proxy.url.strip():
                    os.environ["HTTP_PROXY"] = config.proxy.url
                    os.environ["HTTPS_PROXY"] = config.proxy.url

            cache_dir = _resolve_cache_dir(config)
            device = _resolve_device(config)
            attempt = 0
            while True:
                compute_types = _resolve_compute_types(device)
                for ct in compute_types:
                    attempt += 1
                    key = f"{config.whisper.model_size}@{device}@{ct}@{cache_dir}"
                    if _whisper_model is not None and _whisper_cache_key == key:
                        return _whisper_model
                    try:
                        _whisper_model = WhisperModel(
                            config.whisper.model_size,
                            device=device,
                            compute_type=ct,
                            download_root=str(cache_dir),
                        )
                        _whisper_cache_key = key
                        return _whisper_model
                    except (ValueError, RuntimeError, OSError) as e:
                        is_last = ct == compute_types[-1]
                        err_str = str(e)
                        if device == "cuda" and is_last:
                            print(f"  [警告] CUDA 加载失败 ({err_str})，回退到 CPU")
                            device = "cpu"
                            break
                        if device != "cuda" and is_last:
                            print(f"  [错误] 模型加载失败: {err_str}")
                            print("  [提示] 请执行 `python main.py whisper install` 预下载模型到本地缓存")
                            ep = config.whisper.hf_endpoint or "未设置（使用官方地址）"
                            print(f"  [提示] 国内用户需在设置中配置 hf_endpoint（当前: {ep}）")
                            if (
                                "tls" in err_str.lower()
                                or "handshake" in err_str.lower()
                                or "eof" in err_str.lower()
                                or "connect" in err_str.lower()
                            ):
                                print("  [提示] 可能是网络/代理问题导致模型下载失败，建议：")
                                print("         1. 在配置中设置 hf_endpoint: https://hf-mirror.com")
                                print("         2. 或执行 `python main.py whisper install` 手动下载")
                            if "cublas" in err_str.lower() or "library" in err_str.lower():
                                print("  [提示] 可能是 CUDA 库缺失，建议：")
                                print("         1. 在配置中设置 whisper.device: cpu（跳过 CUDA）")
                                print(
                                    "         2. 或安装 CUDA 运行时: pip install nvidia-cublas-cu12 nvidia-cudnn-cu12"
                                )
                            raise
                        print(f"  [警告] {device} {ct} 加载失败 ({e})，尝试下一个 compute type")
                        continue
                    except Exception as e:
                        if device == "cuda":
                            print(f"  [警告] CUDA 加载异常 ({e})，回退到 CPU")
                            device = "cpu"
                            break
                        raise
            return _whisper_model
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


def transcribe_audio(
    audio_path: Path,
    config: AppConfig,
    progress_callback: Callable[[int], None] | None = None,
) -> list[dict]:
    lang = config.whisper.language
    if progress_callback:
        progress_callback(0)

    try:
        model = _get_model(config)
        segments_iter, info = model.transcribe(
            str(audio_path),
            language=None if lang == "auto" else lang,
            word_timestamps=False,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=300),
            beam_size=5,
            best_of=5,
            temperature=0.0,
        )
    except (RuntimeError, OSError) as e:
        err = str(e)
        if "cublas" in err.lower() or "cuda" in err.lower() or "library" in err.lower():
            print(f"  [警告] CUDA 模型加载/推理失败 ({e})，回退到 CPU 重试")
            _clear_model_cache()
            _orig_device = config.whisper.device
            config.whisper.device = "cpu"
            try:
                model = _get_model(config)
                segments_iter, info = model.transcribe(
                    str(audio_path),
                    language=None if lang == "auto" else lang,
                    word_timestamps=False,
                    vad_filter=True,
                    vad_parameters=dict(min_silence_duration_ms=300),
                    beam_size=5,
                    best_of=5,
                    temperature=0.0,
                )
            except (RuntimeError, OSError):
                print("  [错误] CPU 回退也失败，可能是 cuBLAS 库缺失")
                print("  [提示] 请在配置中设置 whisper.device: cpu，或安装 CUDA 运行时:")
                print("         pip install nvidia-cublas-cu12 nvidia-cudnn-cu12")
                raise
            finally:
                config.whisper.device = _orig_device
        else:
            raise

    total_duration = info.duration
    last_pct = 0
    result = []
    for seg in segments_iter:
        pct = int(seg.end / total_duration * 100) if total_duration > 0 else 0
        if pct >= last_pct + 5:
            print(f"  [whisper] 转录进度: {seg.end:.1f}s / {total_duration:.0f}s ({pct}%)")
            if progress_callback:
                progress_callback(pct)
            last_pct = pct
        is_low = seg.avg_logprob < -0.8 or seg.no_speech_prob > 0.1
        entry = {
            "start": round(seg.start, 2),
            "end": round(seg.end, 2),
            "text": seg.text.strip(),
            "avg_logprob": round(seg.avg_logprob, 3),
        }
        if is_low:
            entry["low_confidence"] = True
        result.append(entry)
    if progress_callback:
        progress_callback(100)
    return result
