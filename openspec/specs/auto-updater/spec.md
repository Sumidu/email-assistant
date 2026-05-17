# Auto-Updater Spec

## Requirement: Version check on startup
The system SHALL check GitHub releases for `Sumidu/email-assistant` in a background thread immediately after the Flask app starts. The check SHALL NOT block startup or UI rendering.

### Scenario: Newer version found
- **WHEN** the GitHub releases API returns a `tag_name` whose version is greater than the running app's `CFBundleShortVersionString`
- **THEN** the system SHALL set internal update state to `{available: true, version: <tag>, dmg_url: <asset_url>}`

### Scenario: No newer version
- **WHEN** the latest release version is equal to or less than the running version
- **THEN** the system SHALL set internal update state to `{available: false}` and take no further action

### Scenario: Network failure or API error
- **WHEN** the GitHub API call fails (timeout, 404, non-200, malformed JSON)
- **THEN** the system SHALL silently ignore the error and leave update state as `{available: false}`

### Scenario: Running in dev mode
- **WHEN** `sys.frozen` is False (app running from source, not a PyInstaller bundle)
- **THEN** the system SHALL skip the version check entirely

## Requirement: Periodic re-check every 24 hours
The system SHALL re-check for updates every 24 hours after the initial startup check, without requiring a restart.

### Scenario: Re-check fires
- **WHEN** 24 hours have elapsed since the last check
- **THEN** the system SHALL repeat the GitHub API check and update internal state accordingly

## Requirement: Update status API endpoint
The system SHALL expose `GET /api/update_status` returning JSON with the current update state.

### Scenario: Update available
- **WHEN** a newer version has been found
- **THEN** `GET /api/update_status` SHALL return `{"available": true, "version": "x.y.z"}`

### Scenario: No update
- **WHEN** no newer version has been found
- **THEN** `GET /api/update_status` SHALL return `{"available": false}`

## Requirement: Blocking update modal
When an update is available, the system SHALL display a full-screen blocking modal overlay that prevents all interaction with the app until the user initiates the update.

### Scenario: Modal appears
- **WHEN** the frontend receives `available: true` from `/api/update_status`
- **THEN** a modal overlay SHALL appear covering the full UI with `pointer-events: none` on the background

### Scenario: Modal cannot be dismissed
- **WHEN** the update modal is visible
- **THEN** there SHALL be no close button, "Later" button, or keyboard shortcut to dismiss it

### Scenario: Modal content
- **WHEN** the modal is shown
- **THEN** it SHALL display the new version number and a single "Update Now" button

## Requirement: Download and install update
The system SHALL download `EmailAssistant.dmg` from the GitHub release asset URL and self-replace the running `.app` bundle.

### Scenario: User clicks Update Now
- **WHEN** the user clicks "Update Now"
- **THEN** the system SHALL begin downloading the DMG in a background task and show a progress spinner; the button SHALL be disabled to prevent double-clicks

### Scenario: Download completes
- **WHEN** the DMG download finishes successfully
- **THEN** the system SHALL write `/tmp/ea_update.sh`, execute it via `subprocess.Popen`, and call `sys.exit()`

### Scenario: Shell script runs
- **WHEN** `/tmp/ea_update.sh` executes after the app has quit
- **THEN** it SHALL: wait 2s, mount the DMG with `hdiutil`, copy the new `.app` to `/Applications` with `ditto`, remove the quarantine flag with `xattr`, unmount the DMG, open the new app, and self-delete

### Scenario: Current app not in /Applications
- **WHEN** the running app's path (derived from `sys.executable`) is not under `/Applications`
- **THEN** the shell script SHALL use the actual current `.app` path for replacement, not the hardcoded `/Applications` path
