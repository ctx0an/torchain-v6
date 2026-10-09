"""Fail-closed kill-switch using Windows Defender Firewall.

Windows cannot transparently redirect traffic into tor like Linux iptables,
so the leak-prevention strategy is:

* switch the default *outbound* action to **Block** on all firewall profiles,
* add a single allow rule for tor.exe so the tor process can still reach the
  guards/relays, and
* allow loopback so local SOCKS clients can hand traffic to tor.

Result: every application that is not routed through tor's SOCKS proxy simply
cannot send packets - no DNS, QUIC, WebRTC or IPv6 leaks. All rules live under
the ``torchain`` name prefix so teardown is surgical and reversible. The
previous outbound policy is restored to the Windows default (allow) on stop.
"""
from __future__ import annotations

import os

from . import FW_RULE_PREFIX
from .config import Config
from .errors import FirewallError
from .log import get_logger
from .sysutil import run, run_ok, which

log = get_logger()

_RULE_TOR = f"{FW_RULE_PREFIX}-allow-tor"
_RULE_LOOPBACK = f"{FW_RULE_PREFIX}-allow-loopback"
_RULE_BLOCK6 = f"{FW_RULE_PREFIX}-block-ipv6"

_KNOWN_PT_NAMES = (
    "lyrebird",
    "conjure-client",
    "snowflake-client",
    "snowflake",
    "webtunnel-client",
    "webtunnel",
    "obfs4proxy",
)


def _find_pt_executables(tor_exe: str) -> list[str]:
    """Locate pluggable transport executables in the Tor directory tree and PATH."""
    pts: list[str] = []
    seen: set[str] = set()
    tor_dir = os.path.dirname(os.path.abspath(tor_exe))
    search_dirs = [
        os.path.join(tor_dir, "PluggableTransports"),
        tor_dir,
        os.path.join(os.path.dirname(tor_dir), "PluggableTransports"),
    ]
    for d in search_dirs:
        if not os.path.isdir(d):
            continue
        try:
            for entry in os.listdir(d):
                if not entry.lower().endswith(".exe") or entry.lower() == "tor.exe":
                    continue
                base = os.path.splitext(entry)[0].lower()
                # In tor's own directory, only match known transport binaries to avoid matching utilities like tor-resolve.exe
                if d == tor_dir and base not in _KNOWN_PT_NAMES:
                    continue
                full = os.path.abspath(os.path.join(d, entry))
                if full.lower() not in seen:
                    seen.add(full.lower())
                    pts.append(full)
        except OSError:
            pass

    for name in _KNOWN_PT_NAMES:
        p = which(name) or which(f"{name}.exe")
        if p:
            abs_p = os.path.abspath(p)
            if abs_p.lower() not in seen:
                seen.add(abs_p.lower())
                pts.append(abs_p)

    return pts


def _netsh(*args: str, check: bool = True):
    return run(["netsh", "advfirewall", *args], check=check, timeout=20)


def _set_policy(outbound: str) -> None:
    # firewallpolicy takes 'inboundpolicy,outboundpolicy'.
    _netsh("set", "allprofiles", "firewallpolicy",
           f"blockinbound,{outbound}", check=False)


def _delete_rules() -> None:
    rule_names = [_RULE_TOR, _RULE_LOOPBACK, _RULE_BLOCK6]
    for pt in _KNOWN_PT_NAMES:
        rule_names.append(f"{FW_RULE_PREFIX}-allow-pt-{pt}")
    for name in rule_names:
        run_ok(["netsh", "advfirewall", "firewall", "delete", "rule",
                f"name={name}"])


def up(cfg: Config, tor_exe: str) -> None:
    """Engage the kill-switch. Additively updates rules and blocks outbound without an open window."""
    if which("netsh") is None:
        raise FirewallError("netsh not found (Windows Defender Firewall unavailable)")
    try:
        # Make sure the firewall itself is on.
        _netsh("set", "allprofiles", "state", "on", check=True)

        # Delete existing torchain rules additively before re-adding, without resetting outbound policy to allow
        _delete_rules()

        # Allow tor.exe outbound on every profile. Quote the path to support spaces.
        run(["netsh", "advfirewall", "firewall", "add", "rule",
             f"name={_RULE_TOR}", "dir=out", "action=allow",
             f'program="{tor_exe}"', "enable=yes", "profile=any"],
            check=True, timeout=20)
        # Allow pluggable transports (lyrebird, conjure-client, snowflake, etc.)
        for pt_exe in _find_pt_executables(tor_exe):
            filename = pt_exe.replace("\\", "/").rsplit("/", 1)[-1]
            base = os.path.splitext(filename)[0].lower()
            run(["netsh", "advfirewall", "firewall", "add", "rule",
                 f"name={FW_RULE_PREFIX}-allow-pt-{base}", "dir=out", "action=allow",
                 f'program="{pt_exe}"', "enable=yes", "profile=any"],
                check=False, timeout=20)
        # Allow loopback so SOCKS clients can reach tor on 127.0.0.1.
        run(["netsh", "advfirewall", "firewall", "add", "rule",
             f"name={_RULE_LOOPBACK}", "dir=out", "action=allow",
             "remoteip=127.0.0.0/8", "enable=yes", "profile=any"],
            check=True, timeout=20)
        if cfg.block_ipv6:
            # Belt-and-suspenders: block IPv6 egress using valid Windows IP range syntax
            run(["netsh", "advfirewall", "firewall", "add", "rule",
                 f"name={_RULE_BLOCK6}", "dir=out", "action=block",
                 "remoteip=0::-ffff:ffff:ffff:ffff:ffff:ffff:ffff:ffff",
                 "enable=yes", "profile=any"],
                check=False, timeout=20)
        # Flip the default outbound policy to block (fail-closed).
        _netsh("set", "allprofiles", "firewallpolicy", "blockinbound,blockoutbound", check=True)
    except Exception as exc:  # noqa: BLE001
        down(cfg, quiet=True)
        if isinstance(exc, FirewallError):
            raise
        raise FirewallError(f"failed to apply firewall kill-switch: {exc}") from exc


def down(cfg: Config | None = None, quiet: bool = False) -> None:
    """Restore normal networking. Best-effort, idempotent, always safe."""
    if which("netsh"):
        # Restore the Windows default outbound policy (allow) FIRST so a
        # failure deleting rules can never leave the machine offline.
        _set_policy("allowoutbound")
        _delete_rules()
    if not quiet:
        log.debug("firewall kill-switch removed")


def is_active() -> bool:
    """True when the tor allow-rule is active and default outbound is blocked.

    Tries reading from the registry without elevation first, falling back to netsh.
    """
    try:
        import winreg
        rule_found = False
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"SYSTEM\CurrentControlSet\Services\SharedAccess\Parameters\FirewallPolicy\FirewallRules",
                            0, winreg.KEY_READ) as k:
            i = 0
            while True:
                try:
                    name, value, typ = winreg.EnumValue(k, i)
                    if isinstance(value, str) and "|Name=torchain-allow-tor|" in value:
                        if "Active=TRUE" in value:
                            rule_found = True
                            break
                    i += 1
                except OSError:
                    break
        if not rule_found:
            return False

        # Verify default outbound policy is indeed block on all profiles
        for profile in ("DomainProfile", "PublicProfile", "StandardProfile"):
            path = rf"SYSTEM\CurrentControlSet\Services\SharedAccess\Parameters\FirewallPolicy\{profile}"
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path, 0, winreg.KEY_READ) as k:
                val, typ = winreg.QueryValueEx(k, "DefaultOutboundAction")
                if val != 1:
                    return False
        return True
    except Exception:
        # Fallback to netsh if registry access fails
        return run_ok(["netsh", "advfirewall", "firewall", "show", "rule",
                       f"name={_RULE_TOR}"])


def block_all() -> None:
    """Panic helper: block ALL outbound, including tor."""
    if which("netsh"):
        _delete_rules()
        _set_policy("blockoutbound")


def allow_all() -> None:
    """Disarm helper: restore permissive outbound and drop our rules."""
    if which("netsh"):
        _set_policy("allowoutbound")
        _delete_rules()
