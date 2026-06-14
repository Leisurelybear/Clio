from __future__ import annotations

from pathlib import Path
from typing import Callable

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


def _resolve_cache_dir(config: AppConfig) -> Path:
    if config.whisper.cache_dir:
        return Path(config.whisper.cache_dir).resolve()
    return PROJECT_ROOT / "models"


def _resolve_device(config: AppConfig) -> str:
    if config.whisper.device == "auto":
        try:
            from ctranslate2 import get_cuda_device_count

            return "cuda" if get_cuda_device_count() > 0 else "cpu"
        except ImportError:
            return "cpu"
    return config.whisper.device


def _resolve_compute_type(device: str) -> str:
    return "int8_float16" if device == "cuda" else "int8"


def _get_model(config: AppConfig):
    global _whisper_model, _whisper_cache_key
    if WhisperModel is None:
        raise ImportError("faster-whisper is not installed. Run: pip install faster-whisper")

    cache_dir = _resolve_cache_dir(config)
    key = f"{config.whisper.model_size}@{cache_dir}"
    if _whisper_model is None or _whisper_cache_key != key:
        device = _resolve_device(config)
        _whisper_model = WhisperModel(
            config.whisper.model_size,
            device=device,
            compute_type=_resolve_compute_type(device),
            download_root=str(cache_dir),
        )
        _whisper_cache_key = key
    return _whisper_model


def transcribe_audio(
    audio_path: Path,
    config: AppConfig,
    progress_callback: Callable[[str], None] | None = None,
) -> list[dict]:
    lang = config.whisper.language
    model = _get_model(config)
    if progress_callback:
        progress_callback("transcribing")

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
    all_segments = list(segments_iter)

    result = []
    for seg in all_segments:
        if seg.avg_logprob >= -0.8 and seg.no_speech_prob <= 0.1:
            result.append(
                {
                    "start": round(seg.start, 2),
                    "end": round(seg.end, 2),
                    "text": seg.text.strip(),
                    "avg_logprob": round(seg.avg_logprob, 3),
                }
            )
    return result
