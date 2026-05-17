"""
main.py — Email Assistant (multi-account)
Run with: python main.py
Then open: http://localhost:5100
"""

import os
import sys
import logging
from datetime import datetime

from app import create_app
from app import runtime


# Resolve base dir so templates/static files are found in dev and PyInstaller.
BASE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))

runtime.init(BASE_DIR)

config = runtime.config
app = create_app(BASE_DIR)


if __name__ == "__main__":
    port = config.get("app", {}).get("port", 5100)
    acct_count = len(config.get("accounts", []))
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    print(f"\n*****************************************************")
    print(f"\n Email Assistant — {acct_count} account(s) configured")
    print(f" http://localhost:{port}")
    print(f" Started at {datetime.now().strftime('%H:%M:%S')}\n")
    app.run(debug=False, port=port, threaded=True)
