#!/usr/bin/env bash
# setup.sh — run once to create a venv and install all dependencies

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

MIN_PY_MAJOR=3
MIN_PY_MINOR=10

echo ""
echo "  EMAIL ASSISTANT — Setup"
echo "  ========================"
echo ""

print_python_help() {
  cat <<'EOF'

  Install a supported Python on macOS:

    Option A — Homebrew:
      brew install python@3.12
      PYTHON="$(brew --prefix python@3.12)/bin/python3.12" ./setup.sh

    Option B — python.org:
      Download Python 3.12 from https://www.python.org/downloads/macos/
      /Library/Frameworks/Python.framework/Versions/3.12/bin/python3 ./setup.sh

  If an old virtual environment already exists, remove it after installing
  the correct Python:

      rm -rf .venv
      PYTHON=/path/to/python3.12 ./setup.sh

EOF
}

python_is_supported() {
  "$1" - "$MIN_PY_MAJOR" "$MIN_PY_MINOR" <<'PY'
import sys
min_major = int(sys.argv[1])
min_minor = int(sys.argv[2])
raise SystemExit(0 if sys.version_info >= (min_major, min_minor) else 1)
PY
}

python_version() {
  "$1" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')"
}

# ── Python check ─────────────────────────────────────────────────────────
PYTHON_BIN=""

if [ -n "${PYTHON:-}" ]; then
  if [ ! -x "$PYTHON" ]; then
    echo "[ERROR] PYTHON is set to '$PYTHON', but that file is not executable."
    print_python_help
    exit 1
  fi
  PYTHON_BIN="$PYTHON"
else
  for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
    if command -v "$candidate" >/dev/null 2>&1 && python_is_supported "$candidate"; then
      PYTHON_BIN="$(command -v "$candidate")"
      break
    fi
  done
fi

if [ -z "$PYTHON_BIN" ]; then
  echo "[ERROR] Python $MIN_PY_MAJOR.$MIN_PY_MINOR+ not found."
  if command -v python3 >/dev/null 2>&1; then
    echo "        Existing python3 is $(python_version "$(command -v python3)")"
  fi
  print_python_help
  exit 1
fi

if ! python_is_supported "$PYTHON_BIN"; then
  echo "[ERROR] Python $MIN_PY_MAJOR.$MIN_PY_MINOR+ is required; '$PYTHON_BIN' is $(python_version "$PYTHON_BIN")."
  print_python_help
  exit 1
fi

PY_VER=$(python_version "$PYTHON_BIN")
echo "  Python $PY_VER detected at $PYTHON_BIN"

# ── Virtual environment ───────────────────────────────────────────────────
if [ ! -d ".venv" ]; then
  echo "  Creating virtual environment…"
  "$PYTHON_BIN" -m venv .venv
else
  VENV_VER=$(.venv/bin/python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')" 2>/dev/null || true)
  if ! python_is_supported ".venv/bin/python"; then
    echo "[ERROR] Existing .venv uses unsupported Python ${VENV_VER:-unknown}."
    echo "        Remove it and run setup again with Python $MIN_PY_MAJOR.$MIN_PY_MINOR+:"
    echo ""
    echo "          rm -rf .venv"
    echo "          PYTHON=$PYTHON_BIN ./setup.sh"
    echo ""
    exit 1
  fi
  echo "  Reusing virtual environment with Python $VENV_VER"
fi

source .venv/bin/activate

echo "  Installing dependencies…"
if [ "${UPGRADE_PIP:-0}" = "1" ]; then
  python -m pip install --disable-pip-version-check --no-cache-dir --upgrade pip -q
fi
python -m pip install --disable-pip-version-check --no-cache-dir -r requirements.txt -q

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
