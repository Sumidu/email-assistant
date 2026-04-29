"""
launcher.py — macOS app entry point using pywebview.

Starts the Flask server in a background thread, waits until it is ready,
then opens a native WKWebView window. Closing the window quits the app.
"""

import threading
import urllib.request
import time
import sys
import os

import webview

# Import the Flask app (all routes are registered on import)
import main as server_module

PORT = server_module.config.get("app", {}).get("port", 5100)
URL  = f"http://127.0.0.1:{PORT}"


def _run_server():
    server_module.app.run(host="127.0.0.1", port=PORT, debug=False, use_reloader=False)


def _wait_for_server(timeout=15):
    """Poll until Flask is accepting connections."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(URL, timeout=0.5)
            return True
        except Exception:
            time.sleep(0.15)
    return False


def _start_server_then_load(window):
    """Called from a thread after webview is initialised; loads URL when ready."""
    if _wait_for_server():
        window.load_url(URL)
    else:
        window.load_html("<h2 style='font-family:sans-serif;padding:40px'>Server failed to start.</h2>")


if __name__ == "__main__":
    # Start Flask in background
    server_thread = threading.Thread(target=_run_server, daemon=True)
    server_thread.start()

    # Create the window (starts blank; _start_server_then_load fills it in)
    window = webview.create_window(
        title="Email Assistant",
        url="about:blank",
        width=1400,
        height=900,
        min_size=(900, 600),
        text_select=True,
    )

    # Load the real URL once Flask is ready
    webview.start(
        func=_start_server_then_load,
        args=(window,),
        gui="cocoa",            # use native WKWebView on macOS
        debug=False,
    )
