"""Module entry point: `python3 -m tc4 ...`."""
import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
