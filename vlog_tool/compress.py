from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from vlog_tool.config import AppConfig
from vlog_tool.log import format_size, timed
from vlog_tool.utils import get_duration_sec, resolve_binary, run_ffmpeg

ProgressCB = Callable[[float, float], None]  # (current_sec, total_sec)


def compress_video(
    input_path: Path,
    output_path: Path,
    config: AppConfig,
    progress_callback: ProgressCB | None = None,
) -> Path:
    """压缩视频：去声音、降分辨率，尽量接近目标大小。"""
    ffmpeg = resolve_binary(config.paths.ffmpeg, "ffmpeg")
    ffprobe = resolve_binary(config.paths.ffprobe, "ffprobe")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    duration = get_duration_sec(input_path, ffprobe)
    _cb = progress_callback

    def _on_ffmpeg_progress(sec: float) -> None:
        if _cb:
            _cb(sec, duration)

    if duration <= 0:
        raise ValueError(f"无法读取视频时长: {input_path}")

    cfg = config.compress
    vf = f"scale=min({cfg.max_width}\\,iw):-2,fps={cfg.fps}"

    args = ["-i", str(input_path), "-vf", vf, "-c:v", cfg.codec]

    if cfg.remove_audio:
        args.append("-an")

    if cfg.target_size_mb > 0:
        target_bits = cfg.target_size_mb * 8 * 1024 * 1024
        if not cfg.remove_audio:
            target_bits -= int(128_000 * duration * 1.05)  # 预留 128kbps 音频 + 5% 余量
        video_bitrate = max(int(target_bits / duration * 0.95), 100_000)
        args.extend(
            [
                "-b:v",
                str(video_bitrate),
                "-maxrate",
                str(video_bitrate),
                "-bufsize",
                str(video_bitrate * 2),
            ]
        )
    else:
        args.extend(["-crf", str(cfg.crf)])

    args.extend(["-y", str(output_path)])
    orig_size = input_path.stat().st_size
    cmd_preview = f"ffmpeg {' '.join(args)}"
    print(f"  ffmpeg: {cmd_preview}")
    with timed(f"压缩 {input_path.name} -> {output_path.name}"):
        run_ffmpeg(args, ffmpeg, progress_callback=_on_ffmpeg_progress)
    new_size = output_path.stat().st_size
    ratio = (1 - new_size / orig_size) * 100 if orig_size > 0 else 0
    print(
        f"  体积: {format_size(orig_size)} -> {format_size(new_size)}"
        f"（压缩 {ratio:.0f}%，目标 {cfg.target_size_mb:.0f} MB）"
    )
    return output_path
