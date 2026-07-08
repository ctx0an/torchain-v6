"""The engine: orchestrates tor + firewall + spoofing into start/stop/status.

Designed to be fast and crash-safe:
- A single dedicated tor process we own (PID tracked in the run dir).
- Fail-closed: if anything goes wrong mid-start, we roll everything back.
- Status is cheap to compute (no heavy work) so polling stays light.
- Optionally supervised by the self-healing watchdog.
- Works on both VMs and bare-metal Linux.
"""
from __future__ import annotations

import os
import signal
import time
from dataclasses import dataclass

from . import CONFIG_DIR, DATA_DIR, LOG_DIR, RUN_DIR, TORRC_FILE
from . import config as config_mod
from . import firewall, platform as plat, spoof, torrc, watchdog
from .config import Config
from .errors import DependencyError, TorError
from .log import get_logger
from .sysutil import ProcessLock, require_root, run, run_ok, which
from .torctl import ControlClient, wait_bootstrap

log = get_logger()

_PIDFILE = os.path.join(RUN_DIR, "tor.pid")
_LOCKFILE = os.path.join(RUN_DIR, "torchain.lock")
_CANDIDATE_TOR_USERS = ("debian-tor", "tor", "_tor")


@dataclass
class Status:
    active: bool
    tor_running: bool
    firewall_up: bool
    bootstrap: int
    pid: int | None
    watchdog: bool = False
    exit_ip: str | None = None


def _detect_tor_user() -> str:
    import pwd
    for name in _CANDIDATE_TOR_USERS:
        try:
            pwd.getpwnam(name)
            return name
        except KeyError:
            continue
    return "debian-tor"


def _ensure_dirs(tor_user: str) -> None:
    """Create and *correctly own* the runtime dirs.

    The dedicated tor instance runs as ``tor_user`` (it drops privileges via the
    ``User`` directive), so its DataDirectory must be owned by that user and be
    mode 0700 - otherwise tor aborts with "Couldn't create private data
    directory". We resolve the user's real uid + *primary gid* with ``pwd`` and
    chown directly: shelling out to ``chown user:user`` silently fails on
    systems where the group name differs from the user name, which used to
    leave the dir root-owned and made tor fail to launch.
    """
    import pwd

    tor_data = os.path.join(DATA_DIR, "tor")
    for d in (CONFIG_DIR, DATA_DIR, LOG_DIR, RUN_DIR, tor_data):
        os.makedirs(d, exist_ok=True)
    # Parent dirs must stay traversable by the dropped tor user.
    for d in (DATA_DIR, RUN_DIR):
        try:
            os.chmod(d, 0o755)
        except OSError:
            pass
    try:
        pw = pwd.getpwnam(tor_user)
        uid, gid = pw.pw_uid, pw.pw_gid
    except KeyError:
        uid = gid = None
    if uid is not None:
        for base, _dirs, files in os.walk(tor_data):
            try:
                os.chown(base, uid, gid)
            except OSError:
                pass
            for name in files:
                try:
                    os.chown(os.path.join(base, name), uid, gid)
                except OSError:
                    pass
        try:
            os.chown(RUN_DIR, uid, gid)
        except OSError:
            pass
    try:
        os.chmod(tor_data, 0o700)
    except OSError:
        pass


def _read_pid() -> int | None:
    try:
        with open(_PIDFILE) as fh:
            return int(fh.read().strip())
    except (OSError, ValueError):
        return None


def _pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _tor_diagnostics(text: str | None) -> str | None:
    """Extract tor's *real* failure reason from its output.

    tor prints a banner of harmless [notice] lines first and the decisive
    [err]/[warn] line last, so naively truncating the head of the output (as
    we used to) hid the actual cause. Keep the meaningful lines instead.
    """
    if not text:
        return None
    keep = [ln.strip() for ln in text.splitlines()
            if "[err]" in ln or "[warn]" in ln]
    msg = " | ".join(keep[-4:]) if keep else text.strip()
    return (msg[:600] or None)


def _start_tor(cfg: Config, tor_user: str) -> int:
    if which("tor") is None:
        raise DependencyError("the 'tor' package is not installed",
                              hint="Install it via ./setup.sh or your package manager.")
    torrc.write(cfg, TORRC_FILE, tor_user=tor_user)
    # Validate first so we surface the precise reason (bad DataDirectory, a
    # rejected option, ...) rather than a generic "failed to launch".
    verify = run(["tor", "--verify-config", "-f", TORRC_FILE],
                 timeout=30, check=False)
    if verify.returncode != 0:
        raise TorError(
            "tor configuration was rejected",
            hint=_tor_diagnostics(verify.stdout or verify.stderr)
            or f"inspect with: tor --verify-config -f {TORRC_FILE}")
    proc = run(["tor", "-f", TORRC_FILE, "--RunAsDaemon", "1",
                "--PidFile", _PIDFILE], timeout=30, check=False)
    if proc.returncode != 0:
        raise TorError("tor failed to launch",
                       hint=_tor_diagnostics(proc.stderr or proc.stdout))
    for _ in range(20):
        pid = _read_pid()
        if _pid_alive(pid):
            return pid  # type: ignore[return-value]
        time.sleep(0.1)
    raise TorError("tor started but no live PID was found")


def start(cfg: Config | None = None, *, on_progress=None, supervise: bool = True) -> Status:
    require_root()
    with ProcessLock(_LOCKFILE):
        cfg = cfg or config_mod.load()
        tor_user = _detect_tor_user()
        _ensure_dirs(tor_user)
        log.debug("environment: %s", plat.describe())
    
        started_tor = False
        try:
            if cfg.spoof_mac:
                spoof.spoof_mac()
            if cfg.spoof_hostname:
                spoof.spoof_hostname()
                
            # Apply firewall first so we are fail-closed during bootstrap!
            firewall.up(cfg, tor_user)
            
            if not _pid_alive(_read_pid()):
                _start_tor(cfg, tor_user)
                started_tor = True
            ok = wait_bootstrap(timeout=60, on_progress=on_progress)
            if not ok:
                raise TorError("tor did not finish bootstrapping in time",
                               hint="Check your connection or try bridges.")
            cfg.active = True
            config_mod.save(cfg)
            if supervise and cfg.watchdog_enabled:
                try:
                    watchdog.start_daemon()
                except Exception as exc:  # noqa: BLE001
                    log.warning("watchdog could not start: %s", exc)
            log.info("torchain is active")
            return status(cfg)
        except Exception:
            log.error("start failed; rolling back")
            try:
                firewall.down(cfg, quiet=True)
            finally:
                if started_tor:
                    _stop_tor()
                if cfg.spoof_mac or cfg.spoof_hostname:
                    spoof.restore()
            raise


def _stop_tor() -> None:
    pid = _read_pid()
    if _pid_alive(pid):
        try:
            os.kill(pid, signal.SIGTERM)  # type: ignore[arg-type]
            for _ in range(30):
                if not _pid_alive(pid):
                    break
                time.sleep(0.1)
            if _pid_alive(pid):
                os.kill(pid, signal.SIGKILL)  # type: ignore[arg-type]
        except OSError:
            pass
    try:
        os.remove(_PIDFILE)
    except OSError:
        pass


def stop(cfg: Config | None = None) -> Status:
    require_root()
    with ProcessLock(_LOCKFILE):
        cfg = cfg or config_mod.load()
        # Stop the watchdog first so it doesn't try to revive tor.
        try:
            watchdog.stop_daemon()
        except Exception as exc:  # noqa: BLE001
            log.debug("watchdog stop: %s", exc)
        # Tear down in a finally-chain so a crash in any single step can NEVER
        # leave the machine with traffic blocked. Connectivity (the firewall) is
        # always restored first, even if stopping tor or restoring the identity
        # later raises.
        try:
            firewall.down(cfg)
        finally:
            try:
                _stop_tor()
            finally:
                if cfg.spoof_mac or cfg.spoof_hostname:
                    try:
                        spoof.restore()
                    except Exception as exc:  # noqa: BLE001
                        log.warning("identity restore failed: %s", exc)
        cfg.active = False
        config_mod.save(cfg)
        log.info("torchain stopped")
        return status(cfg)


def restart(cfg: Config | None = None, *, on_progress=None) -> Status:
    stop(cfg)
    return start(cfg, on_progress=on_progress)


def newnym() -> None:
    with ControlClient() as c:
        c.newnym()
    log.info("requested a new tor identity")


def status(cfg: Config | None = None) -> Status:
    cfg = cfg or config_mod.load()
    pid = _read_pid()
    tor_running = _pid_alive(pid)
    fw = firewall.is_active()
    boot = 0
    if tor_running:
        try:
            with ControlClient(timeout=2.0) as c:
                boot = c.bootstrap_progress()
        except TorError:
            boot = 0
    return Status(
        active=tor_running and fw,
        tor_running=tor_running,
        firewall_up=fw,
        bootstrap=boot,
        pid=pid,
        watchdog=watchdog.is_running(),
    )


def _panic() -> None:
    try:
        watchdog.stop_daemon()
    except Exception:  # noqa: BLE001
        pass
    if which("iptables"):
        for pol in ("OUTPUT", "INPUT", "FORWARD"):
            run_ok(["iptables", "-P", pol, "DROP"])
        run_ok(["iptables", "-A", "OUTPUT", "-o", "lo", "-j", "ACCEPT"])
        run_ok(["iptables", "-A", "INPUT", "-i", "lo", "-j", "ACCEPT"])
    if which("ip6tables"):
        for pol in ("OUTPUT", "INPUT", "FORWARD"):
            run_ok(["ip6tables", "-P", pol, "DROP"])
        run_ok(["ip6tables", "-A", "OUTPUT", "-o", "lo", "-j", "ACCEPT"])
        run_ok(["ip6tables", "-A", "INPUT", "-i", "lo", "-j", "ACCEPT"])
    _stop_tor()


def panic() -> None:
    """Emergency kill switch: drop ALL traffic except loopback, stop tor."""
    require_root()
    with ProcessLock(_LOCKFILE):
        _panic()
        log.warning("PANIC engaged: all non-loopback traffic blocked")


def panic_disarm() -> None:
    require_root()
    with ProcessLock(_LOCKFILE):
        if which("iptables"):
            for pol in ("OUTPUT", "INPUT", "FORWARD"):
                run_ok(["iptables", "-P", pol, "ACCEPT"])
            run_ok(["iptables", "-D", "OUTPUT", "-o", "lo", "-j", "ACCEPT"])
            run_ok(["iptables", "-D", "INPUT", "-i", "lo", "-j", "ACCEPT"])
        if which("ip6tables"):
            for pol in ("OUTPUT", "INPUT", "FORWARD"):
                run_ok(["ip6tables", "-P", pol, "ACCEPT"])
            run_ok(["ip6tables", "-D", "OUTPUT", "-o", "lo", "-j", "ACCEPT"])
            run_ok(["ip6tables", "-D", "INPUT", "-i", "lo", "-j", "ACCEPT"])
        log.info("panic disarmed")


def repair_internet() -> str:
    """Force-restore normal networking. Backs the GUI "Repair Internet" button
    and the ``torchain repair`` command. See :mod:`tc4.netfix`."""
    require_root()
    with ProcessLock(_LOCKFILE):
        from . import netfix
        return netfix.repair()


def pandora() -> str:
    """The 'pandora bomb': hard kill-switch + secure state wipe + memory scrub.

    For when you need to vanish *now*. It:
      1. stops the self-healing watchdog,
      2. engages the panic kill-switch (blocks all non-loopback traffic),
      3. securely wipes torchain's sensitive on-disk state (tor guard keys,
         spoof state, logs) with ``shred`` when available,
      4. scrubs volatile memory traces: drops the kernel page cache / dentries
         / inodes and cycles swap off+on so its contents are cleared.

    Networking can be brought back afterwards with ``torchain repair`` or
    ``torchain panic disarm``.
    """
    require_root()
    with ProcessLock(_LOCKFILE):
        report: list[str] = []
    
        try:
            watchdog.stop_daemon()
        except Exception:  # noqa: BLE001
            pass
    
        try:
            _panic()
            report.append("kill-switch engaged (all traffic blocked)")
        except Exception as exc:  # noqa: BLE001
            report.append(f"kill-switch error: {exc}")
    
        # Securely wipe sensitive state.
        targets = [
            os.path.join(DATA_DIR, "tor"),
            os.path.join(DATA_DIR, "spoof_state.json"),
            LOG_DIR,
        ]
        shred = which("shred")
        wiped = 0
        for path in targets:
            if not os.path.exists(path):
                continue
            if os.path.isfile(path):
                files = [path]
            else:
                files = [os.path.join(b, n) for b, _d, ns in os.walk(path) for n in ns]
            for fp in files:
                if shred:
                    run_ok([shred, "-u", "-z", "-n", "3", fp])
                try:
                    if os.path.exists(fp):
                        os.remove(fp)
                except OSError:
                    pass
            wiped += 1
        report.append(f"wiped {wiped} sensitive path(s)")
    
        # Scrub volatile memory traces.
        try:
            run_ok(["sync"])
            with open("/proc/sys/vm/drop_caches", "w", encoding="ascii") as fh:
                fh.write("3\n")
            report.append("dropped page cache / dentries / inodes")
        except OSError as exc:
            report.append(f"cache drop skipped: {exc}")
    
        if which("swapoff") and which("swapon"):
            if run_ok(["swapoff", "-a"], timeout=120):
                run_ok(["swapon", "-a"], timeout=120)
                report.append("swap scrubbed (off/on cycle)")
    
        msg = "; ".join(report)
        log.warning("PANDORA detonated: %s", msg)
        return msg
