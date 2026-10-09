#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
JNIDIR="$PROJECT_ROOT/app/src/main/jniLibs"
ASSETS="$PROJECT_ROOT/app/src/main/assets"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
ABIS=("arm64-v8a" "armeabi-v7a" "x86" "x86_64")
for abi in "${ABIS[@]}"; do mkdir -p "$JNIDIR/$abi"; done
mkdir -p "$ASSETS"

ORBOT_URL="https://github.com/guardianproject/orbot-android/releases/download/17.9.5-RC-1-tor-0.4.9.9/Orbot-17.9.5-RC-1-tor-0.4.9.9-fullperm-universal-release.apk"
EXPECTED_SHA256="9a5ac9d74d0ff0774ae58ed016cd2cb714fb03f11786e3becfadbefe2429421c"

echo "==> Downloading Orbot universal APK (ships tor 0.4.9.9)..."
echo "    $ORBOT_URL"
if ! curl -sSL --fail --max-time 180 -o "$TMP/orbot.apk" "$ORBOT_URL"; then
  echo "Failed to download Orbot APK." >&2
  exit 1
fi
echo "    downloaded: $(du -h "$TMP/orbot.apk" | cut -f1)"

echo "==> Verifying SHA-256 checksum..."
ACTUAL_SHA256="$(sha256sum "$TMP/orbot.apk" | cut -d' ' -f1)"
if [ "$ACTUAL_SHA256" != "$EXPECTED_SHA256" ]; then
  echo "ERROR: SHA-256 mismatch! File integrity check failed." >&2
  echo "  Expected: $EXPECTED_SHA256" >&2
  echo "  Actual:   $ACTUAL_SHA256" >&2
  exit 1
fi
echo "    Checksum OK: $ACTUAL_SHA256"

echo "==> Extracting libtor.so + libhev-socks5-tunnel.so + geoip databases..."
cd "$TMP"
unzip -o -q orbot.apk 'lib/*/libtor.so' 'lib/*/libhev-socks5-tunnel.so' 'assets/geoip' 'assets/geoip6' || {
  echo "unzip failed" >&2; exit 1
}

MISSING=0
for abi in "${ABIS[@]}"; do
  src="lib/$abi/libtor.so"
  if [[ -f "$src" ]]; then
    cp "$src" "$JNIDIR/$abi/libtor.so"
    echo "  -> $abi/libtor.so  ($(du -h "$JNIDIR/$abi/libtor.so" | cut -f1))"
  else
    echo "  ! ERROR: $abi: libtor.so not found in Orbot APK" >&2
    MISSING=1
  fi
  
  src_tunnel="lib/$abi/libhev-socks5-tunnel.so"
  if [[ -f "$src_tunnel" ]]; then
    cp "$src_tunnel" "$JNIDIR/$abi/libhev-socks5-tunnel.so"
    echo "  -> $abi/libhev-socks5-tunnel.so  ($(du -h "$JNIDIR/$abi/libhev-socks5-tunnel.so" | cut -f1))"
  else
    echo "  ! ERROR: $abi: libhev-socks5-tunnel.so not found in Orbot APK" >&2
    MISSING=1
  fi
done

if [ $MISSING -ne 0 ]; then
  echo "==> ERROR: Some required native libraries are missing. Cannot proceed." >&2
  exit 1
fi

if [[ -f "assets/geoip" ]]; then
  cp assets/geoip "$ASSETS/geoip"
  echo "  -> assets/geoip  ($(du -h "$ASSETS/geoip"  | cut -f1))"
fi
if [[ -f "assets/geoip6" ]]; then
  cp assets/geoip6 "$ASSETS/geoip6"
  echo "  -> assets/geoip6 ($(du -h "$ASSETS/geoip6" | cut -f1))"
fi

echo
echo "==> Done. You can now run:  ./gradlew assembleDebug"
