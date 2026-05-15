# Architecture

Email Assistant is a local-first Flask application with a macOS PyInstaller
shell. The packaged app starts a local Flask server and opens a WKWebView
window; browser mode starts the same Flask app on port `5100`.

## Main Layers

- **Application shell**: `main.py` starts Flask for browser mode; `launcher.py`
  starts Flask in a background thread for the `.app` bundle.
- **Routes**: `app/routes/` exposes JSON APIs for email, accounts, settings,
  knowledge, tasks, logs, calendar, todos, and updates.
- **Services**: `app/services/` contains route-adjacent parsing and rendering
  helpers that can be tested without Flask request contexts.
- **Domain modules**: `modules/` owns IMAP sync, SQLite persistence, knowledge
  generation, response generation, calendar storage, logging, and triage state.
  Large public modules keep compatibility facades while internals move into
  smaller packages such as `modules/db`, `modules/imap`, and `modules/knowledge`.
- **Frontend**: `templates/index.html`, `static/js/app.js`, and
  `static/css/app.css` implement the single-page UI.
- **Runtime data**: configuration, SQLite, logs, and knowledge files live under
  macOS Application Support / Logs / iCloud paths defined in `app.paths`.

## Stability Strategy

Large modules should be split only after behavior is covered by tests. Initial
tests focus on pure helpers and local persistence behavior, not live IMAP,
Keychain, LLM, or network calls.

Relevant OpenSpec section: `openspec/specs/email-assistant/spec.md`.
