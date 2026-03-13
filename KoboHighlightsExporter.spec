# KoboHighlightsExporter.spec
# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_submodules
import glob
import os


datas = [(f, "assets") for f in glob.glob("assets/**/*", recursive=True) if os.path.isfile(f)]

hiddenimports = [
    "PIL._tkinter_finder",
    "PIL.ImageTk",
]

a = Analysis(
    ['src/kobo_exporter/main.py'],
    pathex=['.'],
    binaries=[],  
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
    console=False, 
    icon='assets/app_icon.icns',
)


coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    name='KoboHighlightsExporter',
)
