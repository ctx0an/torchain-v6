"""Aggressive-but-safe network self-repair.

This is the engine behind ``torchain repair`` and the GUI's "Repair Internet"
button. It exists for the worst case: torchain (or a crash) left firewall rules
attached, a locked/loopback-only ``resolv.conf``, or a spoofed hostname behind,
and the machine has no working internet.

Design:
- Surgical first: remove torchain's own iptables chains, then make sure the
  default policies are permissive again (so a leftover DROP can't keep you
  offline) without blindly flushing every unrelated rule.
- Idempotent + defensive: every step is best-effort and never aborts the rest.
- Restores DNS only when it is actually broken (loopback-only / missing), so we
  don't stomp a healthy systemd-resolved / NetworkManager setup.
- Restarts whichever network stack is actually present, flushes DNS caches, and
  brings interfaces back up.
"""
from __future__ import annotations

import json
import os

from . import DATA_DIR
from .log import get_logger
from .sysutil import run, run_ok, which

log = get_logger()

_RESOLV = "/etc/resolv.conf"
_FALLBACK_DNS = ("1.1.1.1", "9.9.9.9", "8.8.8.8")


def _flush_iptables() -> list[str]:
    out: list[str] = []
    if which("iptables"):
        # Remove torchain's chains surgically (delete every OUTPUT jump first).
        for table, chain in (("nat", "TORCHAIN"), ("filter", "TORCHAIN_OUT")):
            base = ["iptables", "-t", table]
            for _ in range(64):
                if not run_ok(base + ["-C", "OUTPUT", "-j", chain]):
                    break
                if not run_ok(base + ["-D", "OUTPUT", "-j", chain]):
                    break
            run_ok(base + ["-F", chain])
            run_ok(base + ["-X", chain])
        # Make sure nothing is left blocking egress.
        for pol in ("INPUT", "OUTPUT", "FORWARD"):
            run_ok(["iptables", "-P", pol, "ACCEPT"])
        out.append("iptables: torchain chains removed, policies set to ACCEPT")
    if which("ip6tables"):
        for pol in ("INPUT", "OUTPUT", "FORWARD"):
            run_ok(["ip6tables", "-P", pol, "ACCEPT"])
        out.append("ip6tables: policies set to ACCEPT")
    return out


def _dns_is_broken() -> bool:
    """True if resolv.conf is missing or only points at loopback (dead tor DNS)."""
    try:
        with open(_RESOLV, "r", encoding="utf-8") as fh:
            servers = [ln for ln in fh.read().splitlines()
                       if ln.strip().startswith("nameserver")]
    except OSError:
        return True
    if not servers:
        return True
    return all(("127.0.0.1" in ln or "::1" in ln) for ln in servers)


def _restore_dns() -> list[str]:
    out: list[str] = []
    # Unlock resolv.conf if torchain or another tool made it immutable.
    if which("chattr"):
        run_ok(["chattr", "-i", _RESOLV])
    if not _dns_is_broken():
        out.append("DNS already valid")
        return out
    try:
        if os.path.exists(_RESOLV) and not os.path.exists(_RESOLV + ".torchain.bak"):
            run_ok(["cp", "-a", _RESOLV, _RESOLV + ".torchain.bak"])
        with open(_RESOLV, "w", encoding="utf-8") as fh:
            fh.write("# restored by torchain repair\n")
            for ns in _FALLBACK_DNS:
                fh.write(f"nameserver {ns}\n")
        out.append("resolv.conf restored with public resolvers")
    except OSError as exc:
        out.append(f"resolv.conf left as-is: {exc}")
    return out


def _verify_hosts_file(orig_host: str | None = None, spoofed_host: str | None = None) -> list[str]:
    out: list[str] = []
    hosts_path = "/etc/hosts"
    if not os.path.exists(hosts_path):
        return out
    try:
        with open(hosts_path, "r", encoding="utf-8") as fh:
            content = fh.read()
        lines = content.splitlines()

        # If spoofed hostname was set and differs from original, remove it
        if spoofed_host and spoofed_host not in ("localhost", "127.0.0.1", "::1", orig_host):
            cleaned = []
            for ln in lines:
                stripped = ln.strip()
                if not stripped or stripped.startswith("#"):
                    cleaned.append(ln)
                    continue
                tokens = stripped.split()
                if len(tokens) >= 2 and tokens[0] in ("127.0.0.1", "127.0.1.1"):
                    remaining = [t for t in tokens[1:] if t != spoofed_host]
                    if not remaining:
                        continue
                    cleaned.append(f"{tokens[0]}\t{' '.join(remaining)}")
                else:
                    cleaned.append(ln)
            lines = cleaned

        # Ensure localhost exists
        has_localhost = any("localhost" in ln.split() for ln in lines if not ln.strip().startswith("#"))
        if not has_localhost:
            lines.append("127.0.0.1\tlocalhost")

        # Ensure current or original hostname exists
        target_host = orig_host or (run(["hostname"], check=False).stdout.strip() if which("hostname") else "")
        if target_host and target_host != "localhost":
            has_host = any(target_host in ln.split() for ln in lines if not ln.strip().startswith("#"))
            if not has_host:
                lines.append(f"127.0.1.1\t{target_host}")
                out.append(f"added {target_host} to /etc/hosts")

        new_content = "\n".join(lines) + "\n"
        if new_content != content:
            with open(hosts_path, "w", encoding="utf-8") as fh:
                fh.write(new_content)
            out.append("/etc/hosts verified and repaired")
    except OSError as exc:
        out.append(f"/etc/hosts could not be updated: {exc}")
    return out


def _restore_identity() -> list[str]:
    out: list[str] = []
    # Bring every non-loopback interface back up (spoofing leaves them down on
    # error paths).
    if which("ip"):
        try:
            for name in sorted(os.listdir("/sys/class/net")):
                if name == "lo":
                    continue
                run_ok(["ip", "link", "set", name, "up"])
        except OSError:
            pass
    # Restore the original hostname if torchain spoofed it.
    state_path = os.path.join(DATA_DIR, "spoof_state.json")
    host: str | None = None
    spoofed_host: str | None = None
    try:
        with open(state_path, "r", encoding="utf-8") as fh:
            state = json.load(fh)
        host = state.get("hostname")
        spoofed_host = state.get("spoofed_hostname")
        if host and which("hostname"):
            run_ok(["hostname", host])
            out.append(f"hostname restored to {host}")
    except (OSError, json.JSONDecodeError):
        pass
    out.extend(_verify_hosts_file(host, spoofed_host))
    return out


def _restart_network() -> list[str]:
    out: list[str] = []
    if which("systemctl"):
        for svc in ("NetworkManager", "systemd-networkd", "networking",
                    "wpa_supplicant"):
            if run_ok(["systemctl", "list-unit-files", f"{svc}.service"]):
                if run_ok(["systemctl", "restart", svc], timeout=30):
                    out.append(f"restarted {svc}")
        # Flush the systemd-resolved cache if present.
        run_ok(["systemctl", "restart", "systemd-resolved"], timeout=30)
    if which("resolvectl"):
        run_ok(["resolvectl", "flush-caches"])
    if which("nscd"):
        run_ok(["nscd", "-i", "hosts"])
    # Last resort: renew DHCP leases directly.
    if not out and which("dhclient"):
        run_ok(["dhclient", "-r"], timeout=20)
        run_ok(["dhclient"], timeout=40)
        out.append("renewed DHCP leases")
    if not out:
        out.append("no network manager found to restart")
    return out


def repair() -> str:
    """Run the full repair sequence and return a one-line human summary."""
    from . import config as config_mod
    from . import engine

    cfg = config_mod.load()
    st = engine.status(cfg)
    if cfg.active or st.active or st.tor_running:
        log.warning("repair requested while Tor is active; stopping Tor first to prevent leaks")
        try:
            engine.stop(cfg)
        except Exception as exc:
            log.error("failed to stop Tor before repair: %s", exc)
            return f"Error: Cannot repair network while Tor is active (stop failed: {exc}). Please run 'torchain stop' first."

    steps: list[str] = []
    steps += _flush_iptables()
    steps += _restore_dns()
    steps += _restore_identity()
    steps += _restart_network()
    msg = "; ".join(s for s in steps if s)
    log.info("internet repair: %s", msg)
    return msg or "nothing to repair"
