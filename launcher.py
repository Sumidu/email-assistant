"""
launcher.py — macOS menu bar entry point for the bundled .app.

Starts the Flask server in a background thread, then opens the browser.
A menu bar icon lets the user open the UI or quit cleanly.
"""

import threading
import webbrowser
import time
import sys
import os

import rumps

# Import the Flask app (all routes are registered on import)
import main as server_module

PORT = server_module.config.get("app", {}).get("port", 5100)
URL  = f"http://localhost:{PORT}"


class EmailAssistantMenuBar(rumps.App):
    def __init__(self):
        super().__init__(
            name="Email Assistant",
            title="✉",
            quit_button=None,           # we add our own so we can clean up
        )
        self.menu = [
            rumps.MenuItem("Open Email Assistant", callback=self.open_browser),
            None,                       # separator
            rumps.MenuItem("Quit", callback=self.quit_app),
        ]
        self._server_thread = threading.Thread(
            target=self._run_server, daemon=True
        )
        self._server_thread.start()
        # Open browser after server has had time to bind
        threading.Timer(1.8, lambda: webbrowser.open(URL)).start()

    def _run_server(self):
        server_module.app.run(host="127.0.0.1", port=PORT, debug=False, use_reloader=False)

    @rumps.clicked("Open Email Assistant")
    def open_browser(self, _=None):
        webbrowser.open(URL)

    def quit_app(self, _=None):
        rumps.quit_application()


if __name__ == "__main__":
    EmailAssistantMenuBar().run()
