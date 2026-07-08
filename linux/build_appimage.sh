#!/usr/bin/env bash
# ============================================================================
#  torchain - Build portable AppImage for Linux
#
#  Creates a single-file AppImage that runs on most Linux distros without
#  installation. Requires: Python 3.9+, PyInstaller, appimagetool.
#
#  Output: dist/Torchain-x86_64.AppImage
# ============================================================================
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$REPO_ROOT"

C_BLUE='\033[38;5;39m'; C_GREEN='\033[38;5;47m'; C_RED='\033[38;5;203m'; C_RST='\033[0m'
info() { echo -e "${C_BLUE}→${C_RST} $*"; }
ok()   { echo -e "${C_GREEN}✓${C_RST} $*"; }
die()  { echo -e "${C_RED}✗ $*${C_RST}" >&2; exit 1; }

# --- Check dependencies ---
info "checking build dependencies..."
for cmd in python3 pip3; do
    command -v "$cmd" >/dev/null 2>&1 || die "'$cmd' not found. Install Python 3.9+."
done

# --- Install/upgrade PyInstaller ---
info "ensuring PyInstaller is installed..."
pip3 install --upgrade --user pyinstaller 2>/dev/null || pip3 install --upgrade pyinstaller

# --- Clean previous build ---
info "cleaning previous build..."
rm -rf build/ dist/

# --- Build with PyInstaller ---
info "building with PyInstaller..."
python3 -m PyInstaller --noconfirm linux/torchain_portable.spec

DIST_DIR="dist/torchain"
[ -d "$DIST_DIR" ] || die "PyInstaller output not found at $DIST_DIR"

# --- Create AppDir structure ---
info "creating AppDir..."
APPDIR="dist/Torchain.AppDir"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin"
mkdir -p "$APPDIR/usr/share/torchain"
mkdir -p "$APPDIR/usr/share/applications"
mkdir -p "$APPDIR/usr/share/icons/hicolor/256x256/apps"

# Copy PyInstaller output
cp -a "$DIST_DIR"/* "$APPDIR/usr/share/torchain/"

# Create launcher script
cat > "$APPDIR/usr/bin/torchain" << 'LAUNCHER'
#!/usr/bin/env bash
# Add bundled tor to PATH so it's found by the engine
APP_DIR="$(dirname "$(readlink -f "$0")")/../share/torchain"
export PATH="$APP_DIR:$PATH"
exec "$APP_DIR/torchain" "$@"
LAUNCHER
chmod +x "$APPDIR/usr/bin/torchain"

# Symlink AppRun -> torchain
ln -sf usr/bin/torchain "$APPDIR/AppRun"

# --- Generate icon ---
info "generating app icon..."
ICON_256="$APPDIR/usr/share/icons/hicolor/256x256/apps/torchain.png"
ICON_ROOT="$APPDIR/torchain.png"

# Generate using the pure-Python icon module (no external deps needed)
python3 -c "
import sys, os
sys.path.insert(0, '$REPO_ROOT')
from tc4.icon import render
import struct, zlib

def write_png(path, size):
    data = render(size)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(data)

write_png('$ICON_256', 256)
write_png('$ICON_ROOT', 256)
print('icon generated (256x256)')
" 2>&1 || {
    # Fallback: use docs/torchain-icon.png if it exists
    if [ -f "$REPO_ROOT/docs/torchain-icon.png" ]; then
        info "using docs/torchain-icon.png as fallback"
        cp "$REPO_ROOT/docs/torchain-icon.png" "$ICON_256"
        cp "$REPO_ROOT/docs/torchain-icon.png" "$ICON_ROOT"
    else
        die "Failed to generate icon and no fallback found. Place a 256x256 torchain.png in docs/"
    fi
}

# Also generate smaller sizes for hicolor
for sz in 16 24 32 48 64 128; do
    python3 -c "
import sys; sys.path.insert(0, '$REPO_ROOT')
from tc4.icon import render
with open('$APPDIR/usr/share/icons/hicolor/${sz}x${sz}/apps/torchain.png', 'wb') as f:
    f.write(render($sz))
" 2>/dev/null || true
done

# --- Desktop entry ---
cat > "$APPDIR/torchain.desktop" << 'EOF'
[Desktop Entry]
Type=Application
Version=1.0
Name=torchain
GenericName=Tor Anonymizer
Comment=Fast, system-wide Tor anonymizer with leak protection
Exec=torchain gui
Icon=torchain
Terminal=false
Categories=Network;Security;System;
Keywords=tor;anonymity;privacy;proxy;security;
StartupNotify=true
EOF

cp "$APPDIR/torchain.desktop" "$APPDIR/usr/share/applications/torchain.desktop"

# --- Create AppImage ---
ARCH="$(uname -m)"
APPIMAGE_NAME="Torchain-${ARCH}.AppImage"

# appimagetool needs FUSE to mount itself; in CI (GitHub Actions) FUSE is not
# available, so we use --appimage-extract-and-run or the env var.
if [ "${CI:-}" = "true" ]; then
    export APPIMAGE_EXTRACT_AND_RUN=1
fi

if command -v appimagetool >/dev/null 2>&1; then
    info "creating AppImage..."
    appimagetool --no-appstream "$APPDIR" "dist/$APPIMAGE_NAME"
elif [ -x "$HOME/.local/bin/appimagetool" ]; then
    info "creating AppImage..."
    "$HOME/.local/bin/appimagetool" --no-appstream "$APPDIR" "dist/$APPIMAGE_NAME"
else
    info "appimagetool not found — downloading..."
    AIO_URL="https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-${ARCH}.AppImage"
    curl -fsSL "$AIO_URL" -o /tmp/appimagetool
    chmod +x /tmp/appimagetool
    /tmp/appimagetool --no-appstream "$APPDIR" "dist/$APPIMAGE_NAME"
fi

# --- Done ---
if [ -f "dist/$APPIMAGE_NAME" ]; then
    SIZE=$(du -h "dist/$APPIMAGE_NAME" | cut -f1)
    ok "Build successful!"
    echo
    echo "  Output: dist/$APPIMAGE_NAME"
    echo "  Size:   $SIZE"
    echo
    echo "  To use:"
    echo "    chmod +x dist/$APPIMAGE_NAME"
    echo "    sudo ./dist/$APPIMAGE_NAME start    # route traffic through Tor"
    echo "    sudo ./dist/$APPIMAGE_NAME gui       # launch dashboard"
    echo
    echo "  No installation needed. Just run the AppImage."
else
    die "AppImage creation failed"
fi
