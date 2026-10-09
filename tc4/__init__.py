"""torchain v6 - high-performance, fully-automated system-wide Tor anonymizer.

v6 adds: enterprise gyroscopic HUD boot sequence, cyber-reactive buttons,
state pulse animations, and zero-idle CPU vector telemetry suite.
"""

__version__ = "6.0.0"
__appname__ = "torchain"

import os

CONFIG_DIR = os.environ.get("TORCHAIN_CONFIG_DIR", "/etc/torchain")
DATA_DIR = os.environ.get("TORCHAIN_DATA_DIR", "/var/lib/torchain")
LOG_DIR = os.environ.get("TORCHAIN_LOG_DIR", "/var/log/torchain")
RUN_DIR = os.environ.get("TORCHAIN_RUN_DIR", "/run/torchain")

CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
TORRC_FILE = os.path.join(CONFIG_DIR, "torrc")
LOG_FILE = os.path.join(LOG_DIR, "torchain.log")
WATCHDOG_LOG = os.path.join(LOG_DIR, "watchdog.log")

# Canonical install locations (used by the migration manager).
SHARE_DIR = "/usr/share/torchain"
BIN_LINK = "/usr/local/bin/torchain"
BIN_LINK_ALT = "/usr/bin/torchain"

# Default local ports for the dedicated tor instance.
TRANS_PORT = 9040
DNS_PORT = 5353
SOCKS_PORT = 9050
CONTROL_PORT = 9051
