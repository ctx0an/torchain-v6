#!/usr/bin/env bash
#
# torchain internet recovery - pro-level, standalone, no-python fallback.
#
# Use this when torchain (or a crash) left the network broken: stale iptables
# rules redirecting everything into a dead tor TransPort, a fail-closed DROP
# still attached, a locked or loopback-only /etc/resolv.conf, a spoofed
# hostname, or interfaces left down. It is safe to run any time and as many
# times as you like - every step is best-effort and idempotent.
#
# It deliberately does NOT depend on torchain's python package, so it still
# works if the install itself is broken. (The GUI "Repair Internet" button and
# `torchain repair` use the same logic implemented in tc4/netfix.py.)
#
set -uo pipefail

C_BLUE=$'\033[38;5;39m'; C_GREEN=$'\033[38;5;47m'; C_RED=$'\033[38;5;203m'
C_AMBER=$'\033[38;5;214m'; C_RST=$'\033[0m'
info() { echo "${C_BLUE}→${C_RST} $*"; }
ok()   { echo "${C_GREEN}✓${C_RST} $*"; }
warn() { echo "${C_AMBER}!${C_RST} $*"; }

DATA_DIR="${TORCHAIN_DATA_DIR:-/var/lib/torchain}"
RESOLV="/etc/resolv.conf"
FALLBACK_DNS=("1.1.1.1" "9.9.9.9" "8.8.8.8")

have() { command -v "$1" >/dev/null 2>&1; }

# --- auto-elevate ----------------------------------------------------------
if [ "$(id -u)" -ne 0 ]; then
  if have sudo; then
    info "elevating with sudo..."
    exec sudo -E bash "$0" "$@"
  elif have pkexec; then
    exec pkexec bash "$0" "$@"
  else
    echo "${C_RED}✗ run me as root: sudo ./internet.sh${C_RST}" >&2
    exit 1
  fi
fi

# --- 1. tear down torchain's firewall surgically ---------------------------
info "removing torchain firewall chains..."
if have iptables; then
  for spec in "nat TORCHAIN" "filter TORCHAIN_OUT"; do
    table="${spec%% *}"
    chain="${spec##* }"
    # delete every OUTPUT jump (handles duplicates that used to strand a DROP)
    while iptables -t "$table" -C OUTPUT -j "$chain" 2>/dev/null; do
      iptables -t "$table" -D OUTPUT -j "$chain" 2>/dev/null || break
    done
    iptables -t "$table" -F "$chain" 2>/dev/null || true
    iptables -t "$table" -X "$chain" 2>/dev/null || true
  done
  # make sure nothing is left blocking egress
  for pol in INPUT OUTPUT FORWARD; do iptables -P "$pol" ACCEPT 2>/dev/null || true; done
  ok "iptables chains removed, policies set to ACCEPT"
fi
if have ip6tables; then
  for pol in INPUT OUTPUT FORWARD; do ip6tables -P "$pol" ACCEPT 2>/dev/null || true; done
  ok "ip6tables policies set to ACCEPT"
fi

# --- 2. fix DNS ------------------------------------------------------------
info "checking DNS..."
have chattr && chattr -i "$RESOLV" 2>/dev/null || true
dns_broken=1
if [ -f "$RESOLV" ]; then
  if grep -q '^nameserver' "$RESOLV" && grep '^nameserver' "$RESOLV" | grep -qvE '127\.0\.0\.1|::1'; then
    dns_broken=0
  fi
fi
if [ "$dns_broken" -eq 1 ]; then
  [ -f "$RESOLV" ] && [ ! -f "$RESOLV.torchain.bak" ] && cp -a "$RESOLV" "$RESOLV.torchain.bak" 2>/dev/null || true
  if { echo "# restored by torchain internet.sh"
       for ns in "${FALLBACK_DNS[@]}"; do echo "nameserver $ns"; done
     } > "$RESOLV" 2>/dev/null; then
    ok "resolv.conf restored"
  else
    warn "could not rewrite resolv.conf"
  fi
else
  ok "resolv.conf already valid"
fi

# --- 3. restore spoofed hostname + bring interfaces up ---------------------
if [ -f "$DATA_DIR/spoof_state.json" ] && have python3; then
  orig_host=$(python3 -c "import json,sys;print(json.load(open('$DATA_DIR/spoof_state.json')).get('hostname',''))" 2>/dev/null || true)
  if [ -n "${orig_host:-}" ]; then hostname "$orig_host" 2>/dev/null && ok "hostname restored to $orig_host" || true; fi
fi
if have ip; then
  for dev in /sys/class/net/*; do
    n=$(basename "$dev"); [ "$n" = "lo" ] && continue
    ip link set "$n" up 2>/dev/null || true
  done
  ok "network interfaces brought up"
fi

# --- 4. restart the network stack + flush caches ---------------------------
info "restarting network services..."
restarted=0
if have systemctl; then
  for svc in NetworkManager systemd-networkd networking wpa_supplicant; do
    if systemctl list-unit-files "$svc.service" >/dev/null 2>&1; then
      systemctl restart "$svc" 2>/dev/null && { ok "restarted $svc"; restarted=1; } || true
    fi
  done
  systemctl restart systemd-resolved 2>/dev/null || true
fi
have resolvectl && resolvectl flush-caches 2>/dev/null || true
have nscd && nscd -i hosts 2>/dev/null || true
if [ "$restarted" -eq 0 ] && have dhclient; then
  dhclient -r 2>/dev/null || true; dhclient 2>/dev/null || true
  ok "renewed DHCP leases"
fi

# --- 5. quick connectivity probe ------------------------------------------
echo
if have curl && curl -fsS --max-time 8 https://1.1.1.1 >/dev/null 2>&1; then
  ok "internet is back - connectivity confirmed."
elif have ping && ping -c1 -W3 1.1.1.1 >/dev/null 2>&1; then
  ok "internet is back - reachable (DNS may still be settling)."
else
  warn "could not confirm connectivity yet - give it a few seconds, then retry."
fi
