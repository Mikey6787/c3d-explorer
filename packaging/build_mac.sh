#!/bin/bash
# ==============================================================================
# C3D Explorer - macOS Native App & DMG Packager
# Builds a standalone macOS application (.app) and drag-and-drop DMG installer
# ==============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

echo "=========================================="
echo " Packaging C3D Explorer for macOS"
echo "=========================================="

# 1. Generate multi-resolution app.icns if needed
ICNS_FILE="assets/icons/app.icns"
PNG_FILE="assets/icons/AppIcon-Dark.png"

if [ -f "$PNG_FILE" ]; then
    echo "[1/4] Generating native macOS iconset (app.icns)..."
    ICONSET="AppIcon.iconset"
    rm -rf "$ICONSET"
    mkdir -p "$ICONSET"
    sips -z 16 16     "$PNG_FILE" --out "$ICONSET/icon_16x16.png" > /dev/null
    sips -z 32 32     "$PNG_FILE" --out "$ICONSET/icon_16x16@2x.png" > /dev/null
    sips -z 32 32     "$PNG_FILE" --out "$ICONSET/icon_32x32.png" > /dev/null
    sips -z 64 64     "$PNG_FILE" --out "$ICONSET/icon_32x32@2x.png" > /dev/null
    sips -z 128 128   "$PNG_FILE" --out "$ICONSET/icon_128x128.png" > /dev/null
    sips -z 256 256   "$PNG_FILE" --out "$ICONSET/icon_128x128@2x.png" > /dev/null
    sips -z 256 256   "$PNG_FILE" --out "$ICONSET/icon_256x256.png" > /dev/null
    sips -z 512 512   "$PNG_FILE" --out "$ICONSET/icon_256x256@2x.png" > /dev/null
    sips -z 512 512   "$PNG_FILE" --out "$ICONSET/icon_512x512.png" > /dev/null
    sips -z 1024 1024 "$PNG_FILE" --out "$ICONSET/icon_512x512@2x.png" > /dev/null
    iconutil -c icns "$ICONSET" -o "$ICNS_FILE"
    rm -rf "$ICONSET"
    echo "       ✓ Generated $ICNS_FILE"
fi

# 2. Build standalone .app with PyInstaller
echo "[2/4] Running PyInstaller..."

if command -v pyinstaller &> /dev/null; then
    PYINSTALLER_BIN="pyinstaller"
elif python3 -m PyInstaller --version &> /dev/null; then
    PYINSTALLER_BIN="python3 -m PyInstaller"
elif [ -f "/opt/homebrew/bin/python3" ] && /opt/homebrew/bin/python3 -m PyInstaller --version &> /dev/null; then
    PYINSTALLER_BIN="/opt/homebrew/bin/python3 -m PyInstaller"
else
    echo "Installing PyInstaller..."
    python3 -m pip install pyinstaller || pip install pyinstaller
    PYINSTALLER_BIN="pyinstaller"
fi

$PYINSTALLER_BIN --clean --distpath dist --workpath build packaging/c3d_explorer.spec

APP_PATH="dist/C3D Explorer.app"
if [ ! -d "$APP_PATH" ]; then
    echo "Error: $APP_PATH was not created!"
    exit 1
fi
echo "       ✓ Built $APP_PATH"

# 3. Create DMG staging folder with Applications symlink
echo "[3/4] Preparing Drag-and-Drop Disk Image..."
DMG_STAGING="dist/dmg_staging"
rm -rf "$DMG_STAGING"
mkdir -p "$DMG_STAGING"
cp -R "$APP_PATH" "$DMG_STAGING/"
ln -s /Applications "$DMG_STAGING/Applications"

# 4. Create final compressed DMG
mkdir -p dist_dmg
OUTPUT_DMG="dist_dmg/C3D_Explorer_Mac.dmg"
rm -f "$OUTPUT_DMG"

echo "[4/4] Creating compressed DMG with hdiutil..."
hdiutil create \
    -volname "C3D Explorer" \
    -srcfolder "$DMG_STAGING" \
    -ov \
    -format UDZO \
    "$OUTPUT_DMG"

rm -rf "$DMG_STAGING"

echo "=========================================="
echo " macOS Packaging Complete!"
echo " Output DMG: $OUTPUT_DMG"
ls -lh "$OUTPUT_DMG"
echo "=========================================="
