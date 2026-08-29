# -*- mode: python ; coding: utf-8 -*-
block_cipher = None
a = Analysis(
    ['fuse.py'],
    pathex=[],
    binaries=[],
    datas=[('assets/logo-256.png', 'assets'), ('assets/logo.ico', 'assets')],
    hiddenimports=['pystray', 'PIL', 'watchdog', 'psutil', 'gi'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='FUSE',
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
    icon='assets/logo.ico',
)
# For macOS .app
app = BUNDLE(
    exe,
    name='FUSE.app',
    icon='assets/logo.ico',
    bundle_identifier='network.evercore.fuse',
)
