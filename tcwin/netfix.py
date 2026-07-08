"""Network recovery for Windows - the 'undo everything' safety net.

This is the Windows analogue of the Linux internet.sh / netfix.py. If torchain
(or a crash) ever leaves networking broken, this restores connectivity.

SAFETY MODEL (important on Windows, where a botched network stack is painful
to fix):

* The DEFAULT repair only performs **reversible, connectivity-restoring**
  actions: it puts the firewall's default outbound policy back to *allow*,
  deletes every ``torchain-*`` firewall rule, clears the per-user WinINET
  proxy, flushes the DNS cache and renews the DHCP lease. None of these can
  leave the machine worse off - the worst case is "no change".

* The aggressive stack resets (``netsh winsock reset`` and
  ``netsh int ip reset``) are **opt-in only** via ``deep=True``. They rebuild
  the Winsock catalog and the TCP/IP stack, which *requires a reboot* and can
  disrupt unrelated VPN / proxy / firewall products. We never run them unless
  the user explicitly asks, so a routine "repair internet" can never destabilise
  Windows networking.

Every step is best-effort and isolated, so one failure never blocks the rest.
"""
from __future__ import annotations

from .log import get_logger
from .sysutil import run_ok, which

log = get_logger()

_TORCHAIN_RULES = (
    "torchain-allow-tor",
    "torchain-allow-loopback",
    "torchain-block-ipv6",
)


def _step(label: str, ok: bool, report: list[str]) -> None:
    report.append(f"  [{'ok' if ok else '!!'}] {label}")


def _safe_steps(report: list[str]) -> None:
    """Reversible recovery that can only ever restore connectivity."""
    if which("netsh"):
        # Restore the permissive Windows default outbound policy FIRST so that,
        # even if everything else fails, the machine is back online.
        _step("restore default outbound firewall policy",
              run_ok(["netsh", "advfirewall", "set", "allprofiles",
                      "firewallpolicy", "blockinbound,allowoutbound"]),
              report)
        for name in _TORCHAIN_RULES:
            run_ok(["netsh", "advfirewall", "firewall", "delete", "rule",
                    f"name={name}"])
        _step("remove torchain firewall rules", True, report)
    else:
        _step("netsh unavailable - skipped firewall restore", False, report)

    # Clear the system proxy (import lazily; registry edits can fail silently).
    try:
        from . import proxy
        proxy.disable()
        _step("clear system (WinINET) proxy", True, report)
    except Exception as exc:  # noqa: BLE001
        _step(f"clear system proxy ({exc})", False, report)

    _step("flush DNS cache", run_ok(["ipconfig", "/flushdns"]), report)
    _step("renew DHCP lease", run_ok(["ipconfig", "/renew"]), report)


def repair(deep: bool = False) -> str:
    """Run the recovery sequence; returns a human-readable report.

    deep=False (default): only safe, reversible, connectivity-restoring steps.
    deep=True: additionally reset the Winsock catalog and TCP/IP stack. These
    require a reboot and may affect other networking software - use only when
    the safe repair did not restore connectivity.
    """
    report: list[str] = ["Network recovery:"]
    _safe_steps(report)

    if deep:
        report.append("Deep stack reset (requires reboot):")
        _step("reset Winsock catalog",
              run_ok(["netsh", "winsock", "reset"]), report)
        _step("reset TCP/IP stack",
              run_ok(["netsh", "int", "ip", "reset"]), report)
        report.append("Deep reset done. REBOOT Windows to finish applying it.")
    else:
        report.append("Done. If you are still offline, run 'torchain repair "
                      "--deep' (this resets the network stack and needs a "
                      "reboot).")
    return "\n".join(report)
