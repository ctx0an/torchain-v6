"""Transparent-proxy firewall: route all TCP/DNS through tor, block leaks.

Implements the well-known Tor TransparentProxy iptables recipe, hardened:
- tor's own traffic (matched by its uid) is allowed out directly,
- loopback is preserved,
- LANs are allowed (so SSH / local services keep working),
- DNS is forced to tor's DNSPort,
- everything else TCP is redirected to tor's TransPort,
- non-matching output is dropped (fail-closed),
- IPv6 is fully blocked when enabled.

All rules live in dedicated chains so teardown is surgical and reversible.
"""
from __future__ import annotations

import pwd

from .config import Config
from .errors import FirewallError
from .log import get_logger
from .sysutil import run, run_ok, which

log = get_logger()

# Reserved / private ranges that must never be sent through tor.
_NON_TOR = [
    "127.0.0.0/8",
    "10.0.0.0/8",
    "172.16.0.0/12",
    "192.168.0.0/16",
    "169.254.0.0/16",
    "100.64.0.0/10",
]


def _tor_uid(tor_user: str) -> str:
    try:
        return str(pwd.getpwnam(tor_user).pw_uid)
    except KeyError as exc:
        raise FirewallError(
            f"tor user '{tor_user}' not found",
            hint="Install the tor package or set the correct user.",
        ) from exc


def _ipt(*args: str, check: bool = True):
    return run(["iptables", *args], check=check, timeout=15)


def _ipt6(*args: str, check: bool = True):
    return run(["ip6tables", *args], check=check, timeout=15)


def up(cfg: Config, tor_user: str) -> None:
    """Apply transparent-proxy rules. Idempotent: tears down first."""
    if which("iptables") is None:
        raise FirewallError("iptables not installed")
    down(cfg, quiet=True)
    uid = _tor_uid(tor_user)
    trans, dns = str(cfg.trans_port), str(cfg.dns_port)
    try:
        # --- NAT: redirect DNS + TCP into tor ---
        _ipt("-t", "nat", "-N", "TORCHAIN", check=False)
        _ipt("-t", "nat", "-F", "TORCHAIN")
        # tor's own traffic is exempt (prevents a redirect loop).
        _ipt("-t", "nat", "-A", "TORCHAIN", "-m", "owner", "--uid-owner", uid, "-j", "RETURN")
        _ipt("-t", "nat", "-A", "TORCHAIN", "-p", "udp", "--dport", "53",
             "-j", "REDIRECT", "--to-ports", dns)
        for net in _NON_TOR:
            _ipt("-t", "nat", "-A", "TORCHAIN", "-d", net, "-j", "RETURN")
        _ipt("-t", "nat", "-A", "TORCHAIN", "-p", "tcp", "--syn",
             "-j", "REDIRECT", "--to-ports", trans)
        _ipt("-t", "nat", "-A", "OUTPUT", "-j", "TORCHAIN")

        # --- FILTER: fail-closed egress ---
        _ipt("-N", "TORCHAIN_OUT", check=False)
        _ipt("-F", "TORCHAIN_OUT")
        _ipt("-A", "TORCHAIN_OUT", "-m", "state", "--state",
             "ESTABLISHED,RELATED", "-j", "ACCEPT")
        _ipt("-A", "TORCHAIN_OUT", "-m", "owner", "--uid-owner", uid, "-j", "ACCEPT")
        _ipt("-A", "TORCHAIN_OUT", "-o", "lo", "-j", "ACCEPT")
        for net in _NON_TOR:
            _ipt("-A", "TORCHAIN_OUT", "-d", net, "-j", "ACCEPT")
        # Allow already-redirected traffic to reach tor's ports on loopback.
        _ipt("-A", "TORCHAIN_OUT", "-p", "tcp", "--dport", trans, "-j", "ACCEPT")
        _ipt("-A", "TORCHAIN_OUT", "-p", "udp", "--dport", dns, "-j", "ACCEPT")
        _ipt("-A", "TORCHAIN_OUT", "-j", "DROP")
        _ipt("-A", "OUTPUT", "-j", "TORCHAIN_OUT")

        if cfg.block_ipv6:
            _block_ipv6()
    except Exception as exc:
        down(cfg, quiet=True)
        if isinstance(exc, FirewallError):
            raise
        raise FirewallError(f"failed to apply firewall rules: {exc}") from exc


def _block_ipv6() -> None:
    if which("ip6tables") is None:
        return
    _ipt6("-P", "OUTPUT", "DROP", check=False)
    _ipt6("-P", "INPUT", "DROP", check=False)
    _ipt6("-P", "FORWARD", "DROP", check=False)
    _ipt6("-A", "INPUT", "-i", "lo", "-j", "ACCEPT", check=False)
    _ipt6("-A", "OUTPUT", "-o", "lo", "-j", "ACCEPT", check=False)


def _del_all_jumps(table: str, chain: str) -> None:
    """Delete *every* OUTPUT jump into ``chain`` (not just the first).

    This is the core internet-cutoff fix: if more than one jump into the
    fail-closed TORCHAIN_OUT chain existed (e.g. up() ran twice), deleting only
    one left the DROP rule attached and ``-X`` failed because the chain was
    still referenced - so the box stayed offline after ``stop``. We now remove
    them all before flushing/deleting the chain.
    """
    base = ["iptables"] + (["-t", table] if table != "filter" else [])
    rule = ["OUTPUT", "-j", chain]
    for _ in range(64):  # defensive cap
        if not run_ok(base + ["-C", *rule]):
            break
        if not run_ok(base + ["-D", *rule]):
            break


def down(cfg: Config, quiet: bool = False) -> None:
    """Remove all torchain rules. Best-effort, idempotent, always safe to call.

    Removes every OUTPUT jump (handling duplicates) so a leftover DROP can
    never keep the machine offline, then flushes + deletes our chains and
    restores permissive IPv6 policies.
    """
    if which("iptables"):
        _del_all_jumps("nat", "TORCHAIN")
        _del_all_jumps("filter", "TORCHAIN_OUT")
        for table, chain in (("nat", "TORCHAIN"), ("filter", "TORCHAIN_OUT")):
            run_ok(["iptables", "-t", table, "-F", chain])
            run_ok(["iptables", "-t", table, "-X", chain])
    if which("ip6tables"):
        for pol in ("OUTPUT", "INPUT", "FORWARD"):
            run_ok(["ip6tables", "-P", pol, "ACCEPT"])
        run_ok(["ip6tables", "-D", "INPUT", "-i", "lo", "-j", "ACCEPT"])
        run_ok(["ip6tables", "-D", "OUTPUT", "-o", "lo", "-j", "ACCEPT"])
    if not quiet:
        log.debug("firewall rules removed")


def is_active() -> bool:
    return run_ok(["iptables", "-t", "nat", "-n", "-L", "TORCHAIN"])
