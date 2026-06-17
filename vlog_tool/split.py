from __future__ import annotations

from pathlib import Path

from vlog_tool.utils import get_duration_sec, run_ffmpeg, write_json_atomic


def split_video(
    video_path: Path,
    output_dir: Path,
    max_duration_min: int,
    ffmpeg: str,
    ffprobe: str,
) -> list[Path]:
    """Split a video into equal-length segments if it exceeds max_duration_min.

    Uses ffmpeg -c copy (no re-encode) for speed — segments are split at
    approximate keyframe boundaries, which is fine for AI analysis.

    Writes a JSON manifest sidecar (e.g. GL010683_split_manifest.json)
    recording each segment's source_stem, segment_index, offset_sec,
    and actual_duration_sec.

    Returns list of segment paths. If no splitting is needed, returns [video_path].
    """
    duration_sec = get_duration_sec(video_path, ffprobe)
    max_sec = max_duration_min * 60

    if duration_sec <= max_sec:
        return [video_path]

    num = int(duration_sec / max_sec) + (1 if duration_sec % max_sec > 0 else 0)
    seg_duration = duration_sec / num

    output_dir.mkdir(parents=True, exist_ok=True)
    segments: list[Path] = []
    manifest: list[dict] = []

    try:
        for i in range(num):
            start = round(i * seg_duration, 2)
            dur = round(seg_duration if i < num - 1 else duration_sec - i * seg_duration, 2)

            seg_path = output_dir / f"{video_path.stem}_seg{i + 1:02d}{video_path.suffix}"
            args = [
                "-ss",
                str(start),
                "-i",
                str(video_path),
                "-t",
                str(dur),
                "-c",
                "copy",
                "-map",
                "0:v:0",
                "-map",
                "0:a:0?",
                "-y",
                str(seg_path),
            ]
            run_ffmpeg(args, ffmpeg)
            segments.append(seg_path)
            manifest.append(
                {
                    "segment_index": i + 1,
                    "filename": seg_path.name,
                    "source_stem": video_path.stem,
                    "offset_sec": start,
                    "actual_duration_sec": dur,
                }
            )

        manifest_path = output_dir / f"{video_path.stem}_split_manifest.json"
        write_json_atomic(manifest_path, manifest)
    except BaseException:
        for f in segments:
            f.unlink(missing_ok=True)
        raise

    return segments
