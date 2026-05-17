## Context

Email Assistant is a PyInstaller-bundled macOS `.app` (WKWebView + Flask). Users receive the app as a DMG and install it to `/Applications`. There is no package manager or update daemon — once installed, the app has no mechanism to notify users of new versions.

The GitHub release workflow tags `vx.y.z` → CI produces `EmailAssistant.dmg` as a release asset. The app's current version is hardcoded in `EmailAssistant.spec` as `CFBundleShortVersionString`. The running app has no way to read its own version at runtime today.

## Goals / Non-Goals

**Goals:**
- Check GitHub releases on startup and every 24 hours
- Show a blocking modal when a newer version is available (user cannot dismiss)
- Download `EmailAssistant.dmg` and self-replace via an external shell script
- Embed version from git tag at build time; read it from `Info.plist` at runtime

**Non-Goals:**
- Silent/background updates (user must confirm)
- Delta/patch updates (always full DMG)
- Update checks in dev mode (`sys.frozen` is False)
- Rollback on failed update
- Windows or Linux support

## Decisions

### D1: Version source of truth → git tag + `version.py` + `Info.plist`

`build_app.sh` runs `git describe --tags --abbrev=0` → strips `v` → writes `version.py: __version__ = "x.y.z"`. The spec imports `version.py` for `CFBundleShortVersionString`. At runtime the frozen app reads its own `Info.plist` via `plistlib` — this is authoritative even if the file is moved or renamed.

**Alternatives considered:**
- Hardcode in spec only: can't read at runtime without plistlib dance anyway; single source eliminates drift
- Read from `version.py` at runtime: works in dev, but PyInstaller may not include it unless explicitly listed; Info.plist is always present in a real bundle

### D2: Update check in background thread, not blocking startup

The GitHub API call can take 1-3s. Startup already has a Flask warm-up delay; adding a blocking network call would make it worse.

**Approach:** Spawn a daemon thread in `app/updater.py`. Store result in a module-level `_state` dict. Frontend polls `/api/update_status` (same pattern as `/api/task_status`). Modal appears as soon as the check resolves.

### D3: Blocking modal — no dismiss, no Later

Updates are mandatory. The modal overlays the full UI with `pointer-events: none` on the background. No X button, no Later. The only exit is clicking "Update Now" or force-quitting the app.

### D4: Self-replacement via external shell script

A running `.app` binary is locked by macOS — it cannot delete or overwrite itself. Standard pattern: write a small bash script to `/tmp/ea_update.sh`, `chmod +x`, then `subprocess.Popen(["bash", "/tmp/ea_update.sh"])` + `sys.exit()`. The script runs after the app quits.

Script steps:
1. `sleep 2` (ensure app process is gone)
2. `hdiutil attach <dmg> -quiet -nobrowse -mountpoint /tmp/ea_mount`
3. `rm -rf "/Applications/Email Assistant.app"`
4. `ditto "/tmp/ea_mount/Email Assistant.app" "/Applications/Email Assistant.app"`
5. `hdiutil detach /tmp/ea_mount -quiet`
6. `open "/Applications/Email Assistant.app"`
7. `rm -- "$0"` (self-delete)

**Why `ditto` over `cp -r`:** `ditto` preserves extended attributes, resource forks, and ACLs on macOS. `cp -r` silently drops them, which can cause Gatekeeper or Launch Services issues.

### D5: Download as background task using existing `task_runner` pattern

DMG can be 80-150 MB. Download runs in a background thread. The frontend shows a progress spinner and disables the Update button once clicked. Progress is reported via `/api/task_status` (existing pattern). After download completes, the script is written and `sys.exit()` is called.

### D6: 24-hour repeat via `threading.Timer`

After the first check, schedule a `threading.Timer(86400, _check)` that re-arms itself. No external scheduler needed.

## Risks / Trade-offs

- **App not in `/Applications`**: The update script assumes `/Applications/Email Assistant.app`. If the user moved it, `rm` fails silently and the old app stays. → Mitigation: derive the current `.app` path from `sys.executable` at script-write time; pass it as a variable in the script.
- **DMG asset name changes**: Hard-coded `EmailAssistant.dmg` lookup. If the release workflow renames the asset, no update is found. → Mitigation: document asset name as a convention; updater logs a warning if no matching asset found.
- **No rollback**: If `ditto` fails mid-copy, the app may be broken. → Acceptable risk for v1; no mitigation.
- **Gatekeeper on unsigned app**: Replacing an app via script bypasses Gatekeeper's first-launch check. On macOS 15+, this may trigger a quarantine flag on the new `.app`. → Mitigation: the script can run `xattr -dr com.apple.quarantine` before `open`.

## Migration Plan

1. `build_app.sh` change is additive — adds a `git describe` call and `version.py` write before PyInstaller. No breakage for existing builds.
2. `EmailAssistant.spec` change: replace hardcoded version string with `exec(open('version.py').read())` + reference to `__version__`.
3. `version.py` added to `.gitignore`.
4. New routes registered in `app/__init__.py` — no existing routes affected.
5. Frontend modal injected into base template — hidden by default, shown only when update state is set.

## Open Questions

- None — all decisions made during exploration.
