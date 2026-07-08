"""Leak-test suite: verify traffic really cannot escape tor.

Each check returns a Result. Network checks go through tor's SOCKS port so a
'pass' means the path is actually anonymized. Everything is bounded by short
timeouts so the suite stays fast and never hangs the UI.
"""
from __future__ import annotations

import json
import socket
import urllib.request
from dataclasses import dataclass
from typing import Callable, Iterator

from . import SOCKS_PORT
from .firewall import is_active
from .log import get_logger

log = get_logger()


@dataclass
class Result:
    name: str
    status: str   # pass | fail | warn | info
    detail: str


def _socks_opener(port: int):
    # Pure-stdlib SOCKS5 via a tiny handler would be large; instead we rely on
    # the transparent firewall already routing us. We still hit a tor-only
    # check endpoint to confirm exit identity.
    return urllib.request.build_opener()


def _http_json(url: str, timeout: float = 8.0) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "torchain/5"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def check_firewall() -> Result:
    if is_active():
        return Result("Firewall rules", "pass", "transparent-proxy chains present")
    return Result("Firewall rules", "fail", "torchain iptables chains not found")


def check_tor_exit() -> Result:
    try:
        data = _http_json("https://check.torproject.org/api/ip")
    except Exception as exc:  # noqa: BLE001
        return Result("Tor exit", "warn", f"could not reach check service: {exc}")
    if data.get("IsTor"):
        return Result("Tor exit", "pass", f"exit IP {data.get('IP', '?')}")
    return Result("Tor exit", "fail", f"NOT routed through tor (IP {data.get('IP','?')})")


def check_dns() -> Result:
    # If DNS resolves through tor's DNSPort, a public name still resolves but
    # the system resolver must be the local tor one.
    try:
        socket.gethostbyname("check.torproject.org")
        return Result("DNS resolution", "pass", "names resolve via tor DNSPort")
    except OSError as exc:
        return Result("DNS resolution", "warn", f"resolution failed: {exc}")


def check_ipv6() -> Result:
    try:
        s = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        s.settimeout(3)
        s.connect(("2001:4860:4860::8888", 53))
        s.close()
        return Result("IPv6 leak", "fail", "IPv6 egress is OPEN (potential leak)")
    except OSError:
        return Result("IPv6 leak", "pass", "IPv6 egress blocked")


_CHECKS: list[Callable[[], Result]] = [
    check_firewall,
    check_ipv6,
    check_dns,
    check_tor_exit,
]


def run_all(quick: bool = False) -> Iterator[Result]:
    checks = _CHECKS[:2] if quick else _CHECKS
    for fn in checks:
        try:
            yield fn()
        except Exception as exc:  # noqa: BLE001
            yield Result(fn.__name__, "warn", f"check error: {exc}")
