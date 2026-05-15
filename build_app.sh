#!/usr/bin/env bash
# build_app.sh — build Email Assistant.app for macOS
# Usage: ./build_app.sh
# Output: dist/Email Assistant.app
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "==> Activating venv"
if [ ! -d ".venv" ]; then
  echo "No .venv found — run ./setup.sh first."
  exit 1
fi
source .venv/bin/activate

echo "==> Installing build dependencies"
pip install --quiet pyinstaller pywebview

echo "==> Cleaning previous build"
rm -rf build dist

echo "==> Embedding version from git tag"
TAG="${GITHUB_REF_NAME:-}"
if [[ "$TAG" != v* ]]; then
  TAG=$(git describe --tags --abbrev=0 2>/dev/null || echo "")
fi
if [[ "$TAG" == v* ]]; then
  VERSION="${TAG#v}"
else
  VERSION="0.0.0"
fi
echo "__version__ = \"$VERSION\"" > version.py
echo "    version: $VERSION"

echo "==> Running PyInstaller"
pyinstaller EmailAssistant.spec

echo ""
echo "==> Build complete!"
echo "    App: $(pwd)/dist/Email Assistant.app"
echo ""
echo "To run:"
echo "    open \"dist/Email Assistant.app\""
echo ""
echo "To distribute:"
echo "    Copy 'dist/Email Assistant.app'."
echo "    Config and local runtime data live in ~/Library/Application Support/Email Assistant/."
echo ""
