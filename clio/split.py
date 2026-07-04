from __future__ import annotations

import threading
from pathlib import Path
from typing import cast

from clio.utils import JsonValue, get_duration_sec, run_ffmpeg, write_json_atomic


def split_video(
    video_path: Path,
    output_dir: Path,
    max_duration_min: int,
    ffmpeg: str,
    ffprobe: str,
    reencode: bool = False,
    manifest_dir: Path | None = None,
    cancel_event: threading.Event | None = None,
) -> list[Path]:
    """Split a video into equal-length segments if it exceeds max_duration_min.

    Uses ffmpeg -c copy (no re-encode) for speed — segments are split at
    approximate keyframe boundaries, which is fine for AI analysis.
    When reencode=True, re-encodes at each cut point for precise frame-accurate
    splitting (slower but avoids black frames at segment start).

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
            if reencode:
                args = [
                    "-ss",
                    str(start),
                    "-i",
                    str(video_path),
                    "-t",
                    str(dur),
                    "-c:v",
                    "libx264",
                    "-preset",
                    "fast",
                    "-crf",
                    "23",
                    "-c:a",
                    "aac",
                    "-map",
                    "0:v:0",
                    "-map",
                    "0:a:0?",
                    "-y",
                    str(seg_path),
                ]
            else:
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
            if cancel_event is None:
                run_ffmpeg(args, ffmpeg)
            else:
                run_ffmpeg(args, ffmpeg, cancel_event=cancel_event)
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

        manifest_target = manifest_dir or output_dir
        manifest_path = manifest_target / f"{video_path.stem}_split_manifest.json"
        write_json_atomic(manifest_path, cast(JsonValue, manifest))
    except BaseException:
        for f in segments:
            f.unlink(missing_ok=True)
        raise

    return segments
