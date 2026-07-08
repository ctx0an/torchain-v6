"""Minimal, fast Tor control-port client (no external deps).

Speaks just enough of the control protocol to authenticate via the safe
cookie method, watch bootstrap progress, request new identities, and read
circuit status. Sockets are always closed via context management.
"""
from __future__ import annotations

import binascii
import re
import socket
import time

from . import CONTROL_PORT, DATA_DIR
from .errors import TorError
from .log import get_logger

log = get_logger()

import os

_COOKIE = os.path.join(DATA_DIR, "tor", "control_auth_cookie")
_FP_RE = re.compile(r"\$([0-9A-Fa-f]{40})(?:=([^,\s]+))?")


class ControlClient:
    def __init__(self, host: str = "127.0.0.1", port: int = CONTROL_PORT,
                 cookie_path: str | None = None, timeout: float = 5.0):
        self.host = host
        self.port = port
        self.cookie_path = cookie_path or _COOKIE
        self.timeout = timeout
        self._sock: socket.socket | None = None

    # -- context manager --
    def __enter__(self) -> "ControlClient":
        self.connect()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def connect(self) -> None:
        try:
            self._sock = socket.create_connection((self.host, self.port), self.timeout)
            self._sock.settimeout(self.timeout)
        except OSError as exc:
            raise TorError(
                f"cannot reach tor control port {self.host}:{self.port}",
                hint="Is tor running? Try 'torchain start'.",
            ) from exc
        self._authenticate()

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._send("QUIT")
            except Exception:
                pass
            try:
                self._sock.close()
            finally:
                self._sock = None

    # -- low level --
    def _send(self, line: str) -> None:
        assert self._sock is not None
        self._sock.sendall((line + "\r\n").encode("utf-8"))

    def _recv(self) -> list[str]:
        """Read one full reply (handles multi-line 'mid' responses)."""
        assert self._sock is not None
        buf = b""
        while b"\r\n" not in buf or not self._reply_complete(buf):
            chunk = self._sock.recv(4096)
            if not chunk:
                break
            buf += chunk
        return buf.decode("utf-8", "replace").splitlines()

    @staticmethod
    def _reply_complete(buf: bytes) -> bool:
        # A final line looks like 'NNN <text>'; mid lines use 'NNN-' or 'NNN+'.
        for line in buf.decode("utf-8", "replace").splitlines():
            if len(line) >= 4 and line[3] == " " and line[:3].isdigit():
                return True
        return False

    def _command(self, line: str) -> list[str]:
        self._send(line)
        reply = self._recv()
        if reply and not reply[-1].startswith("250"):
            raise TorError(f"control command failed: {line} -> {reply[-1]}")
        return reply

    def _authenticate(self) -> None:
        try:
            with open(self.cookie_path, "rb") as fh:
                cookie = binascii.hexlify(fh.read()).decode("ascii")
        except OSError:
            cookie = ""
        cmd = f"AUTHENTICATE {cookie}" if cookie else "AUTHENTICATE"
        self._send(cmd)
        reply = self._recv()
        if not reply or not reply[-1].startswith("250"):
            raise TorError(
                "control port authentication failed",
                hint="Cookie file unreadable; run as root or restart torchain.",
            )

    # -- high level --
    def get_info(self, key: str) -> str:
        reply = self._command(f"GETINFO {key}")
        out: list[str] = []
        in_data = False
        for line in reply:
            if line.startswith("250+") or line.startswith("250-"):
                if "=" in line:
                    val = line.split("=", 1)[1]
                    if val:
                        out.append(val)
                if line.startswith("250+"):
                    in_data = True
            elif in_data and line == ".":
                in_data = False
            elif in_data:
                out.append(line)
        return "\n".join(out)

    def bootstrap_progress(self) -> int:
        try:
            info = self.get_info("status/bootstrap-phase")
        except TorError:
            return 0
        for tok in info.split():
            if tok.startswith("PROGRESS="):
                try:
                    return int(tok.split("=", 1)[1])
                except ValueError:
                    return 0
        return 0

    def newnym(self) -> None:
        self._command("SIGNAL NEWNYM")

    def circuits(self) -> list[str]:
        raw = self.get_info("circuit-status")
        return [ln for ln in raw.splitlines() if ln.strip()]

    def relay_ip(self, fingerprint: str) -> str | None:
        """Look up the IP address of a relay or bridge by its hex fingerprint."""
        fp = fingerprint.upper()
        # Try consensus (public relays)
        try:
            raw = self.get_info(f"ns/id/{fp}")
        except TorError:
            pass
        else:
            for line in raw.splitlines():
                if line.startswith("@type "):
                    continue
                if line.startswith("r "):
                    parts = line.split()
                    if len(parts) >= 8:
                        return parts[5]
        # Fallback: full descriptor (bridges, etc.)
        try:
            raw = self.get_info(f"desc/id/{fp}")
        except TorError:
            return None
        for line in raw.splitlines():
            if line.startswith("router "):
                parts = line.split()
                if len(parts) >= 6:
                    return parts[2]
            if line.startswith("or-address "):
                parts = line.split()
                if len(parts) >= 2:
                    return parts[1].rsplit(":", 1)[0]
        return None

    def ip_country(self, ip: str) -> str:
        """Get 2-letter country code for an IP via tor's GeoIP."""
        try:
            return self.get_info(f"ip-to-country/{ip}").strip()
        except TorError:
            return "??"

    def circuit_details(self) -> list[dict]:
        """Return structured info for each circuit with relay IPs and countries."""
        raw = self._command("GETINFO circuit-status")
        circuits: list[dict] = []
        data_lines: list[str] = []
        in_data = False
        for line in raw:
            if line.startswith("250+circuit-status="):
                in_data = True
            elif in_data and line == ".":
                in_data = False
            elif in_data:
                data_lines.append(line)
            elif line.startswith("250-circuit-status="):
                val = line.split("=", 1)[1] if "=" in line else ""
                data_lines.append(val)

        for raw_line in data_lines:
            ln = raw_line.strip()
            if not ln:
                continue
            parts = ln.split(" ", 2)
            if len(parts) < 2:
                continue
            cid = parts[0]
            status = parts[1]
            extra = parts[2] if len(parts) > 2 else ""
            purpose = "GENERAL"
            pm = re.search(r"PURPOSE=(\S+)", extra)
            if pm:
                purpose = pm.group(1)
            path_raw = extra.split(" ", 1)[0] if " " in extra else extra
            hops: list[dict] = []
            for m in _FP_RE.finditer(path_raw):
                fp = m.group(1).lower()
                nickname = m.group(2) or "?"
                hops.append({
                    "fingerprint": fp,
                    "nickname": nickname,
                    "ip": self.relay_ip(fp) or "?",
                    "country": "?",
                })
            for hop in hops:
                if hop["ip"] and hop["ip"] != "?":
                    hop["country"] = self.ip_country(hop["ip"]) or "??"
            circuits.append({
                "id": cid,
                "status": status,
                "purpose": purpose,
                "hops": hops,
            })
        return circuits


def wait_bootstrap(timeout: float = 60.0, poll: float = 0.5,
                   on_progress=None, check_pid: int | None = None) -> bool:
    """Block until tor reports 100% bootstrap or timeout. Returns success."""
    deadline = time.time() + timeout
    last = -1
    while time.time() < deadline:
        if check_pid is not None:
            from .sysutil import pid_alive
            if not pid_alive(check_pid):
                log.warning("tor process %s died during bootstrap", check_pid)
                return False
        try:
            with ControlClient() as c:
                pct = c.bootstrap_progress()
        except TorError:
            pct = 0
        if pct != last and on_progress:
            on_progress(pct)
        last = pct
        if pct >= 100:
            return True
        time.sleep(poll)
    return False
