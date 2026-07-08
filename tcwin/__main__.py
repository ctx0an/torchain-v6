"""Module entry point: `python -m tcwin ...`."""
import sys


def _bootstrap_portable():
    """Extract bundled tor.exe on first run when running as a frozen .exe."""
    if getattr(sys, 'frozen', False):
        try:
            from .portable import ensure_tor
            ensure_tor()
        except Exception:
            pass


_bootstrap_portable()

from .cli import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
