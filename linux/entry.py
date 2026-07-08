"""Entry point for PyInstaller builds.

PyInstaller doesn't set up package context for __main__.py, so relative
imports fail. This wrapper uses absolute imports and is referenced by
the PyInstaller spec as the entry script.
"""
import sys
import os

# When running as a PyInstaller bundle, the tc4 package is in the same
# directory as this script. Ensure it's importable.
if getattr(sys, 'frozen', False):
    # Add the bundle directory to sys.path so 'import tc4' works
    bundle_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
    if bundle_dir not in sys.path:
        sys.path.insert(0, bundle_dir)

from tc4.cli import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
