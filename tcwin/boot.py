"""Run-on-boot management via the Windows Task Scheduler.

We register a SYSTEM-level scheduled task that runs ``torchain start`` at boot
with highest privileges. This is the Windows analogue of the Linux systemd
unit. ``schtasks`` ships with every Windows install, so there is no extra
dependency.
"""
from __future__ import annotations

import os
import sys

from . import SHARE_DIR
from . import config as config_mod
from .log import get_logger
from .sysutil import run, run_ok, which

log = get_logger()

_TASK = "torchain"
_TASK_WD = "torchain-watchdog"


def _launcher() -> str:
    """Best command line to (re)start torchain non-interactively."""
    # If running as a frozen .exe, use the .exe path directly.
    if getattr(sys, 'frozen', False):
        return f'"{sys.argv[0]}"'
    python = sys.executable or "python"
    # Prefer the installed launcher if present, else `python -m tcwin`.
    installed = os.path.join(SHARE_DIR, "torchain.cmd")
    if os.path.exists(installed):
        return f'"{installed}"'
    return f'"{python}" -m tcwin'


def enable() -> str:
    cfg = config_mod.load()
    cmd = _launcher()
    run(["schtasks", "/Create", "/TN", _TASK, "/SC", "ONSTART",
         "/RU", "SYSTEM", "/RL", "HIGHEST", "/F",
         "/TR", f"{cmd} start"], check=False, timeout=30)
    if cfg.watchdog_enabled:
        run(["schtasks", "/Create", "/TN", _TASK_WD, "/SC", "ONSTART",
             "/RU", "SYSTEM", "/RL", "HIGHEST", "/F",
             "/TR", f"{cmd} watchdog --foreground"], check=False, timeout=30)
    cfg.start_on_boot = True
    config_mod.save(cfg)
    log.info("start-on-boot enabled via Task Scheduler")
    return "Windows Task Scheduler (task 'torchain')"


def disable() -> str:
    cfg = config_mod.load()
    run_ok(["schtasks", "/Delete", "/TN", _TASK, "/F"])
    run_ok(["schtasks", "/Delete", "/TN", _TASK_WD, "/F"])
    cfg.start_on_boot = False
    config_mod.save(cfg)
    log.info("start-on-boot disabled")
    return "Task Scheduler"


def status() -> bool:
    if which("schtasks") is None:
        return False
    return run_ok(["schtasks", "/Query", "/TN", _TASK])
