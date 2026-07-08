"""Bridge / pluggable-transport management.

Supports obfs4, snowflake, meek_lite and webtunnel built-in transports plus
fully custom user-supplied bridge lines. All state lives in the main config
(`use_bridges`, `bridge_type`, `custom_bridges`) so it persists atomically.

We deliberately do NOT ship hardcoded bridge addresses (they rot fast and can
harm users). Instead we validate user input and, where available, help fetch
fresh bridges from Tor's BridgeDB.
"""
from __future__ import annotations

import json
import re
import socket
import urllib.error
import urllib.request

from . import config as config_mod
from .config import Config, _VALID_BRIDGE_TYPES
from .errors import ConfigError
from .log import get_logger

log = get_logger()

MOAT_URL = "https://bridges.torproject.org/moat/circumvention/builtin"

BRIDGE_TYPES = _VALID_BRIDGE_TYPES

# A loose validator: an obfs4 line looks like
#   obfs4 1.2.3.4:443 <FINGERPRINT> cert=... iat-mode=0
# while plain bridges are "IP:PORT [FINGERPRINT]".
_OBFS4_RE = re.compile(r"^obfs4\s+\d{1,3}(?:\.\d{1,3}){3}:\d{2,5}\s+[0-9A-Fa-f]{40}\s+cert=\S+")
_PLAIN_RE = re.compile(r"^(?:Bridge\s+)?\d{1,3}(?:\.\d{1,3}){3}:\d{2,5}(?:\s+[0-9A-Fa-f]{40})?$")
_GENERIC_PT_RE = re.compile(r"^(snowflake|meek_lite|webtunnel|obfs4)\s+\S+")


def validate_bridge_line(line: str) -> bool:
    line = line.strip()
    if not line or line.startswith("#"):
        return False
    return bool(_OBFS4_RE.match(line) or _PLAIN_RE.match(line)
                or _GENERIC_PT_RE.match(line))


def set_type(bridge_type: str, cfg: Config | None = None) -> Config:
    cfg = cfg or config_mod.load()
    if bridge_type not in BRIDGE_TYPES:
        raise ConfigError(f"unknown bridge type '{bridge_type}'",
                          hint=f"choose one of: {', '.join(BRIDGE_TYPES)}")
    cfg.bridge_type = bridge_type
    config_mod.save(cfg)
    log.info("bridge type set to %s", bridge_type)
    return cfg


def enable(on: bool, cfg: Config | None = None) -> Config:
    cfg = cfg or config_mod.load()
    cfg.use_bridges = bool(on)
    config_mod.save(cfg)
    log.info("bridges %s", "enabled" if on else "disabled")
    return cfg


def _detect_transport(lines: list[str]) -> str | None:
    for raw in lines:
        m = _GENERIC_PT_RE.match(raw.strip())
        if m:
            return m.group(1).lower()
    return None


def add(lines, cfg: Config | None = None) -> Config:
    """Add one or more custom bridge lines (string or list)."""
    cfg = cfg or config_mod.load()
    if not hasattr(cfg, "enabled_bridges") or cfg.enabled_bridges is None:
        cfg.enabled_bridges = []
    if isinstance(lines, str):
        lines = [lines]
    added = 0
    for raw in lines:
        line = raw.strip()
        if not validate_bridge_line(line):
            raise ConfigError(
                f"invalid bridge line: {line[:60]}",
                hint="Expected e.g. 'obfs4 1.2.3.4:443 <FP> cert=... iat-mode=0'.",
            )
        if line not in cfg.custom_bridges:
            cfg.custom_bridges.append(line)
            added += 1
            if line not in cfg.enabled_bridges:
                cfg.enabled_bridges.append(line)
    # Auto-align bridge_type with the transport detected in the added lines so
    # the correct ClientTransportPlugin is registered (fixes pasting a webtunnel
    # line while bridge_type is still the default 'obfs4').
    if added:
        detected = _detect_transport([raw for raw in lines if raw.strip()])
        if detected and cfg.bridge_type != detected:
            cfg.bridge_type = detected
    config_mod.save(cfg)
    log.info("added %d custom bridge(s)", added)
    return cfg


def remove(index_or_line, cfg: Config | None = None) -> Config:
    cfg = cfg or config_mod.load()
    if not hasattr(cfg, "enabled_bridges") or cfg.enabled_bridges is None:
        cfg.enabled_bridges = []
    if isinstance(index_or_line, int):
        if 0 <= index_or_line < len(cfg.custom_bridges):
            line = cfg.custom_bridges.pop(index_or_line)
            if line in cfg.enabled_bridges:
                cfg.enabled_bridges.remove(line)
        else:
            raise ConfigError(f"no bridge at index {index_or_line}")
    else:
        line = index_or_line.strip()
        try:
            cfg.custom_bridges.remove(line)
        except ValueError as exc:
            raise ConfigError("that bridge line is not in the list") from exc
        if line in cfg.enabled_bridges:
            cfg.enabled_bridges.remove(line)
    config_mod.save(cfg)
    return cfg


def clear(cfg: Config | None = None) -> Config:
    cfg = cfg or config_mod.load()
    cfg.custom_bridges = []
    cfg.enabled_bridges = []
    config_mod.save(cfg)
    log.info("cleared all custom bridges")
    return cfg


def listing(cfg: Config | None = None) -> list[str]:
    cfg = cfg or config_mod.load()
    return list(cfg.custom_bridges)


# -- Bridge fetching ------------------------------------------------------------

def fetch_bridges(transport: str = "obfs4", url: str | None = None) -> list[str]:
    """Fetch bridge lines from the Tor Project's API (or a custom URL).

    Default source: the ``/moat/circumvention/builtin`` endpoint which returns
    the official builtin (public) obfs4/snowflake bridges -- no captcha needed.

    A custom *url* can point to any plain-text file with one bridge per line
    (e.g. community-maintained bridge lists on GitHub).
    """
    source = url or MOAT_URL
    try:
        with urllib.request.urlopen(source, timeout=15) as resp:
            body = resp.read().decode("utf-8")
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise ConfigError(
            f"could not fetch bridges from {source}",
            hint=f"Network error: {exc}. Check your connection or specify a custom URL.",
        ) from exc

    lines: list[str] = []
    # Try JSON (moat API format); fall back to line-by-line plain text.
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        data = None

    if isinstance(data, dict):
        for key in (transport, "meek", "meek-azure", "snowflake", "webtunnel"):
            chunk = data.get(key, [])
            if isinstance(chunk, list):
                for item in chunk:
                    if isinstance(item, str) and validate_bridge_line(item) and item not in lines:
                        lines.append(item)
        # Also pick up *any* transport key (handles future transports).
        for val in data.values():
            if isinstance(val, list):
                for item in val:
                    if isinstance(item, str) and validate_bridge_line(item) and item not in lines:
                        lines.append(item)
    else:
        for raw in body.splitlines():
            ln = raw.strip()
            if validate_bridge_line(ln):
                lines.append(ln)

    if not lines:
        raise ConfigError(
            f"no valid {transport} bridge lines found at {source}",
            hint="The source may have changed. Try specifying a custom URL.",
        )
    return lines


def append_fetched(transport: str = "obfs4", url: str | None = None,
                   cfg: Config | None = None) -> Config:
    """Fetch bridge lines and append them to the config."""
    cfg = cfg or config_mod.load()
    if not hasattr(cfg, "enabled_bridges") or cfg.enabled_bridges is None:
        cfg.enabled_bridges = []
    fetched = fetch_bridges(transport=transport, url=url)
    added = 0
    enabled_changed = False
    for ln in fetched:
        if ln not in cfg.custom_bridges:
            cfg.custom_bridges.append(ln)
            added += 1
        if ln not in cfg.enabled_bridges:
            cfg.enabled_bridges.append(ln)
            enabled_changed = True
    if added or enabled_changed:
        detected = _detect_transport(fetched)
        if detected and cfg.bridge_type != detected:
            cfg.bridge_type = detected
        config_mod.save(cfg)
        log.info("fetched and added %d bridge(s) from %s", added, url or MOAT_URL)
    return cfg


# -- Bridge testing ------------------------------------------------------------

_IP_PORT_RE = re.compile(r"(\d{1,3}(?:\.\d{1,3}){3}):(\d{2,5})")


def _extract_addr(line: str) -> tuple[str, int] | None:
    m = _IP_PORT_RE.search(line)
    if m:
        return m.group(1), int(m.group(2))
    return None


def test_bridges(bridge_lines: list[str] | None = None,
                 cfg: Config | None = None, *,
                 timeout: float = 5.0) -> list[tuple[str, bool, str]]:
    """TCP-ping each bridge and return ``(line, alive, info)`` tuples."""
    if bridge_lines is None:
        cfg = cfg or config_mod.load()
        bridge_lines = cfg.custom_bridges
    results: list[tuple[str, bool, str]] = []
    for line in bridge_lines:
        line_strip = line.strip()
        # Pluggable transports using dummy/placeholder addresses cannot be TCP-pinged directly.
        is_placeholder = False
        for pt in ("snowflake", "meek_lite", "webtunnel"):
            if line_strip.startswith(pt):
                is_placeholder = True
                break
        if is_placeholder:
            results.append((line, True, "assumed reachable (pluggable transport)"))
            continue

        addr = _extract_addr(line)
        if not addr:
            results.append((line, False, "no IP:port found"))
            continue
        host, port = addr
        try:
            sock = socket.create_connection((host, port), timeout=timeout)
            sock.close()
            results.append((line, True, f"{host}:{port} reachable"))
        except OSError as exc:
            results.append((line, False, f"{host}:{port} — {exc}"))
    return results
