# Security Policy & Posture 🛡️

We take the security of TorChain seriously. As a tool designed to anonymize and protect user traffic, ensuring there are no leakages or security vulnerabilities is our top priority.

---

## 🔒 Threat Model

TorChain is designed to protect users against:
- **Local Network Sniffing:** Prevents local routers, ISPs, and hackers on public Wi-Fi from seeing what web targets you visit by encrypting and routing all TCP traffic through Tor.
- **ISP Tracking:** Obfuscation bridges make Tor traffic resemble generic TLS, hiding Tor usage.
- **DNS Leaks:** Forces all DNS lookups to go through Tor's secure resolvers.
- **Device Fingerprinting:** Spoofs MAC addresses and machine UUIDs to prevent physical hardware profiling on local networks.
- **Website Blocks:** Hides Tor exit node IPs via downstream SOCKS5 proxy wrapping.

**Out of Scope:**
- TorChain cannot protect against browser-based fingerprinting (e.g. canvas hashes, user-agent details, cookies). We highly recommend using the **Tor Browser** or a locked-down browser profile alongside TorChain.
- Local system compromise: If an attacker has root access to the VM, they can bypass iptables rules or modify the configuration.

---

## 🛠️ Security Best Practices in TorChain

1. **No `eval` Configuration Loading:** We parse settings using strict bash regex matching to prevent command execution vulnerabilities.
2. **Buffer Limits:** Sockets polling Tor's ControlPort implement a strict 64KB size limit to prevent memory exhaustion and DoS attacks.
3. **Privileged Escalation Guard:** The GUI and scripts require explicit administrative privileges (`sudo`). Subprocesses inherit this context rather than requesting redundant sudo credentials, protecting against prompt injection.
4. **SSH Protection:** MAC randomization automatically detects and skips interfaces carrying active SSH sessions, preventing lockout.

---

## 📞 Reporting a Vulnerability

If you discover a security vulnerability (such as a DNS leak, firewall bypass, or code execution vulnerability), please **do not open a public Github issue**. Instead, follow these steps:

1. Send an encrypted email to the maintainers at `security@torchain.local` (or use the PGP key listed in the project release page).
2. Include a detailed description of the vulnerability, steps to reproduce, and a Proof of Concept (PoC) if available.
3. We will acknowledge receipt of your report within 24 hours and work on a patch immediately.
4. We follow a standard 90-day responsible disclosure window before public disclosure.
