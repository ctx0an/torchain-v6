"""System (WinINET) proxy control.

Windows has no transparent proxy, so to actually route applications through
tor we point the per-user WinINET proxy at tor's SOCKS port. WinINET-based
apps (Edge, Chrome by default, most desktop apps that honor system proxy)
then tunnel through tor. Combined with the firewall kill-switch, apps that
ignore the proxy simply cannot reach the network.

We save the previous proxy settings and restore them exactly on teardown.
"""
from __future__ import annotations

import ctypes
import json
import os
import struct

from . import DATA_DIR, HTTP_PORT, SOCKS_PORT
from .log import get_logger

log = get_logger()


def _pack_connection_settings(server: str, bypass: str = "<local>") -> bytes:
    """Pack manual proxy configuration into Windows Connections binary format."""
    server_bytes = server.encode("ascii", "ignore")
    bypass_bytes = bypass.encode("ascii", "ignore")
    blob = bytearray()
    blob.extend(struct.pack("<III", 70, 1, 3))  # 70 bytes min header, counter 1, flags 3 (manual proxy)
    blob.extend(struct.pack("<I", len(server_bytes)))
    blob.extend(server_bytes)
    blob.extend(struct.pack("<I", len(bypass_bytes)))
    blob.extend(bypass_bytes)
    blob.extend(b"\x00" * 36)
    return bytes(blob)


def _pack_direct_settings() -> bytes:
    """Pack direct (no proxy) configuration into Windows Connections binary format."""
    blob = bytearray()
    blob.extend(struct.pack("<III", 70, 1, 1))  # flags 1 = direct connection
    blob.extend(struct.pack("<I", 0))
    blob.extend(struct.pack("<I", 0))
    blob.extend(b"\x00" * 36)
    return bytes(blob)

try:
    import winreg  # type: ignore
except ImportError:  # pragma: no cover - allows import on non-Windows for tests
    winreg = None  # type: ignore

_KEY = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
_STATE = os.path.join(DATA_DIR, "proxy_state.json")

_INTERNET_OPTION_SETTINGS_CHANGED = 39
_INTERNET_OPTION_REFRESH = 37


def _refresh() -> None:
    try:
        wininet = ctypes.windll.wininet
        wininet.InternetSetOptionW(0, _INTERNET_OPTION_SETTINGS_CHANGED, 0, 0)
        wininet.InternetSetOptionW(0, _INTERNET_OPTION_REFRESH, 0, 0)
    except Exception as exc:  # noqa: BLE001
        log.debug("proxy refresh notify failed: %s", exc)


def _get_user_keys(write_access: bool = False) -> list[tuple[int, str]]:
    """Get registry keys for HKEY_CURRENT_USER and any loaded user hives in HKEY_USERS.
    
    This ensures that when running elevated, we still apply settings to the 
    standard user's profile hive.
    """
    keys = []
    # Always include HKEY_CURRENT_USER
    keys.append((winreg.HKEY_CURRENT_USER, ""))
    
    # Enumerate loaded user hives in HKEY_USERS
    if winreg is not None:
        try:
            with winreg.OpenKey(winreg.HKEY_USERS, "", 0, winreg.KEY_READ) as hk_users:
                i = 0
                while True:
                    try:
                        subkey_name = winreg.EnumKey(hk_users, i)
                        # SIDs of real users start with S-1-5-21- and don't end in _Classes
                        if subkey_name.startswith("S-1-5-21-") and not subkey_name.endswith("_Classes"):
                            keys.append((winreg.HKEY_USERS, subkey_name))
                        i += 1
                    except OSError:
                        break
        except OSError:
            pass
    return keys


def _read_val(key, name: str):
    try:
        value, _typ = winreg.QueryValueEx(key, name)
        if isinstance(value, bytes):
            return value.hex()
        return value
    except FileNotFoundError:
        return None


def _save_current() -> None:
    try:
        state = {}
        for root, subkey in _get_user_keys(write_access=False):
            key_repr = subkey if subkey else "HKCU"
            path = f"{subkey}\\{_KEY}".strip("\\")
            try:
                with winreg.OpenKey(root, path, 0, winreg.KEY_READ) as k:
                    state[key_repr] = {
                        "ProxyEnable": _read_val(k, "ProxyEnable"),
                        "ProxyServer": _read_val(k, "ProxyServer"),
                        "AutoConfigURL": _read_val(k, "AutoConfigURL"),
                    }
                    try:
                        with winreg.OpenKey(root, path + "\\Connections", 0, winreg.KEY_READ) as ck:
                            state[key_repr]["DefaultConnectionSettings"] = _read_val(ck, "DefaultConnectionSettings")
                            state[key_repr]["SavedLegacySettings"] = _read_val(ck, "SavedLegacySettings")
                    except OSError:
                        pass
            except OSError:
                pass
        
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(_STATE, "w", encoding="utf-8") as fh:
            json.dump(state, fh)
    except OSError as exc:
        log.debug("could not save proxy state: %s", exc)


def enable(socks_port: int = SOCKS_PORT, http_port: int = HTTP_PORT) -> None:
    """Point the WinINET proxy at the local tor HTTP tunnel and SOCKS ports."""
    if winreg is None:
        return
    if not os.path.exists(_STATE):
        _save_current()
    # Configure both HTTP/HTTPS tunnel (for browser web traffic + remote DNS)
    # and SOCKS (for other tools).
    server = f"http=127.0.0.1:{http_port};https=127.0.0.1:{http_port};socks=127.0.0.1:{socks_port}"
    conn_blob = _pack_connection_settings(server)

    for root, subkey in _get_user_keys(write_access=True):
        path = f"{subkey}\\{_KEY}".strip("\\")
        try:
            with winreg.OpenKey(root, path, 0, winreg.KEY_SET_VALUE) as k:
                winreg.SetValueEx(k, "ProxyEnable", 0, winreg.REG_DWORD, 1)
                winreg.SetValueEx(k, "ProxyServer", 0, winreg.REG_SZ, server)
                try:
                    winreg.DeleteValue(k, "AutoConfigURL")
                except FileNotFoundError:
                    pass
            try:
                with winreg.OpenKey(root, path + "\\Connections", 0, winreg.KEY_SET_VALUE) as ck:
                    winreg.SetValueEx(ck, "DefaultConnectionSettings", 0, winreg.REG_BINARY, conn_blob)
                    winreg.SetValueEx(ck, "SavedLegacySettings", 0, winreg.REG_BINARY, conn_blob)
            except OSError:
                pass
        except OSError as exc:
            log.debug("failed to set proxy for key %s\\%s: %s", root, path, exc)

    _refresh()
    log.info("system proxy set to %s", server)


def disable() -> None:
    """Restore the user's previous proxy settings (or simply turn it off)."""
    if winreg is None:
        return
    prev = {}
    try:
        with open(_STATE, "r", encoding="utf-8") as fh:
            prev = json.load(fh)
    except (OSError, json.JSONDecodeError):
        prev = {}

    for root, subkey in _get_user_keys(write_access=True):
        key_repr = subkey if subkey else "HKCU"
        path = f"{subkey}\\{_KEY}".strip("\\")
        user_prev = prev.get(key_repr, {})
        try:
            with winreg.OpenKey(root, path, 0, winreg.KEY_SET_VALUE) as k:
                winreg.SetValueEx(k, "ProxyEnable", 0, winreg.REG_DWORD,
                                  int(user_prev.get("ProxyEnable") or 0))
                server = user_prev.get("ProxyServer")
                if server:
                    winreg.SetValueEx(k, "ProxyServer", 0, winreg.REG_SZ, server)
                else:
                    try:
                        winreg.DeleteValue(k, "ProxyServer")
                    except FileNotFoundError:
                        pass
                pac = user_prev.get("AutoConfigURL")
                if pac:
                    winreg.SetValueEx(k, "AutoConfigURL", 0, winreg.REG_SZ, pac)
                else:
                    try:
                        winreg.DeleteValue(k, "AutoConfigURL")
                    except OSError:
                        pass
            try:
                with winreg.OpenKey(root, path + "\\Connections", 0, winreg.KEY_SET_VALUE) as ck:
                    dcs = user_prev.get("DefaultConnectionSettings")
                    if dcs:
                        winreg.SetValueEx(ck, "DefaultConnectionSettings", 0, winreg.REG_BINARY, bytes.fromhex(dcs))
                    else:
                        winreg.SetValueEx(ck, "DefaultConnectionSettings", 0, winreg.REG_BINARY, _pack_direct_settings())

                    sls = user_prev.get("SavedLegacySettings")
                    if sls:
                        winreg.SetValueEx(ck, "SavedLegacySettings", 0, winreg.REG_BINARY, bytes.fromhex(sls))
                    else:
                        winreg.SetValueEx(ck, "SavedLegacySettings", 0, winreg.REG_BINARY, _pack_direct_settings())
            except OSError:
                pass
        except OSError:
            pass

    _refresh()
    try:
        os.remove(_STATE)
    except OSError:
        pass
    log.info("system proxy restored")


def is_set(socks_port: int = SOCKS_PORT, http_port: int = HTTP_PORT) -> bool:
    if winreg is None:
        return False
    for root, subkey in _get_user_keys(write_access=False):
        path = f"{subkey}\\{_KEY}".strip("\\")
        try:
            with winreg.OpenKey(root, path, 0, winreg.KEY_READ) as k:
                enable_val = _read_val(k, "ProxyEnable")
                server_val = str(_read_val(k, "ProxyServer") or "")
                if bool(enable_val) and (str(socks_port) in server_val or str(http_port) in server_val):
                    return True
        except OSError:
            pass
    return False
