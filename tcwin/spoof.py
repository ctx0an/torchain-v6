"""Optional identity spoofing on Windows: MAC address (and a hostname note).

MAC spoofing on Windows is done by writing the ``NetworkAddress`` value under
the adapter's driver registry key and bouncing the adapter. We:
* only touch physical adapters,
* verify the change actually took effect (some NICs/hypervisors reject it) and
  roll back the interface if it did not, so we never knock the box offline,
* persist originals to ``spoof_state.json`` for exact restore on stop.

Hostname spoofing is intentionally a no-op + warning: renaming a Windows
machine requires a reboot, so it cannot be applied/reverted transiently the
way it can on Linux.
"""
from __future__ import annotations

import json
import os
import random

from . import DATA_DIR
from .log import get_logger
from .sysutil import powershell

log = get_logger()

_STATE = os.path.join(DATA_DIR, "spoof_state.json")

# Class GUID for network adapters in the Windows registry.
_NET_CLASS = "{4d36e972-e325-11ce-bfc1-08002be10318}"


def _save_state(state: dict) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(_STATE, "w", encoding="utf-8") as fh:
        json.dump(state, fh)


def _load_state() -> dict:
    try:
        with open(_STATE, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}


def random_mac() -> str:
    """Locally-administered, unicast MAC with no separators (Windows format)."""
    first = (random.randint(0, 255) & 0xFC) | 0x02
    octets = [first] + [random.randint(0, 255) for _ in range(5)]
    return "".join(f"{o:02X}" for o in octets)


# PowerShell that finds a NIC's driver registry instance by InterfaceGuid,
# sets (or clears) NetworkAddress, restarts the adapter and prints the result.
# Placeholders @NAME@ / @MAC@ / @CLASS@ are substituted with str.replace to
# avoid brace-escaping pitfalls. @MAC@ == 'RESTORE' clears the override.
_SET_MAC_PS = r"""
$ErrorActionPreference = 'SilentlyContinue'
$name  = '@NAME@'
$mac   = '@MAC@'
$root  = 'HKLM:\SYSTEM\CurrentControlSet\Control\Class\@CLASS@'
$a = Get-NetAdapter -Name $name
foreach ($i in (Get-ChildItem $root)) {
  $drv = (Get-ItemProperty -Path $i.PSPath -Name 'NetCfgInstanceId').NetCfgInstanceId
  if ($drv -eq $a.InterfaceGuid) {
    if ($mac -eq 'RESTORE') {
      Remove-ItemProperty -Path $i.PSPath -Name 'NetworkAddress' -ErrorAction SilentlyContinue
    } else {
      Set-ItemProperty -Path $i.PSPath -Name 'NetworkAddress' -Value $mac
    }
  }
}
Restart-NetAdapter -Name $name -Confirm:$false
Start-Sleep -Seconds 2
(Get-NetAdapter -Name $name).MacAddress
"""


def _adapters() -> list[dict]:
    proc = powershell(
        "Get-NetAdapter -Physical | Where-Object Status -ne 'Not Present' | "
        "Select-Object Name,MacAddress | ConvertTo-Json -Compress",
        timeout=30,
    )
    raw = (proc.stdout or "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else [data]


def _norm(mac: str) -> str:
    return mac.replace("-", "").replace(":", "").upper()


def _render(name: str, mac: str) -> str:
    # Escape single quotes in adapter names for PowerShell single-quoted string
    name_escaped = name.replace("'", "''")
    return (_SET_MAC_PS
            .replace("@NAME@", name_escaped)
            .replace("@MAC@", mac)
            .replace("@CLASS@", _NET_CLASS))


def _set_mac(name: str, mac: str) -> str:
    proc = powershell(_render(name, mac), timeout=60)
    out = (proc.stdout or "").strip().splitlines()
    return _norm(out[-1]) if out else ""


def spoof_mac() -> dict:
    state = _load_state()
    macs = state.get("macs", {})
    for ad in _adapters():
        name = ad.get("Name")
        original = _norm(ad.get("MacAddress", ""))
        if not name:
            continue
        new = random_mac()
        macs.setdefault(name, original)
        applied = _set_mac(name, new)
        if applied != _norm(new):
            log.warning("MAC change rejected on %s (NIC/hypervisor); reverting", name)
            _set_mac(name, "RESTORE")
            macs[name] = original
        else:
            log.info("spoofed %s %s -> %s", name, original, new)
    state["macs"] = macs
    _save_state(state)
    return state


def spoof_hostname(new_name: str | None = None) -> dict:
    log.warning("hostname spoofing is not supported transiently on Windows "
                "(a rename requires a reboot); skipping")
    return _load_state()


def restore() -> None:
    state = _load_state()
    for name in state.get("macs", {}):
        _set_mac(name, "RESTORE")
    try:
        os.remove(_STATE)
    except OSError:
        pass
    log.info("identity restored")
