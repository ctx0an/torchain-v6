<div align="center">

<img src="img/torchain-256.png" alt="Torchain Logo" width="128" height="128">

# Torchain v6

**System-Wide Transparent Tor Routing & Fail-Closed Kill-Switch for Windows, Linux & Android**

[![Release](https://img.shields.io/github/v/release/ctx0an/torchain-v6?color=7952b3&logo=github&style=flat-square)](https://github.com/ctx0an/torchain-v6/releases/latest)
[![Security Audit](https://img.shields.io/badge/Security_Audit-25_Vectors_Hardened-success?style=flat-square&logo=shield)](https://github.com/ctx0an/torchain-v6#security-audit--hardening)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20Android%20%7C%20Termux-blue?style=flat-square)](https://github.com/ctx0an/torchain-v6#downloads)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](LICENSE)
[![GitHub Stars](https://img.shields.io/github/stars/ctx0an/torchain-v6?style=flat-square&color=gold)](https://github.com/ctx0an/torchain-v6/stargazers)

<p align="center">
  <a href="#downloads">⚡ Download Binaries</a> •
  <a href="#key-features">✨ Key Features</a> •
  <a href="#why-torchain">🛡️ Comparison</a> •
  <a href="#security-audit--hardening">🔒 Security Audit</a> •
  <a href="#quick-start">🚀 Quick Start</a> •
  <a href="#cli--configuration">⚙️ CLI & Config</a>
</p>

<img src="docs/dashboard.png" alt="Torchain Cyber Dashboard" width="90%">

</div>

---

## ⚡ Overview

**Torchain** routes **100% of your operating system's network traffic** through the Tor network with an unbypassable, hardware-level firewall kill-switch. Unlike ordinary proxies or browser extensions, Torchain transparently anonymizes every application on your machine—browsers, CLI tools, instant messengers, games, background daemons, and system updates.

If Tor crashes, disconnects, or is terminated, **Torchain's fail-closed kill-switch drops all egress instantly**, ensuring your real IP address is **never exposed in cleartext**.

---

## 📦 Downloads (Zero Dependencies Required)

Pre-built, standalone binaries with embedded Tor engines and GUI dashboards:

| Platform | Download | Package Type | Size | Requirements |
| :--- | :--- | :--- | :--- | :--- |
| **Windows** | [📥 **torchain.exe**](https://github.com/ctx0an/torchain-v6/releases/latest/download/torchain.exe) | Single-File Executable | ~33 MB | Windows 10 / 11 (64-bit) |
| **Windows** | [📥 **torchain-portable.zip**](https://github.com/ctx0an/torchain-v6/releases/latest/download/torchain-portable.zip) | Portable Directory Archive | ~33 MB | No install / Instant extraction |
| **Linux** | [📥 **Torchain-x86_64.AppImage**](https://github.com/ctx0an/torchain-v6/releases/latest/download/Torchain-x86_64.AppImage) | Portable Linux AppImage | ~18 MB | Kernel 4.x+ (Debian, Ubuntu, Arch, Fedora, Kali) |
| **Android** | [📥 **app-debug.apk**](https://github.com/ctx0an/torchain-v6/releases/latest/download/app-debug.apk) | Standalone APK | ~80 MB | Android 8.0+ (ARM64, ARMv7, x86, x64) |
| **Termux** | [`torchain-termux`](#termux) | Standalone Shell Script | ~15 KB | Termux on Android (No Root Required) |

---

## ✨ Key Features

- 🛡️ **Fail-Closed Hardware Kill-Switch**: Uses native kernel firewalls (Windows Defender Firewall WFP / Linux `iptables` / Android TUN blackholing) to prevent any socket from bypassing Tor.
- ⚡ **OptimisticData & Low Latency**: Saves 1 full round-trip time (RTT) on stream initialization, backed by adaptive circuit build timeouts and single guard profiles.
- 🚫 **Complete IPv6 & DNS Blackholing**: Enforces strict `::/0` IPv6 blocking and captures all DNS requests into Tor's isolated `DNSPort` (`127.0.0.1:5353`), eliminating DNS leaks.
- 🧪 **Built-In 7-Point Leak Verification**: Live one-click audit testing your public IP, DNS resolvers, IPv6 status, direct socket connectivity, and WebRTC.
- 🌉 **Censorship Circumvention (Bridges)**: Built-in support for Pluggable Transports (`obfs4`, `snowflake`, `meek_lite`, `webtunnel`) with automatic bridge fetching via Tor Project Moat API.
- 🎨 **Kali-Themed Cyber Dashboard**: Built with a responsive Tk / Jetpack Compose HUD featuring live hop latency badges, circuit telemetry, and real-time logs.
- 🎭 **Identity & MAC Spoofing**: Automatic MAC address and system hostname randomization with full clean restoration on shutdown.
- 💣 **Pandora Protocol**: Emergency panic command that flushes memory, terminates sockets, nukes temporary keys, and severs all network connectivity instantly.

---

## 🛡️ Why Torchain?

| Feature | 🧅 Tor Browser | 🚷 TorGhost / AnonSurf | 💿 Tails OS | 🚀 **Torchain v6** |
| :--- | :---: | :---: | :---: | :---: |
| **Scope** | Browser Only | Entire OS | Entire OS | **Entire OS** |
| **No Reboot Required** | ✅ | ✅ | ❌ (Requires USB Boot) | ✅ **Instant One-Click** |
| **Multi-Platform** | Desktop & Mobile | Linux Only (Outdated) | Live USB Only | **Windows, Linux, Android & Termux** |
| **Fail-Closed Killswitch** | ⚠️ App Level Only | ❌ Leaky on teardown | ✅ | ✅ **Kernel-Enforced WFP / Iptables** |
| **IPv6 Leak Protection** | ✅ | ❌ Frequent leaks | ✅ | ✅ **Strict `::/0` Blackhole** |
| **Anti-Censorship Bridges** | ✅ | ❌ | ✅ | ✅ **Moat, obfs4, Snowflake, Meek** |
| **Zero Runtime Dependencies** | ✅ | ❌ (Complex deps) | N/A | ✅ **Single-File `.exe` & `.AppImage`** |
| **Security Audited** | ✅ | ❌ | ✅ | ✅ **25 Leak Vectors Patched** |

---

## 🔒 Security Audit & Hardening

Torchain v6 was comprehensively audited against **25 attack vectors and leak scenarios** across Windows, Linux, Android, and build pipelines:

```
[PASS] C1: Android VPN revocation handled fail-closed (prevents cleartext fall-through)
[PASS] C2: Repair flows gated strictly when Tor is active (zero teardown window)
[PASS] C3: Android LeakTester sockets routed through proxy (no physical NIC disclosure)
[PASS] C4: Native Android TProxy crash fails closed into blackholed TUN
[PASS] C5: Upstream binary downloads verified via SHA-256 integrity checksums
[PASS] C6: Linux firewall status verifies filter table DROP rules
[PASS] H1: Atomic firewall rules prevent intermediate egress leaks during bootstrap
[PASS] H2: IPv6 configuration fails closed if rule insertion fails
[PASS] H3: Windows tor data directory and auth cookie ACL-restricted via icacls
[PASS] H4: DNS redirect strictly scoped to loopback interfaces
[PASS] M1-M7: Bridge health testing isolated; sensitive IPs masked in telemetry logs
```

---

## 🚀 Quick Start

### Windows (No Installation Required)

1. Download [`torchain.exe`](https://github.com/ctx0an/torchain-v6/releases/latest/download/torchain.exe).
2. Right-click → **Run as administrator** (required to manage Windows Defender Firewall rules).
3. Click **START** in the cyber dashboard to route all traffic through Tor.

*Or via Command Prompt / PowerShell (Admin):*
```powershell
.\torchain.exe gui        # Launch GUI Dashboard
.\torchain.exe start      # Enable system-wide Tor tunnel
.\torchain.exe leaktest   # Run leak audit
.\torchain.exe stop       # Restore clean direct network
```

### Linux (Debian, Ubuntu, Arch, Fedora, Kali)

1. Download and run the standalone AppImage:
```bash
wget https://github.com/ctx0an/torchain-v6/releases/latest/download/Torchain-x86_64.AppImage
chmod +x Torchain-x86_64.AppImage

sudo ./Torchain-x86_64.AppImage gui     # Launch GUI Dashboard
sudo ./Torchain-x86_64.AppImage start   # Enable transparent proxy
```

### Android

1. Download [`app-debug.apk`](https://github.com/ctx0an/torchain-v6/releases/latest/download/app-debug.apk).
2. Install and tap **Connect**. Torchain will establish a high-performance VPN tunnel and route all apps through Tor.

### Termux

No root permissions needed. Runs as a local gateway for mobile terminal environments:
```bash
git clone https://github.com/ctx0an/torchain-v6.git
cd torchain-v6
./torchain-termux install
torchain start
```

---

## 📸 Interface Preview

<div align="center">

| Built-In 7-Point Leak Tester | Pluggable Transports & Bridges |
| :---: | :---: |
| <img src="docs/leaktest.png" width="450"> | <img src="docs/bridges.png" width="450"> |

| Live Circuit Visualizer & Telemetry | Advanced Network & Identity Settings |
| :---: | :---: |
| <img src="docs/dashboard.png" width="450"> | <img src="docs/settings.png" width="450"> |

</div>

---

## ⚙️ CLI & Configuration

Full command-line parity exists across all platforms:

```bash
torchain doctor        # Pre-flight environment check (firewall, routing, permissions)
sudo torchain start    # Route 100% of network traffic through Tor
torchain status        # Show current circuit, exit IP, and firewall state
sudo torchain rotate   # Trigger NEWNYM: build fresh circuits with new exit IP
torchain leaktest      # Run full automated leak test suite
sudo torchain stop     # Safely disarm firewall and restore direct connectivity
torchain repair        # Emergency recovery: unjam networking if forced mid-session
torchain pandora       # Emergency panic: wipe state, cut network, kill active processes
```

### Configuration Options

```bash
torchain config                           # Display all current configuration flags
torchain config --set exit_country=is     # Pin exit nodes to a specific country (e.g. Iceland, Switzerland)
torchain config --set block_ipv6=true     # Enforce strict IPv6 drop
torchain config --set spoof_mac=true      # Randomize MAC address on startup
torchain config --set auto_rotate_minutes=10  # Automatically rotate circuits every 10 minutes
torchain config --set watchdog_enabled=true   # Automatic daemon health monitoring
```

---

## 🌟 Star History

If Torchain helped protect your privacy, please give it a star! ⭐

[![Star History Chart](https://api.star-history.com/svg?repos=ctx0an/torchain-v6&type=Date)](https://star-history.com/#ctx0an/torchain-v6&Date)

---

## ⚖️ License & Disclaimer

Distributed under the **MIT License**. See [`LICENSE`](LICENSE) for details.

> **Disclaimer:** Torchain is designed for security research, anti-surveillance defense, and privacy education. No automated software provides 100% infallible anonymity against global state-level adversaries. Always understand your threat model and verify your egress using the built-in `leaktest`.