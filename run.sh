#!/usr/bin/env bash
# run.sh — activate venv and start the server

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -d ".venv" ]; then
  echo "[!] Run ./setup.sh first."
  exit 1
fi

source .venv/bin/activate

echo ""
echo "  Starting Email Assistant…"
echo "  Open: http://localhost:5100"
echo "  Press Ctrl+C to stop."
echo ""

python main.py
