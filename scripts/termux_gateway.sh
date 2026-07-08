#!/data/data/com.termux/files/usr/bin/bash

# Torchain - Termux Gateway Server Setup Script
# This script configures your Android device (running Termux) as a Tor gateway.
# Other devices on the same Wi-Fi network can route their traffic through this device.

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0;0m'

echo -e "${BLUE}==================================================${NC}"
echo -e "${GREEN}    Torchain — Termux Tor Gateway Installer       ${NC}"
echo -e "${BLUE}==================================================${NC}"

# 1. Install required packages
echo -e "\n[*] Updating packages and installing Tor & Privoxy..."
pkg update -y
pkg install -y tor privoxy iproute2

# 2. Determine local IP address
echo -e "\n[*] Detecting network interfaces..."
LOCAL_IP=""
if command -v python3 >/dev/null 2>&1; then
    LOCAL_IP=$(python3 -c "import socket; s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(('8.8.8.8', 80)); print(s.getsockname()[0]); s.close()" 2>/dev/null)
fi
if [ -z "$LOCAL_IP" ]; then
    LOCAL_IP=$(ip -o -4 addr show | awk '{print $4}' | cut -d/ -f1 | grep -v '127.0.0.1' | head -n 1)
fi

if [ -z "$LOCAL_IP" ]; then
    echo -e "${RED}[!] Warning: Could not auto-detect local IP address. Are you connected to Wi-Fi?${NC}"
    LOCAL_IP="0.0.0.0"
else
    echo -e "${GREEN}[+] Detected Local IP: $LOCAL_IP${NC}"
fi

# Create config directories
CONF_DIR="$HOME/.config/torchain-gateway"
mkdir -p "$CONF_DIR"

# 3. Write torrc configuration
TORRC_PATH="$CONF_DIR/torrc"
echo -e "[*] Writing Tor configuration to $TORRC_PATH..."
cat << EOF > "$TORRC_PATH"
# Torchain Termux Gateway torrc
DataDirectory $CONF_DIR/tor_data
AvoidDiskWrites 1

# Listen on all interfaces so local network devices can connect
SocksPort 0.0.0.0:9050
DNSPort 0.0.0.0:5400

# Security: Only allow local network subnets to connect
SocksPolicy accept 192.168.0.0/16
SocksPolicy accept 10.0.0.0/8
SocksPolicy accept 172.16.0.0/12
SocksPolicy reject *
EOF

# 4. Write Privoxy configuration (converts SOCKS5 to HTTP proxy for devices that don't support SOCKS5)
PRIVOXY_CONF_PATH="$CONF_DIR/privoxy.conf"
TERMUX_PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
echo -e "[*] Writing Privoxy configuration to $PRIVOXY_CONF_PATH..."
cat << EOF > "$PRIVOXY_CONF_PATH"
# Torchain Termux Gateway Privoxy Config
confdir $TERMUX_PREFIX/etc/privoxy
logdir $CONF_DIR
logfile privoxy.log

# Listen on all interfaces on port 8118
listen-address  0.0.0.0:8118

# Forward all traffic to the local Tor SOCKS5 proxy
forward-socks5t / 127.0.0.1:9050 .

# Toggle filters
toggle  1
enable-remote-toggle  0
enable-remote-http-toggle  0
enable-edit-actions 0
buffer-limit 4096
keep-alive-timeout 5
socket-timeout 300
EOF

# 5. Create start script
START_SCRIPT="$HOME/start-gateway.sh"
echo -e "[*] Creating start script at $START_SCRIPT..."
cat << 'EOF' > "$START_SCRIPT"
#!/data/data/com.termux/files/usr/bin/bash
CONF_DIR="$HOME/.config/torchain-gateway"

# Helper to check if a port is open
is_port_open() {
  local host="$1"
  local port="$2"
  (echo > "/dev/tcp/$host/$port") >/dev/null 2>&1
}

echo "Starting Torchain Gateway..."
# Kill any existing instances
killall tor 2>/dev/null || true
killall privoxy 2>/dev/null || true

# Start Tor
tor -f "$CONF_DIR/torrc" --RunAsDaemon 1

# Wait for Tor ports to open (SOCKS on 9050, DNS on 5400)
echo "Waiting for Tor to start..."
tor_ok=0
for i in {1..30}; do
  if is_port_open "127.0.0.1" 9050 && is_port_open "127.0.0.1" 5400; then
    tor_ok=1
    break
  fi
  sleep 0.5
done

if [ "$tor_ok" -ne 1 ]; then
  echo "ERROR: Tor failed to start within 15 seconds. Check Tor logs or try running manually: tor -f $CONF_DIR/torrc" >&2
  killall tor 2>/dev/null || true
  exit 1
fi

# Start Privoxy
privoxy "$CONF_DIR/privoxy.conf"

# Wait for Privoxy port to open (HTTP on 8118)
echo "Waiting for Privoxy to start..."
privoxy_ok=0
for i in {1..10}; do
  if is_port_open "127.0.0.1" 8118; then
    privoxy_ok=1
    break
  fi
  sleep 0.5
done

if [ "$privoxy_ok" -ne 1 ]; then
  echo "ERROR: Privoxy failed to start. Port 8118 might be in use." >&2
  killall tor privoxy 2>/dev/null || true
  exit 1
fi

# Determine active local IP address dynamically
LOCAL_IP=""
if command -v python3 >/dev/null 2>&1; then
  LOCAL_IP=$(python3 -c "import socket; s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(('8.8.8.8', 80)); print(s.getsockname()[0]); s.close()" 2>/dev/null)
fi
if [ -z "$LOCAL_IP" ]; then
  LOCAL_IP=$(ip -o -4 addr show | awk '{print $4}' | cut -d/ -f1 | grep -v '127.0.0.1' | head -n 1)
fi
if [ -z "$LOCAL_IP" ]; then
  LOCAL_IP="0.0.0.0"
fi

echo "=================================================="
echo " Torchain Gateway is now RUNNING!"
echo "=================================================="
echo " Your Gateway IP: $LOCAL_IP"
echo "--------------------------------------------------"
echo " Configure other devices on your Wi-Fi network to:"
echo "   - HTTP Proxy:   $LOCAL_IP : 8118"
echo "   - SOCKS5 Proxy: $LOCAL_IP : 9050"
echo "   - DNS Server:   $LOCAL_IP : 5400"
echo "--------------------------------------------------"
echo " To stop the gateway, run: killall tor privoxy"
echo "=================================================="
EOF
chmod +x "$START_SCRIPT"

echo -e "${GREEN}\n[+] Setup Complete!${NC}"
echo -e "To start your Tor gateway server, run: ${BLUE}~/start-gateway.sh${NC}"
echo -e "${BLUE}==================================================${NC}"
