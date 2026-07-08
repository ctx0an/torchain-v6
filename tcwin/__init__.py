"""torchain for Windows 11 - system-wide Tor anonymizer.

This is the native Windows 11 port of torchain. Because Windows has no
iptables transparent-proxy and no ``debian-tor`` user, the enforcement model
is different from the Linux build:

* tor runs as an ordinary (elevated) process exposing a local SOCKS + DNS port,
* the system WinINET proxy is pointed at tor's SOCKS port, and
* Windows Defender Firewall is switched to *block all outbound* except tor.exe
  itself - a fail-closed kill-switch that stops leaks from non-proxied apps.

Dependencies are installed via ``windows\\setup.bat`` (no package manager
required - Python is downloaded directly and tor.exe is extracted from the
bundled Tor.zip).
"""

__version__ = "5.0.0-win"
__appname__ = "torchain"

import os


def _program_data() -> str:
    return os.environ.get("ProgramData", r"C:\ProgramData")


# All persistent state lives under %ProgramData%\torchain so it is shared by
# the (elevated) service and the user-facing GUI.
BASE_DIR = os.environ.get("TORCHAIN_HOME", os.path.join(_program_data(), "torchain"))

CONFIG_DIR = os.environ.get("TORCHAIN_CONFIG_DIR", os.path.join(BASE_DIR, "config"))
DATA_DIR = os.environ.get("TORCHAIN_DATA_DIR", os.path.join(BASE_DIR, "data"))
LOG_DIR = os.environ.get("TORCHAIN_LOG_DIR", os.path.join(BASE_DIR, "logs"))
RUN_DIR = os.environ.get("TORCHAIN_RUN_DIR", os.path.join(BASE_DIR, "run"))

CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
TORRC_FILE = os.path.join(CONFIG_DIR, "torrc")
LOG_FILE = os.path.join(LOG_DIR, "torchain.log")
WATCHDOG_LOG = os.path.join(LOG_DIR, "watchdog.log")

# Where the package installs itself (used by the installer / launcher).
SHARE_DIR = os.path.join(_program_data(), "torchain", "app")

# Default local ports for the dedicated tor instance.
# NOTE: TransPort is intentionally absent - tor does not support transparent
# proxying on Windows. We rely on the SOCKS proxy + firewall kill-switch.
DNS_PORT = 9053
SOCKS_PORT = 9050
CONTROL_PORT = 9051
# Kept for config compatibility with the cross-platform Config dataclass; not
# used for transparent proxying on Windows.
TRANS_PORT = 9040

# Firewall rule name prefix so teardown is surgical.
FW_RULE_PREFIX = "torchain"
