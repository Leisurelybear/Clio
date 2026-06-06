#!/usr/bin/env python3
"""单视频分析示例（完整工具请用 main.py analyze -i 文件夹）"""

from pathlib import Path

from vlog_tool.analyze import analyze_video
from vlog_tool.compress import compress_video
from vlog_tool.config import load_config

VIDEO_PATH = Path(r"E:\Videos\云南\05042024194855.mov")


def main():
    config = load_config("config.yaml")
    compressed = Path("./output/compressed/single_preview.mp4")
    compressed.parent.mkdir(parents=True, exist_ok=True)

    print("压缩中...")
    compress_video(VIDEO_PATH, compressed, config)

    print("AI 分析中...")
    result = analyze_video(str(compressed), config)
    print(result)


if __name__ == "__main__":
    main()
