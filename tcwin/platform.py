"""Platform / environment detection for the Windows build.

Reports the Windows edition/build, whether the process is elevated, the
virtualization type (Hyper-V, VMware, VirtualBox, KVM, or physical) and the
list of physical network adapters. Callers use this for accurate guidance.
"""
from __future__ import annotations

import os
import platform as _py_platform
from dataclasses import dataclass, field

from .sysutil import is_admin, powershell


@dataclass
class Environment:
    virt: str           # "none", "vmware", "virtualbox", "hyper-v", "kvm", ...
    is_vm: bool
    is_admin: bool
    edition: str
    build: str
    interfaces: list = field(default_factory=list)


def detect_virt() -> str:
    try:
        proc = powershell(
            "(Get-CimInstance Win32_ComputerSystem).Manufacturer + '|' + "
            "(Get-CimInstance Win32_ComputerSystem).Model",
            timeout=20,
        )
        blob = (proc.stdout or "").strip().lower()
    except Exception:  # noqa: BLE001
        blob = ""
    if "vmware" in blob:
        return "vmware"
    if "virtualbox" in blob or "oracle" in blob:
        return "virtualbox"
    if "microsoft" in blob and ("virtual" in blob or "hyper" in blob):
        return "hyper-v"
    if "kvm" in blob or "qemu" in blob:
        return "kvm"
    if "xen" in blob:
        return "xen"
    return "none"


def list_interfaces() -> list:
    try:
        proc = powershell(
            "Get-NetAdapter -Physical | Where-Object Status -ne 'Not Present' "
            "| Select-Object -ExpandProperty Name",
            timeout=20,
        )
        return [n.strip() for n in (proc.stdout or "").splitlines() if n.strip()]
    except Exception:  # noqa: BLE001
        return []


def detect() -> Environment:
    virt = detect_virt()
    edition = ""
    try:
        edition = _py_platform.win32_edition() or ""
    except Exception:  # noqa: BLE001
        edition = ""
    build = _py_platform.version() or ""
    return Environment(
        virt=virt,
        is_vm=virt != "none",
        is_admin=is_admin(),
        edition=edition,
        build=build,
        interfaces=list_interfaces(),
    )


def describe(env: Environment | None = None) -> str:
    env = env or detect()
    kind = f"virtual machine ({env.virt})" if env.is_vm else "physical"
    elev = "elevated" if env.is_admin else "standard (not elevated)"
    ed = (env.edition + " ") if env.edition else ""
    return (f"Windows {ed}build {env.build}, {kind}, {elev}, "
            f"adapters: {', '.join(env.interfaces) or 'none'}")
