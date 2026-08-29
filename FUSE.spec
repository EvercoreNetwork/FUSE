# -*- mode: python ; coding: utf-8 -*-
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules
block_cipher = None
# Collect GI typelibs - Linux only, optional on Windows/macOS
try:
    gi_datas = collect_data_files('gi', include_py_files=False)
except Exception:
    gi_datas = []
# Also ensure pystray backends collected (optional)
try:
    pystray_mods = collect_submodules('pystray')
except Exception:
    pystray_mods = []

# gi hiddenimports only on Linux; on Windows/macOS PyGObject not installed and would fail
if sys.platform.startswith("linux"):
    gi_hidden = ['gi', 'gi.repository.Gtk', 'gi.repository.GLib', 'gi.repository.GObject', 'gi.repository.Gdk', 'gi.repository.WebKit2', 'gi.repository.AyatanaAppIndicator3', 'gi.repository.AppIndicator3', 'cairo']
else:
    gi_hidden = []

a = Analysis(
    ['fuse.py'],
    pathex=[],
    binaries=[],
    datas=[('assets/logo-256.png', 'assets'), ('assets/logo.ico', 'assets'), ('frontend/tray.html', 'frontend'), ('frontend/index.html', 'frontend')] + gi_datas,
    hiddenimports=['pystray', 'PIL', 'watchdog', 'psutil'] + gi_hidden + pystray_mods,
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
    console=True,
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
