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
from vlog_tool.processing_state import ProcessingState
from vlog_tool.progress import ProgressTracker
from vlog_tool.tasks.analyze import _resolve_original
from vlog_tool.transcribe import check_whisper, transcribe_audio
from vlog_tool.utils import get_duration_sec, resolve_binary


def _extract_audio(video_path: Path) -> Path | None:
    """ffmpeg 提取 16kHz 单声道 WAV，返回临时文件路径。"""
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    tmp_path = Path(tmp.name)
    try:
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
            str(tmp_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            print(f"  [ffmpeg] 失败: {result.stderr.strip()}")
            tmp_path.unlink(missing_ok=True)
            return None
        if result.stderr.strip():
            print(f"  [ffmpeg] stderr: {result.stderr.strip()[-500:]}")
        return tmp_path
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def run_transcribe_all(
    config: AppConfig,
    tracker: ProgressTracker | None = None,
    single_file: Path | None = None,
) -> int:
    if not config.whisper.enabled:
        print("Whisper 转录未启用（whisper.enabled=false），跳过")
        return 0
    if not check_whisper():
        msg = "faster-whisper 未安装，跳过转录。执行: python main.py whisper install"
        print(f"警告：{msg}")
        if tracker:
            tracker.error(msg)
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
        return 0

    if tracker:
        tracker.update(phase="transcribe", total=total, current=0, message="Whisper 语音转录...")
    state = ProcessingState(config.paths.output_dir)

    start_time = time.time()
    for i, stem in enumerate(stems):
        out_path = transcripts_dir / f"{stem}_transcript.json"
        if config.analyze.skip_existing and out_path.exists():
            print(f"[跳过] {stem} (已有转录)")
            state.mark(stem, "transcribe", "skipped")
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
                state.mark(stem, "transcribe", "skipped")
                if tracker:
                    tracker.next(message=f"跳过 {stem} (超长)")
                continue
        except Exception as e:
            print(f"  [警告] 无法检查 {stem} 时长: {e}")

        wav_path = _extract_audio(orig_video)
        if wav_path is None:
            print(f"  [跳过] {stem}: 音频提取失败（可能无音轨）")
            state.mark(stem, "transcribe", "skipped")
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
            state.mark(stem, "transcribe", "done")
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
            state.mark(stem, "transcribe", "error")
            if tracker:
                tracker.next(message=f"失败 {stem}")
            wav_path.unlink(missing_ok=True)
            continue
        finally:
            wav_path.unlink(missing_ok=True)

        if tracker:
            tracker.next(message=f"完成 {stem}")

    return 0


def run_transcribe_one(config: AppConfig, video_path: Path) -> dict:
    """单文件转录（供 UI rerun 使用）。"""
    import time

    t0 = time.time()
    print(f"  [transcribe_one] 开始处理: {video_path.name}")
    if not video_path.is_file():
        return {"error": f"文件不存在: {video_path}"}
    print("  [transcribe_one] 提取音频...")
    wav_path = _extract_audio(video_path)
    if wav_path is None:
        return {"error": "音频提取失败"}
    wav_size = wav_path.stat().st_size
    print(f"  [transcribe_one] WAV 提取完成: {wav_path.name} ({wav_size / 1024:.0f} KB)，耗时 {time.time() - t0:.1f}s")
    try:
        print(
            f"  [transcribe_one] 开始 Whisper 转录 (device={config.whisper.device}, model={config.whisper.model_size})..."
        )
        t1 = time.time()
        segments = transcribe_audio(wav_path, config)
        t2 = time.time()
        print(f"  [transcribe_one] Whisper 完成: {len(segments)} 段, 耗时 {t2 - t1:.1f}s")
        transcript = {
            "source_video": video_path.name,
            "source_stem": video_path.stem,
            "language": config.whisper.language,
            "model_size": config.whisper.model_size,
            "segments": segments,
            "generated_at": datetime.now().isoformat(),
        }
        transcripts_dir = config.paths.output_dir / config.whisper.transcripts_subdir
        transcripts_dir.mkdir(parents=True, exist_ok=True)
        out_path = transcripts_dir / f"{video_path.stem}_transcript.json"
        out_path.write_text(json.dumps(transcript, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  [transcribe_one] ✓ 已保存到 {out_path}")
        return transcript
    finally:
        wav_path.unlink(missing_ok=True)
        print(f"  [transcribe_one] 临时 WAV 已删除，总计耗时 {time.time() - t0:.1f}s")
