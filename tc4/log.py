"""Lightweight logging: rotating file handler + colored console.

Kept dependency-free and cheap so it adds negligible memory/CPU overhead.
"""
from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler

from . import LOG_DIR, LOG_FILE

_CONFIGURED = False

# ANSI colors for the console handler (Kali-ish palette).
_COLORS = {
    "DEBUG": "\033[38;5;245m",
    "INFO": "\033[38;5;39m",
    "WARNING": "\033[38;5;214m",
    "ERROR": "\033[38;5;203m",
    "CRITICAL": "\033[1;38;5;196m",
}
_RESET = "\033[0m"


class _ColorFormatter(logging.Formatter):
    def __init__(self, color: bool):
        super().__init__("%(message)s")
        self.color = color

    def format(self, record):
        msg = super().format(record)
        if self.color and record.levelname in _COLORS:
            return f"{_COLORS[record.levelname]}{msg}{_RESET}"
        return msg


def get_logger(name: str = "torchain") -> logging.Logger:
    return logging.getLogger(name)


def setup_logging(verbose: bool = False, to_file: bool = True) -> logging.Logger:
    """Idempotently configure the root 'torchain' logger."""
    global _CONFIGURED
    logger = logging.getLogger("torchain")
    if _CONFIGURED:
        logger.setLevel(logging.DEBUG if verbose else logging.INFO)
        return logger

    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.propagate = False

    console = logging.StreamHandler(sys.stderr)
    console.setLevel(logging.DEBUG if verbose else logging.INFO)
    console.setFormatter(_ColorFormatter(color=sys.stderr.isatty()))
    logger.addHandler(console)

    if to_file:
        try:
            os.makedirs(LOG_DIR, exist_ok=True)
            fileh = RotatingFileHandler(
                LOG_FILE, maxBytes=1_000_000, backupCount=5, encoding="utf-8"
            )
            fileh.setLevel(logging.DEBUG)
            fileh.setFormatter(
                logging.Formatter("%(asctime)s %(levelname)-7s %(message)s")
            )
            logger.addHandler(fileh)
        except (OSError, PermissionError):
            # File logging is best-effort; console still works without root.
            pass

    _CONFIGURED = True
    return logger
