# 分支与构建

AntiSmurf 现在只有**单一版本**（内存模式 6 大厅识别），不再区分 standard / memory 风味。

## 构建

```powershell
# 构建便携版 + 安装包（自动踢人启用）
.\scripts\build_installer.ps1 -EnableAutoKick
```

输出：

- `dist/AntiSmurf.exe` — 便携版主程序
- `dist/AntiSmurf-Setup-{VERSION}.exe` — 安装包
- `dist/AntiSmurf-{VERSION}-portable.zip` — 便携压缩包

若未安装 Inno Setup，脚本仍会生成便携版 exe，并提示如何单独编译安装包。

## 技术说明

打包前 `scripts/generate_build_meta.py` 会写入 `src/antismurf/build_meta.py`（版本号、自动踢人开关、产物文件名），该文件默认值为当前版本，保证 `pytest` 与 `python main.py` 无需先打包即可测试内存功能。
