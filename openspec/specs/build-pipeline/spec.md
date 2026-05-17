# Build Pipeline Spec

## Requirement: Version embedded from git tag at build time
`build_app.sh` SHALL read the latest git tag before running PyInstaller and write it to `version.py` so the built `.app` bundle's `Info.plist` reflects the exact release version.

### Scenario: Tag exists
- **WHEN** `git describe --tags --abbrev=0` returns a tag of the form `vx.y.z`
- **THEN** `build_app.sh` SHALL strip the leading `v` and write `__version__ = "x.y.z"` to `version.py`

### Scenario: No tag found
- **WHEN** no git tag exists in the repository
- **THEN** `build_app.sh` SHALL write `__version__ = "0.0.0"` to `version.py` and continue the build

## Requirement: Spec reads version from version.py
`EmailAssistant.spec` SHALL read `__version__` from `version.py` and use it for `CFBundleShortVersionString` in the app bundle's `Info.plist`.

### Scenario: Build runs
- **WHEN** PyInstaller processes `EmailAssistant.spec`
- **THEN** the resulting `Info.plist` SHALL contain `CFBundleShortVersionString` equal to the value from `version.py`

## Requirement: version.py is gitignored
`version.py` SHALL be listed in `.gitignore` so generated version files are never committed.

### Scenario: Developer runs git status after build
- **WHEN** a developer runs `./build_app.sh` and then `git status`
- **THEN** `version.py` SHALL NOT appear as an untracked or modified file
