from __future__ import annotations

import json
import os
from pathlib import Path


def load_selected_videos(project_dir: Path) -> list[Path]:
    video_file = project_dir / "videos.json"
    if not video_file.is_file():
        return []
    try:
        data = json.loads(video_file.read_text(encoding="utf-8"))
        return [Path(p) for p in data]
    except (json.JSONDecodeError, OSError):
        return []


def save_selected_videos(project_dir: Path, videos: list[Path]) -> None:
    video_file = project_dir / "videos.json"
    video_file.parent.mkdir(parents=True, exist_ok=True)
    data = [str(p) for p in videos]
    suffix = os.urandom(4).hex()
    tmp = video_file.with_suffix(f".json.tmp.{suffix}")
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        tmp.replace(video_file)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
