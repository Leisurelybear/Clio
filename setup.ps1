# Vlog 工具一键配置脚本（PowerShell）
# 用法: .\setup.ps1

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
Set-Location $ProjectRoot

Write-Host "=== Vlog 剪辑辅助工具 - 环境配置 ===" -ForegroundColor Cyan

# 1. Python 虚拟环境
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "[1/4] 创建 Python 虚拟环境..."
    python -m venv .venv
} else {
    Write-Host "[1/4] 虚拟环境已存在，跳过"
}

Write-Host "[2/4] 安装 Python 依赖..."
.\.venv\Scripts\python.exe -m pip install --upgrade pip -q
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -q

# Whisper 语音转录（可选加速）
$whisperAnswer = Read-Host "是否安装 Whisper 语音转录? (y/N, 默认 N)"
if ($whisperAnswer -eq 'y' -or $whisperAnswer -eq 'Y') {
    Write-Host "[2b] 安装 faster-whisper 及推理依赖..." -ForegroundColor Yellow
    .\.venv\Scripts\python.exe -m pip install -r requirements-whisper.txt -q
    if ($LASTEXITCODE -ne 0) {
        Write-Host "     Whisper 依赖安装失败，跳过后续步骤" -ForegroundColor Red
    } else {
        # 检测 CUDA 显卡
        $cudaAvail = $false
        try {
            $nvidiaSmi = Get-Command nvidia-smi -ErrorAction Stop
            $cudaAvail = $true
            Write-Host "     检测到 NVIDIA GPU，安装 CUDA 运行时加速..." -ForegroundColor Green
            .\.venv\Scripts\python.exe -m pip install nvidia-cublas-cu12 nvidia-cudnn-cu12 -q
            if ($LASTEXITCODE -ne 0) {
                Write-Host "     CUDA 运行时安装失败，将使用 CPU 运行（速度较慢）" -ForegroundColor DarkYellow
            }
        } catch {
            Write-Host "     未检测到 NVIDIA GPU，将使用 CPU 运行（速度较慢）" -ForegroundColor DarkYellow
        }
    }
} else {
    Write-Host "     跳过 Whisper 安装，后续可运行 'python main.py whisper install' 单独安装" -ForegroundColor DarkYellow
}

# 2. ffmpeg
$ffmpeg = Get-Command ffmpeg -ErrorAction SilentlyContinue
if (-not $ffmpeg) {
    $wingetFfmpeg = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Filter ffmpeg.exe -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($wingetFfmpeg) {
        Write-Host "[3/4] 检测到 WinGet 安装的 ffmpeg: $($wingetFfmpeg.FullName)"
    } else {
        Write-Host "[3/4] 未检测到 ffmpeg，尝试通过 winget 安装..."
        winget install --id Gyan.FFmpeg -e --accept-package-agreements --accept-source-agreements
    }
} else {
    Write-Host "[3/4] ffmpeg 已就绪: $($ffmpeg.Source)"
}

# 3. .env
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "[4/4] 已创建 .env，请编辑并填入 GEMINI_API_KEY"
} else {
    Write-Host "[4/4] .env 已存在"
}

# 4. config.yaml
if (-not (Test-Path "config.yaml") -and (Test-Path "config.example.yaml")) {
    Copy-Item "config.example.yaml" "config.yaml"
    Write-Host "[*] 已创建 config.yaml，请按需修改 paths / proxy"
}

# 5. Git hooks
$hooksPath = git config core.hooksPath
if ($hooksPath -ne ".githooks") {
    Write-Host "[5/5] 设置 git hooks 路径为 .githooks..."
    git config core.hooksPath .githooks
} else {
    Write-Host "[5/5] git hooks 路径已配置为 .githooks"
}

Write-Host ""
Write-Host "=== 环境检查 ===" -ForegroundColor Cyan
.\.venv\Scripts\python.exe main.py check

Write-Host ""
Write-Host "配置完成后运行:" -ForegroundColor Green
Write-Host "  .\.venv\Scripts\Activate.ps1"
Write-Host "  python main.py run --day day1"
