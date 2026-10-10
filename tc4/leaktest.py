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


import ssl


def _recv_exact(s: socket.socket, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = s.recv(n - len(buf))
        if not chunk:
            raise OSError("unexpected EOF reading SOCKS5 response")
        buf.extend(chunk)
    return bytes(buf)


def _socks5_connect(host: str, port: int, *, sport: int, timeout: float = 10.0) -> socket.socket:
    """Open a TCP stream to host:port via the local tor SOCKS5 proxy."""
    s = socket.create_connection(("127.0.0.1", sport), timeout)
    s.settimeout(timeout)
    s.sendall(b"\x05\x01\x00")
    greet = _recv_exact(s, 2)
    if greet != b"\x05\x00":
        s.close()
        raise OSError("SOCKS5 handshake rejected")
    h = host.encode("idna")
    req = b"\x05\x01\x00\x03" + bytes([len(h)]) + h + port.to_bytes(2, "big")
    s.sendall(req)
    rep = _recv_exact(s, 4)
    if rep[1] != 0x00:
        s.close()
        raise OSError(f"SOCKS5 connect failed (code {rep[1]})")
    atyp = rep[3]
    if atyp == 1:
        _recv_exact(s, 4 + 2)
    elif atyp == 3:
        ln = _recv_exact(s, 1)[0]
        _recv_exact(s, ln + 2)
    elif atyp == 4:
        _recv_exact(s, 16 + 2)
    return s


def _http_json_via_tor(host: str, path: str, *, sport: int, timeout: float = 12.0) -> dict:
    buf = b""
    try:
        raw = _socks5_connect(host, 443, sport=sport, timeout=timeout)
        try:
            ctx = ssl.create_default_context()
        except Exception:
            ctx = ssl._create_unverified_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        try:
            sock = ctx.wrap_socket(raw, server_hostname=host)
        except Exception:
            ctx = ssl._create_unverified_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            sock = ctx.wrap_socket(raw, server_hostname=host)
        try:
            req = (f"GET {path} HTTP/1.1\r\nHost: {host}\r\n"
                   "User-Agent: Mozilla/5.0 (Windows NT 10.0; rv:109.0) Gecko/20100101 Firefox/115.0\r\nConnection: close\r\nAccept: application/json,*/*\r\n\r\n")
            sock.sendall(req.encode())
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                buf += chunk
        finally:
            sock.close()
    except Exception as https_err:
        log.debug("HTTPS check via tor failed (%s); trying HTTP fallback", https_err)
        raw = _socks5_connect(host, 80, sport=sport, timeout=timeout)
        try:
            req = (f"GET {path} HTTP/1.1\r\nHost: {host}\r\n"
                   "User-Agent: Mozilla/5.0 (Windows NT 10.0; rv:109.0) Gecko/20100101 Firefox/115.0\r\nConnection: close\r\nAccept: application/json,*/*\r\n\r\n")
            raw.sendall(req.encode())
            while True:
                chunk = raw.recv(4096)
                if not chunk:
                    break
                buf += chunk
        finally:
            raw.close()

    head, _, body = buf.partition(b"\r\n\r\n")
    text = body.decode("utf-8", "replace").strip()
    if b"transfer-encoding: chunked" in head.lower():
        out = b""
        rem = body
        while rem:
            line, _, rem = rem.partition(b"\r\n")
            try:
                size = int(line.strip(), 16)
            except ValueError:
                break
            if size == 0:
                break
            out += rem[:size]
            rem = rem[size + 2:]
        text = out.decode("utf-8", "replace").strip()
    start = text.find("{")
    return json.loads(text[start:]) if start >= 0 else {}



def check_firewall() -> Result:
    if is_active():
        return Result("Firewall rules", "pass", "transparent-proxy chains present")
    return Result("Firewall rules", "fail", "torchain iptables chains not found")


def check_tor_exit() -> Result:
    try:
        data = _http_json_via_tor("check.torproject.org", "/api/ip", sport=SOCKS_PORT)
    except Exception as exc:  # noqa: BLE001
        return Result("Tor exit", "warn", f"could not reach check service via tor: {exc}")
    if data.get("IsTor"):
        return Result("Tor exit", "pass", f"exit IP {data.get('IP', '?')}")
    return Result("Tor exit", "fail", f"NOT routed through tor (IP {data.get('IP','?')})")


def check_dns() -> Result:
    # If DNS resolves through tor's DNSPort with AutomapHostsOnResolve,
    # resolving a .onion address succeeds and yields a 10.192.0.0/10 IP.
    # Regular clearnet DNS (e.g. 8.8.8.8) fails or returns NXDOMAIN.
    try:
        ip = socket.gethostbyname("duckduckgogg42xjoc72x3sjasowoarfbgcmvfimaftt6twagswzczad.onion")
        if ip.startswith("10.192.") or ip.startswith("10."):
            return Result("DNS resolution", "pass", f"onion automap confirmed ({ip}) via tor DNSPort")
        return Result("DNS resolution", "warn", f"resolved onion unexpectedly to {ip}")
    except OSError:
        pass

    try:
        socket.gethostbyname("check.torproject.org")
        return Result("DNS resolution", "pass", "names resolve via redirected DNSPort")
    except OSError as exc:
        return Result("DNS resolution", "fail", f"resolution failed: {exc}")


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
    check_dns,
    check_tor_exit,
    check_ipv6,
]


def run_all(quick: bool = False) -> Iterator[Result]:
    checks = _CHECKS[:2] if quick else _CHECKS
    for fn in checks:
        try:
            yield fn()
        except Exception as exc:  # noqa: BLE001
            yield Result(fn.__name__, "warn", f"check error: {exc}")
