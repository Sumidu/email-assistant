---
name: github
description: GitHub actions, CI/CD workflows, releases, PRs, and repository management for this project
license: MIT
compatibility: opencode
metadata:
  audience: maintainers
  workflow: github
---

## What I do

- Set up GitHub Actions workflows for macOS builds (PyInstaller)
- Create and manage releases using `gh` CLI
- Handle code signing and notarization for macOS
- Manage pull requests, branches, and tags
- Configure repository secrets and settings

## When to use me

Use this when you need to:
- Set up CI/CD for this project
- Create a new GitHub release
- Manage git tags and branches
- Configure GitHub Actions workflows
- Work with GitHub issues or PRs

## Project Context

- **Build script:** `build_app.sh`
- **Spec file:** `EmailAssistant.spec` (PyInstaller)
- **Deploy script:** `deploy.sh`
- **macOS app building:** Requires PyInstaller on macOS runner

## Quick Commands

```bash
# Tag and release
git tag v1.2.3 && git push origin v1.2.3

# Create release via gh
gh release create v1.2.3 --title "v1.2.3" --notes "..." dist/EmailAssistant.dmg

# Build workflow trigger (on tag push)
git tag v* && git push origin --tags
```

## Code Signing (macOS)

```bash
# Sign the app
codesign --sign "Developer ID Application" dist/EmailAssistant.app

# Notarize
xcrun notarytool submit dist/EmailAssistant.zip --apple-id "email" --password "app-specific-password" --team-id "TEAM_ID"
```

## GitHub Actions Example

```yaml
on:
  push:
    tags:
      - 'v*'
  release:
    types: [created]

jobs:
  build:
    runs-on: macos-latest
    steps:
      - uses: actions/checkout@v4
      - name: Build
        run: |
          pip install -r requirements.txt
          ./build_app.sh
      - uses: actions/upload-artifact@v4
        with:
          name: EmailAssistant
          path: dist/
```

## Permissions

This skill can create/modify workflow files, run git commands, and interact with GitHub via `gh` CLI.