#!/usr/bin/env bash
#
# torchain v5 installer. Idempotent and safe to re-run.
#
# It auto-elevates (so `./setup.sh` works without typing sudo yourself),
# installs dependencies, then hands off to the built-in migration manager,
# which removes ANY older torchain install and puts v5 in its place.
#
set -Eeuo pipefail

C_BLUE=$'\033[38;5;39m'; C_GREEN=$'\033[38;5;47m'; C_RED=$'\033[38;5;203m'; C_RST=$'\033[0m'
info() { echo "${C_BLUE}→${C_RST} $*"; }
ok()   { echo "${C_GREEN}✓${C_RST} $*"; }
die()  { echo "${C_RED}✗ $*${C_RST}" >&2; exit 1; }

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- fully automatic privilege elevation -----------------------------------
if [ "$(id -u)" -ne 0 ]; then
  if command -v sudo >/dev/null 2>&1; then
    info "elevating with sudo..."
    exec sudo -E bash "$SRC_DIR/setup.sh" "$@"
  elif command -v pkexec >/dev/null 2>&1; then
    exec pkexec bash "$SRC_DIR/setup.sh" "$@"
  else
    die "please run the installer as root: sudo ./setup.sh"
  fi
fi

SHARE_DIR="/usr/share/torchain"
BIN_LINK="/usr/local/bin/torchain"

install_deps() {
  # Core: tor + transports, firewall, python+tk for the GUI.
  # GUI elevation: xauth + xhost (X cookie handling) and polkit (pkexec prompt).
  local pkgs_apt="tor obfs4proxy iptables iproute2 python3 python3-tk xauth x11-xserver-utils polkitd pkexec"
  if command -v apt-get >/dev/null 2>&1; then
    info "installing dependencies via apt-get"
    # shellcheck disable=SC2086
    if apt-get update -y && apt-get install -y $pkgs_apt; then true; else die "dependency install failed"; fi
  elif command -v dnf >/dev/null 2>&1; then
    info "installing dependencies via dnf"
    dnf install -y tor obfs4 iptables iproute python3 python3-tkinter xorg-x11-xauth xorg-x11-server-utils polkit || die "dependency install failed"
  elif command -v pacman >/dev/null 2>&1; then
    info "installing dependencies via pacman"
    pacman -Sy --noconfirm tor obfs4proxy iptables iproute2 python tk xorg-xauth xorg-xhost polkit || die "dependency install failed"
  else
    info "unknown package manager - ensure tor, obfs4proxy, iptables, iproute2, python3, python3-tk, xauth, xhost and polkit are installed"
  fi
}

ensure_tor_user() {
  for u in debian-tor tor _tor; do
    if id "$u" >/dev/null 2>&1; then ok "tor user present: $u"; return; fi
  done
  info "creating system user 'debian-tor'"
  useradd --system --no-create-home --shell /usr/sbin/nologin debian-tor || true
}

migrate_and_install() {
  # The migration manager detects + removes older torchain installs (v3 'trc',
  # old layouts, stray binaries, services, configs) and installs v5 in place.
  info "running migration manager (removing any older torchain + installing v5)"
  PYTHONPATH="$SRC_DIR" python3 -m tc4 migrate || die "migration failed"

  mkdir -p /etc/torchain /var/lib/torchain/tor /var/log/torchain /run/torchain
  local toruser=debian-tor
  for u in debian-tor tor _tor; do id "$u" >/dev/null 2>&1 && toruser="$u" && break; done
  chown -R "$toruser:$toruser" /var/lib/torchain/tor || true
  chmod 700 /var/lib/torchain/tor
  if [ -f /usr/share/torchain/torchain ]; then
    ln -sf /usr/share/torchain/torchain /usr/bin/torchain 2>/dev/null || true
  fi
}

install_desktop_entry() {
  # Generate the icon and register a .desktop launcher so torchain shows up in
  # the application menu of any desktop environment (GNOME, KDE, XFCE, Kali, ...).
  local png="$SHARE_DIR/torchain.png"
  local apps_dir="/usr/share/applications"
  local desktop="$apps_dir/torchain.desktop"

  # 1) Render the app icon (pure-Python PNG).
  PYTHONPATH="$SHARE_DIR" python3 -c "from tc4 import icon; icon.write_png('$png', 128)" 2>/dev/null || true

  # 2) Install the icon into the hicolor theme so 'Icon=torchain' resolves by
  #    name in every environment (the most portable approach).
  for sz in 16 24 32 48 64 128 256; do
    local idir="/usr/share/icons/hicolor/${sz}x${sz}/apps"
    mkdir -p "$idir"
    PYTHONPATH="$SHARE_DIR" python3 -c "from tc4 import icon; icon.write_png('$idir/torchain.png', $sz)" 2>/dev/null || true
  done

  # 3) Write the desktop entry.
  mkdir -p "$apps_dir"
  cat > "$desktop" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=torchain
GenericName=Tor Anonymizer
Comment=Fast, system-wide Tor anonymizer with leak protection
Exec=$BIN_LINK gui
Icon=torchain
Terminal=false
Categories=Network;Security;System;
Keywords=tor;anonymity;privacy;vpn;proxy;security;
StartupNotify=true
EOF
  chmod 644 "$desktop"

  # 4) Refresh the desktop + icon caches so it appears immediately.
  command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$apps_dir" >/dev/null 2>&1 || true
  command -v gtk-update-icon-cache  >/dev/null 2>&1 && gtk-update-icon-cache -f -t /usr/share/icons/hicolor >/dev/null 2>&1 || true

  # 5) Validate the entry if the freedesktop tool is available.
  if command -v desktop-file-validate >/dev/null 2>&1; then
    if desktop-file-validate "$desktop" >/dev/null 2>&1; then ok "desktop entry installed and validated"; else ok "desktop entry installed"; fi
  else
    ok "desktop entry installed (will appear in the application menu)"
  fi
}

install_deps
ensure_tor_user
migrate_and_install
install_desktop_entry

echo
ok "torchain v5 installed."
echo "  Run a check : torchain doctor"
echo "  Connect    : torchain start        (auto-elevates)"
echo "  Dashboard  : torchain gui           (auto-elevates with X forwarding)"
echo "  Boot start : torchain boot enable"
echo "  Watchdog   : torchain watchdog start"
echo "  Bridges    : torchain bridge add '<bridge line>'"
