# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for building torchain as a Linux AppImage.

Usage (from the repo root on Linux):
    pip install pyinstaller
    pyinstaller linux/torchain_portable.spec

The output is dist/torchain/ — an AppDir ready for appimagetool.
"""
import os
import sys
import subprocess

block_cipher = None
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(SPEC), '..'))

# ---------------------------------------------------------------------------
# Detect tor binary to bundle
# ---------------------------------------------------------------------------
def _find_tor() -> str | None:
    """Find tor binary on the system."""
    result = subprocess.run(["which", "tor"], capture_output=True, text=True)
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    for p in ("/usr/bin/tor", "/usr/local/bin/tor"):
        if os.path.isfile(p):
            return p
    return None

_tor_path = _find_tor()
_binaries = []
_datas = []

if _tor_path:
    _binaries.append((_tor_path, '.'))

# Bundle geoip databases if found
for geoip_dir in ("/usr/share/tor", "/usr/share/torbrowser"):
    for f in ("geoip", "geoip6"):
        p = os.path.join(geoip_dir, f)
        if os.path.isfile(p):
            _datas.append((p, 'tor_data'))

a = Analysis(
    [os.path.join(REPO_ROOT, 'tc4', '__main__.py')],
    pathex=[REPO_ROOT],
    binaries=_binaries,
    datas=_datas,
    hiddenimports=[
        'tkinter',
        'tkinter.ttk',
        'tkinter.messagebox',
        'tkinter.constants',
        'tkinter.font',
        '_tkinter',
        'json',
        'ctypes',
        'dataclasses',
        'logging',
        'logging.handlers',
        'subprocess',
        'shutil',
        'threading',
        'queue',
        'math',
        'struct',
        'zlib',
        'base64',
        'webbrowser',
        'tempfile',
        'ipaddress',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'numpy', 'pandas', 'scipy', 'matplotlib', 'PIL',
        'pytest', 'unittest', 'doctest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='torchain',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=True,
    console=True,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=True,
    upx=True,
    upx_exclude=[],
    name='torchain',
)
