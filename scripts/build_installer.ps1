# Build AntiSmurf-Memory.exe and Windows installer (Inno Setup)

param(
    [switch]$GrayRelease,
    [switch]$EnableAutoKick
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$Version = (Get-Content "VERSION" -Raw).Trim()
$GithubRepo = $env:ANTISMURF_GITHUB_REPO
if (-not $GithubRepo) {
    $GithubRepo = "STCrazyCat/KerriganSurvival2Antismurf"
}
$AppUrl = "https://github.com/$GithubRepo"

Write-Host "AntiSmurf version: $Version"
Write-Host "Repository URL: $AppUrl"

$metaArgs = @()
if ($GrayRelease) { $metaArgs += "--gray" }
if ($EnableAutoKick -and -not $GrayRelease) { $metaArgs += "--enable-auto-kick" }
python scripts/generate_build_meta.py @metaArgs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Step 1/3: PyInstaller ..."
python -m PyInstaller build.spec --noconfirm
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$ExePath = Join-Path $Root "dist\AntiSmurf-Memory.exe"
if (-not (Test-Path $ExePath)) {
    Write-Error "dist\AntiSmurf-Memory.exe not found after PyInstaller. Run from repo root after: pip install -r requirements.txt"
}

$IsccCandidates = @(
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
)
if ($env:INNO_SETUP_PATH -and (Test-Path $env:INNO_SETUP_PATH)) {
    $IsccCandidates = @($env:INNO_SETUP_PATH) + $IsccCandidates
}
# Where-Object may return a single string; wrap with @() so [0] is the path, not the first character.
$IsccCandidates = @($IsccCandidates | Where-Object { $_ -and (Test-Path $_) })

if ($IsccCandidates.Count -eq 0) {
    Write-Host ""
    Write-Host "Inno Setup 6 not found. Portable exe ready: dist\AntiSmurf-Memory.exe"
    exit 0
}

$Iscc = $IsccCandidates[0]
$VersionNumeric = ($Version -replace '-.*$', '') + '.0'
Write-Host "Step 2/3: Inno Setup ..."
Write-Host "  ISCC: $Iscc"
& "$Iscc" "/DAppVersion=$Version" "/DAppVersionNumeric=$VersionNumeric" "/DAppURL=$AppUrl" "installer\AntiSmurf-Memory.iss"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$InstallerPath = Join-Path $Root "dist\AntiSmurf-Memory-Setup-$Version.exe"
if (-not (Test-Path $InstallerPath)) {
    Write-Error "Expected installer not found: dist\AntiSmurf-Memory-Setup-$Version.exe"
}

Write-Host "Step 3/3: Portable zip ..."
$PortableZip = Join-Path $Root "dist\AntiSmurf-Memory-$Version-portable.zip"
$Staging = Join-Path $Root "dist\_portable_staging"
if (Test-Path $Staging) { Remove-Item $Staging -Recurse -Force }
New-Item -ItemType Directory -Path (Join-Path $Staging "config") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $Staging "data") -Force | Out-Null
Copy-Item $ExePath (Join-Path $Staging "AntiSmurf-Memory.exe")
Copy-Item (Join-Path $Root "config\user.toml.example") (Join-Path $Staging "config\user.toml.example")
Copy-Item (Join-Path $Root "config\blocklist.txt") (Join-Path $Staging "config\blocklist.txt") -ErrorAction SilentlyContinue
Copy-Item (Join-Path $Root "docs\规则设置手册.md") (Join-Path $Staging "规则设置手册.md") -ErrorAction SilentlyContinue
$ReleaseNotes = @"
AntiSmurf 内存扫描版 v$Version
==============================

便携版目录说明：
  AntiSmurf-Memory.exe   主程序（双击运行）
  config\                配置文件（首次可将 user.toml.example 复制为 user.toml）
  data\                  运行时数据（数据库、校准文件等，自动创建）

安装版（推荐）：
  dist\AntiSmurf-Memory-Setup-$Version.exe

构建时间：$(Get-Date -Format 'yyyy-MM-dd HH:mm')
"@
Set-Content -Path (Join-Path $Staging "发布说明.txt") -Value $ReleaseNotes -Encoding UTF8
if (Test-Path $PortableZip) { Remove-Item $PortableZip -Force }
Compress-Archive -Path (Join-Path $Staging "*") -DestinationPath $PortableZip -Force
Remove-Item $Staging -Recurse -Force

Write-Host ""
Write-Host "Release artifacts (dist\):" -ForegroundColor Green
Write-Host "  Portable exe:  dist\AntiSmurf-Memory.exe"
Write-Host "  Portable zip:  dist\AntiSmurf-Memory-$Version-portable.zip"
Write-Host "  Installer:     dist\AntiSmurf-Memory-Setup-$Version.exe"
Write-Host "Done." -ForegroundColor Green
