"""Thin, safe wrappers around subprocess and the environment.

Goals: never hang (always a timeout), never leak file descriptors, and turn
every failure into a typed CommandError with the captured stderr so callers
get actionable messages instead of opaque tracebacks.
"""
from __future__ import annotations

import fcntl
import os
import shutil
import subprocess
import sys
from typing import Sequence

from .errors import CommandError, DependencyError, PrivilegeError, TimeoutError_, TorChainError
from .log import get_logger

log = get_logger()


def which(binary: str) -> str | None:
    return shutil.which(binary)


def require_binaries(*binaries: str) -> None:
    missing = [b for b in binaries if which(b) is None]
    if missing:
        raise DependencyError(
            f"missing required executables: {', '.join(missing)}",
            hint="Run 'torchain doctor' or './setup.sh' to install dependencies.",
        )


def is_root() -> bool:
    try:
        return os.geteuid() == 0
    except AttributeError:
        import ctypes
        try:
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            return False


def require_root() -> None:
    if is_root():
        return
    # Auto-elevation: try desktop polkit first (shows a GUI auth dialog),
    # then fall back to sudo, and finally to the error message.
    display = os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    pkexec = shutil.which("pkexec")
    
    # If the current script is a python file, run it with the interpreter
    base_args = [sys.executable] + sys.argv if sys.argv[0].endswith(".py") else sys.argv
    
    if pkexec and display:
        argv = ["pkexec"] + base_args
        os.execvp(pkexec, argv)
        # never returns
        
    sudo = shutil.which("sudo")
    if sudo:
        argv = ["sudo"] + base_args
        os.execvp(sudo, argv)
        # never returns
        
    raise PrivilegeError(
        "this operation requires root privileges",
        hint="Re-run with sudo, e.g. 'sudo torchain start'.",
    )


class ProcessLock:
    """A cross-process mutual exclusion lock using fcntl.flock."""
    def __init__(self, path: str):
        self.path = path
        self._fd = None

    def __enter__(self) -> ProcessLock:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            os.close(self._fd)
            self._fd = None
            raise TorChainError(
                "Another torchain operation is in progress.",
                hint="Wait for the other process to finish."
            ) from exc
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._fd is not None:
            try:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
            except OSError:
                pass
            os.close(self._fd)
            self._fd = None


def run(
    cmd: Sequence[str],
    *,
    timeout: float = 30.0,
    check: bool = True,
    capture: bool = True,
    input_text: str | None = None,
    env: dict | None = None,
) -> subprocess.CompletedProcess:
    """Run a command with a hard timeout and typed error handling."""
    log.debug("exec: %s", " ".join(cmd))
    try:
        proc = subprocess.run(
            list(cmd),
            timeout=timeout,
            input=input_text,
            text=True,
            capture_output=capture,
            env=env,
        )
    except FileNotFoundError as exc:
        raise DependencyError(f"executable not found: {cmd[0]}") from exc
    except OSError as exc:
        raise CommandError(cmd, -1, f"Failed to execute command: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError_(
            f"command timed out after {timeout:g}s: {' '.join(cmd)}"
        ) from exc
    if check and proc.returncode != 0:
        raise CommandError(cmd, proc.returncode, proc.stderr or "")
    return proc


def run_ok(cmd: Sequence[str], *, timeout: float = 15.0) -> bool:
    """Return True if the command exits zero; never raises on non-zero."""
    try:
        return run(cmd, timeout=timeout, check=False).returncode == 0
    except TorChainErrorTuple:  # pragma: no cover - defensive
        return False


# Tuple of swallowable errors for run_ok.
from .errors import TorChainError as _TCE  # noqa: E402

TorChainErrorTuple = (_TCE,)


def read_first_line(path: str, default: str = "") -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.readline().strip()
    except OSError:
        return default
