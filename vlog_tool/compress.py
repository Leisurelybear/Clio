from __future__ import annotations

from pathlib import Path

from vlog_tool.config import AppConfig
from vlog_tool.utils import get_duration_sec, resolve_binary, run_ffmpeg


def compress_video(
    input_path: Path,
    output_path: Path,
    config: AppConfig,
) -> Path:
    """压缩视频：去声音、降分辨率，尽量接近目标大小。"""
    ffmpeg = resolve_binary(config.paths.ffmpeg, "ffmpeg")
    ffprobe = resolve_binary(config.paths.ffprobe, "ffprobe")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    duration = get_duration_sec(input_path, ffprobe)
    if duration <= 0:
        raise ValueError(f"无法读取视频时长: {input_path}")

    cfg = config.compress
    vf = f"scale=min({cfg.max_width},iw):-2,fps={cfg.fps}"

    args = ["-i", str(input_path), "-vf", vf, "-c:v", cfg.codec]

    if cfg.remove_audio:
        args.append("-an")

    if cfg.target_size_mb > 0:
        target_bits = cfg.target_size_mb * 8 * 1024 * 1024
        video_bitrate = max(int(target_bits / duration * 0.92), 100_000)
        args.extend([
            "-b:v", str(video_bitrate),
            "-maxrate", str(video_bitrate),
            "-bufsize", str(video_bitrate * 2),
        ])
    else:
        args.extend(["-crf", str(cfg.crf)])

    args.extend(["-y", str(output_path)])
    run_ffmpeg(args, ffmpeg)
    return output_path
