"""Module entry point: `python -m tcwin ...`."""
import os
import sys

# Ensure parent directory is in sys.path and remove package dir from sys.path[0]
# to prevent shadowing standard library modules (e.g., platform.py).
if __package__ is None or __package__ == "":
    _pkg_dir = os.path.dirname(os.path.abspath(__file__))
    _parent = os.path.dirname(_pkg_dir)
    if sys.path and os.path.abspath(sys.path[0]) == _pkg_dir:
        sys.path.pop(0)
    if _parent not in sys.path:
        sys.path.insert(0, _parent)


def _bootstrap_portable():
    """Extract bundled tor.exe on first run when running as a frozen .exe."""
    if getattr(sys, 'frozen', False):
        try:
            from .portable import ensure_tor
            ensure_tor()
        except Exception:
            pass


_bootstrap_portable()

if getattr(sys, 'frozen', False):
    from tcwin.cli import main
else:
    try:
        from .cli import main
    except (ImportError, ValueError):
        from tcwin.cli import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
