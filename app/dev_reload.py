"""
Dev-only hot-reload watcher.

Polls for a LOCALUPDATE file in the project root. When found, starts a fresh
replacement process then immediately exits. Using subprocess.Popen (close_fds=True
by default) means the new process does not inherit the Flask socket, so it can
bind port 5100 cleanly once the old process exits.

Only active outside a frozen PyInstaller bundle (i.e. during `python main.py`).
"""

import os
import subprocess
import sys
import threading
import time

from flask import Blueprint, jsonify

_SENTINEL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "LOCALUPDATE")
_STARTED_AT = str(time.time())

bp = Blueprint("dev_reload", __name__, url_prefix="/api/dev")


@bp.route("/ping")
def ping():
    return jsonify({"started_at": _STARTED_AT})


def _watch():
    while True:
        time.sleep(1)
        if os.path.exists(_SENTINEL):
            try:
                os.remove(_SENTINEL)
            except OSError:
                pass
            # Let in-flight responses flush, then spawn a fresh process
            # (no inherited fds) and exit cleanly so the port is freed
            # before the new process tries to bind it.
            time.sleep(0.3)
            subprocess.Popen([sys.executable] + sys.argv)
            os._exit(0)


def start_watcher():
    if getattr(sys, "frozen", False):
        return
    t = threading.Thread(target=_watch, daemon=True, name="dev-reload-watcher")
    t.start()
