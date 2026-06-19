#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -f ".venv/bin/python" ]; then
    echo "Virtual environment not found. Run bash setup.sh first." >&2
    exit 1
fi

echo "Installing faster-whisper and pre-downloading model..."
.venv/bin/python main.py whisper install
if [ $? -eq 0 ]; then
    echo "Whisper 安装完成，模型已预下载到本地。"
else
    echo "安装失败，请检查网络或 hf_endpoint 配置。" >&2
fi
