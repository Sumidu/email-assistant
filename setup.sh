#!/usr/bin/env bash
# setup.sh — run once to create a venv and install all dependencies

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "  EMAIL ASSISTANT — Setup"
echo "  ========================"
echo ""

# ── Python check ─────────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
  echo "[ERROR] python3 not found. Install Python 3.10+ from python.org"
  exit 1
fi

PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "  Python $PY_VER detected"

# ── Virtual environment ───────────────────────────────────────────────────
if [ ! -d ".venv" ]; then
  echo "  Creating virtual environment…"
  python3 -m venv .venv
fi

source .venv/bin/activate

echo "  Installing dependencies (this may take a few minutes for Whisper)…"
pip install --upgrade pip -q
pip install -r requirements.txt -q

# ── Config ────────────────────────────────────────────────────────────────
CONFIG_DIR="$HOME/email_assistant"
CONFIG_PATH="$CONFIG_DIR/config.json"
mkdir -p "$CONFIG_DIR"

if [ ! -f "$CONFIG_PATH" ]; then
  cp config.json.example "$CONFIG_PATH"
  echo ""
  echo "  [!] Config created from example:"
  echo "      $CONFIG_PATH"
  echo "      You can also configure accounts from Settings in the app."
  echo ""
else
  echo "  Config already exists — skipping: $CONFIG_PATH"
fi

# ── Knowledge dir ─────────────────────────────────────────────────────────
mkdir -p "$CONFIG_DIR/knowledge"
echo "  Knowledge directory: $CONFIG_DIR/knowledge"

echo ""
echo "  Setup complete!"
echo ""
echo "  Next steps:"
echo "    1. Start the app and open Settings to add your email account"
echo "    2. Start LM Studio and load a model (server on port 1234)"
echo "    3. Run:  ./run.sh"
echo ""
