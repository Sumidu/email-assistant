#!/usr/bin/env bash
# deploy.sh — build and install Email Assistant.app to /Applications
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

APP_NAME="Email Assistant.app"
DIST_PATH="$SCRIPT_DIR/dist/$APP_NAME"
INSTALL_PATH="/Applications/$APP_NAME"

echo "==> Building app"
bash "$SCRIPT_DIR/build_app.sh"

if [ ! -d "$DIST_PATH" ]; then
  echo "Build failed — $DIST_PATH not found."
  exit 1
fi

echo "==> Installing to $INSTALL_PATH (requires sudo)"
sudo rm -rf "$INSTALL_PATH"
sudo cp -r "$DIST_PATH" "$INSTALL_PATH"

echo ""
echo "==> Installed: $INSTALL_PATH"
echo "    Run: open \"/Applications/$APP_NAME\""
echo ""
