"""Entry point for PyInstaller builds (Windows).

PyInstaller doesn't set up package context for __main__.py, so relative
imports fail. This wrapper uses absolute imports and is referenced by
the PyInstaller spec as the entry script.
"""
import sys
import os

# Under PyInstaller windowed/GUI mode (console=False), sys.stdout and sys.stderr
# are None. Provide dummy streams so print/logging calls don't crash.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

# When running as a PyInstaller bundle, the tcwin package is in the same
# directory as this script. Ensure it's importable.
if getattr(sys, 'frozen', False):
    bundle_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(sys.argv[0])))
    if bundle_dir not in sys.path:
        sys.path.insert(0, bundle_dir)

def _cleanup_old_meipass():
    """Remove orphaned _MEI temp directories left over from previous runs."""
    try:
        temp_dir = os.environ.get("TEMP") or os.environ.get("TMP")
        if not temp_dir or not os.path.isdir(temp_dir):
            return
        current_mei = getattr(sys, '_MEIPASS', None)
        import glob, shutil
        for path in glob.glob(os.path.join(temp_dir, "_MEI*")):
            if os.path.isdir(path):
                if current_mei and os.path.abspath(path) == os.path.abspath(current_mei):
                    continue
                try:
                    shutil.rmtree(path, ignore_errors=True)
                except Exception:
                    pass
    except Exception:
        pass

_cleanup_old_meipass()

# Extract bundled tor.exe on first run
try:
    from tcwin.portable import ensure_tor
    ensure_tor()
except Exception:
    pass

from tcwin.cli import main

if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        args = ["gui"]
    sys.exit(main(args))
