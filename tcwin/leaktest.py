"""Leak-test suite for Windows: verify traffic really cannot escape tor.

The exit check is performed through tor's SOCKS5 port (with remote DNS) using a
tiny built-in SOCKS5 client - so a 'pass' means the path is genuinely
anonymized rather than just 'the internet works'. Everything is bounded by
short timeouts so the suite stays fast and never hangs the UI.
"""
from __future__ import annotations

import json
import socket
import ssl
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


def _socks5_connect(host: str, port: int, *, sport: int, timeout: float = 10.0) -> socket.socket:
    """Open a TCP stream to host:port via the local tor SOCKS5 proxy.

    Uses SOCKS5 'connect by domain name' so DNS resolution also happens inside
    tor (no local DNS leak).
    """
    s = socket.create_connection(("127.0.0.1", sport), timeout)
    s.settimeout(timeout)
    # Greeting: VER=5, one method, 0x00 = no auth.
    s.sendall(b"\x05\x01\x00")
    if s.recv(2) != b"\x05\x00":
        s.close()
        raise OSError("SOCKS5 handshake rejected")
    h = host.encode("idna")
    req = b"\x05\x01\x00\x03" + bytes([len(h)]) + h + port.to_bytes(2, "big")
    s.sendall(req)
    rep = s.recv(4)
    if len(rep) < 2 or rep[1] != 0x00:
        s.close()
        raise OSError("SOCKS5 connect failed (code %s)" % (rep[1] if len(rep) > 1 else "?"))
    # Drain the bound address that follows the reply.
    atyp = rep[3] if len(rep) > 3 else 1
    if atyp == 1:
        s.recv(4 + 2)
    elif atyp == 3:
        ln = s.recv(1)
        s.recv(ln[0] + 2)
    elif atyp == 4:
        s.recv(16 + 2)
    return s


def _http_json_via_tor(host: str, path: str, *, sport: int, timeout: float = 12.0) -> dict:
    raw = _socks5_connect(host, 443, sport=sport, timeout=timeout)
    ctx = ssl.create_default_context()
    sock = ctx.wrap_socket(raw, server_hostname=host)
    try:
        req = (f"GET {path} HTTP/1.1\r\nHost: {host}\r\n"
               "User-Agent: torchain/5\r\nConnection: close\r\nAccept: */*\r\n\r\n")
        sock.sendall(req.encode())
        buf = b""
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            buf += chunk
    finally:
        sock.close()
    head, _, body = buf.partition(b"\r\n\r\n")
    text = body.decode("utf-8", "replace").strip()
    # Handle chunked transfer encoding minimally.
    if b"transfer-encoding: chunked" in head.lower():
        text = _dechunk(body).decode("utf-8", "replace").strip()
    start = text.find("{")
    return json.loads(text[start:]) if start >= 0 else {}


def _dechunk(body: bytes) -> bytes:
    out = b""
    while body:
        line, _, body = body.partition(b"\r\n")
        try:
            size = int(line.strip(), 16)
        except ValueError:
            break
        if size == 0:
            break
        out += body[:size]
        body = body[size + 2:]
    return out


def check_firewall() -> Result:
    if is_active():
        return Result("Kill-switch", "pass", "firewall blocks all non-tor egress")
    return Result("Kill-switch", "fail", "torchain firewall rules not found")


def check_proxy() -> Result:
    try:
        from . import proxy
        if proxy.is_set():
            return Result("System proxy", "pass", "WinINET proxy points at tor SOCKS")
        return Result("System proxy", "warn", "system proxy is not set to tor")
    except Exception as exc:  # noqa: BLE001
        return Result("System proxy", "warn", f"could not read proxy: {exc}")


def check_tor_exit() -> Result:
    try:
        data = _http_json_via_tor("check.torproject.org", "/api/ip", sport=SOCKS_PORT)
    except Exception as exc:  # noqa: BLE001
        return Result("Tor exit", "warn", f"could not reach check service via tor: {exc}")
    if data.get("IsTor"):
        return Result("Tor exit", "pass", f"exit IP {data.get('IP', '?')}")
    return Result("Tor exit", "fail", f"NOT routed through tor (IP {data.get('IP','?')})")


def check_dns() -> Result:
    # With the kill-switch up, direct UDP/53 is blocked, so a direct system
    # resolution SHOULD fail - that is the safe state (apps must use tor DNS).
    try:
        socket.setdefaulttimeout(4)
        socket.gethostbyname("example.com")
        return Result("DNS leak", "warn",
                      "direct DNS resolved - some app may bypass tor's resolver")
    except OSError:
        return Result("DNS leak", "pass", "direct DNS blocked (resolve via tor)")
    finally:
        socket.setdefaulttimeout(None)


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
    check_proxy,
    check_ipv6,
    check_dns,
    check_tor_exit,
]


def run_all(quick: bool = False) -> Iterator[Result]:
    checks = _CHECKS[:3] if quick else _CHECKS
    for fn in checks:
        try:
            yield fn()
        except Exception as exc:  # noqa: BLE001
            yield Result(fn.__name__, "warn", f"check error: {exc}")
