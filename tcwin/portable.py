"""Portable .exe support: extracts bundled tor.exe + geoip on first run.

When torchain is built as a single-file PyInstaller .exe, tor.exe and the
geoip databases are embedded inside the .exe as a Tor.zip data file. This
module extracts them to %ProgramData%\\torchain\\app\\tor\\ on first run so
that engine.find_tor() can locate them.
"""
from __future__ import annotations

import os
import sys
import zipfile


def _app_dir() -> str:
    base = os.environ.get("ProgramData", r"C:\ProgramData")
    return os.path.join(base, "torchain", "app")


def _tor_dir() -> str:
    return os.path.join(_app_dir(), "tor")


def _marker() -> str:
    return os.path.join(_tor_dir(), ".extracted")


def _bundled_zip() -> str | None:
    """Return the path to the bundled Tor.zip inside the PyInstaller temp dir."""
    if not getattr(sys, 'frozen', False):
        return None
    # PyInstaller extracts data files to sys._MEIPASS
    base = getattr(sys, '_MEIPASS', None)
    if not base:
        return None
    candidate = os.path.join(base, 'tor_bundle', 'Tor.zip')
    if os.path.exists(candidate):
        return candidate
    return None


def ensure_tor() -> bool:
    """Extract tor.exe from the bundled Tor.zip if not already present.

    Returns True if tor.exe is available (either already extracted or just extracted).
    """
    # Check if already extracted
    tor_dir = _tor_dir()
    if os.path.exists(_marker()):
        # Verify tor.exe still exists
        for sub in ('tor.exe', r'Tor\tor.exe', r'tor\tor.exe'):
            if os.path.exists(os.path.join(tor_dir, sub)):
                return True
        # Marker exists but tor.exe is gone — re-extract
        try:
            os.remove(_marker())
        except OSError:
            pass

    # Find the bundled zip
    zp = _bundled_zip()
    if not zp:
        return False

    try:
        os.makedirs(tor_dir, exist_ok=True)
        with zipfile.ZipFile(zp, 'r') as zf:
            zf.extractall(tor_dir)
        # Write marker so we don't re-extract every run
        with open(_marker(), 'w') as f:
            f.write('ok')
        return True
    except Exception:
        return False


def tor_exe_path() -> str | None:
    """Return the path to tor.exe after extraction, or None."""
    tor_dir = _tor_dir()
    for sub in ('tor.exe', r'Tor\tor.exe', r'tor\tor.exe'):
        candidate = os.path.join(tor_dir, sub)
        if os.path.exists(candidate):
            return candidate
    return None
