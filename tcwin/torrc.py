"""Generate a torrc for a dedicated tor instance on Windows.

Key differences from the Linux torrc:
* No ``TransPort`` - tor does not support transparent proxying on Windows.
  Enforcement is done with the SOCKS proxy + firewall kill-switch instead.
* No ``User`` directive - the process runs as the (elevated) launching user.
* Windows-style paths for DataDirectory, and GeoIP files are pointed at the
  files shipped with the Tor bundle (extracted from the bundled Tor.zip) when found.
"""
from __future__ import annotations

import os
import re
import shutil

from . import DATA_DIR, LOG_DIR
from .config import Config


def _default_tor_dir() -> str | None:
    try:
        from .engine import find_tor
        t = find_tor()
        if t:
            return os.path.dirname(t)
    except Exception:
        pass
    cand = os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"), "torchain", "app", "tor", "Tor")
    if os.path.isdir(cand):
        return cand
    return None


def _plugin_path(tor_dir: str | None, *names: str) -> str | None:
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    target_dir = tor_dir or _default_tor_dir()
    if target_dir:
        # Search the tor directory itself, and also the PluggableTransports
        # subdirectory (used by the Tor Expert Bundle / bundled Tor.zip).
        search_dirs = [
            target_dir,
            os.path.join(target_dir, "PluggableTransports"),
            os.path.join(os.path.dirname(target_dir), "PluggableTransports"),
        ]
        for d in search_dirs:
            for n in names:
                cand = os.path.join(d, n if n.endswith(".exe") else n + ".exe")
                if os.path.exists(cand):
                    return cand
    return None


def is_transport_supported(transport: str, tor_dir: str | None = None) -> bool:
    """Return True if the pluggable transport executable exists on this system."""
    t = transport.lower()
    if t in ("obfs4", "meek_lite"):
        return _plugin_path(tor_dir, "obfs4proxy", "lyrebird") is not None
    if t == "snowflake":
        return _plugin_path(tor_dir, "snowflake-client", "snowflake") is not None
    if t == "webtunnel":
        return _plugin_path(tor_dir, "webtunnel-client", "webtunnel") is not None
    if t == "conjure":
        return _plugin_path(tor_dir, "conjure-client", "conjure") is not None
    return False


def available_transports(tor_dir: str | None = None) -> list[str]:
    """Return the list of pluggable transports actually available on this system."""
    avail: list[str] = []
    if _plugin_path(tor_dir, "obfs4proxy", "lyrebird"):
        avail.extend(["obfs4", "meek_lite"])
    if _plugin_path(tor_dir, "conjure-client", "conjure"):
        avail.append("conjure")
    if _plugin_path(tor_dir, "snowflake-client", "snowflake"):
        avail.append("snowflake")
    if _plugin_path(tor_dir, "webtunnel-client", "webtunnel"):
        avail.append("webtunnel")
    return avail


def _transport_for_line(line: str) -> str | None:
    m = re.match(r"^(?:bridge\s+)?(obfs4|snowflake|meek_lite|webtunnel|conjure)\b", line.strip(), re.I)
    return m.group(1).lower() if m else None


def _transport_lines(cfg: Config, tor_dir: str | None) -> list[str]:
    needed: list[str] = []

    for br in cfg.custom_bridges:
        t = _transport_for_line(br)
        if t and t not in needed and is_transport_supported(t, tor_dir):
            needed.append(t)

    bt = cfg.bridge_type
    if bt not in needed and bt != "custom" and is_transport_supported(bt, tor_dir):
        needed.insert(0, bt)

    out: list[str] = []
    seen_lines: set[str] = set()
    for t in needed:
        if t in ("obfs4", "meek_lite"):
            path = _plugin_path(tor_dir, "obfs4proxy", "lyrebird")
            if not path:
                continue
            path_clean = path.replace("\\", "/")
            line = f'ClientTransportPlugin obfs4,meek_lite exec "{path_clean}"'
        elif t == "snowflake":
            path = _plugin_path(tor_dir, "snowflake-client", "snowflake")
            if not path:
                continue
            path_clean = path.replace("\\", "/")
            line = f'ClientTransportPlugin snowflake exec "{path_clean}"'
        elif t == "webtunnel":
            path = _plugin_path(tor_dir, "webtunnel-client", "webtunnel")
            if not path:
                continue
            path_clean = path.replace("\\", "/")
            line = f'ClientTransportPlugin webtunnel exec "{path_clean}"'
        elif t == "conjure":
            path = _plugin_path(tor_dir, "conjure-client", "conjure")
            if not path:
                continue
            path_clean = path.replace("\\", "/")
            line = f'ClientTransportPlugin conjure exec "{path_clean}"'
        else:
            continue
        if line not in seen_lines:
            seen_lines.add(line)
            out.append(line)
    return out


def _bridge_lines(cfg: Config, tor_dir: str | None) -> list[str]:
    if not cfg.use_bridges:
        return []

    valid_bridges: list[str] = []
    for br in cfg.custom_bridges:
        br_str = br.strip()
        if not br_str or br_str.startswith("#"):
            continue
        t = _transport_for_line(br_str)
        if t and not is_transport_supported(t, tor_dir):
            from .log import get_logger
            get_logger().warning(
                "Skipping bridge with unbundled transport '%s': %s",
                t, br_str[:50]
            )
            continue
        if not br_str.lower().startswith("bridge "):
            br_str = "Bridge " + br_str
        valid_bridges.append(br_str)

    if not valid_bridges:
        from .log import get_logger
        get_logger().warning(
            "UseBridges is enabled but no valid bridge lines are configured. "
            "Disabling bridges to prevent Tor configuration failure."
        )
        return []

    lines = ["UseBridges 1"]
    lines.extend(_transport_lines(cfg, tor_dir))
    lines.extend(valid_bridges)
    return lines


def _geoip_lines(tor_dir: str | None) -> list[str]:
    if not tor_dir:
        return []
    out = []
    geoip = os.path.join(tor_dir, "geoip")
    geoip6 = os.path.join(tor_dir, "geoip6")
    # Tor Browser ships these under ...\Tor\ or a sibling \Data\Tor\.
    for base in (tor_dir, os.path.join(os.path.dirname(tor_dir), "Data", "Tor")):
        g = os.path.join(base, "geoip")
        g6 = os.path.join(base, "geoip6")
        if os.path.exists(g):
            geoip, geoip6 = g, g6
            break
    if os.path.exists(geoip):
        out.append(f"GeoIPFile {geoip}")
    if os.path.exists(geoip6):
        out.append(f"GeoIPv6File {geoip6}")
    return out


def build(cfg: Config, tor_dir: str | None = None) -> str:
    tor_data = os.path.join(DATA_DIR, "tor")
    tor_log = os.path.join(LOG_DIR, "tor.log")
    lines = [
        "# Generated by torchain (Windows) - do not edit by hand.",
        f"Log notice file {tor_log}",
        "ClientOnly 1",
        "SocksPort 127.0.0.1:%d" % cfg.socks_port,
        "HTTPTunnelPort 127.0.0.1:%d" % getattr(cfg, "http_port", 9080),
        "DNSPort 127.0.0.1:%d" % cfg.dns_port,
        "AutomapHostsOnResolve 1",
        "AutomapHostsSuffixes .onion,.exit",
        "VirtualAddrNetworkIPv4 10.192.0.0/10",
        "ControlPort 127.0.0.1:%d" % cfg.control_port,
        "CookieAuthentication 1",
        f"DataDirectory {tor_data}",
        "AvoidDiskWrites 1",
        "SafeLogging 1",
        "OptimisticData 1",
        "LearnCircuitBuildTimeout 1",
        "KeepalivePeriod 120",
        "NewCircuitPeriod 120",
    ]
    lines.extend(_geoip_lines(tor_dir))
    if cfg.block_ipv6:
        lines.append("ClientUseIPv6 0")
    else:
        lines.append("ClientUseIPv6 1")
    if cfg.exit_country:
        cc = cfg.exit_country.lower()
        lines.append("ExitNodes {%s}" % cc)
        lines.append("StrictNodes 1")
    lines.extend(_bridge_lines(cfg, tor_dir))
    return "\n".join(lines) + "\n"


def write(cfg: Config, path: str, tor_dir: str | None = None) -> None:
    content = build(cfg, tor_dir)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(content)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
    try:
        from .sysutil import which, run_ok
        import getpass
        if which("icacls"):
            curr_user = getpass.getuser()
            grants = ["/grant:r", "*S-1-5-18:F", "/grant:r", "*S-1-5-32-544:F"]
            if curr_user:
                grants.extend(["/grant:r", f"{curr_user}:F"])
            run_ok(["icacls", path, "/inheritance:r", *grants])
    except Exception:
        pass
