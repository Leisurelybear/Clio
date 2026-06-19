#!/usr/bin/env pwsh
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSCommandPath
Set-Location $root

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Virtual environment not found. Run .\setup.ps1 first." -ForegroundColor Red
    exit 1
}

Write-Host "Installing faster-whisper and pre-downloading model..." -ForegroundColor Cyan
.\.venv\Scripts\python.exe main.py whisper install
if ($LASTEXITCODE -eq 0) {
    Write-Host "Whisper 安装完成，模型已预下载到本地。" -ForegroundColor Green
} else {
    Write-Host "安装失败，请检查网络或 hf_endpoint 配置。" -ForegroundColor Red
}
