#!/usr/bin/env pwsh
# Install PaddlePaddle + PaddleOCR for lobby OCR.
# Requires Python 3.9–3.13 (NOT 3.14). CPU build by default.

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$pyVersion = python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
$pyMajor, $pyMinor = $pyVersion.Split(".") | ForEach-Object { [int]$_ }

if ($pyMajor -eq 3 -and $pyMinor -ge 14) {
    Write-Host "ERROR: Python $pyVersion is not supported by PaddlePaddle." -ForegroundColor Red
    Write-Host "Please install Python 3.12 or 3.13 (64-bit) and recreate your venv:"
    Write-Host "  https://www.python.org/downloads/"
    Write-Host "  py -3.12 -m venv .venv"
    exit 1
}

if ($pyMajor -eq 3 -and $pyMinor -lt 9) {
    Write-Host "ERROR: Python $pyVersion is too old. Use Python 3.9–3.13." -ForegroundColor Red
    exit 1
}

$PaddleVersion = $env:PADDLE_VERSION
if (-not $PaddleVersion) { $PaddleVersion = "3.3.0" }

$Index = $env:PADDLE_INDEX
if (-not $Index) {
    $Index = "https://www.paddlepaddle.org.cn/packages/stable/cpu/"
}

Write-Host "Installing PaddlePaddle $PaddleVersion (CPU) from Paddle index..."
python -m pip install "paddlepaddle==$PaddleVersion" -i $Index
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Installing PaddleOCR..."
python -m pip install -r requirements-vision.txt
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "Vision dependencies installed. Verify with:"
Write-Host "  python -c `"from paddleocr import PaddleOCR; print('OK')`""
