"""Platform / environment detection so torchain works on both VMs and
bare-metal Linux without surprises.

We detect the init system (systemd vs other), the virtualization type
(VMware, VirtualBox, KVM, Xen, container, or physical), and the available
network interfaces. Callers use this to choose safe defaults and to give the
user accurate guidance.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from .sysutil import read_first_line, run, which


@dataclass
class Environment:
    virt: str          # e.g. "none" (bare metal), "vmware", "kvm", "oracle", "docker"
    is_vm: bool
    is_container: bool
    has_systemd: bool
    interfaces: list


_CONTAINER_VIRTS = {"docker", "lxc", "lxc-libvirt", "openvz", "podman", "systemd-nspawn", "wsl"}


def detect_virt() -> str:
    # Preferred: systemd-detect-virt (handles VM + container in one shot).
    if which("systemd-detect-virt"):
        try:
            proc = run(["systemd-detect-virt"], check=False, timeout=5)
            out = (proc.stdout or "").strip()
            if out:
                return out
        except Exception:  # noqa: BLE001
            pass
    # Fallback: DMI product name hints.
    product = read_first_line("/sys/class/dmi/id/product_name").lower()
    vendor = read_first_line("/sys/class/dmi/id/sys_vendor").lower()
    blob = f"{product} {vendor}"
    if "vmware" in blob:
        return "vmware"
    if "virtualbox" in blob or "oracle" in blob:
        return "oracle"
    if "kvm" in blob or "qemu" in blob:
        return "kvm"
    if "xen" in blob:
        return "xen"
    if "microsoft" in blob or "hyper-v" in blob:
        return "microsoft"
    # Container hints.
    if os.path.exists("/.dockerenv"):
        return "docker"
    if "microsoft" in read_first_line("/proc/version").lower():
        return "wsl"
    return "none"


def list_interfaces() -> list:
    try:
        names = sorted(os.listdir("/sys/class/net"))
    except OSError:
        return []
    return [n for n in names if n != "lo"]


def detect() -> Environment:
    virt = detect_virt()
    is_container = virt in _CONTAINER_VIRTS
    is_vm = virt != "none" and not is_container
    has_systemd = os.path.isdir("/run/systemd/system") or which("systemctl") is not None
    return Environment(
        virt=virt,
        is_vm=is_vm,
        is_container=is_container,
        has_systemd=has_systemd,
        interfaces=list_interfaces(),
    )


def describe(env: Environment | None = None) -> str:
    env = env or detect()
    if env.is_container:
        kind = f"container ({env.virt})"
    elif env.is_vm:
        kind = f"virtual machine ({env.virt})"
    else:
        kind = "bare-metal"
    init = "systemd" if env.has_systemd else "non-systemd"
    return f"{kind}, {init}, interfaces: {', '.join(env.interfaces) or 'none'}"
