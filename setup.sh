#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

echo "=== Vlog 剪辑辅助工具 - 环境配置 ==="

# ---- Python 版本检查（项目要求 3.11+）----
pyVer=$(python3 --version 2>&1) || {
    echo "错误：未检测到 Python3，请安装 Python 3.11 或更高版本" >&2
    echo "      下载: https://python.org/downloads/" >&2
    echo -n "      是否在浏览器中打开下载页面? (Y/n) " >&2
    read -r choice
    if [ "$choice" != "n" ] && [ "$choice" != "N" ]; then
        case "$(uname -s)" in
            Darwin) open "https://python.org/downloads/" 2>/dev/null || true ;;
            Linux)  xdg-open "https://python.org/downloads/" 2>/dev/null || true ;;
        esac
    fi
    exit 1
}
if [[ $pyVer =~ Python\ ([0-9]+)\.([0-9]+) ]]; then
    major=${BASH_REMATCH[1]}
    minor=${BASH_REMATCH[2]}
    if [[ $major -lt 3 || ($major -eq 3 && $minor -lt 11) ]]; then
        echo "错误：需要 Python 3.11+，当前版本: $pyVer" >&2
        echo "      下载: https://python.org/downloads/" >&2
        case "$(uname -s)" in
            Darwin) echo "      推荐: brew install python@3.12" >&2 ;;
            Linux)  echo "      推荐: sudo apt install python3 python3-pip（或使用系统包管理器）" >&2 ;;
        esac
        echo -n "      是否在浏览器中打开下载页面? (Y/n) " >&2
        read -r choice
        if [ "$choice" != "n" ] && [ "$choice" != "N" ]; then
            case "$(uname -s)" in
                Darwin) open "https://python.org/downloads/" 2>/dev/null || true ;;
                Linux)  xdg-open "https://python.org/downloads/" 2>/dev/null || true ;;
            esac
        fi
        exit 1
    fi
    echo "     Python $major.$minor - 版本检查通过"
else
    echo "错误：无法解析 Python 版本: $pyVer" >&2
    echo "      请从 https://python.org/downloads/ 安装 Python 3.11+" >&2
    exit 1
fi

# 1. Python 虚拟环境
if [ -f ".venv/bin/python" ]; then
    venvVer=$(.venv/bin/python --version 2>&1)
    if [[ $venvVer =~ Python\ ([0-9]+)\.([0-9]+) ]]; then
        vmajor=${BASH_REMATCH[1]}
        vminor=${BASH_REMATCH[2]}
        if [[ $vmajor -lt 3 || ($vmajor -eq 3 && $vminor -lt 11) ]]; then
            echo "     虚拟环境 Python 版本过旧 ($vmajor.$vminor)，正在重建..."
            rm -rf ".venv"
        fi
    fi
fi
if [ ! -f ".venv/bin/python" ]; then
    echo "[1/4] 创建 Python 虚拟环境..."
    python3 -m venv .venv
else
    echo "[1/4] 虚拟环境已存在，跳过"
fi

# 确保虚拟环境中有 pip（某些系统 Python 不会自带）
if ! .venv/bin/python -m pip --version >/dev/null 2>&1; then
    echo "     正在通过 ensurepip 安装 pip..."
    if ! .venv/bin/python -m ensurepip --upgrade --default-pip; then
        echo "     ensurepip 不可用，下载 get-pip.py..."
        curl -fsSL --connect-timeout 30 -o /tmp/get-pip.py https://bootstrap.pypa.io/get-pip.py || {
            echo "     无法下载 get-pip.py，请检查网络或手动安装: python3 -m ensurepip --upgrade" >&2
            exit 1
        }
        .venv/bin/python /tmp/get-pip.py
        rm -f /tmp/get-pip.py
    fi
fi

echo "[2/4] 安装 Python 依赖..."
.venv/bin/python -m pip install --upgrade pip -q
.venv/bin/python -m pip install -r requirements.txt -q

# Whisper 语音转录（可选加速）
read -rp "是否安装 Whisper 语音转录? (y/N, 默认 N) " whisperAnswer
if [ "$whisperAnswer" = "y" ] || [ "$whisperAnswer" = "Y" ]; then
    echo "[2b] 安装 faster-whisper 及推理依赖..."
    if ! .venv/bin/python -m pip install -r requirements-whisper.txt -q; then
        echo "     Whisper 依赖安装失败，跳过后续步骤" >&2
    else
        if command -v nvidia-smi &>/dev/null; then
            echo "     检测到 NVIDIA GPU，安装 CUDA 运行时加速..."
            free_kb=$(df -k . | awk 'NR==2{print $4}' 2>/dev/null || echo 0)
            cuda_args=""
            if [ "$free_kb" -gt 0 ] && [ "$free_kb" -lt $((5*1024*1024)) ]; then
                echo "     磁盘仅剩 $((free_kb/1024/1024))GB，使用无缓存模式安装..."
                cuda_args="--no-cache-dir"
            fi
            if ! .venv/bin/python -m pip install nvidia-cublas-cu12 nvidia-cudnn-cu12 $cuda_args -q; then
                echo "     CUDA 运行时安装失败，将使用 CPU 运行（速度较慢）"
            fi
        else
            echo "     未检测到 NVIDIA GPU，将使用 CPU 运行（速度较慢）"
        fi
    fi
else
    echo "     跳过 Whisper 安装，后续可运行 'python main.py whisper install' 单独安装"
fi

# 2. ffmpeg
if ! command -v ffmpeg &>/dev/null; then
    echo "[3/4] 未检测到 ffmpeg，尝试安装..."
    case "$(uname -s)" in
        Linux)
            if command -v apt-get &>/dev/null; then
                sudo apt-get update -qq && sudo apt-get install -y -qq ffmpeg || echo "     apt 安装失败，请手动安装: https://ffmpeg.org/download.html" >&2
            elif command -v dnf &>/dev/null; then
                sudo dnf install -y ffmpeg || echo "     dnf 安装失败，请手动安装: https://ffmpeg.org/download.html" >&2
            elif command -v brew &>/dev/null; then
                brew install ffmpeg || echo "     brew 安装失败，请手动安装: https://ffmpeg.org/download.html" >&2
            else
                echo "     请手动安装 ffmpeg: https://ffmpeg.org/download.html" >&2
            fi
            ;;
        Darwin)
            if command -v brew &>/dev/null; then
                brew install ffmpeg || echo "     brew 安装失败，请手动安装: https://ffmpeg.org/download.html" >&2
            else
                echo "     请先安装 Homebrew (https://brew.sh)，然后运行: brew install ffmpeg" >&2
            fi
            ;;
    esac
else
    echo "[3/4] ffmpeg 已就绪: $(command -v ffmpeg)"
fi

# 3. .env
if [ ! -f ".env" ]; then
    cp ".env.example" ".env"
    echo "[4/4] 已创建 .env，请编辑并填入 GEMINI_API_KEY"
else
    echo "[4/4] .env 已存在"
fi

# 4. config.yaml
if [ ! -f "config.yaml" ] && [ -f "config.example.yaml" ]; then
    cp "config.example.yaml" "config.yaml"
    echo "[*] 已创建 config.yaml，请按需修改 paths / proxy"
fi

# 5. Git hooks
hooksPath=$(git config core.hooksPath || true)
if [ "$hooksPath" != ".githooks" ]; then
    echo "[5/5] 设置 git hooks 路径为 .githooks..."
    git config core.hooksPath .githooks
else
    echo "[5/5] git hooks 路径已配置为 .githooks"
fi

echo ""
echo "=== 环境检查 ==="
.venv/bin/python main.py check

echo ""
echo "配置完成后运行:"
echo "  source .venv/bin/activate"
echo "  python main.py run --day day1"
