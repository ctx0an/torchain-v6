"""Module entry point: `python3 -m tc4 ...`."""
import os
import sys

# Ensure parent directory is in sys.path and remove package dir from sys.path[0]
# to prevent shadowing standard library modules.
if __package__ is None or __package__ == "":
    _pkg_dir = os.path.dirname(os.path.abspath(__file__))
    _parent = os.path.dirname(_pkg_dir)
    if sys.path and os.path.abspath(sys.path[0]) == _pkg_dir:
        sys.path.pop(0)
    if _parent not in sys.path:
        sys.path.insert(0, _parent)

# PyInstaller bundles __main__.py without the parent package context,
# so relative imports (from .cli) fail. Use absolute import in that case.
if getattr(sys, 'frozen', False):
    from tc4.cli import main
else:
    try:
        from .cli import main
    except (ImportError, ValueError):
        from tc4.cli import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
