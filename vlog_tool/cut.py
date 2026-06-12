from __future__ import annotations

from pathlib import Path

from vlog_tool.log import format_duration, timed
from vlog_tool.utils import run_ffmpeg


def parse_time_range(range_str: str) -> tuple[float, float]:
    """将 '00:00-00:20' 格式解析为 (start_sec, end_sec)。"""
    parts = range_str.split("-", 1)
    if len(parts) != 2:
        raise ValueError(f"无法解析时间范围: {range_str}")
    start = _to_seconds(parts[0].strip())
    end = _to_seconds(parts[1].strip())
    if end <= start:
        raise ValueError(
            f"end ({parts[1].strip()}) 必须大于 start ({parts[0].strip()})"
        )
    return start, end


def _to_seconds(s: str) -> float:
    """将 'HH:MM:SS' 或 'MM:SS' 或秒数转为 float 秒。"""
    s = s.strip()
    if not s:
        return 0.0
    chunks = s.split(":")
    try:
        if len(chunks) == 3:
            return float(chunks[0]) * 3600 + float(chunks[1]) * 60 + float(chunks[2])
        if len(chunks) == 2:
            return float(chunks[0]) * 60 + float(chunks[1])
        return float(chunks[0])
    except (ValueError, IndexError) as e:
        raise ValueError(f"无法解析时间字符串 '{s}': {e}")


def cut_one(
    video_path: Path,
    output_path: Path,
    start_sec: float,
    end_sec: float,
    ffmpeg: str,
    reencode: bool = False,
) -> Path:
    """用 ffmpeg 从 video_path 中裁剪 [start_sec, end_sec] 区间到 output_path。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    duration_sec = end_sec - start_sec
    label = f"裁剪 {video_path.name} ({format_duration(start_sec)}-{format_duration(end_sec)})"

    args = [
        "-ss",
        str(start_sec),
        "-i",
        str(video_path),
        "-to",
        str(duration_sec),
    ]
    if reencode:
        args.extend(["-c:v", "libx264", "-crf", "23"])
    else:
        args.extend(["-c", "copy"])
    args.extend(["-y", str(output_path)])

    with timed(label):
        run_ffmpeg(args, ffmpeg)
    return output_path
