from __future__ import annotations

import json
import re
import subprocess
import tempfile
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from vlog_tool._constants import VIDEO_EXTS
from vlog_tool.config import AppConfig
from vlog_tool.log import format_duration
from vlog_tool.processing_state import ProcessingState
from vlog_tool.progress import ProgressTracker
from vlog_tool.transcribe import check_whisper, transcribe_audio
from vlog_tool.utils import resolve_binary, write_json_atomic


def _extract_audio(
    video_path: Path, ffmpeg: str, progress_callback: Callable[[float], None] | None = None
) -> Path | None:
    """ffmpeg 提取 16kHz 单声道 WAV，返回临时文件路径。实时输出进度。"""
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    tmp_path = Path(tmp.name)
    try:
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
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, bufsize=1)
        time_pat = re.compile(r"time=(\d+):(\d+):(\d+\.\d+)")
        last_pct = 0
        total_assumed: float | None = None
        for line in proc.stderr or []:
            m = time_pat.search(line)
            if m:
                sec = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
                if progress_callback and sec > 0:
                    progress_callback(sec)
                pct = int(sec)
                if pct >= last_pct + 5:
                    print(f"  [提取音频] {sec:.0f}s")
                    last_pct = pct
        proc.wait()
        if proc.returncode != 0:
            print(f"  [ffmpeg] 提取失败 (code {proc.returncode})")
            tmp_path.unlink(missing_ok=True)
            return None
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
    for f in sorted(config.paths.input_dir.iterdir()):
        if f.is_file() and f.suffix.lower() in VIDEO_EXTS:
            stems.add(f.stem)

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
            try:
                json.loads(out_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                print(f"  [重新转录] {stem} (已有文件损坏)")
            else:
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

        # Whisper 没有像 Gemini 那样的时长限制，跳过时长检查

        ffmpeg = resolve_binary(config.paths.ffmpeg, "ffmpeg")
        wav_path = _extract_audio(orig_video, ffmpeg)
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
            write_json_atomic(out_path, transcript)
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
    ffmpeg = resolve_binary(config.paths.ffmpeg, "ffmpeg")
    wav_path = _extract_audio(video_path, ffmpeg)
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
        write_json_atomic(out_path, transcript)
        print(f"  [transcribe_one] ✓ 已保存到 {out_path}")
        return transcript
    finally:
        wav_path.unlink(missing_ok=True)
        print(f"  [transcribe_one] 临时 WAV 已删除，总计耗时 {time.time() - t0:.1f}s")
