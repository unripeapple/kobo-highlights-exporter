# KoboHighlightsExporter.spec
from PyInstaller.utils.hooks import collect_data_files
from PyInstaller.building.build_main import Analysis, PYZ, EXE, COLLECT

datas = collect_data_files('assets')

a = Analysis(
    ['src/kobo_exporter/main.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=["PIL._tkinter_finder", "PIL.ImageTk"],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,  # crucial for COLLECT
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
