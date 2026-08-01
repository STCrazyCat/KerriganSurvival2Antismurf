#!/usr/bin/env pwsh
# Prepare a new GitHub repository from a clean checkout.
# Usage: .\scripts\prepare_github_repo.ps1 -Remote "https://github.com/STCrazyCat/KerriganSurvival2Antismurf.git"

param(
    [Parameter(Mandatory = $true)]
    [string]$Remote,
    [string]$Branch = "main"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

if (Test-Path ".git") {
    Write-Error "This directory is already a git repository."
}

$repo = ""
if ($Remote -match "github\.com[:/](.+?)(?:\.git)?$") {
    $repo = $Matches[1]
}

Write-Host "Initializing git repository..."
git init
git checkout -b $Branch

Write-Host "Staging files (respecting .gitignore)..."
git add .

Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Replace STCrazyCat/KerriganSurvival2Antismurf in README.md, CONTRIBUTING.md, pyproject.toml, CHANGELOG.md"
if ($repo) {
    Write-Host "     Suggested value: $repo"
    Write-Host "     `$env:ANTISMURF_GITHUB_REPO = '$repo'"
}
Write-Host "  2. git commit -m 'Initial open-source release'"
Write-Host "  3. git remote add origin $Remote"
Write-Host "  4. git push -u origin $Branch"
Write-Host "  5. Create GitHub Release after running scripts\build_installer.ps1"
