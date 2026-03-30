# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['src/kobo_exporter/main.py'],
    pathex=['src'],
    binaries=[],
    datas=[('assets', 'assets')],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Kobo Highlights Exporter',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    argv_emulation=True,
    target_arch="arm64",
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/app_icon.icns',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Kobo Highlights Exporter',
)

app = BUNDLE(
    coll,
    name='Kobo Highlights Exporter.app',
    icon='assets/app_icon.icns',
    bundle_identifier='com.yourname.kobohighlightsexporter',
)
