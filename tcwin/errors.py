"""Typed exception hierarchy and helpers for clear, actionable errors.

Every user-facing failure should raise a TorChainError (or subclass) with a
short message and, when useful, a `hint` describing how to fix it. The CLI
and GUI render these consistently instead of dumping raw tracebacks.
"""
from __future__ import annotations


class TorChainError(Exception):
    """Base class for all expected, user-facing errors."""

    exit_code = 1

    def __init__(self, message: str, hint: str | None = None):
        super().__init__(message)
        self.message = message
        self.hint = hint

    def render(self) -> str:
        out = self.message
        if self.hint:
            out += f"\n  → {self.hint}"
        return out


class PrivilegeError(TorChainError):
    """Raised when root is required but not available."""

    exit_code = 13


class DependencyError(TorChainError):
    """Raised when a required binary or Python module is missing."""

    exit_code = 69


class ConfigError(TorChainError):
    """Raised on invalid or unreadable configuration."""

    exit_code = 78


class TorError(TorChainError):
    """Raised when the tor process or control protocol fails."""

    exit_code = 70


class FirewallError(TorChainError):
    """Raised when applying or tearing down firewall rules fails."""

    exit_code = 71


class CommandError(TorChainError):
    """Raised when an external command exits non-zero."""

    exit_code = 72

    def __init__(self, cmd, returncode, stderr="", hint=None):
        msg = f"command failed ({returncode}): {' '.join(cmd) if isinstance(cmd, (list, tuple)) else cmd}"
        if stderr:
            msg += f"\n  {stderr.strip().splitlines()[-1] if stderr.strip() else ''}"
        super().__init__(msg, hint)
        self.cmd = cmd
        self.returncode = returncode
        self.stderr = stderr


class TimeoutError_(TorChainError):
    """Raised when an operation exceeds its deadline."""

    exit_code = 124
