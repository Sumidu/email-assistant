## Why

Users running the installed macOS app have no way to know when a new version is available — they must manually check GitHub. Since the app is a PyInstaller bundle with no package manager, updates require manual download and reinstall.

## What Changes

- At startup and every 24 hours, the app checks GitHub releases (`Sumidu/email-assistant`) for a newer version
- If a newer release is found, a **blocking modal** is shown — the user cannot use the app until they update
- Clicking "Update Now" downloads `EmailAssistant.dmg`, writes a swap shell script, execs it, and quits
- The shell script mounts the DMG, copies the new `.app` to `/Applications` with `ditto`, unmounts, relaunches, and self-deletes
- Version is embedded at build time from the git tag into `version.py` and `Info.plist`
- In dev mode (not frozen), the update check is skipped entirely

## Capabilities

### New Capabilities

- `auto-updater`: Periodic GitHub release check, blocking update modal, DMG download, and self-replacement via shell script

### Modified Capabilities

- `build-pipeline`: `build_app.sh` now reads the git tag and writes `version.py` before PyInstaller runs; `EmailAssistant.spec` reads `version.py` for `CFBundleShortVersionString`

## Impact

- **New files**: `app/updater.py`, `app/routes/update.py`, `version.py` (generated, gitignored)
- **Modified files**: `build_app.sh`, `EmailAssistant.spec`, `app/__init__.py` (register route), frontend templates (modal UI)
- **New dependency**: none (uses `urllib.request`, `plistlib`, `subprocess` — all stdlib)
- **macOS only**: `hdiutil` and `ditto` are macOS tools; feature is gated on `sys.frozen`
