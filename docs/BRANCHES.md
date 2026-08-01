# 分支与构建风味

AntiSmurf 在**同一代码库**中维护两种发布风味，功能一致；差异仅在于是否包含**可手动开启的内存扫描**。

| 风味 | 分支建议 | 可执行文件 | 安装包 |
|------|----------|------------|--------|
| **standard** | `main` | `AntiSmurf.exe` | `AntiSmurf-Setup-x.y.z.exe` |
| **memory** | `memory-scan` | `AntiSmurf-Memory.exe` | `AntiSmurf-Memory-Setup-x.y.z.exe` |

两种构建均包含：OCR 识别、录像扫描、规则评分、名册同步等全部功能。  
仅 **memory** 构建在界面显示 **「内存扫描」** 开关，并可读取 `data/memory_profile.db`。

## 本地开发（默认 memory）

本地打包**始终默认 memory 风味**（便于测试内存扫描）：

```powershell
.\scripts\build_installer.ps1
# 等价于
.\scripts\build_installer.ps1 -Flavor memory
```

打包结束后会自动将 `src/antismurf/build_meta.py` 恢复为 `memory`，方便继续开发。

## 正式版（standard）

```powershell
.\scripts\build_installer.ps1 -Flavor standard
```

## 一次打出两个安装包

```powershell
.\scripts\build_installer.ps1 -AllFlavors
```

输出：

- `dist/AntiSmurf.exe` + `dist/AntiSmurf-Setup-{VERSION}.exe`
- `dist/AntiSmurf-Memory.exe` + `dist/AntiSmurf-Memory-Setup-{VERSION}.exe`

## Git 分支工作流

```bash
# 主分支：面向公开发布（CI 打 standard 包）
git checkout main

# 内存扫描分支：与 main 功能同步，本地/内测默认打 memory 包
git checkout memory-scan
git merge main   # 或 rebase，保持两分支一致
```

建议：

1. 日常功能开发在 `main` 完成并跑测试。
2. 合并到 `memory-scan` 后本地用 `build_installer.ps1`（默认 memory）出内测安装包。
3. 发 GitHub Release 时对 `main` 打 tag，用 `-Flavor standard` 或 `-AllFlavors` 上传产物。

## 技术说明

打包前 `scripts/generate_build_meta.py` 会写入 `build_meta.py`：

- `MEMORY_SCAN_AVAILABLE` — 是否在运行时暴露内存扫描 UI 与逻辑
- `APP_EXE_BASENAME` — PyInstaller 输出文件名

该文件在仓库中默认值为 `memory`，保证 `pytest` 与 `python main.py` 无需先打包即可测试内存功能。
