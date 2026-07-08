"""Self-healing watchdog daemon.

Responsibilities:
- Keep torchain healthy: if tor dies or the firewall chains vanish while
  torchain is supposed to be active, repair them (fail-closed first).
- Enforce automatic identity rotation on the configured interval.

Design for robustness (the v3 watchdog 'failed to start'):
- Proper UNIX double-fork daemonization with a PID file.
- All work wrapped so a transient error never kills the loop.
- Cheap: it sleeps between checks and only acts on real state changes.
"""
from __future__ import annotations

import os
import signal
import sys
import time

from . import RUN_DIR, WATCHDOG_LOG
from . import config as config_mod
from .log import get_logger

log = get_logger()

_PIDFILE = os.path.join(RUN_DIR, "watchdog.pid")


def _read_pid() -> int | None:
    try:
        with open(_PIDFILE) as fh:
            return int(fh.read().strip())
    except (OSError, ValueError):
        return None


def _alive(pid) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    # Verify the PID belongs to torchain/watchdog to avoid PID recycling bugs.
    try:
        with open(f"/proc/{pid}/cmdline", "r", encoding="utf-8", errors="replace") as fh:
            cmdline = fh.read()
            return "torchain" in cmdline or "watchdog" in cmdline or "tc4" in cmdline
    except OSError:
        return False


def is_running() -> bool:
    return _alive(_read_pid())


def _daemonize() -> None:
    """Standard double-fork so the watchdog detaches from the controlling tty."""
    if os.fork() > 0:
        os._exit(0)
    os.setsid()
    if os.fork() > 0:
        os._exit(0)
    sys.stdout.flush()
    sys.stderr.flush()
    os.makedirs(RUN_DIR, exist_ok=True)
    devnull = os.open(os.devnull, os.O_RDWR)
    os.dup2(devnull, 0)
    # Redirect stdout/stderr into the watchdog log.
    try:
        os.makedirs(os.path.dirname(WATCHDOG_LOG), exist_ok=True)
        logfd = os.open(WATCHDOG_LOG, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o640)
        os.dup2(logfd, 1)
        os.dup2(logfd, 2)
        os.close(logfd)
    except OSError:
        os.dup2(devnull, 1)
        os.dup2(devnull, 2)
    os.close(devnull)


def start_daemon() -> bool:
    """Fork the watchdog into the background. Returns True if it started."""
    if is_running():
        log.info("watchdog already running (pid %s)", _read_pid())
        return True
    pid = os.fork()
    if pid > 0:
        # Parent: wait briefly to confirm the child wrote its pid file.
        for _ in range(20):
            if is_running():
                return True
            time.sleep(0.1)
        return is_running()
    # Child path.
    try:
        _daemonize()
        with open(_PIDFILE, "w") as fh:
            fh.write(str(os.getpid()))
        _run_loop()
    except Exception as exc:  # noqa: BLE001
        try:
            log.error("watchdog crashed: %s", exc)
        finally:
            os._exit(1)
    os._exit(0)


def stop_daemon() -> None:
    pid = _read_pid()
    if _alive(pid):
        try:
            os.kill(pid, signal.SIGTERM)
            for _ in range(30):
                if not _alive(pid):
                    break
                time.sleep(0.1)
            if _alive(pid):
                os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
    try:
        os.remove(_PIDFILE)
    except OSError:
        pass


_STOP = False


def _handle_signal(signum, frame):
    global _STOP
    _STOP = True


def _run_loop() -> None:
    """The actual monitoring loop (runs in the daemon process)."""
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)
    # Import here so the daemon has a clean module state.
    from . import engine

    last_rotate = time.time()
    print(time.strftime("%Y-%m-%d %H:%M:%S"), "watchdog started", flush=True)
    while not _STOP:
        try:
            cfg = config_mod.load()
            if not cfg.watchdog_enabled:
                break
            st = engine.status(cfg)
            # Self-heal only if torchain is *meant* to be active.
            if cfg.active and not st.active:
                print(time.strftime("%Y-%m-%d %H:%M:%S"),
                      "health check failed -> repairing", flush=True)
                try:
                    engine.start(cfg)
                except Exception as exc:  # noqa: BLE001
                    print("repair failed:", exc, flush=True)
            # Auto identity rotation.
            if cfg.active and cfg.auto_rotate_minutes > 0:
                if time.time() - last_rotate >= cfg.auto_rotate_minutes * 60:
                    try:
                        engine.newnym()
                        last_rotate = time.time()
                        print(time.strftime("%Y-%m-%d %H:%M:%S"),
                              "rotated identity", flush=True)
                    except Exception as exc:  # noqa: BLE001
                        print("rotate failed:", exc, flush=True)
            interval = max(5, cfg.watchdog_interval)
        except Exception as exc:  # noqa: BLE001
            print("watchdog loop error:", exc, flush=True)
            interval = 15
        # Sleep in small slices so SIGTERM is honored promptly.
        slept = 0.0
        while slept < interval and not _STOP:
            time.sleep(0.5)
            slept += 0.5
    print(time.strftime("%Y-%m-%d %H:%M:%S"), "watchdog stopped", flush=True)


def run_foreground() -> int:
    """Run the loop in the foreground (used by the systemd service)."""
    os.makedirs(RUN_DIR, exist_ok=True)
    with open(_PIDFILE, "w") as fh:
        fh.write(str(os.getpid()))
    try:
        _run_loop()
    finally:
        try:
            os.remove(_PIDFILE)
        except OSError:
            pass
    return 0
