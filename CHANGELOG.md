# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/), and the project adheres to
[Semantic Versioning](https://semver.org/).

## [5.0.1] - 2026-06-23

### Added
- **Safe uninstaller (`uninstall.bat`).** A self-elevating script that cleanly removes Torchain, terminating active processes, deleting boot tasks, restoring system firewall and proxy settings, removing environment variables and PATH additions, and deleting all shortcuts and installed files.
- **Automatic system PATH registration.** The setup script now automatically appends the Torchain app folder to the machine's environment PATH using a robust PowerShell call that bypasses the 1024-character registry limit.
- **Start Menu & Desktop shortcuts.** The setup script now creates a "Torchain" Start Menu folder containing launch and internet recovery shortcuts, plus a Desktop shortcut, making Torchain searchable via Windows Search.

### Changed
- **Windows setup completely rewritten as `setup.bat`.** No winget, Chocolatey,
  or any package manager required. The `.bat` file self-elevates via UAC and can
  be run by double-clicking — no PowerShell execution policy changes needed.
- **Full portable Python** (with Tcl/Tk for GUI support) is downloaded directly
  from python.org and installed quietly into the app folder. Replaces the old
  embeddable Python build that lacked tkinter.
- **tor.exe is extracted from the bundled `Tor.zip`** already in the repo
  instead of downloading from the Tor Project or requiring winget.
- All references to winget/Chocolatey removed from code, CLI doctor check,
  error hints, and documentation.

### Fixed
- **Pluggable transport discovery** (`torrc.py`): `_plugin_path()` now searches
  the `PluggableTransports/` subdirectory used by the Tor Expert Bundle and
  bundled Tor.zip. Previously, bridge transports like `lyrebird.exe` (obfs4)
  would not be found, causing silent failures for users on censored networks.


## [5.0.0] - 2026-06-22

### Added
- **Fully automatic privilege elevation.** Every privileged command — including
  the desktop GUI — transparently elevates via sudo (or pkexec). The GUI now
  forwards `DISPLAY`/`XAUTHORITY` and grants the X cookie, fixing the
  `Invalid MIT-MAGIC-COOKIE-1` failure when launching as root.
- **Self-healing watchdog daemon** (`watchdog.py`): robust double-fork
  daemonization with a PID file, auto-repairs tor/firewall if they drop, and
  enforces automatic identity rotation. Available as a systemd service too.
- **Run-on-boot** (`boot.py`): systemd `torchain.service` (after network),
  with an rc.local/cron `@reboot` fallback for non-systemd systems.
- **Rich bridge management** (`bridges.py`): obfs4, snowflake, meek_lite and
  webtunnel transports plus add/remove/list/clear of custom bridge lines, with
  validation. New `torchain bridge ...` CLI and a Bridges view in the GUI.
- **Advanced migration manager** (`migrate.py`): detects ANY older torchain
  install (v3 `trc`, old layouts, stray binaries, services, configs), removes
  it, and installs v5 in its place. Wired into `setup.sh`.
- **VM + bare-metal awareness** (`platform.py`): detects VMware/VirtualBox/
  KVM/Xen/Hyper-V/containers and the init system; surfaced in `doctor` and the
  Advanced view. MAC spoofing now verifies the change and rolls back safely
  under hypervisor port security so a VM never loses its link.
- **Unique generated app icon** (`icon.py`): an "onion + chain link" mark in
  the Kali palette, rendered to PNG in pure Python (no binary assets) and used
  for the window icon and the installed `.desktop` entry.
- New settings: `watchdog_enabled`, `watchdog_interval`, `start_on_boot`, and
  expanded `bridge_type` options.

### Changed
- `setup.sh` and the launcher now auto-elevate, so you no longer need to type
  `sudo` yourself.
- torrc generation supports multiple pluggable-transport binaries.

## [4.0.0] - 2026-06-22

### Added
- Complete ground-up rewrite as a modular Python package (`tc4`) behind a thin
  bash launcher.
- Enterprise-grade, Kali-Linux-themed desktop dashboard with sidebar
  navigation, status pills, stat tiles, and scrollable circuit/leak/log views.
- Typed exception hierarchy (`errors.py`) with actionable hints surfaced in both
  CLI and GUI.
- Fail-closed engine: any failure during `start` rolls back firewall + tor.
- Fast Tor bootstrap via persistent guard state, `AvoidDiskWrites`, tuned
  circuit timeouts, and live control-port progress polling.
- Minimal dependency-free Tor control-port client (cookie authentication).
- Transparent-proxy firewall using dedicated iptables chains for surgical,
  reversible teardown.
- Reversible MAC and hostname spoofing.
- Leak-test suite (firewall, IPv6, DNS, Tor exit IP).
- Emergency `panic` kill switch and `panic disarm`.
- `doctor` pre-flight system check.
- Atomic JSON configuration with validation.
- Rotating file + colored console logging.

### Changed
- Window title is now simply `torchain`.
- Branding reduced to the single name `torchain` throughout.

### Performance
- GUI is fully event-driven: no animation loops; widgets update only on change.
- Idle footprint reduced to roughly ~15 MB RAM and near-zero idle CPU.

## [3.0.3] - 2026-06-21
- Final v3 maintenance release (rebranded to TorChain, scrollbars, CPU/animation
  optimizations, X11/elevation fixes). Superseded by 4.0.0.
