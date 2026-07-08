"""The engine: orchestrates tor + firewall + system proxy + spoofing on Windows.

Enforcement model (Windows has no transparent proxy):
  1. launch a dedicated tor.exe exposing local SOCKS + DNS ports,
  2. point the system (WinINET) proxy at tor's SOCKS port, and
  3. flip Windows Defender Firewall to block-all-outbound except tor.exe
     (a fail-closed kill-switch).

Fail-closed: if anything goes wrong mid-start we roll everything back. On stop
we ALWAYS restore connectivity first (firewall + proxy) so a later failure can
never strand the machine offline. Status is cheap so GUI polling stays light.
"""
from __future__ import annotations

import ctypes
import os
import time
from dataclasses import dataclass

from . import CONFIG_DIR, DATA_DIR, LOG_DIR, RUN_DIR, TORRC_FILE
from . import config as config_mod
from . import firewall, platform as plat, proxy, spoof, torrc, watchdog
from .config import Config
from .errors import DependencyError, TorError
from .log import get_logger
from .sysutil import pid_alive, require_root, run, run_ok, which
from .torctl import ControlClient, wait_bootstrap

log = get_logger()

_PIDFILE = os.path.join(RUN_DIR, "tor.pid")

# Common locations where the Tor Browser keeps tor.exe.
_TOR_SUBPATH = os.path.join("Browser", "TorBrowser", "Tor", "tor.exe")


@dataclass
class Status:
    active: bool
    tor_running: bool
    firewall_up: bool
    bootstrap: int
    pid: int | None
    watchdog: bool = False
    exit_ip: str | None = None


def _tor_browser_roots() -> list[str]:
    roots = []
    for env in ("LOCALAPPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)", "USERPROFILE"):
        base = os.environ.get(env)
        if not base:
            continue
        roots += [
            os.path.join(base, "Tor Browser"),
            os.path.join(base, "Programs", "Tor Browser"),
            os.path.join(base, "Desktop", "Tor Browser"),
        ]
    return roots


def _bundled_tor_candidates() -> list[str]:
    """tor.exe locations used by the bundled-zip extraction fallback.

    setup.bat extracts the bundled Tor.zip into the torchain app dir, so we
    look there too. This lets torchain work with no package manager at all.
    """
    from . import SHARE_DIR
    cands = []
    for base in (SHARE_DIR, DATA_DIR):
        cands += [
            os.path.join(base, "tor", "tor.exe"),
            os.path.join(base, "tor", "Tor", "tor.exe"),
        ]
    return cands


def find_tor() -> str | None:
    """Locate tor.exe.

    Resolution order: explicit override -> PATH -> Tor Browser
    -> torchain-bundled tor (from Tor.zip). This means torchain
    keeps working even when no package manager is available.
    """
    override = os.environ.get("TORCHAIN_TOR")
    if override and os.path.exists(override):
        return override
    onpath = which("tor")
    if onpath:
        return onpath
    for root in _tor_browser_roots():
        cand = os.path.join(root, _TOR_SUBPATH)
        if os.path.exists(cand):
            return cand
    for cand in _bundled_tor_candidates():
        if os.path.exists(cand):
            return cand
    return None


def _tor_dir() -> str | None:
    exe = find_tor()
    return os.path.dirname(exe) if exe else None


def _ensure_dirs() -> None:
    tor_data = os.path.join(DATA_DIR, "tor")
    for d in (CONFIG_DIR, DATA_DIR, LOG_DIR, RUN_DIR, tor_data):
        os.makedirs(d, exist_ok=True)


def _read_pid() -> int | None:
    try:
        with open(_PIDFILE, encoding="utf-8") as fh:
            return int(fh.read().strip())
    except (OSError, ValueError):
        return None


def _tor_diagnostics(text: str | None) -> str | None:
    if not text:
        return None
    keep = [ln.strip() for ln in text.splitlines()
            if "[err]" in ln or "[warn]" in ln]
    msg = " | ".join(keep[-4:]) if keep else text.strip()
    return (msg[:600] or None)


def _start_tor(cfg: Config) -> int:
    tor_exe = find_tor()
    if not tor_exe:
        raise DependencyError(
            "tor.exe was not found",
            hint="Run windows\\setup.bat to extract the bundled Tor, "
                 "or set TORCHAIN_TOR to the full path of tor.exe.")
    tor_dir = os.path.dirname(tor_exe)
    torrc.write(cfg, TORRC_FILE, tor_dir=tor_dir)

    # Validate first so we surface tor's precise reason for refusing to start.
    verify = run([tor_exe, "--verify-config", "-f", TORRC_FILE],
                 timeout=30, check=False)
    if verify.returncode != 0:
        raise TorError("tor configuration was rejected",
                       hint=_tor_diagnostics(verify.stdout or verify.stderr))

    # Launch tor.exe detached (no RunAsDaemon on Windows). Track the PID.
    import subprocess
    from .sysutil import NO_WINDOW
    DETACHED = 0x00000008
    proc = subprocess.Popen(
        [tor_exe, "-f", TORRC_FILE],
        creationflags=DETACHED | NO_WINDOW,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
    )
    with open(_PIDFILE, "w", encoding="utf-8") as fh:
        fh.write(str(proc.pid))
    for _ in range(20):
        if pid_alive(proc.pid):
            return proc.pid
        time.sleep(0.1)
    raise TorError("tor started but no live PID was found")


def start(cfg: Config | None = None, *, on_progress=None, supervise: bool = True) -> Status:
    require_root()
    cfg = cfg or config_mod.load()
    _ensure_dirs()
    log.debug("environment: %s", plat.describe())

    started_tor = False
    proxy_set = False
    try:
        if cfg.spoof_mac:
            spoof.spoof_mac()
        if cfg.spoof_hostname:
            spoof.spoof_hostname()
        pid = _read_pid()
        if not pid_alive(pid):
            pid = _start_tor(cfg)
            started_tor = True

        # Engage firewall early to prevent leaks during bootstrapping
        firewall.up(cfg, find_tor())

        ok = wait_bootstrap(timeout=90, on_progress=on_progress, check_pid=pid)
        if not ok:
            if not pid_alive(pid):
                raise TorError("tor process terminated unexpectedly during bootstrapping",
                               hint="Check for port conflicts (is another Tor instance running?) or logs in tor.log.")
            raise TorError("tor did not finish bootstrapping in time",
                           hint="Check your connection or enable bridges.")
        proxy.enable(cfg.socks_port)
        proxy_set = True
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
            try:
                if proxy_set:
                    proxy.disable()
            finally:
                if started_tor:
                    _stop_tor(cfg)
                if cfg.spoof_mac or cfg.spoof_hostname:
                    spoof.restore()
        raise


def _stop_tor(cfg: Config | None = None) -> None:
    # 1. Stop process by tracked PID
    pid = _read_pid()
    if pid_alive(pid):
        run_ok(["taskkill", "/PID", str(pid), "/T", "/F"])
        for _ in range(30):
            if not pid_alive(pid):
                break
            time.sleep(0.1)

    # 2. Stop process by querying the control port (for untracked orphaned tor processes)
    cfg = cfg or config_mod.load()
    try:
        with ControlClient(port=cfg.control_port) as c:
            pid_str = c.get_info("process/pid").strip()
            if pid_str.isdigit():
                pid_val = int(pid_str)
                if pid_alive(pid_val):
                    run_ok(["taskkill", "/PID", str(pid_val), "/T", "/F"])
                    for _ in range(30):
                        if not pid_alive(pid_val):
                            break
                        time.sleep(0.1)
    except Exception:
        pass

    try:
        os.remove(_PIDFILE)
    except OSError:
        pass


def stop(cfg: Config | None = None) -> Status:
    require_root()
    cfg = cfg or config_mod.load()
    try:
        watchdog.stop_daemon()
    except Exception as exc:  # noqa: BLE001
        log.debug("watchdog stop: %s", exc)
    # Restore connectivity FIRST (firewall, then proxy) so any later failure
    # can never leave the machine offline.
    try:
        firewall.down(cfg)
    finally:
        try:
            proxy.disable()
        finally:
            try:
                _stop_tor(cfg)
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
    tor_running = pid_alive(pid)
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


def panic() -> None:
    """Emergency kill switch: block ALL outbound (even tor), stop tor."""
    require_root()
    try:
        watchdog.stop_daemon()
    except Exception:  # noqa: BLE001
        pass
    firewall.block_all()
    _stop_tor()
    log.warning("PANIC engaged: all outbound traffic blocked")


def panic_disarm() -> None:
    require_root()
    firewall.allow_all()
    try:
        proxy.disable()
    except Exception:  # noqa: BLE001
        pass
    log.info("panic disarmed")


def repair_internet(deep: bool = False) -> str:
    """Force-restore normal networking (GUI "Repair Internet" / ``repair``).

    deep=False does only safe, reversible, connectivity-restoring steps.
    deep=True additionally resets the Winsock/TCP-IP stack (needs a reboot).
    """
    require_root()
    from . import netfix
    return netfix.repair(deep=deep)


def _scrub_memory(report: list[str]) -> None:
    """Best-effort volatile-memory scrub on Windows.

    Purges the system standby (cached) page list and the file-system cache via
    NtSetSystemInformation, trims this process's working set, then flushes DNS
    and ARP caches. Standby-list purging needs SeProfileSingleProcessPrivilege
    (Administrator); each step is guarded so partial success is fine.
    """
    try:
        ntdll = ctypes.windll.ntdll
        # Enable the privileges required to purge the standby list.
        _enable_privilege("SeProfileSingleProcessPrivilege")
        _enable_privilege("SeIncreaseQuotaPrivilege")
        SystemMemoryListInformation = 0x50
        MemoryPurgeStandbyList = ctypes.c_int(4)
        rc = ntdll.NtSetSystemInformation(
            SystemMemoryListInformation,
            ctypes.byref(MemoryPurgeStandbyList),
            ctypes.sizeof(MemoryPurgeStandbyList),
        )
        report.append("purged standby memory list"
                      if rc == 0 else f"standby purge rc=0x{rc & 0xffffffff:x}")
    except Exception as exc:  # noqa: BLE001
        report.append(f"standby purge skipped: {exc}")

    try:
        # Flush the system file cache.
        ctypes.windll.kernel32.SetSystemFileCacheSize(-1, -1, 0)
        report.append("flushed system file cache")
    except Exception:  # noqa: BLE001
        pass

    try:
        k32 = ctypes.windll.kernel32
        k32.SetProcessWorkingSetSizeEx(k32.GetCurrentProcess(), -1, -1, 0)
    except Exception:  # noqa: BLE001
        pass

    run_ok(["ipconfig", "/flushdns"])
    run_ok(["arp", "-d", "*"])
    report.append("flushed DNS + ARP caches")


def _enable_privilege(name: str) -> None:
    import ctypes.wintypes as w
    TOKEN_ADJUST_PRIVILEGES = 0x20
    TOKEN_QUERY = 0x8
    SE_PRIVILEGE_ENABLED = 0x2

    class LUID(ctypes.Structure):
        _fields_ = [("LowPart", w.DWORD), ("HighPart", ctypes.c_long)]

    class LUID_AND_ATTRIBUTES(ctypes.Structure):
        _fields_ = [("Luid", LUID), ("Attributes", w.DWORD)]

    class TOKEN_PRIVILEGES(ctypes.Structure):
        _fields_ = [("PrivilegeCount", w.DWORD), ("Privileges", LUID_AND_ATTRIBUTES * 1)]

    adv = ctypes.windll.advapi32
    k32 = ctypes.windll.kernel32
    token = w.HANDLE()
    if not adv.OpenProcessToken(k32.GetCurrentProcess(),
                                TOKEN_ADJUST_PRIVILEGES | TOKEN_QUERY,
                                ctypes.byref(token)):
        return
    luid = LUID()
    if not adv.LookupPrivilegeValueW(None, name, ctypes.byref(luid)):
        return
    tp = TOKEN_PRIVILEGES()
    tp.PrivilegeCount = 1
    tp.Privileges[0].Luid = luid
    tp.Privileges[0].Attributes = SE_PRIVILEGE_ENABLED
    adv.AdjustTokenPrivileges(token, False, ctypes.byref(tp), 0, None, None)


def pandora() -> str:
    """The 'pandora bomb': hard kill-switch + secure state wipe + memory scrub.

    For when you need to vanish *now*. It:
      1. stops the watchdog,
      2. engages the panic kill-switch (blocks all outbound traffic),
      3. securely overwrites + deletes torchain's sensitive on-disk state
         (tor guard keys, spoof/proxy state, logs), and
      4. scrubs volatile memory: purges the standby page list + file cache and
         flushes DNS/ARP caches.

    Networking can be restored afterwards with ``torchain repair`` (or
    ``torchain panic disarm``).
    """
    require_root()
    report: list[str] = []

    try:
        watchdog.stop_daemon()
    except Exception:  # noqa: BLE001
        pass

    try:
        panic()
        report.append("kill-switch engaged (all traffic blocked)")
    except Exception as exc:  # noqa: BLE001
        report.append(f"kill-switch error: {exc}")

    # Securely wipe sensitive state (3-pass overwrite then delete).
    targets = [
        os.path.join(DATA_DIR, "tor"),
        os.path.join(DATA_DIR, "spoof_state.json"),
        os.path.join(DATA_DIR, "proxy_state.json"),
        LOG_DIR,
    ]
    wiped = 0
    for path in targets:
        if not os.path.exists(path):
            continue
        files = ([path] if os.path.isfile(path)
                 else [os.path.join(b, n) for b, _d, ns in os.walk(path) for n in ns])
        for fp in files:
            _secure_delete(fp)
        wiped += 1
    report.append(f"wiped {wiped} sensitive path(s)")

    _scrub_memory(report)

    msg = "; ".join(report)
    log.warning("PANDORA detonated: %s", msg)
    return msg


def _secure_delete(path: str) -> None:
    try:
        if os.path.isfile(path):
            size = os.path.getsize(path)
            with open(path, "r+b", buffering=0) as fh:
                for _ in range(3):
                    fh.seek(0)
                    fh.write(os.urandom(size))
                    fh.flush()
                    os.fsync(fh.fileno())
        os.remove(path)
    except OSError:
        try:
            os.remove(path)
        except OSError:
            pass
