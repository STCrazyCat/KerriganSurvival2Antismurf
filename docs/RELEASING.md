# Release guide

This document describes how maintainers publish AntiSmurf for end users (Windows installer) while keeping source on GitHub.

## Versioning

- Single source of truth: [`VERSION`](../VERSION) (e.g. `1.0.0`)
- Tag format: `v1.0.0` (must match `VERSION` with a `v` prefix)
- Update [`CHANGELOG.md`](../CHANGELOG.md): move `[Unreleased]` items into the new version section

## Pre-release checklist

1. All tests pass: `python -m pytest`
2. `VERSION` and `CHANGELOG.md` updated
3. Replace `STCrazyCat/KerriganSurvival2Antismurf` placeholders in README/CONTRIBUTING if not done yet
4. No secrets in the tree (`config/user.toml`, API keys)

## Build Windows artifacts (maintainer machine)

Requirements:

- Windows 10/11 x64
- **Python 3.11–3.13** (64-bit) with `pip install -r requirements.txt` and `.\scripts\install_vision_deps.ps1`
- [Inno Setup 6](https://jrsoftware.org/isdl.php) (optional, for `.exe` installer)

```powershell
cd AntiSmurf
# 构建便携版 + 安装包（自动踢人启用,见 docs/BRANCHES.md）
.\scripts\build_installer.ps1 -EnableAutoKick
```

Outputs:

| File | Description |
|------|-------------|
| `dist/AntiSmurf.exe` | 便携版主程序 |
| `dist/AntiSmurf-Setup-x.y.z.exe` | 安装包 |
| `dist/AntiSmurf-x.y.z-portable.zip` | 便携压缩包 |

Optional: set GitHub URL baked into installer metadata:

```powershell
$env:ANTISMURF_GITHUB_REPO = "STCrazyCat/KerriganSurvival2Antismurf"
.\scripts\build_installer.ps1
```

## Publish to GitHub Releases

1. Commit release prep and push to `main`
2. Create and push tag:

```bash
git tag -a v1.0.0 -m "Release 1.0.0"
git push origin v1.0.0
```

3. On GitHub: **Releases → Draft a new release** → select tag `v1.0.0`
4. Upload assets:
   - `AntiSmurf-Setup-x.y.z.exe` (recommended for most users)
   - `AntiSmurf.exe` (portable)
5. Paste changelog section from `CHANGELOG.md` as release notes

GitHub Actions (`.github/workflows/release.yml`) validates the tag on push; **installer binaries are built locally** due to PyInstaller + PaddleOCR size and Windows-only dependencies.

## First-time GitHub repository setup

```bash
git init
git add .
git commit -m "Initial open-source release"
git branch -M main
git remote add origin https://github.com/STCrazyCat/KerriganSurvival2Antismurf.git
git push -u origin main
```

Recommended repository settings:

- Default branch: `main`
- Enable Issues and Discussions (optional)
- Add topics: `starcraft2`, `kerrigan-survival`, `anti-cheat`, `python`
- Branch protection on `main`: require CI status check `test`

## Post-release

- Verify installer on a clean VM or secondary account
- Open a follow-up issue for any known limitations documented in README
