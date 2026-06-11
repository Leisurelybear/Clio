from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".webm"}

T = TypeVar("T")


def with_retry(
    fn: Callable[[], T],
    *,
    attempts: int = 3,
    base_delay: float = 1.0,
    retry_on: tuple[type[BaseException], ...],
    what: str = "operation",
) -> T:
    """调用 fn()，按指数退避（1s/2s/4s）重试最多 attempts 次。

    只对 retry_on 列出的异常类型重试；其它异常（如 ValueError）立即抛出。
    每次重试会打印一行（控制台 + 日志都看得到），最后一次失败时也打印。

    用法::

        return with_retry(
            lambda: self._client.post(...).json()["choices"][0]["message"]["content"],
            attempts=3, retry_on=(httpx.HTTPError,),
            what="OpenAI 兼容 API",
        )
    """
    last_exc: BaseException | None = None
    for i in range(attempts):
        try:
            return fn()
        except retry_on as e:
            last_exc = e
            if i + 1 >= attempts:
                print(
                    f"  [重试] {what} 失败 {attempts} 次，放弃: "
                    f"{type(e).__name__}: {e}"
                )
                break
            delay = base_delay * (2 ** i)
            print(
                f"  [重试] {what} 失败 ({type(e).__name__}: {str(e)[:80]})，"
                f"{delay:.1f}s 后重试 ({i + 2}/{attempts})"
            )
            time.sleep(delay)
    assert last_exc is not None
    raise last_exc


def extract_json(text: str) -> dict:
    """从 AI 返回的文本中容错提取 JSON 对象。

    先尝试整体解析（多数情况）；失败时用正则抓第一个 {...} 块。
    都失败时抛出 ValueError，含原文前 500 字方便排查。
    """
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            return json.loads(match.group())
        raise ValueError(f"AI 返回内容无法解析为 JSON:\n{text[:500]}")


def mask_if_looks_like_key(value: str) -> str:
    """如果字符串看起来像 API key 而非环境变量名，遮蔽中间部分。

    避免错误信息把误填的 key 原样回显到终端/日志。
    """
    if not value:
        return value
    if value.startswith(("sk-", "sk_", "AIza", "gho_", "ghp_", "xai-")) and len(value) > 12:
        return f"{value[:4]}***{value[-4:]}"
    if len(value) > 32 and " " not in value:
        return f"{value[:6]}***{value[-4:]}"
    return value


def discover_ffmpeg_bin(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found

    local_app = Path(os.environ.get("LOCALAPPDATA", ""))
    search_roots = [
        local_app / "Microsoft/WinGet/Packages",
        Path("C:/ffmpeg"),
        Path("G:/ffmpeg"),
    ]
    for root in search_roots:
        if not root.is_dir():
            continue
        matches = sorted(root.glob(f"**/{name}.exe"))
        if matches:
            return str(matches[0])
    return None


def resolve_binary(configured: str, fallback: str) -> str:
    if configured:
        path = Path(configured)
        if path.is_file():
            return str(path)
        raise FileNotFoundError(f"找不到可执行文件: {configured}")

    found = discover_ffmpeg_bin(fallback)
    if found:
        return found
    raise FileNotFoundError(
        f"找不到 {fallback}。请运行 setup.ps1 安装，或在 config.yaml 的 paths 中填写路径。"
    )


def find_videos(directory: Path, recursive: bool = False) -> list[Path]:
    if not directory.is_dir():
        raise NotADirectoryError(f"素材目录不存在: {directory}")
    if recursive:
        files = [
            p for p in sorted(directory.rglob("*"))
            if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS
        ]
    else:
        files = [
            p for p in sorted(directory.iterdir())
            if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS
        ]
    return files


def get_duration_sec(video_path: Path, ffprobe: str) -> float:
    cmd = [
        ffprobe,
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return float(result.stdout.strip())


def sanitize_name(text: str, max_len: int = 40) -> str:
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", text)
    text = re.sub(r"\s+", "_", text.strip())
    return text[:max_len] or "clip"


def format_index(index: int, width: int) -> str:
    return str(index).zfill(width)


def probe_video_info(video_path: Path, ffprobe: str) -> dict:
    duration = get_duration_sec(video_path, ffprobe)
    size_mb = video_path.stat().st_size / (1024 * 1024)
    return {"duration_sec": round(duration, 2), "size_mb": round(size_mb, 2)}


def run_ffmpeg(args: list[str], ffmpeg: str) -> None:
    cmd = [ffmpeg, *args]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg 执行失败:\n{' '.join(cmd)}\n{result.stderr}"
        )
