"""Run-on-boot management. Works on both VMs and bare-metal Linux.

Primary path: a systemd service that runs `torchain start` at boot (after the
network is online) and optionally keeps the watchdog alive. If systemd is not
present (some minimal VMs/containers), we fall back to an rc.local entry or a
cron @reboot job so the feature still works everywhere.
"""
from __future__ import annotations

import os

from . import BIN_LINK
from . import config as config_mod
from . import platform as plat
from .errors import TorChainError
from .log import get_logger
from .sysutil import run, run_ok, which

log = get_logger()

_SERVICE_PATH = "/etc/systemd/system/torchain.service"
_WATCHDOG_SERVICE_PATH = "/etc/systemd/system/torchain-watchdog.service"
_RC_LOCAL = "/etc/rc.local"
_MARKER = "# >>> torchain boot >>>"
_MARKER_END = "# <<< torchain boot <<<"


def _service_unit() -> str:
    return f"""[Unit]
Description=torchain - system-wide Tor anonymizer
Wants=network-online.target
After=network-online.target nss-lookup.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart={BIN_LINK} start
ExecStop={BIN_LINK} stop
TimeoutStartSec=120

[Install]
WantedBy=multi-user.target
"""


def _watchdog_unit() -> str:
    return f"""[Unit]
Description=torchain watchdog - self-healing + identity rotation
After=torchain.service
Requires=torchain.service

[Service]
Type=simple
ExecStart={BIN_LINK} watchdog --foreground
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
"""


def _write(path: str, content: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)


def enable() -> str:
    """Enable start-on-boot. Returns a human description of the method used."""
    env = plat.detect()
    cfg = config_mod.load()
    if env.has_systemd and which("systemctl"):
        _write(_SERVICE_PATH, _service_unit())
        _write(_WATCHDOG_SERVICE_PATH, _watchdog_unit())
        run_ok(["systemctl", "daemon-reload"])
        run(["systemctl", "enable", "torchain.service"], check=False)
        if cfg.watchdog_enabled:
            run(["systemctl", "enable", "torchain-watchdog.service"], check=False)
        method = "systemd service (torchain.service)"
    else:
        _enable_rc_local()
        method = "rc.local / cron @reboot fallback"
    cfg.start_on_boot = True
    config_mod.save(cfg)
    log.info("start-on-boot enabled via %s", method)
    return method


def disable() -> str:
    env = plat.detect()
    cfg = config_mod.load()
    if env.has_systemd and which("systemctl"):
        run(["systemctl", "disable", "torchain.service"], check=False)
        run(["systemctl", "disable", "torchain-watchdog.service"], check=False)
        for p in (_SERVICE_PATH, _WATCHDOG_SERVICE_PATH):
            try:
                os.remove(p)
            except OSError:
                pass
        run_ok(["systemctl", "daemon-reload"])
        method = "systemd"
    else:
        _disable_rc_local()
        method = "rc.local / cron"
    cfg.start_on_boot = False
    config_mod.save(cfg)
    log.info("start-on-boot disabled (%s)", method)
    return method


def status() -> bool:
    env = plat.detect()
    if env.has_systemd and which("systemctl"):
        return run_ok(["systemctl", "is-enabled", "--quiet", "torchain.service"])
    if os.path.exists(_RC_LOCAL):
        try:
            with open(_RC_LOCAL, encoding="utf-8") as fh:
                return _MARKER in fh.read()
        except OSError:
            return False
    return False


def _enable_rc_local() -> None:
    block = f"{_MARKER}\n{BIN_LINK} start\n{_MARKER_END}\n"
    if which("crontab"):
        # Prefer a cron @reboot job (works without rc-local support).
        existing = run(["crontab", "-l"], check=False).stdout or ""
        if "torchain start" not in existing:
            new = existing.rstrip("\n") + f"\n@reboot {BIN_LINK} start\n"
            run(["crontab", "-"], input_text=new, check=False)
        return
    # rc.local fallback.
    content = ""
    if os.path.exists(_RC_LOCAL):
        with open(_RC_LOCAL, encoding="utf-8") as fh:
            content = fh.read()
    else:
        content = "#!/bin/sh\n"
    if _MARKER not in content:
        if not content.rstrip().endswith("exit 0"):
            content = content.rstrip("\n") + "\n"
        content += block
        _write(_RC_LOCAL, content)
        os.chmod(_RC_LOCAL, 0o755)


def _disable_rc_local() -> None:
    if which("crontab"):
        existing = run(["crontab", "-l"], check=False).stdout or ""
        if "torchain start" in existing:
            kept = [ln for ln in existing.splitlines() if "torchain start" not in ln]
            run(["crontab", "-"], input_text="\n".join(kept) + "\n", check=False)
    if os.path.exists(_RC_LOCAL):
        try:
            with open(_RC_LOCAL, encoding="utf-8") as fh:
                content = fh.read()
            if _MARKER in content and _MARKER_END in content:
                head = content.split(_MARKER)[0]
                tail = content.split(_MARKER_END)[1]
                _write(_RC_LOCAL, head + tail)
        except OSError:
            pass
