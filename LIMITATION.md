# Limitations & Threat Model

torchain hardens your **network layer** by forcing all traffic through Tor and
failing closed. It is a powerful tool, but it is **not** a magic anonymity
button. Read this before relying on it for anything that matters.

---

## What torchain does protect

- **Network-level routing.** All TCP traffic is transparently routed through
  Tor; non-Tor TCP is dropped.
- **DNS leaks.** DNS is forced through Tor's `DNSPort`, so lookups don't escape
  to your ISP's resolver.
- **IPv6 leaks.** IPv6 egress is blocked by default.
- **Fail-closed behavior.** If any startup step fails, firewall rules and tor
  are rolled back so you are never left half-protected.
- **Censorship circumvention.** Pluggable transports (obfs4 / snowflake /
  meek_lite / webtunnel) make the connection blend in as ordinary traffic.

---

## What torchain does NOT protect against

torchain operates at the network layer. It **cannot** defend against threats
above or below that layer:

- **Application-level identifiers.** Logins, cookies, browser fingerprints,
  canvas/WebGL fingerprinting, and account activity can deanonymize you even
  over a perfect Tor circuit. Use **Tor Browser** for browsing — torchain is
  not a substitute for it.
- **Browser/Tor Browser parity.** Routing a normal browser through Tor still
  leaks a unique fingerprint. torchain protects packets, not your browser
  identity.
- **Non-TCP traffic.** UDP (except DNS via Tor), ICMP, and other protocols are
  not anonymized — they are dropped, not tunneled. Some apps may simply break.
- **Malware / compromised system.** If your machine is already compromised,
  no transparent proxy can save you.
- **Global passive adversaries.** Tor does not defend against an adversary who
  can observe both ends of a connection (traffic-correlation attacks).
- **Endpoint metadata.** Timing, volume, and behavioral patterns can still
  correlate activity over time.
- **Physical / local-network deanonymization.** A hostile local network, ISP
  with deep records, or physical access changes your threat model entirely.

---

## Spoofing caveats

- **MAC / hostname spoofing is environment-fragile.** It is reversible and
  VM-aware, but it does **not** help in many common situations:
  - Behind a home router/NAT, your MAC is never seen by the wider internet.
  - Under a hypervisor with port security, spoofing may be rolled back or
    blocked.
  - It changes the *local* link identity only — it is not an anonymity feature
    on its own.

---

## Trust & privilege surface

- torchain **auto-elevates via sudo** and rewrites `iptables` rules and your
  `torrc`. This is a large privileged surface — audit the code before trusting
  it on a sensitive machine.
- Spoofing saves original values and restores them on `stop`, but an unclean
  shutdown (crash, power loss) can leave modified state. Verify with
  `torchain status` and `torchain leaktest` after recovery.

---

## Verify, don't assume

Protection is only real if you confirm it:

```shell
torchain leaktest      # run after every start

torchain status        # confirm firewall + tor are active
```

Always verify your exit IP, DNS, and IPv6 with the built-in **Leak Test** (or an
independent service) before assuming you are protected.

---

## Bottom line

> torchain is a tool for **privacy and security research**. No tool makes you
> perfectly anonymous. It raises the bar significantly at the network layer, but
> your overall anonymity depends on your full threat model, your behavior, and
> the applications you run. Understand that model and use torchain responsibly
> and legally.
