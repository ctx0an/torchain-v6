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

from . import FW_RULE_PREFIX
from .config import Config
from .errors import FirewallError
from .log import get_logger
from .sysutil import run, run_ok, which

log = get_logger()

_RULE_TOR = f"{FW_RULE_PREFIX}-allow-tor"
_RULE_LOOPBACK = f"{FW_RULE_PREFIX}-allow-loopback"
_RULE_BLOCK6 = f"{FW_RULE_PREFIX}-block-ipv6"


def _netsh(*args: str, check: bool = True):
    return run(["netsh", "advfirewall", *args], check=check, timeout=20)


def _set_policy(outbound: str) -> None:
    # firewallpolicy takes 'inboundpolicy,outboundpolicy'.
    _netsh("set", "allprofiles", "firewallpolicy",
           f"blockinbound,{outbound}", check=False)


def _delete_rules() -> None:
    for name in (_RULE_TOR, _RULE_LOOPBACK, _RULE_BLOCK6):
        run_ok(["netsh", "advfirewall", "firewall", "delete", "rule",
                f"name={name}"])


def up(cfg: Config, tor_exe: str) -> None:
    """Engage the kill-switch. Idempotent: tears down first."""
    if which("netsh") is None:
        raise FirewallError("netsh not found (Windows Defender Firewall unavailable)")
    down(cfg, quiet=True)
    try:
        # Make sure the firewall itself is on.
        _netsh("set", "allprofiles", "state", "on", check=True)
        # Allow tor.exe outbound on every profile. Quote the path to support spaces.
        run(["netsh", "advfirewall", "firewall", "add", "rule",
             f"name={_RULE_TOR}", "dir=out", "action=allow",
             f'program="{tor_exe}"', "enable=yes", "profile=any"],
            check=True, timeout=20)
        # Allow loopback so SOCKS clients can reach tor on 127.0.0.1.
        run(["netsh", "advfirewall", "firewall", "add", "rule",
             f"name={_RULE_LOOPBACK}", "dir=out", "action=allow",
             "remoteip=127.0.0.0/8", "enable=yes", "profile=any"],
            check=True, timeout=20)
        if cfg.block_ipv6:
            # Belt-and-suspenders: explicitly block all IPv6 egress.
            run(["netsh", "advfirewall", "firewall", "add", "rule",
                 f"name={_RULE_BLOCK6}", "dir=out", "action=block",
                 "remoteip=::/0", "enable=yes", "profile=any"],
                check=True, timeout=20)
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
