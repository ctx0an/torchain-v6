"""Advanced migration manager.

Goal (user request): "if any other version of torchain is found, remove it and
install this one in its place." This module scans the system for prior
torchain/TorChain installs (v3 'trc', older v4/v5 layouts, stray binaries,
systemd units, configs) and cleanly removes them, then installs the current
package into the canonical location and links it onto PATH.

Everything is reversible-by-design where it matters: logs are preserved by
default, and a one-line report of every action is returned to the caller.
"""
from __future__ import annotations

import os
import shutil

from . import BIN_LINK, BIN_LINK_ALT, SHARE_DIR, __version__
from .log import get_logger
from .sysutil import run, run_ok, which

log = get_logger()

# Known legacy / alternate install artifacts from older TorChain versions.
_LEGACY_BINARIES = [
    "/usr/local/bin/trc", "/usr/bin/trc",
    "/usr/local/bin/tc",  # v3 short alias (only if it points at torchain)
    "/usr/local/bin/torchain", "/usr/bin/torchain",
    "/usr/local/sbin/torchain",
]
_LEGACY_DIRS = [
    "/usr/share/torchain", "/opt/torchain", "/usr/local/share/torchain",
    "/usr/local/lib/torchain",
]
_LEGACY_CONFIGS = [
    "/etc/tor/torchain.conf", "/etc/tor/profiles",
    "/etc/tor/torchain_orig_hostname",
]
_LEGACY_SERVICES = [
    "torchain.service", "torchain-boot.service", "torchain-watchdog.service",
    "trc.service",
]
_SERVICE_DIR = "/etc/systemd/system"


def _is_torchain_alias(path: str) -> bool:
    """Only treat /usr/local/bin/tc as ours if it resolves to a torchain file."""
    try:
        target = os.path.realpath(path)
        return "torchain" in target.lower()
    except OSError:
        return False


def scan(self_dir: str | None = None) -> list:
    """Return a list of detected legacy artifacts (paths / unit names)."""
    found = []
    self_dir = os.path.realpath(self_dir) if self_dir else None
    for b in _LEGACY_BINARIES:
        if os.path.lexists(b):
            if b.endswith("/tc") and not _is_torchain_alias(b):
                continue
            found.append(b)
    for d in _LEGACY_DIRS:
        if os.path.isdir(d) and os.path.realpath(d) != self_dir:
            found.append(d)
    for c in _LEGACY_CONFIGS:
        if os.path.lexists(c):
            found.append(c)
    if which("systemctl"):
        for svc in _LEGACY_SERVICES:
            if os.path.lexists(os.path.join(_SERVICE_DIR, svc)):
                found.append(f"systemd:{svc}")
    return found


def purge(self_dir: str | None = None, keep_logs: bool = True) -> list:
    """Remove detected legacy artifacts. Returns a report of actions taken."""
    report = []
    self_dir = os.path.realpath(self_dir) if self_dir else None
    # Stop and disable any old services first so files aren't in use.
    if which("systemctl"):
        for svc in _LEGACY_SERVICES:
            unit = os.path.join(_SERVICE_DIR, svc)
            if os.path.lexists(unit):
                run_ok(["systemctl", "stop", svc])
                run_ok(["systemctl", "disable", svc])
                try:
                    os.remove(unit)
                    report.append(f"removed service {svc}")
                except OSError as exc:
                    report.append(f"could not remove service {svc}: {exc}")
        run_ok(["systemctl", "daemon-reload"])
    # Try to gracefully stop a legacy CLI if present.
    for legacy in ("trc", "torchain"):
        p = which(legacy)
        if p and os.path.realpath(p) != BIN_LINK:
            run_ok([p, "stop"])
    # Binaries / symlinks.
    for b in _LEGACY_BINARIES:
        if os.path.lexists(b):
            if b.endswith("/tc") and not _is_torchain_alias(b):
                continue
            if (b == BIN_LINK or b == BIN_LINK_ALT) and self_dir:
                continue  # we'll relink these ourselves
            try:
                os.remove(b)
                report.append(f"removed binary {b}")
            except OSError as exc:
                report.append(f"could not remove {b}: {exc}")
    # Directories.
    for d in _LEGACY_DIRS:
        if os.path.isdir(d) and os.path.realpath(d) != self_dir:
            try:
                shutil.rmtree(d)
                report.append(f"removed directory {d}")
            except OSError as exc:
                report.append(f"could not remove {d}: {exc}")
    # Configs.
    for c in _LEGACY_CONFIGS:
        if os.path.lexists(c):
            try:
                if os.path.isdir(c):
                    shutil.rmtree(c)
                else:
                    os.remove(c)
                report.append(f"removed config {c}")
            except OSError as exc:
                report.append(f"could not remove {c}: {exc}")
    if not keep_logs and os.path.isdir("/var/log/torchain"):
        shutil.rmtree("/var/log/torchain", ignore_errors=True)
        report.append("removed logs")
    return report


def install_self(src_dir: str) -> list:
    """Copy the current package into SHARE_DIR and link it onto PATH."""
    report = []
    src_dir = os.path.realpath(src_dir)
    tc4_src = os.path.join(src_dir, "tc4")
    launcher_src = os.path.join(src_dir, "torchain")
    if not os.path.isdir(tc4_src) or not os.path.exists(launcher_src):
        raise FileNotFoundError(f"source package not found in {src_dir}")
    os.makedirs(SHARE_DIR, exist_ok=True)
    # Replace the package directory atomically-ish.
    dst_tc4 = os.path.join(SHARE_DIR, "tc4")
    if os.path.isdir(dst_tc4):
        shutil.rmtree(dst_tc4, ignore_errors=True)
    shutil.copytree(tc4_src, dst_tc4)
    shutil.copy2(launcher_src, os.path.join(SHARE_DIR, "torchain"))
    os.chmod(os.path.join(SHARE_DIR, "torchain"), 0o755)
    report.append(f"installed package to {SHARE_DIR}")
    # Link onto PATH.
    try:
        if os.path.lexists(BIN_LINK):
            os.remove(BIN_LINK)
        os.symlink(os.path.join(SHARE_DIR, "torchain"), BIN_LINK)
        report.append(f"linked {BIN_LINK}")
    except OSError as exc:
        report.append(f"could not link {BIN_LINK}: {exc}")
    # Fallback symlink in /usr/bin (always on sudo's secure_path).
    try:
        if os.path.lexists(BIN_LINK_ALT):
            os.remove(BIN_LINK_ALT)
        os.symlink(os.path.join(SHARE_DIR, "torchain"), BIN_LINK_ALT)
        report.append(f"linked {BIN_LINK_ALT}")
    except OSError:
        pass
    # Write the icon + desktop entry (best-effort).
    try:
        from . import icon
        os.makedirs(SHARE_DIR, exist_ok=True)
        icon.write_png(os.path.join(SHARE_DIR, "torchain.png"), size=128)
        report.append("generated app icon")
    except Exception as exc:  # noqa: BLE001
        report.append(f"icon generation skipped: {exc}")
    report.append(f"now at version {__version__}")
    return report


def migrate(src_dir: str, do_install: bool = True) -> list:
    """Full flow: scan -> purge legacy -> install self in its place."""
    report = []
    detected = scan(self_dir=src_dir)
    if detected:
        report.append("detected older torchain artifacts: " + ", ".join(detected))
        report.extend(purge(self_dir=src_dir))
    else:
        report.append("no older torchain installation found")
    if do_install:
        report.extend(install_self(src_dir))
    return report
