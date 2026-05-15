import os
import plistlib
import sys
import threading
import time
import urllib.request
import urllib.error
import json
import subprocess
import logging

logger = logging.getLogger(__name__)

_state: dict = {"available": False, "error": None}
_timer: threading.Timer | None = None
_UPDATE_CHECK_INTERVAL = 86400
_REPO_OWNER = "Sumidu"
_REPO_NAME = "email-assistant"
_DMG_ASSET_NAME = "EmailAssistant.dmg"


def _read_info_plist_version(path: str) -> str:
    try:
        if path and os.path.exists(path):
            with open(path, "rb") as f:
                plist = plistlib.load(f)
            version = plist.get("CFBundleShortVersionString")
            if version:
                return str(version)
    except Exception as exc:
        logger.debug("Could not read version from %s: %s", path, exc)
    return ""


def _candidate_info_plists() -> list[str]:
    candidates = []
    app_path = get_app_path()
    if app_path:
        candidates.append(os.path.join(app_path, "Contents", "Info.plist"))
    meipass = getattr(sys, "_MEIPASS", "")
    if meipass:
        cur = os.path.abspath(meipass)
        for _ in range(5):
            candidates.append(os.path.join(cur, "Info.plist"))
            candidates.append(os.path.join(cur, "Contents", "Info.plist"))
            parent = os.path.dirname(cur)
            if parent == cur:
                break
            cur = parent
    deduped = []
    for path in candidates:
        if path and path not in deduped:
            deduped.append(path)
    return deduped


def _bundle_version_from_foundation() -> str:
    try:
        from Foundation import NSBundle

        info = NSBundle.mainBundle().infoDictionary()
        version = info.get("CFBundleShortVersionString") if info else None
        return str(version) if version else ""
    except Exception as exc:
        logger.debug("Could not read version from NSBundle: %s", exc)
        return ""


def get_current_version() -> str:
    for info_plist_path in _candidate_info_plists():
        version = _read_info_plist_version(info_plist_path)
        if version:
            return version
    version = _bundle_version_from_foundation()
    if version:
        return version
    try:
        from version import __version__

        return str(__version__)
    except Exception:
        pass
    return "dev"


def get_app_path() -> str:
    executable = sys.executable
    if executable.endswith(".app/Contents/MacOS/"):
        return executable.split(".app/Contents/MacOS/")[0] + ".app"
    if ".app" in executable:
        return executable.split(".app/Contents/MacOS/")[0] + ".app"
    return "/Applications/Email Assistant.app"


def _parse_version(version: str) -> tuple:
    return tuple(int(x) for x in version.lstrip("v").split(".") if x.isdigit())


def _version_gt(a: str, b: str) -> bool:
    try:
        return _parse_version(a) > _parse_version(b)
    except Exception:
        return False


def _check_for_update():
    global _state
    try:
        current = get_current_version()
        url = f"https://api.github.com/repos/{_REPO_OWNER}/{_REPO_NAME}/releases/latest"
        req = urllib.request.Request(url, headers={"User-Agent": "EmailAssistant"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        latest_tag = data.get("tag_name", "")
        latest_version = latest_tag.lstrip("v")
        dmg_url = None
        for asset in data.get("assets", []):
            if asset.get("name") == _DMG_ASSET_NAME:
                dmg_url = asset.get("browser_download_url")
                break
        if not dmg_url:
            msg = f"No {_DMG_ASSET_NAME} asset found in release {latest_tag or '(unknown)'}"
            logger.warning(msg)
            _state = {"available": False, "error": msg}
            return
        if _version_gt(latest_version, current):
            _state = {"available": True, "version": latest_version, "dmg_url": dmg_url, "error": None}
            logger.info("Update available: %s (current: %s)", latest_version, current)
        else:
            _state = {"available": False, "error": None}
            logger.info("No update available. Latest: %s, current: %s", latest_version, current)
    except Exception as exc:
        logger.error("Update check failed: %s", exc)
        _state = {"available": False, "error": str(exc)}


def _schedule_next():
    global _timer
    if _timer:
        _timer.cancel()
    _timer = threading.Timer(_UPDATE_CHECK_INTERVAL, _run_check_and_reschedule)
    _timer.daemon = True
    _timer.start()


def _run_check_and_reschedule():
    _check_for_update()
    _schedule_next()


def start_update_checker():
    if not getattr(sys, "frozen", False):
        logger.info("Dev mode — skipping update checker")
        return
    logger.info("Starting update checker")
    _check_for_update()
    _schedule_next()


def get_state() -> dict:
    return {**_state, "current_version": get_current_version()}


def trigger_check() -> dict:
    _check_for_update()
    return get_state()


def download_and_install(dmg_url: str, app_path: str | None = None, progress_cb=None):
    if progress_cb:
        progress_cb("Preparing download...")
    target_path = app_path or get_app_path()
    dmg_path = "/tmp/ea_update.dmg"
    script_path = "/tmp/ea_update.sh"
    if os.path.exists(dmg_path):
        os.remove(dmg_path)
    if progress_cb:
        progress_cb("Downloading update...")
    try:
        req = urllib.request.Request(dmg_url, headers={"User-Agent": "EmailAssistant"})
        with urllib.request.urlopen(req, timeout=300) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            with open(dmg_path, "wb") as out:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    out.write(chunk)
                    downloaded += len(chunk)
                    if total and progress_cb:
                        pct = int(downloaded / total * 100)
                        progress_cb(f"Downloading... {pct}%")
    except Exception as exc:
        if progress_cb:
            progress_cb(f"Download failed: {exc}")
        raise
    if progress_cb:
        progress_cb("Installing update...")
    shell_script = f'''#!/bin/bash
sleep 2
hdiutil attach "{dmg_path}" -quiet -nobrowse -mountpoint /tmp/ea_mount
rm -rf "{target_path}"
ditto "/tmp/ea_mount/Email Assistant.app" "{target_path}"
xattr -dr com.apple.quarantine "{target_path}"
hdiutil detach /tmp/ea_mount -quiet
open "{target_path}"
rm -- "$0"
'''
    with open(script_path, "w") as f:
        f.write(shell_script)
    os.chmod(script_path, 0o755)
    if progress_cb:
        progress_cb("Launching installer...")
    subprocess.Popen(["bash", script_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    sys.exit()
