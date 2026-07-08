"""Configuration: a typed dataclass persisted as atomic JSON.

Atomic writes (temp file + os.replace) guarantee we never leave a partially
written config behind on crash or power loss.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from typing import List

from . import CONFIG_DIR, CONFIG_FILE, CONTROL_PORT, DNS_PORT, SOCKS_PORT, TRANS_PORT
from .errors import ConfigError
from .log import get_logger

log = get_logger()

_VALID_BRIDGE_TYPES = ("obfs4", "snowflake", "meek_lite", "webtunnel", "custom")


@dataclass
class Config:
    # Routing
    trans_port: int = TRANS_PORT
    dns_port: int = DNS_PORT
    socks_port: int = SOCKS_PORT
    control_port: int = CONTROL_PORT

    # Behavior
    exit_country: str = ""            # e.g. "us"; empty = any
    block_ipv6: bool = True

    # Bridges / pluggable transports
    use_bridges: bool = False
    bridge_type: str = "obfs4"       # see _VALID_BRIDGE_TYPES
    custom_bridges: List[str] = field(default_factory=list)

    # Identity rotation (handled by the watchdog)
    auto_rotate_minutes: int = 0     # 0 = disabled

    # Spoofing
    spoof_mac: bool = False
    spoof_hostname: bool = False

    # Self-healing / automation
    watchdog_enabled: bool = True
    watchdog_interval: int = 15      # seconds between health checks
    start_on_boot: bool = False

    # State (managed by the engine)
    active: bool = False
    last_profile: str = ""

    def validate(self) -> None:
        for p in (self.trans_port, self.dns_port, self.socks_port, self.control_port):
            if not (1 <= int(p) <= 65535):
                raise ConfigError(f"invalid port: {p}")
        if self.exit_country and len(self.exit_country) != 2:
            raise ConfigError("exit_country must be a 2-letter code (e.g. 'us')")
        if self.auto_rotate_minutes < 0:
            raise ConfigError("auto_rotate_minutes cannot be negative")
        if self.bridge_type not in _VALID_BRIDGE_TYPES:
            raise ConfigError(
                f"invalid bridge_type '{self.bridge_type}'",
                hint=f"choose one of: {', '.join(_VALID_BRIDGE_TYPES)}",
            )
        if self.watchdog_interval < 5:
            raise ConfigError("watchdog_interval must be at least 5 seconds")


def load() -> Config:
    if not os.path.exists(CONFIG_FILE):
        return Config()
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(
            f"could not read config at {CONFIG_FILE}: {exc}",
            hint="Delete the file to reset to defaults.",
        ) from exc
    known = {f.name for f in fields(Config)}
    clean = {k: v for k, v in data.items() if k in known}
    cfg = Config(**clean)
    if cfg.dns_port == 5353:
        cfg.dns_port = DNS_PORT
    cfg.validate()
    return cfg


def save(cfg: Config) -> None:
    cfg.validate()
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        tmp = CONFIG_FILE + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(asdict(cfg), fh, indent=2, sort_keys=True)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, CONFIG_FILE)
    except OSError as exc:
        raise ConfigError(f"could not write config: {exc}") from exc
