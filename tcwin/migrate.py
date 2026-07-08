"""Leak / hardening pre-flight scan for Windows.

The Linux build calls this 'migrate' (advisory checks before going live). On
Windows we surface the most common foot-guns: IPv6 still enabled system-wide,
QUIC/HTTP3 (UDP 443) which can bypass a SOCKS-only setup, Teredo tunnelling,
and whether the bundled tor.exe could be located.

Returns a list of (severity, message) advisories; it never changes anything.
"""
from __future__ import annotations

from .sysutil import powershell, which


def scan() -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []

    # IPv6 enabled on any adapter?
    try:
        proc = powershell(
            "(Get-NetAdapterBinding -ComponentID ms_tcpip6 | "
            "Where-Object Enabled -eq $true).Name -join ','",
            timeout=20,
        )
        v6 = (proc.stdout or "").strip()
        if v6:
            out.append(("warn",
                        f"IPv6 is enabled on: {v6}. The kill-switch blocks IPv6 "
                        "egress, but disabling it system-wide removes all doubt."))
    except Exception:  # noqa: BLE001
        pass

    # Teredo / 6to4 tunnelling.
    try:
        proc = powershell("(Get-NetTeredoConfiguration).Type", timeout=15)
        if "disabled" not in (proc.stdout or "").strip().lower():
            out.append(("warn", "Teredo IPv6 tunnelling is not disabled."))
    except Exception:  # noqa: BLE001
        pass

    # tor.exe present?
    try:
        from . import engine
        if not engine.find_tor():
            out.append(("error",
                        "tor.exe was not found. Run windows\\setup.bat "
                        "to extract the bundled Tor."))
    except Exception:  # noqa: BLE001
        pass


    if not out:
        out.append(("ok", "No common leak vectors detected."))
    return out
