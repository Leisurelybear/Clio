from __future__ import annotations

import json
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path

from vlog_tool._constants import VIDEO_EXTS
from vlog_tool.config import AppConfig
from vlog_tool.log import format_duration
from vlog_tool.progress import ProgressTracker
from vlog_tool.tasks.analyze import _resolve_original
from vlog_tool.transcribe import transcribe_audio
from vlog_tool.utils import get_duration_sec, resolve_binary


def _check_whisper() -> bool:
    try:
        import faster_whisper  # noqa: F401

        return True
    except ImportError:
        return False


def _extract_audio(video_path: Path) -> Path | None:
    """ffmpeg 提取 16kHz 单声道 WAV，返回临时文件路径。"""
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        "16000",
        "-ac",
        "1",
        str(tmp.name),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        print(f"  [ffmpeg] {result.stderr.strip()}")
        Path(tmp.name).unlink(missing_ok=True)
        return None
    return Path(tmp.name)


def run_transcribe_all(
    config: AppConfig,
    tracker: ProgressTracker | None = None,
    single_file: Path | None = None,
) -> int:
    if not config.whisper.enabled:
        print("Whisper 转录未启用（whisper.enabled=false），跳过")
        return 0
    if not _check_whisper():
        print("警告：faster-whisper 未安装，跳过转录。执行: python main.py whisper install")
        return 0

    transcripts_dir = config.paths.output_dir / config.whisper.transcripts_subdir
    transcripts_dir.mkdir(parents=True, exist_ok=True)

    stems: set[str] = set()
    compressed_dir = config.paths.output_dir / config.analyze.compressed_subdir
    for f in sorted(compressed_dir.rglob("*")):
        if f.suffix.lower() in VIDEO_EXTS and f.is_file():
            orig = _resolve_original(config.paths.input_dir, f.stem)
            if orig:
                stems.add(orig.stem)

    stems = sorted(stems)
    total = len(stems)
    if total == 0:
        print("没有找到需要转录的视频")
        return

    if tracker:
        tracker.update(phase="transcribe", total=total, current=0, message="Whisper 语音转录...")

    start_time = time.time()
    for i, stem in enumerate(stems):
        out_path = transcripts_dir / f"{stem}_transcript.json"
        if config.analyze.skip_existing and out_path.exists():
            print(f"[跳过] {stem} (已有转录)")
            if tracker:
                tracker.next(message=f"跳过 {stem}")
            continue

        orig_video: Path | None = None
        for ext in (".mp4", ".mov", ".mkv", ".avi", ".mts", ".m2ts", ".m4v", ".webm", ".lrv"):
            candidate = config.paths.input_dir / f"{stem}{ext}"
            if candidate.is_file():
                orig_video = candidate
                break
        if orig_video is None:
            print(f"  [跳过] {stem}: 找不到原始视频")
            continue

        try:
            ffprobe = resolve_binary(config.paths.ffprobe, "ffprobe")
            duration = get_duration_sec(orig_video, ffprobe)
            max_min = config.analyze.max_analyze_duration_min
            if max_min > 0 and duration > max_min * 60:
                print(f"  [跳过] {stem}: 时长 {format_duration(duration)} 超过限制")
                if tracker:
                    tracker.next(message=f"跳过 {stem} (超长)")
                continue
        except Exception as e:
            print(f"  [警告] 无法检查 {stem} 时长: {e}")

        wav_path = _extract_audio(orig_video)
        if wav_path is None:
            print(f"  [跳过] {stem}: 音频提取失败（可能无音轨）")
            if tracker:
                tracker.next(message=f"跳过 {stem} (no audio)")
            continue

        try:
            segments = transcribe_audio(wav_path, config)
            transcript = {
                "source_video": orig_video.name,
                "source_stem": stem,
                "language": config.whisper.language,
                "model_size": config.whisper.model_size,
                "segments": segments,
                "generated_at": datetime.now().isoformat(),
            }
            out_path.write_text(json.dumps(transcript, ensure_ascii=False, indent=2), encoding="utf-8")
            seg_info = f"{len(segments)} 段" if segments else "无有效内容"
            elapsed = time.time() - start_time
            pace = elapsed / (i + 1)
            eta = pace * (total - i - 1)
            print(
                f"  [转录 {i + 1}/{total}] {stem}（{seg_info}，平均 {format_duration(pace)}，剩余 ~{format_duration(eta)}）"
            )
        except KeyboardInterrupt:
            wav_path.unlink(missing_ok=True)
            raise
        except Exception as e:
            print(f"  [错误] {stem}: {e}")
        finally:
            wav_path.unlink(missing_ok=True)

        if tracker:
            tracker.next(message=f"完成 {stem}")

    return 0


def run_transcribe_one(config: AppConfig, video_path: Path) -> dict:
    """单文件转录（供 UI rerun 使用）。"""
    if not video_path.is_file():
        return {"error": f"文件不存在: {video_path}"}
    wav_path = _extract_audio(video_path)
    if wav_path is None:
        return {"error": "音频提取失败"}
    try:
        segments = transcribe_audio(wav_path, config)
        return {
            "source_video": video_path.name,
            "source_stem": video_path.stem,
            "segments": segments,
        }
    finally:
        wav_path.unlink(missing_ok=True)
