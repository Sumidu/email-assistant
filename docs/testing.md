# Testing

The first test layer is a smoke suite that avoids external services. Tests
should not require IMAP, Keychain, LM Studio, GitHub, or network access.

## Commands

```bash
pytest
ruff check .
python -m py_compile main.py launcher.py app/*.py app/routes/*.py modules/*.py
node --check static/js/app.js
sphinx-build -b html docs docs/_build/html
```

## Test Priorities

- Keep local triage decisions persistent across app restarts.
- Keep updater/version helpers deterministic.
- Keep config import/export from leaking or overwriting secrets.
- Keep IMAP sync helper decisions testable without a live server.
- Extract pure helpers before refactoring larger modules.
