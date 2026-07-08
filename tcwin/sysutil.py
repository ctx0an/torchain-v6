"""Thin, safe wrappers around subprocess and the Windows environment.

Goals mirror the Linux build: never hang (always a timeout), turn failures
into typed CommandError with captured stderr, and provide an admin check that
works on Windows (there is no ``os.geteuid`` here).
"""
from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import sys
from typing import Sequence

from .errors import CommandError, DependencyError, PrivilegeError, TimeoutError_
from .log import get_logger

log = get_logger()

# Hide child console windows when launched from the GUI.
NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW


def which(binary: str) -> str | None:
    return shutil.which(binary)


def require_binaries(*binaries: str) -> None:
    missing = [b for b in binaries if which(b) is None]
    if missing:
        raise DependencyError(
            f"missing required executables: {', '.join(missing)}",
            hint="Run 'torchain doctor' or windows\\setup.bat to install dependencies.",
        )


def is_admin() -> bool:
    """True when the current process holds an elevated (Administrator) token."""
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:  # noqa: BLE001 - non-Windows / restricted environments
        return False


# Alias so shared code that calls is_root() keeps working on Windows.
is_root = is_admin


def require_root() -> None:
    """Require an elevated token (the Windows analogue of requiring root)."""
    if not is_admin():
        raise PrivilegeError(
            "this operation requires Administrator privileges",
            hint="Right-click torchain and 'Run as administrator', or run an "
                 "elevated terminal. The GUI elevates these actions via UAC.",
        )


require_admin = require_root


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
            creationflags=NO_WINDOW,
        )
    except FileNotFoundError as exc:
        raise DependencyError(f"executable not found: {cmd[0]}") from exc
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


def powershell(script: str, *, timeout: float = 60.0, check: bool = False) -> subprocess.CompletedProcess:
    """Run a PowerShell snippet with execution policy bypassed."""
    exe = which("powershell") or "powershell"
    return run(
        [exe, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
        timeout=timeout,
        check=check,
    )


def pid_alive(pid: int | None) -> bool:
    """Return True if a process with ``pid`` exists (Windows-safe)."""
    if not pid:
        return False
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    STILL_ACTIVE = 259
    try:
        k32 = ctypes.windll.kernel32
        handle = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not handle:
            return False
        try:
            code = ctypes.c_ulong(0)
            if k32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return code.value == STILL_ACTIVE
            return True
        finally:
            k32.CloseHandle(handle)
    except Exception:  # noqa: BLE001
        return False


def elevate(args: Sequence[str], *, wait: bool = False) -> bool:
    """Re-launch ``python -m tcwin <args>`` elevated via UAC (ShellExecute runas).

    Returns True if the elevated process was launched (Windows shows its secure
    consent / password prompt). This is the Windows analogue of asking for the
    sudo password before a privileged action.
    """
    python = sys.executable or "python"
    params = "-m tcwin " + " ".join(_quote(a) for a in args)

    import ctypes.wintypes as w

    class SHELLEXECUTEINFOW(ctypes.Structure):
        _fields_ = [
            ("cbSize", w.DWORD),
            ("fMask", w.ULONG),
            ("hwnd", w.HWND),
            ("lpVerb", w.LPCWSTR),
            ("lpFile", w.LPCWSTR),
            ("lpParameters", w.LPCWSTR),
            ("lpDirectory", w.LPCWSTR),
            ("nShow", ctypes.c_int),
            ("hInstApp", w.HANDLE),
            ("lpIDList", ctypes.c_void_p),
            ("lpClass", w.LPCWSTR),
            ("hkeyClass", w.HANDLE),
            ("dwHotKey", w.DWORD),
            ("hIconOrMonitor", w.HANDLE),
            ("hProcess", w.HANDLE)
        ]

    SEE_MASK_NOCLOSEPROCESS = 0x00000040
    SW_HIDE = 0

    sei = SHELLEXECUTEINFOW()
    sei.cbSize = ctypes.sizeof(SHELLEXECUTEINFOW)
    sei.fMask = SEE_MASK_NOCLOSEPROCESS if wait else 0
    sei.hwnd = None
    sei.lpVerb = "runas"
    sei.lpFile = python
    sei.lpParameters = params
    sei.lpDirectory = None
    sei.nShow = SW_HIDE

    try:
        success = ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(sei))
        if not success:
            return False
        if int(sei.hInstApp or 0) <= 32:
            return False
        if wait and sei.hProcess:
            INFINITE = 0xFFFFFFFF
            ctypes.windll.kernel32.WaitForSingleObject(sei.hProcess, INFINITE)
            ctypes.windll.kernel32.CloseHandle(sei.hProcess)
        return True
    except Exception as exc:  # noqa: BLE001
        log.error("elevation failed: %s", exc)
        return False


def _quote(arg: str) -> str:
    """Quote an argument for CommandLineToArgvW rules on Windows."""
    if not arg:
        return '""'
    if not any(c in arg for c in ' \t\n\v"'):
        return arg
    res = []
    bs_count = 0
    for c in arg:
        if c == '\\':
            bs_count += 1
        elif c == '"':
            res.append('\\' * (bs_count * 2 + 1))
            res.append('"')
            bs_count = 0
        else:
            if bs_count > 0:
                res.append('\\' * bs_count)
                bs_count = 0
            res.append(c)
    if bs_count > 0:
        res.append('\\' * bs_count)
    return '"' + ''.join(res) + '"'


# Tuple of swallowable errors for run_ok.
from .errors import TorChainError as _TCE  # noqa: E402

TorChainErrorTuple = (_TCE,)


def read_first_line(path: str, default: str = "") -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.readline().strip()
    except OSError:
        return default
