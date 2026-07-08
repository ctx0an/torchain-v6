# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for building torchain as a portable folder distribution.

Usage (from the repo root on Windows):
    pip install pyinstaller
    pyinstaller windows/torchain_portable.spec

The output is dist/torchain/ — a folder containing torchain.exe and ALL
dependencies (Python, VC++ DLLs, Tcl/Tk, tkinter, tor.exe). The folder
is fully portable: copy it to any Windows 10/11 machine and run.

A folder distribution is used instead of --onefile because tkinter's Tcl/Tk
runtime needs its data directories on disk. The build script zips the folder
into dist/torchain-portable.zip for easy transport.
"""
import os
import sys
import glob as _glob

block_cipher = None
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(SPEC), '..'))

# ---------------------------------------------------------------------------
# Auto-detect VC++ Redistributable DLLs from the Python install dir.
# These are needed by the Python interpreter and tor.exe.  We search:
#   1. The directory containing the Python we're building with
#   2. The system System32 directory
# The DLLs are small (~150 KB each) so bundling them is cheap.
# ---------------------------------------------------------------------------
_binaries = []

_VC_DLLS = [
    "vcruntime140.dll",
    "vcruntime140_1.dll",
    "msvcp140.dll",
    "vcruntime140_threads.dll",
]

def _find_vc_dll(name: str) -> str | None:
    """Find a VC++ DLL by searching Python's dir and System32."""
    search_dirs = [
        os.path.dirname(sys.executable),
        sys.prefix,
        os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32"),
    ]
    for d in search_dirs:
        candidate = os.path.join(d, name)
        if os.path.isfile(candidate):
            return candidate
    return None

for dll_name in _VC_DLLS:
    path = _find_vc_dll(dll_name)
    if path:
        _binaries.append((path, '.'))  # (absolute source, dest in bundle root)

# Also grab any Tcl/Tk DLLs if present (needed for tkinter GUI)
py_dir = os.path.dirname(sys.executable)
for pattern in ("tcl*.dll", "tk*.dll"):
    for dll_path in _glob.glob(os.path.join(py_dir, pattern)):
        _binaries.append((dll_path, '.'))

a = Analysis(
    [os.path.join(REPO_ROOT, 'tcwin', '__main__.py')],
    pathex=[REPO_ROOT],
    binaries=_binaries,
    datas=[
        # Bundle Tor.zip so the .exe can extract tor.exe + geoip on first run
        (os.path.join(REPO_ROOT, 'windows', 'Tor.zip'), 'tor_bundle'),
    ],
    hiddenimports=[
        'tkinter',
        'tkinter.ttk',
        'tkinter.messagebox',
        'tkinter.constants',
        'tkinter.font',
        '_tkinter',
        'json',
        'ctypes',
        'ctypes.wintypes',
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
        'zipfile',
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
    exclude_binaries=True,  # folder distribution: binaries go into COLLECT
    name='torchain',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # CLI mode by default; GUI is launched via 'torchain.exe gui'
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # icon.py generates the icon procedurally at runtime
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[os.path.basename(src) for src, _ in _binaries],
    name='torchain',
)
