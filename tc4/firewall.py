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
    """Apply transparent-proxy rules. Insert filter drop rule FIRST before nat rules."""
    if which("iptables") is None:
        raise FirewallError("iptables not installed")
    uid = _tor_uid(tor_user)
    trans, dns = str(cfg.trans_port), str(cfg.dns_port)
    try:
        # --- FILTER FIRST: establish fail-closed egress barrier BEFORE nat redirection ---
        _ipt("-N", "TORCHAIN_OUT", check=False)
        _ipt("-F", "TORCHAIN_OUT")
        _ipt("-A", "TORCHAIN_OUT", "-m", "state", "--state",
             "ESTABLISHED,RELATED", "-j", "ACCEPT")
        _ipt("-A", "TORCHAIN_OUT", "-m", "owner", "--uid-owner", uid, "-j", "ACCEPT")
        _ipt("-A", "TORCHAIN_OUT", "-o", "lo", "-j", "ACCEPT")
        # Allow .onion virtual address range to tor transport before _NON_TOR bypass.
        _ipt("-A", "TORCHAIN_OUT", "-d", "10.192.0.0/10", "-p", "tcp", "-j", "ACCEPT")
        for net in _NON_TOR:
            _ipt("-A", "TORCHAIN_OUT", "-d", net, "-j", "ACCEPT")
        # Allow already-redirected traffic to reach tor's ports strictly on loopback (lo / 127.0.0.1)
        _ipt("-A", "TORCHAIN_OUT", "-o", "lo", "-d", "127.0.0.1", "-p", "tcp", "--dport", trans, "-j", "ACCEPT")
        _ipt("-A", "TORCHAIN_OUT", "-o", "lo", "-d", "127.0.0.1", "-p", "udp", "--dport", dns, "-j", "ACCEPT")
        _ipt("-A", "TORCHAIN_OUT", "-j", "DROP")

        # Ensure jump exists in OUTPUT chain for TORCHAIN_OUT
        if not run_ok(["iptables", "-C", "OUTPUT", "-j", "TORCHAIN_OUT"]):
            _ipt("-I", "OUTPUT", "1", "-j", "TORCHAIN_OUT")

        # --- NAT: redirect DNS + TCP into tor ---
        _ipt("-t", "nat", "-N", "TORCHAIN", check=False)
        _ipt("-t", "nat", "-F", "TORCHAIN")
        # tor's own traffic is exempt (prevents a redirect loop).
        _ipt("-t", "nat", "-A", "TORCHAIN", "-m", "owner", "--uid-owner", uid, "-j", "RETURN")
        _ipt("-t", "nat", "-A", "TORCHAIN", "-p", "udp", "--dport", "53",
             "-j", "REDIRECT", "--to-ports", dns)
        # Route .onion virtual addresses (10.192.0.0/10) to tor before private IP bypass.
        _ipt("-t", "nat", "-A", "TORCHAIN", "-d", "10.192.0.0/10", "-p", "tcp", "--syn",
             "-j", "REDIRECT", "--to-ports", trans)
        for net in _NON_TOR:
            _ipt("-t", "nat", "-A", "TORCHAIN", "-d", net, "-j", "RETURN")
        _ipt("-t", "nat", "-A", "TORCHAIN", "-p", "tcp", "--syn",
             "-j", "REDIRECT", "--to-ports", trans)

        if not run_ok(["iptables", "-t", "nat", "-C", "OUTPUT", "-j", "TORCHAIN"]):
            _ipt("-t", "nat", "-A", "OUTPUT", "-j", "TORCHAIN")

        if cfg.block_ipv6:
            _block_ipv6()
    except Exception as exc:
        down(cfg, quiet=True)
        if isinstance(exc, FirewallError):
            raise
        raise FirewallError(f"failed to apply firewall rules: {exc}") from exc


def _block_ipv6() -> None:
    if which("ip6tables") is None:
        raise FirewallError("ip6tables not installed but IPv6 blocking was requested")
    # Accept loopback before setting drop policies so local IPv6 IPC remains functional
    _ipt6("-I", "INPUT", "1", "-i", "lo", "-j", "ACCEPT", check=True)
    _ipt6("-I", "OUTPUT", "1", "-o", "lo", "-j", "ACCEPT", check=True)
    _ipt6("-P", "OUTPUT", "DROP", check=True)
    _ipt6("-P", "INPUT", "DROP", check=True)
    _ipt6("-P", "FORWARD", "DROP", check=True)


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
    """Check both nat table and filter table fail-closed DROP chain."""
    nat_active = run_ok(["iptables", "-t", "nat", "-n", "-L", "TORCHAIN"])
    filter_active = run_ok(["iptables", "-t", "filter", "-n", "-L", "TORCHAIN_OUT"])
    drop_active = False
    if filter_active:
        res = run(["iptables", "-t", "filter", "-S", "TORCHAIN_OUT"], check=False)
        drop_active = "-j DROP" in res.stdout
    return nat_active and filter_active and drop_active
