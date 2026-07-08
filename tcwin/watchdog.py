"""Connection watchdog for Windows.

There is no ``os.fork`` on Windows, so the daemon is implemented as a detached
background process (``python -m tcwin watchdog --foreground``) tracked by a PID
file. The loop periodically checks that tor is alive and the kill-switch is
still engaged; if tor died it restarts it, and if recovery fails it forces the
firewall closed so the machine fails safe rather than leaking.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

from . import RUN_DIR, WATCHDOG_LOG
from . import config as config_mod
from .log import get_logger
from .sysutil import NO_WINDOW, pid_alive, run_ok

log = get_logger()

_PIDFILE = os.path.join(RUN_DIR, "watchdog.pid")

# Detached, no console, own process group.
_DETACHED = 0x00000008  # DETACHED_PROCESS
_NEW_GROUP = 0x00000200  # CREATE_NEW_PROCESS_GROUP


def _read_pid() -> int | None:
    try:
        with open(_PIDFILE, "r", encoding="utf-8") as fh:
            return int(fh.read().strip())
    except (OSError, ValueError):
        return None


def is_running() -> bool:
    return pid_alive(_read_pid())


def start_daemon() -> bool:
    if is_running():
        log.info("watchdog already running")
        return True
    os.makedirs(RUN_DIR, exist_ok=True)
    python = sys.executable or "python"
    proc = subprocess.Popen(
        [python, "-m", "tcwin", "watchdog", "--foreground"],
        creationflags=_DETACHED | _NEW_GROUP | NO_WINDOW,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
    )
    with open(_PIDFILE, "w", encoding="utf-8") as fh:
        fh.write(str(proc.pid))
    log.info("watchdog started (pid %s)", proc.pid)
    return True


def stop_daemon() -> None:
    pid = _read_pid()
    if pid and pid_alive(pid):
        run_ok(["taskkill", "/PID", str(pid), "/T", "/F"])
    try:
        os.remove(_PIDFILE)
    except OSError:
        pass
    log.info("watchdog stopped")


def _log(msg: str) -> None:
    try:
        os.makedirs(os.path.dirname(WATCHDOG_LOG), exist_ok=True)
        with open(WATCHDOG_LOG, "a", encoding="utf-8") as fh:
            fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
    except OSError:
        pass


def run_foreground() -> int:
    """Blocking supervision loop (invoked in the detached child)."""
    # Import here to avoid a heavy import chain for the common CLI paths.
    from . import engine

    os.makedirs(RUN_DIR, exist_ok=True)
    with open(_PIDFILE, "w", encoding="utf-8") as fh:
        fh.write(str(os.getpid()))
    cfg = config_mod.load()
    interval = max(5, int(cfg.watchdog_interval))
    _log("watchdog online; interval=%ss" % interval)
    fails = 0
    try:
        while True:
            time.sleep(interval)
            try:
                cfg = config_mod.load()
            except Exception:
                pass
            if not cfg.active:
                _log("torchain deactivated by user; watchdog standing down")
                break
            try:
                st = engine.status(cfg)
            except Exception as exc:  # noqa: BLE001
                _log(f"status error: {exc}")
                continue
            if not st.tor_running:
                fails += 1
                _log(f"tor down (attempt {fails}); restarting")
                try:
                    engine.start(cfg, supervise=False)
                    fails = 0
                    _log("tor recovered")
                except Exception as exc:  # noqa: BLE001
                    _log(f"restart failed: {exc}")
                    if fails >= 3:
                        _log("too many failures; forcing kill-switch closed")
                        try:
                            from . import firewall
                            firewall.block_all()
                        except Exception:  # noqa: BLE001
                            pass
            elif not st.firewall_up:
                _log("kill-switch dropped; re-engaging")
                try:
                    from . import firewall
                    firewall.up(cfg, engine.find_tor())
                except Exception as exc:  # noqa: BLE001
                    _log(f"re-arm failed: {exc}")
    finally:
        try:
            os.remove(_PIDFILE)
        except OSError:
            pass
        _log("watchdog exiting")
    return 0
