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
