#!/usr/bin/env pwsh
# Install all AntiSmurf dependencies (core + optional OCR stack).

param(
    [switch]$SkipVision
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

Write-Host "Installing core dependencies..."
python -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if (-not $SkipVision) {
    & "$Root\scripts\install_vision_deps.ps1"
    exit $LASTEXITCODE
}

Write-Host "Core install complete. For OCR, run: .\scripts\install_vision_deps.ps1"
