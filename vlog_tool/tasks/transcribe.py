from __future__ import annotations

import json
import re
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from vlog_tool.config import AppConfig
from vlog_tool.log import format_duration
from vlog_tool.processing_state import ProcessingState
from vlog_tool.progress import ProgressTracker
from vlog_tool.transcribe import check_whisper, transcribe_audio
from vlog_tool.utils import find_videos, popen_subprocess, resolve_binary, write_json_atomic

# isort: split
from vlog_tool.shutdown import register_process, unregister_process


def _get_video_duration(video_path: Path, ffprobe: str) -> float:
    """Use ffprobe to get video duration in seconds."""
    import subprocess as _subprocess

    cmd = [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video_path)]
    try:
        r = _subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if r.returncode == 0 and r.stdout.strip():
            return float(r.stdout.strip())
    except Exception:
        pass
    return 0.0


def _extract_audio(
    video_path: Path,
    ffmpeg: str,
    progress_callback: Callable[[int], None] | None = None,
    cancel_event: threading.Event | None = None,
    total_duration: float = 0.0,
) -> Path | None:
    """ffmpeg 提取 16kHz 单声道 WAV，返回临时文件路径。实时输出进度（百分比）。"""
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    tmp_path = Path(tmp.name)
    cmd = [
        ffmpeg,
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
    proc = popen_subprocess(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, bufsize=1)
    register_process(proc)
    time_pat = re.compile(r"time=(\d+):(\d+):(\d+\.\d+)")
    last_log_pct = -1
    try:
        for line in proc.stderr or []:
            if cancel_event and cancel_event.is_set():
                proc.terminate()
                proc.wait()
                print("  [提取音频] 被用户取消")
                tmp_path.unlink(missing_ok=True)
                return None
            m = time_pat.search(line)
            if m:
                sec = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
                pct = min(int(sec / total_duration * 100), 100) if total_duration > 0 else 0
                if progress_callback and pct >= 0:
                    progress_callback(pct)
                if pct >= last_log_pct + 5:
                    print(f"  [提取音频] {sec:.0f}s / {total_duration:.0f}s ({pct}%)")
                    last_log_pct = pct
        proc.wait()
        if proc.returncode != 0:
            print(f"  [ffmpeg] 提取失败 (code {proc.returncode})")
            tmp_path.unlink(missing_ok=True)
            return None
        if progress_callback:
            progress_callback(100)
        return tmp_path
    except BaseException:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        tmp_path.unlink(missing_ok=True)
        raise
    finally:
        unregister_process(proc)


def run_transcribe_all(
    config: AppConfig,
    tracker: ProgressTracker | None = None,
    single_file: Path | None = None,
    cancel_event: threading.Event | None = None,
    files: list[str] | None = None,
    overwrite: bool = False,
) -> int:
    if not config.whisper.enabled:
        print("Whisper 转录未启用（whisper.enabled=false），跳过")
        if tracker:
            tracker.log("Whisper 转录未启用，跳过")
            tracker.update(phase="transcribe", current=0, total=0, message="Whisper 未启用，跳过")
        return 0
    if not check_whisper():
        msg = "faster-whisper 未安装，跳过转录。执行: python main.py whisper install"
        print(f"警告：{msg}")
        if tracker:
            tracker.error(msg)
        return 0

    transcripts_dir = config.paths.output_dir / config.whisper.transcripts_subdir
    transcripts_dir.mkdir(parents=True, exist_ok=True)

    videos = find_videos(config.paths.input_dir, recursive=config.paths.recursive)
    if files is not None:
        allowed = {f.lower() for f in files}
        videos = [v for v in videos if v.stem.lower() in allowed]
    total = len(videos)
    if total == 0:
        print("没有找到需要转录的视频")
        return 0

    if tracker:
        tracker.update(phase="transcribe", total=total, current=0, message="Whisper 语音转录...")
    state = ProcessingState(config.paths.output_dir)

    start_time = time.time()
    for i, orig_video in enumerate(videos):
        stem = orig_video.stem
        out_path = transcripts_dir / f"{stem}_transcript.json"
        if not overwrite and config.analyze.skip_existing and out_path.exists():
            try:
                json.loads(out_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                print(f"  [重新转录] {stem} (已有文件损坏)")
            else:
                print(f"[跳过] {stem} (已有转录)")
                state.mark(stem, "transcribe", "skipped")
                if tracker:
                    tracker.next(message=f"跳过 {stem}")
                    tracker.log(f"跳过 {stem}（已转录）")
                continue

        if cancel_event and cancel_event.is_set():
            print("  [取消] 转录阶段被终止")
            break
        ffmpeg = resolve_binary(config.paths.ffmpeg, "ffmpeg")
        ffprobe = resolve_binary(config.paths.ffmpeg, "ffprobe")
        audio_dur = _get_video_duration(orig_video, ffprobe)

        def _on_extract_progress(pct: int) -> None:
            if tracker:
                tracker.update(phase="transcribe", current=pct, total=100, message=f"{stem}: 提取音频 ({pct}%)")

        def _on_transcribe_progress(pct: int) -> None:
            if tracker:
                tracker.update(phase="transcribe", current=pct, total=100, message=f"{stem}: Whisper 转录 ({pct}%)")

        wav_path = _extract_audio(
            orig_video,
            ffmpeg,
            progress_callback=_on_extract_progress,
            cancel_event=cancel_event,
            total_duration=audio_dur,
        )
        if wav_path is None:
            if cancel_event and cancel_event.is_set():
                print(f"  [取消] {stem}: 音频提取被用户中断")
                state.mark(stem, "transcribe", "cancelled")
                if tracker:
                    tracker.next(message=f"取消 {stem}")
                    tracker.log(f"取消 {stem}")
                break
            print(f"  [跳过] {stem}: 音频提取失败（可能无音轨）")
            state.mark(stem, "transcribe", "skipped")
            if tracker:
                tracker.next(message=f"跳过 {stem} (no audio)")
                tracker.log(f"跳过 {stem}（无音轨）")
            continue

        try:
            segments = transcribe_audio(wav_path, config, progress_callback=_on_transcribe_progress)
            transcript = {
                "source_video": orig_video.name,
                "source_stem": stem,
                "language": config.whisper.language,
                "model_size": config.whisper.model_size,
                "segments": segments,
                "generated_at": datetime.now().isoformat(),
            }
            write_json_atomic(out_path, transcript)
            state.mark(stem, "transcribe", "done")
            seg_info = f"{len(segments)} 段" if segments else "无有效内容"
            elapsed = time.time() - start_time
            pace = elapsed / (i + 1)
            eta = pace * (total - i - 1)
            eta_str = format_duration(eta)
            print(f"  [转录 {i + 1}/{total}] {stem}（{seg_info}，平均 {format_duration(pace)}，剩余 ~{eta_str}）")
        except KeyboardInterrupt:
            raise
        except Exception as e:
            print(f"  [错误] {stem}: {e}")
            state.mark(stem, "transcribe", "error")
            if tracker:
                tracker.next(message=f"失败 {stem}")
                tracker.log(f"转录 {stem} 失败")
            continue
        finally:
            wav_path.unlink(missing_ok=True)

        if tracker:
            tracker.next(message=f"完成 {stem}")
            tracker.log(f"转录 {stem} ✓")

    return 0


def run_transcribe_one(config: AppConfig, video_path: Path, cancel_event: threading.Event | None = None) -> dict:
    """单文件转录（供 UI rerun 使用）。"""
    import time

    t0 = time.time()
    print(f"  [transcribe_one] 开始处理: {video_path.name}")
    if not video_path.is_file():
        return {"error": f"文件不存在: {video_path}"}
    if cancel_event and cancel_event.is_set():
        return {"error": "转录被用户取消"}
    print("  [transcribe_one] 提取音频...")
    ffmpeg = resolve_binary(config.paths.ffmpeg, "ffmpeg")
    wav_path = _extract_audio(video_path, ffmpeg, cancel_event=cancel_event)
    if wav_path is None:
        return {"error": "音频提取失败"}
    wav_size = wav_path.stat().st_size
    print(f"  [transcribe_one] WAV 提取完成: {wav_path.name} ({wav_size / 1024:.0f} KB)，耗时 {time.time() - t0:.1f}s")
    try:
        dev = config.whisper.device
        model = config.whisper.model_size
        print(f"  [transcribe_one] 开始 Whisper 转录 (device={dev}, model={model})...")
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
        write_json_atomic(out_path, transcript)
        print(f"  [transcribe_one] ✓ 已保存到 {out_path}")
        return transcript
    finally:
        wav_path.unlink(missing_ok=True)
        print(f"  [transcribe_one] 临时 WAV 已删除，总计耗时 {time.time() - t0:.1f}s")
