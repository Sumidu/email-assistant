# Release And Packaging

Releases are tag driven. Pushing a `v*` tag runs the GitHub release workflow,
builds the PyInstaller `.app`, creates a DMG, uploads it as an artifact, and
attaches it to a GitHub Release.

## Versioning

- `build_app.sh` writes `version.py` from the release tag.
- `EmailAssistant.spec` copies that value into `CFBundleShortVersionString`.
- The running packaged app reads its version from bundle metadata.
- Browser/dev mode may report `dev`.

## Packaged App Runtime

The `.app` starts Flask on a free local port to avoid accidentally connecting to
a development server on port `5100`. Browser mode still uses the configured
port for predictable local development.

Related OpenSpec proposal: `openspec/changes/auto-updater/`.
