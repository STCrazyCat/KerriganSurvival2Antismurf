# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

root = Path(SPECPATH)
exe_name = "AntiSmurf"

a = Analysis(
    [str(root / "main.py")],
    pathex=[str(root / "src")],
    binaries=[],
    datas=[
        (str(root / "config"), "config"),
    ],
    hiddenimports=[
        "customtkinter",
        "pywinauto",
        "win32gui",
        "win32con",
        "win32process",
        "win32api",
        "winotify",
        "sc2reader",
        "sc2reader.events",
        "sc2reader.resources",
        "sc2reader.factories",
        "mpyq",
        "antismurf.build_meta",
        "cv2",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=exe_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
