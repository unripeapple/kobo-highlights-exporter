# KoboHighlightsExporter.spec
# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_submodules
import glob
import os

# Manually include assets folder
datas = [(f, "assets") for f in glob.glob("assets/**/*", recursive=True) if os.path.isfile(f)]

hiddenimports = [
    "PIL._tkinter_finder",
    "PIL.ImageTk",
]

a = Analysis(
    ['src/kobo_exporter/main.py'],
    pathex=['.'],
    binaries=[],  # no extra binaries
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    name='KoboHighlightsExporter',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # GUI app
    icon='assets/app_icon.icns',
)

# COLLECT: do NOT pass the EXE folder! Only pass exe, datas, binaries
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    name='KoboHighlightsExporter',
)
