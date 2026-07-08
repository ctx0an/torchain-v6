"""Module entry point: `python3 -m tc4 ...`."""
import sys

# PyInstaller bundles __main__.py without the parent package context,
# so relative imports (from .cli) fail. Use absolute import in that case.
if getattr(sys, 'frozen', False):
    from tc4.cli import main
else:
    from .cli import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
