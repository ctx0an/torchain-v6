<div align="center">

# Torchain

**System-wide Tor anonymizer with a Kali-themed dashboard.**

<img src="img/torchain-icon.png" alt="torchain" width="64" height="64">

[![CI](https://github.com/ctx0an/torchain-v6/actions/workflows/ci.yml/badge.svg)](https://github.com/ctx0an/torchain-v6/actions/workflows/ci.yml)
[![Build Windows](https://github.com/ctx0an/torchain-v6/actions/workflows/build-portable.yml/badge.svg)](https://github.com/ctx0an/torchain-v6/actions/workflows/build-portable.yml)
[![Build Linux](https://github.com/ctx0an/torchain-v6/actions/workflows/build-appimage.yml/badge.svg)](https://github.com/ctx0an/torchain-v6/actions/workflows/build-appimage.yml)
[![Build Android](https://github.com/ctx0an/torchain-v6/actions/workflows/build-apk.yml/badge.svg)](https://github.com/ctx0an/torchain-v6/actions/workflows/build-apk.yml)
[![Release](https://img.shields.io/github/v/release/ctx0an/torchain-v6.svg)](https://github.com/ctx0an/torchain-v6/releases/latest)

</div>

---

## Quick start

Grab a binary, run it as admin, done.

### Windows (no Python needed)

There are two builds. Pick whichever you like:

| Build | What it is | Size |
| --- | --- | --- |
| [`torchain.exe`](https://github.com/ctx0an/torchain-v6/releases/latest/download/torchain.exe) | Single file. Python, Tk and Tor are all bundled inside. | ~32 MB |
| [`torchain-portable.zip`](https://github.com/ctx0an/torchain-v6/releases/latest/download/torchain-portable.zip) | Unpacked folder, faster startup since nothing is extracted at run time. | ~33 MB |

Both are self-contained. No Python install, no pip, no package manager.

1. Download either one from [Releases](https://github.com/ctx0an/torchain-v6/releases/latest)
2. `torchain.exe` goes anywhere. For the zip, extract it anywhere
3. Right-click → **Run as administrator** (needed for firewall and proxy changes)
4. Windows SmartScreen will complain the first time. The file is unsigned, so click **More info → Run anyway**

```batch
torchain.exe gui        :: dashboard
torchain.exe doctor     :: check what's missing before you start
torchain.exe start      :: route everything through Tor
```

`torchain.exe` unpacks itself into `%ProgramData%\torchain\` on first run. That takes a few seconds and only happens once.

If you want it on `PATH`, run `windows\setup.bat` from the extracted folder — it registers the command, creates Start Menu and Desktop shortcuts, and can be removed later with `uninstall.bat`.

### Linux (x86_64)

```bash
wget https://github.com/ctx0an/torchain-v6/releases/latest/download/Torchain-x86_64.AppImage
chmod +x Torchain-x86_64.AppImage

sudo ./Torchain-x86_64.AppImage gui     # dashboard
sudo ./Torchain-x86_64.AppImage start   # route everything through Tor
```

That's the whole install. No packages, nothing written outside your home directory until you run `start`. Works on Debian/Ubuntu, Fedora, Arch, Kali, and anything else with kernel 4.x+.

AppImages sometimes refuse to launch on hardened distros. If you get a FUSE error:

```bash
sudo apt install libfuse2      # Debian/Ubuntu
sudo ./Torchain-x86_64.AppImage --appimage-extract-and-run
```

### Android

Grab the APK from [Releases](https://github.com/ctx0an/torchain-v6/releases/latest), allow "install from unknown sources" for your browser when it asks, and open it. Needs Android 8.0+.

The app runs Tor through `TorVpnService` and draws the same dashboard in Jetpack Compose.

### Termux

```bash
git clone https://github.com/ctx0an/torchain-v6.git
cd torchain-v6
./torchain-termux install
torchain start
```

`torchain-termux` is a single standalone script, no root required. It's unprivileged, so it can't touch iptables — instead it exposes a local gateway you can point other apps at.

---

## Using it

```bash
torchain doctor        # pre-flight check: deps, firewall, existing leaks
sudo torchain start    # route ALL traffic through Tor
torchain status        # where am I right now
sudo torchain rotate   # new identity, new circuits
torchain leaktest      # prove nothing is escaping
sudo torchain stop     # put everything back the way it was
torchain gui           # dashboard
```

Same commands on every platform. On Windows just drop the `sudo`, the `.exe` asks for elevation itself.

Two of these are worth knowing about:

```bash
torchain repair       # "my internet is dead" — force-restore networking
torchain pandora      # nuclear option: kill-switch, wipe state, scrub memory
```

`repair` is the first thing to try if you unplugged the network mid-connect or a firewall rule got half-applied. `pandora` is for when you need the machine to stop talking to Tor *and* forget it did.

### Dashboard

![dashboard](docs/dashboard.png)

Sidebar covers connect/disconnect with live bootstrap progress, the circuit table, bridges, leak tests, settings, and a log tail.

### Circuits

Each hop with its nickname, IP and country, live over the control port.

### Bridges

Pick a transport (obfs4, snowflake, meek_lite, webtunnel), paste your own bridge lines, or pull fresh ones from the Tor Project through the Moat API. `test` does a TCP ping against each line so you know which ones actually work before you need them.

![bridges](docs/bridges.png)

### Leak test

Your real IP, DNS, and IPv6, checked and color-coded.

![leaktest](docs/leaktest.png)

### Settings & logs

![settings](docs/settings.png)
![logs](docs/logs.png)

---

## Bridges

For networks where Tor is blocked:

```bash
torchain bridge type obfs4
torchain bridge add 'obfs4 1.2.3.4:443 <fingerprint> cert=... iat-mode=0'
torchain bridge fetch                 # fresh list from Tor Project
torchain bridge fetch --transport webtunnel
torchain bridge test --timeout 10
torchain bridge list
torchain bridge remove 0              # index, or the exact line
torchain bridge enable
```

Get bridges from [bridges.torproject.org](https://bridges.torproject.org/) if `fetch` is blocked too — that's the whole point.

---

## Config

```bash
torchain config                           # show everything
torchain config --set exit_country=us     # pin exit nodes
torchain config --set block_ipv6=true
torchain config --set spoof_mac=true
torchain config --set auto_rotate_minutes=10
torchain config --set watchdog_enabled=true
torchain config --set start_on_boot=true
```

Kill switch, if you need to drop everything immediately:

```bash
sudo torchain panic          # block all non-loopback traffic now
sudo torchain panic disarm   # undo
```

Watchdog and boot:

```bash
torchain watchdog start      # repairs tor/firewall if they die, rotates on a timer
torchain boot enable         # systemd on Linux, Task Scheduler on Windows
```

---

## What's in v6

v6 is mostly a performance pass plus a standalone Windows binary, with some real bugs fixed along the way.

**Standalone `torchain.exe`.** One file, no runtime deps. PyInstaller onefile build with native Python, Tcl/Tk, and the Tor bundle baked in.

**Faster circuits.** `OptimisticData 1` is on across all four platforms, which saves a full round trip when a stream is initialized. `LearnCircuitBuildTimeout 1` lets Tor adapt the build timeout instead of using a fixed one, and `NumEntryGuards 1` keeps the guard set small.

**Less blocking work.** Bridge health checks run through a `ThreadPoolExecutor` instead of one at a time. ControlPort GeoIP and relay lookups are memoized with `lru_cache`.

**Animation suite** — one-shot, no idle CPU:

- `ProGyroBootHUD` — boot sequence with three rotating azimuth dials, a scanning radar beam, and live telemetry
- `ProCyberButton` — chamfered buttons with hover ripple, a text scramble decode, and spring press
- 3-hop circuit mesh with packet sparks and latency badges
- Elastic pulse on status nodes

**Bugs fixed:**

- Linux transparent proxy dropped `.onion` traffic. The `10.192.0.0/10` redirect now runs before the RFC1918 bypass
- Windows Defender blocked pluggable transports. Added allow rules for `lyrebird.exe`, `conjure-client.exe`, and friends
- Hostname restore could corrupt `/etc/hosts`
- Elevated recovery scripts only cleaned `HKCU`; now walks all of `HKEY_USERS`
- Hardcoded bridge IPs removed from `torchain-termux`
- Android `LeakTester.kt` reported false positives

Full list in [CHANGELOG.md](CHANGELOG.md).

---

## Building from source

```bash
git clone https://github.com/ctx0an/torchain-v6.git
cd torchain-v6
```

**Linux** — installs `tor`, `obfs4proxy`, `iptables`, `python3`, `python3-tk`, `xauth`, `pkexec`, then drops the package in `/usr/share/torchain` and symlinks `torchain` into `/usr/bin`:

```bash
sudo ./setup.sh
```

**Windows** — no winget, no Chocolatey. Downloads a portable Python with Tk support and extracts the bundled `tor.exe`:

```batch
windows\setup.bat
```

**Binaries:**

```batch
pip install pyinstaller
windows\build_portable.bat          :: dist\torchain.exe + dist\torchain-portable.zip
```

```bash
pip install pyinstaller
linux/build_appimage.sh             # dist/Torchain-x86_64.AppImage
bash scripts/download_tor.sh
./gradlew assembleDebug             # app/build/outputs/apk/debug/app-debug.apk
```

CI runs ShellCheck, `bash -n`, and Python byte-compilation on every push.

---

## Layout

```
torchain              thin bash launcher, auto-elevates everything
tc4/                  Linux engine + dashboard
├── engine.py         tor + firewall + spoofing + watchdog, fail-closed
├── gui.py            event-driven Tk dashboard
├── animations/       gyro HUD, cyber buttons, pulse engine
└── torrc.py          torrc + pluggable transport discovery
tcwin/                Windows engine + dashboard (WinINET proxy + Firewall)
app/                  Android, Kotlin + Jetpack Compose
torchain-termux       standalone unprivileged script for Termux
```

The whole thing is standard library only. No pip dependencies, which is why the onefile build stays around 32 MB.

---

## Security model

- **Fail-closed.** If any start step fails, firewall rules and tor get rolled back. You are never left half-protected.
- **No leaks by default.** IPv6 egress blocked, DNS forced through Tor's `DNSPort`, all non-Tor TCP dropped.
- **Reversible.** Spoofing saves the original MAC and hostname and puts them back on `stop`.

This protects the network layer and nothing else. Read [LIMITATION.md](LIMITATION.md) before you rely on it.

## Contributing

PRs welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) and [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## Credits

By **ctx0an**.

## License

MIT — [LICENSE](LICENSE).

> torchain is for privacy research and testing. No tool makes you anonymous. Know your threat model.