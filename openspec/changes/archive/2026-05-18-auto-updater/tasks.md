## 1. Build Pipeline — Version Embedding

- [x] 1.1 Add `version.py` to `.gitignore`
- [x] 1.2 Update `build_app.sh` to run `git describe --tags --abbrev=0`, strip `v`, write `version.py` (fallback to `0.0.0` if no tag)
- [x] 1.3 Update `EmailAssistant.spec` to `exec(open('version.py').read())` and use `__version__` for `CFBundleShortVersionString`

## 2. Updater Module

- [x] 2.1 Create `app/updater.py` with `get_current_version()` that reads `Info.plist` via `plistlib` when frozen, returns `"dev"` otherwise
- [x] 2.2 Add `get_app_path()` to derive the `.app` bundle path from `sys.executable`
- [x] 2.3 Implement `_check_for_update()` — call GitHub releases API, compare versions, store result in module-level `_state` dict
- [x] 2.4 Implement `start_update_checker()` — run initial check in daemon thread, schedule 24h repeat via `threading.Timer`
- [x] 2.5 Implement `download_and_install(dmg_url, app_path, progress_cb)` — stream DMG to `/tmp/ea_update.dmg`, write `/tmp/ea_update.sh`, `subprocess.Popen(["bash", ...])`, `sys.exit()`
- [x] 2.6 Write the shell script template in `download_and_install`: sleep 2 → hdiutil attach → rm old app → ditto → xattr quarantine strip → hdiutil detach → open → rm script

## 3. API Routes

- [x] 3.1 Create `app/routes/update.py` with `GET /api/update_status` returning `_state` as JSON
- [x] 3.2 Add `POST /api/update/install` that kicks off `download_and_install` as a background task using existing `task_runner` pattern; return 409 if a task is already running
- [x] 3.3 Register the update blueprint in `app/__init__.py`

## 4. Frontend Modal

- [x] 4.1 Add update modal HTML to base template (hidden by default): full-screen overlay, version text, "Update Now" button, no close/dismiss controls
- [x] 4.2 Add CSS: overlay covers full viewport, `pointer-events: none` on underlying content, centered modal card
- [x] 4.3 Add JS: on page load, fetch `/api/update_status`; if `available: true`, show modal
- [x] 4.4 Add JS: "Update Now" click → disable button, show spinner, `POST /api/update/install`, poll `/api/task_status` for progress

## 5. Wiring & Startup

- [x] 5.1 Call `updater.start_update_checker()` in `app/__init__.py` after app is created (not in `main.py` — needs app context for logging)
- [x] 5.2 Verify update check is skipped when `sys.frozen` is False (dev mode guard in `start_update_checker`)

## 6. Verification

- [x] 6.1 Build a test DMG with a bumped version tag and confirm the modal appears and the swap completes successfully
- [x] 6.2 Confirm modal cannot be dismissed (no keyboard shortcut, no click-outside)
- [ ] 6.3 Confirm dev mode (`python main.py`) shows no update modal and makes no GitHub API calls
