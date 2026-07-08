"""Command-line interface: thin, fast, and forgiving.

Every command is wrapped so a TorChainError prints a clean message (+ hint)
and returns a meaningful exit code instead of a traceback.
"""
from __future__ import annotations

import argparse
import sys

from . import __version__
from . import config as config_mod
from . import engine
from .errors import TorChainError
from .log import get_logger, setup_logging

log = get_logger()

_C = {
    "blue": "\033[38;5;39m", "green": "\033[38;5;47m", "red": "\033[38;5;203m",
    "amber": "\033[38;5;214m", "dim": "\033[2m", "bold": "\033[1m", "r": "\033[0m",
}


def _c(text: str, color: str) -> str:
    if not sys.stdout.isatty():
        return text
    return f"{_C.get(color, '')}{text}{_C['r']}"


def _print_status(st: engine.Status) -> None:
    dot = _c("●", "green") if st.active else _c("●", "red")
    print(f"{dot} torchain: {_c('ACTIVE', 'green') if st.active else _c('INACTIVE', 'red')}")
    print(f"  tor process : {'running (pid %s)' % st.pid if st.tor_running else 'stopped'}")
    print(f"  bootstrap   : {st.bootstrap}%")
    print(f"  firewall    : {'engaged' if st.firewall_up else 'off'}")


def _progress_printer(pct: int) -> None:
    if sys.stderr.isatty():
        bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
        sys.stderr.write(f"\r  bootstrapping [{bar}] {pct:3d}%")
        sys.stderr.flush()
        if pct >= 100:
            sys.stderr.write("\n")


# -- command handlers --

def cmd_start(args) -> int:
    st = engine.start(on_progress=_progress_printer)
    _print_status(st)
    return 0


def cmd_stop(args) -> int:
    _print_status(engine.stop())
    return 0


def cmd_restart(args) -> int:
    _print_status(engine.restart(on_progress=_progress_printer))
    return 0


def cmd_status(args) -> int:
    _print_status(engine.status())
    return 0


def cmd_rotate(args) -> int:
    engine.newnym()
    print(_c("✓", "green"), "new identity requested")
    return 0


def cmd_panic(args) -> int:
    if args.action == "disarm":
        engine.panic_disarm()
        print(_c("✓", "green"), "panic disarmed")
    else:
        engine.panic()
        print(_c("⚠", "amber"), "PANIC engaged — all traffic blocked. Run 'torchain panic disarm' to restore.")
    return 0


def cmd_repair(args) -> int:
    msg = engine.repair_internet()
    print(_c("\u2713", "green"), "internet repair complete")
    for part in msg.split("; "):
        if part:
            print("  -", part)
    return 0


def cmd_pandora(args) -> int:
    if not getattr(args, "yes", False):
        sys.stderr.write(_c(
            "PANDORA will block ALL traffic, securely wipe torchain state, "
            "and scrub memory.\n", "amber"))
        try:
            ans = input("Type 'pandora' to confirm: ").strip().lower()
        except EOFError:
            ans = ""
        if ans != "pandora":
            print("aborted")
            return 1
    msg = engine.pandora()
    print(_c("\u26a0", "amber"), "PANDORA detonated")
    for part in msg.split("; "):
        if part:
            print("  -", part)
    print("Run 'torchain repair' or 'torchain panic disarm' to restore networking.")
    return 0


def cmd_leaktest(args) -> int:
    from . import leaktest
    icons = {"pass": _c("PASS", "green"), "fail": _c("FAIL", "red"),
             "warn": _c("WARN", "amber"), "info": _c("INFO", "blue")}
    failed = 0
    for r in leaktest.run_all(quick=args.quick):
        if r.status == "fail":
            failed += 1
        print(f"  [{icons.get(r.status, r.status)}] {r.name}: {r.detail}")
    return 1 if failed else 0


def cmd_config(args) -> int:
    cfg = config_mod.load()
    if args.set:
        key, eq, value = args.set.partition("=")
        if not eq:
            raise TorChainError(
                f"invalid config format '{args.set}'",
                hint="Expected KEY=VALUE, e.g. 'torchain config --set exit_country=US'",
            )
        key = key.strip()
        _WRITABLE_KEYS = {
            "exit_country", "block_ipv6", "use_bridges", "bridge_type",
            "auto_rotate_minutes", "spoof_mac", "spoof_hostname",
            "watchdog_enabled", "watchdog_interval", "start_on_boot",
            "trans_port", "dns_port", "socks_port", "control_port",
        }
        if key not in _WRITABLE_KEYS:
            raise TorChainError(f"unknown or read-only config key: {key}")
        cur = getattr(cfg, key)
        if isinstance(cur, bool):
            newv = value.strip().lower() in ("1", "true", "yes", "on")
        elif isinstance(cur, int):
            newv = int(value)
        else:
            newv = value.strip()
        setattr(cfg, key, newv)
        config_mod.save(cfg)
        print(_c("✓", "green"), f"{key} = {newv}")
    else:
        from dataclasses import asdict
        for k, v in asdict(cfg).items():
            print(f"  {k:20s} {v}")
    return 0


def cmd_doctor(args) -> int:
    from .sysutil import which, is_root
    print(_c("torchain doctor", "bold"))
    checks = [
        ("root privileges", is_root()),
        ("tor", which("tor") is not None),
        ("iptables", which("iptables") is not None),
        ("ip (iproute2)", which("ip") is not None),
        ("python3 tkinter (GUI)", _has_tk()),
    ]
    from . import platform as plat
    print(f"  {_c('environment', 'blue')}: {plat.describe()}")
    ok = True
    for name, passed in checks:
        mark = _c("✓", "green") if passed else _c("✗", "red")
        print(f"  {mark} {name}")
        ok = ok and (passed or name == "python3 tkinter (GUI)")
    print(_c("all systems go" if ok else "issues detected", "green" if ok else "amber"))
    return 0 if ok else 1


def _has_tk() -> bool:
    try:
        import tkinter  # noqa: F401
        return True
    except Exception:
        return False


def cmd_bridge(args) -> int:
    from . import bridges
    if args.bridge_cmd == "list":
        cfg = config_mod.load()
        print(f"  type: {cfg.bridge_type}   enabled: {cfg.use_bridges}")
        if not cfg.custom_bridges:
            print("  (no custom bridges)")
        for i, ln in enumerate(cfg.custom_bridges):
            print(f"  [{i}] {ln}")
    elif args.bridge_cmd == "add":
        bridges.add(args.line)
        print(_c("✓", "green"), "bridge added")
    elif args.bridge_cmd == "remove":
        try:
            idx = int(args.line)
            bridges.remove(idx)
        except ValueError:
            bridges.remove(args.line)
        print(_c("✓", "green"), "bridge removed")
    elif args.bridge_cmd == "clear":
        bridges.clear()
        print(_c("✓", "green"), "all custom bridges cleared")
    elif args.bridge_cmd == "type":
        bridges.set_type(args.line)
        print(_c("✓", "green"), f"bridge type set to {args.line}")
    elif args.bridge_cmd == "fetch":
        count = len(bridges.append_fetched(
            transport=args.transport, url=args.url).custom_bridges)
        print(_c("✓", "green"), f"bridges fetched ({count} in config)")
    elif args.bridge_cmd == "test":
        results = bridges.test_bridges(timeout=args.timeout)
        alive = sum(1 for _, ok, _ in results if ok)
        print(f"  tested {len(results)} bridge(s) — {alive} reachable, {len(results) - alive} dead")
        for line, ok, info in results:
            icon = _c("✓", "green") if ok else _c("✗", "red")
            print(f"  {icon} {info}")
    elif args.bridge_cmd == "enable":
        bridges.enable(True)
        print(_c("✓", "green"), "bridges enabled")
    elif args.bridge_cmd == "disable":
        bridges.enable(False)
        print(_c("✓", "green"), "bridges disabled")
    return 0


def cmd_watchdog(args) -> int:
    from . import watchdog
    if args.foreground:
        return watchdog.run_foreground()
    if args.watchdog_cmd == "stop":
        watchdog.stop_daemon()
        print(_c("✓", "green"), "watchdog stopped")
    elif args.watchdog_cmd == "status":
        print("  watchdog:", "running" if watchdog.is_running() else "stopped")
    else:  # start
        ok = watchdog.start_daemon()
        print(_c("✓" if ok else "✗", "green" if ok else "red"),
              "watchdog started" if ok else "watchdog failed to start")
        return 0 if ok else 1
    return 0


def cmd_boot(args) -> int:
    from . import boot
    if args.boot_cmd == "enable":
        method = boot.enable()
        print(_c("✓", "green"), f"start-on-boot enabled ({method})")
    elif args.boot_cmd == "disable":
        boot.disable()
        print(_c("✓", "green"), "start-on-boot disabled")
    else:  # status
        print("  start on boot:", "enabled" if boot.status() else "disabled")
    return 0


def cmd_migrate(args) -> int:
    from . import migrate
    import os
    src = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if args.scan:
        found = migrate.scan(self_dir=src)
        if found:
            print(_c("detected older torchain artifacts:", "amber"))
            for f in found:
                print("  -", f)
        else:
            print(_c("✓", "green"), "no older torchain installation found")
        return 0
    report = migrate.migrate(src_dir=src, do_install=not args.no_install)
    for line in report:
        print("  " + line)
    print(_c("✓", "green"), "migration complete")
    return 0


def cmd_gui(args) -> int:
    try:
        from .gui import launch
    except Exception as exc:  # noqa: BLE001
        raise TorChainError(f"GUI unavailable: {exc}",
                            hint="Install python3-tk (Tkinter).")
    return launch()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="torchain",
        description="torchain — fast, system-wide Tor anonymizer",
        epilog="Created by ctx0an with Claude Opus 4.8 · https://github.com/ctx0an/torchain",
    )
    p.add_argument("-v", "--verbose", action="store_true", help="verbose logging")
    p.add_argument("-V", "--version", action="version",
                   version=f"torchain {__version__}  (by ctx0an · Claude Opus 4.8)")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("start", help="route all traffic through tor").set_defaults(fn=cmd_start)
    sub.add_parser("stop", help="restore normal networking").set_defaults(fn=cmd_stop)
    sub.add_parser("restart", help="stop then start").set_defaults(fn=cmd_restart)
    sub.add_parser("status", help="show current state").set_defaults(fn=cmd_status)
    sub.add_parser("rotate", help="request a new tor identity").set_defaults(fn=cmd_rotate)

    pp = sub.add_parser("panic", help="emergency kill switch")
    pp.add_argument("action", nargs="?", choices=["arm", "disarm"], default="arm")
    pp.set_defaults(fn=cmd_panic)

    lt = sub.add_parser("leaktest", help="verify there are no leaks")
    lt.add_argument("--quick", action="store_true", help="run only fast checks")
    lt.set_defaults(fn=cmd_leaktest)

    cf = sub.add_parser("config", help="view or change settings")
    cf.add_argument("--set", metavar="KEY=VALUE", help="set a config value")
    cf.set_defaults(fn=cmd_config)

    sub.add_parser("doctor", help="run a pre-flight system check").set_defaults(fn=cmd_doctor)
    sub.add_parser("gui", help="launch the desktop dashboard").set_defaults(fn=cmd_gui)
    sub.add_parser("repair", help="force-restore normal networking (fix internet)").set_defaults(fn=cmd_repair)

    pd = sub.add_parser("pandora", help="kill-switch + wipe torchain state + scrub memory")
    pd.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    pd.set_defaults(fn=cmd_pandora)

    br = sub.add_parser("bridge", help="manage bridges / pluggable transports")
    brs = br.add_subparsers(dest="bridge_cmd", required=True)
    brs.add_parser("list", help="list configured bridges")
    ba = brs.add_parser("add", help="add a custom bridge line")
    ba.add_argument("line", help="a full bridge line")
    brm = brs.add_parser("remove", help="remove a bridge by index or exact line")
    brm.add_argument("line", help="index or exact bridge line")
    brs.add_parser("clear", help="remove all custom bridges")
    bt = brs.add_parser("type", help="set transport type")
    bt.add_argument("line", metavar="TYPE", help="obfs4|snowflake|meek_lite|webtunnel|custom")
    bf = brs.add_parser("fetch", help="fetch obfs4 bridges from the Tor Project")
    bf.add_argument("--transport", "-t", default="obfs4",
                    help="transport type (default: obfs4)")
    bf.add_argument("--url", "-u", default=None,
                    help="custom bridge source URL (default: Tor Project moat API)")
    btst = brs.add_parser("test", help="test which bridges are reachable")
    btst.add_argument("--timeout", "-t", type=float, default=5.0,
                      help="TCP connect timeout in seconds (default: 5)")
    brs.add_parser("enable", help="enable bridges")
    brs.add_parser("disable", help="disable bridges")
    br.set_defaults(fn=cmd_bridge)

    wd = sub.add_parser("watchdog", help="self-healing watchdog daemon")
    wd.add_argument("watchdog_cmd", nargs="?", choices=["start", "stop", "status"], default="start")
    wd.add_argument("--foreground", action="store_true", help="run in foreground (for systemd)")
    wd.set_defaults(fn=cmd_watchdog)

    bo = sub.add_parser("boot", help="manage start-on-boot")
    bo.add_argument("boot_cmd", nargs="?", choices=["enable", "disable", "status"], default="status")
    bo.set_defaults(fn=cmd_boot)

    mg = sub.add_parser("migrate", help="remove older torchain installs and install this one")
    mg.add_argument("--scan", action="store_true", help="only report what would be removed")
    mg.add_argument("--no-install", action="store_true", help="purge old versions without installing")
    mg.set_defaults(fn=cmd_migrate)
    return p


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    args = parser.parse_args(argv)
    setup_logging(verbose=getattr(args, "verbose", False))
    try:
        return args.fn(args)
    except TorChainError as exc:
        print(_c("✗ ", "red") + exc.render(), file=sys.stderr)
        return exc.exit_code
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130
