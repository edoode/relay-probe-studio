#!/bin/zsh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_NAME="${APP_NAME:-中转稳定性检测}"
BUNDLE_DIR="$SCRIPT_DIR/$APP_NAME.app"
CONTENTS_DIR="$BUNDLE_DIR/Contents"
MACOS_DIR="$CONTENTS_DIR/MacOS"
RESOURCES_DIR="$CONTENTS_DIR/Resources"
PAYLOAD_DIR="$RESOURCES_DIR/app"
ICON_SOURCE="$SCRIPT_DIR/图标.png"
ICON_NAME="AppIcon"
LAUNCHER_NAME="relay-probe-launcher"

TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/relay-probe-build.XXXXXX")"
ICONSET_DIR="$TMP_DIR/${ICON_NAME}.iconset"
SQUARE_ICON="$TMP_DIR/icon-square.png"

cleanup() {
  rm -rf "$TMP_DIR"
}

trap cleanup EXIT

build_icon() {
  mkdir -p "$ICONSET_DIR"

  read -r pixel_width pixel_height < <(
    /usr/bin/sips -g pixelWidth -g pixelHeight "$ICON_SOURCE" |
      /usr/bin/awk '/pixelWidth/ {w=$2} /pixelHeight/ {h=$2} END {print w, h}'
  )

  min_side=$(( pixel_width < pixel_height ? pixel_width : pixel_height ))
  /usr/bin/sips -c "$min_side" "$min_side" "$ICON_SOURCE" --out "$SQUARE_ICON" >/dev/null

  make_icon() {
    local size="$1"
    local filename="$2"
    /usr/bin/sips -z "$size" "$size" "$SQUARE_ICON" --out "$ICONSET_DIR/$filename" >/dev/null
  }

  make_icon 16 icon_16x16.png
  make_icon 32 icon_16x16@2x.png
  make_icon 32 icon_32x32.png
  make_icon 64 icon_32x32@2x.png
  make_icon 128 icon_128x128.png
  make_icon 256 icon_128x128@2x.png
  make_icon 256 icon_256x256.png
  make_icon 512 icon_256x256@2x.png
  make_icon 512 icon_512x512.png
  make_icon 1024 icon_512x512@2x.png
}

rm -rf "$BUNDLE_DIR"
mkdir -p "$MACOS_DIR" "$RESOURCES_DIR" "$PAYLOAD_DIR"

if [[ -f "$ICON_SOURCE" ]]; then
  build_icon
  /usr/bin/iconutil -c icns "$ICONSET_DIR" -o "$RESOURCES_DIR/$ICON_NAME.icns"
else
  echo "Icon not found at $ICON_SOURCE"
  echo "Building app without a custom icon."
fi

/usr/bin/ditto "$SCRIPT_DIR/web" "$PAYLOAD_DIR/web"
/bin/cp "$SCRIPT_DIR/probe_web.py" "$PAYLOAD_DIR/probe_web.py"
/bin/cp "$SCRIPT_DIR/relay_probe.py" "$PAYLOAD_DIR/relay_probe.py"
/bin/cp "$SCRIPT_DIR/app_launcher.sh" "$MACOS_DIR/$LAUNCHER_NAME"
/bin/chmod +x "$MACOS_DIR/$LAUNCHER_NAME"

cat > "$CONTENTS_DIR/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleDevelopmentRegion</key>
  <string>zh_CN</string>
  <key>CFBundleDisplayName</key>
  <string>${APP_NAME}</string>
  <key>CFBundleExecutable</key>
  <string>${LAUNCHER_NAME}</string>
$(if [[ -f "$ICON_SOURCE" ]]; then cat <<ICON
  <key>CFBundleIconFile</key>
  <string>${ICON_NAME}</string>
ICON
fi)
  <key>CFBundleIdentifier</key>
  <string>dev.zeusy.relay-probe-studio</string>
  <key>CFBundleInfoDictionaryVersion</key>
  <string>6.0</string>
  <key>CFBundleName</key>
  <string>${APP_NAME}</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>1.0</string>
  <key>CFBundleVersion</key>
  <string>1</string>
  <key>LSMinimumSystemVersion</key>
  <string>13.0</string>
  <key>NSHighResolutionCapable</key>
  <true/>
</dict>
</plist>
EOF

echo "Built app bundle:"
echo "$BUNDLE_DIR"
