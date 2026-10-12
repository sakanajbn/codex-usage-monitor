# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules


project_root = Path(SPECPATH).parent
source_root = project_root / "src"
hiddenimports = collect_submodules("codex_monitor")

a = Analysis(
    [str(source_root / "codex_monitor" / "main.py")],
    pathex=[str(source_root)],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
# PyInstaller's ICU DLLs can shadow Windows ICU and prevent QtCore/QtWidgets loading.
icu_conflicts = {"icuuc.dll", "icudt78.dll"}
a.binaries = [entry for entry in a.binaries if Path(entry[1]).name.lower() not in icu_conflicts]
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="Codex监控面板_win_x64",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
)
