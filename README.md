# Email Assistant

A local, privacy-first email assistant that runs entirely on your machine.
Reads your emails via IMAP, learns your writing style using a local or remote LLM,
and helps you draft replies through a chat interface. **No email is ever sent automatically.**

---

## Requirements

| Dependency | Notes |
|---|---|
| Python 3.10+ | Python 3.12 is a good default on macOS |
| An LLM backend | LM Studio (local), Ollama, LiteLLM proxy, or any OpenAI-compatible API |
| IMAP access | Works with any IMAP server — Outlook, Gmail, Fastmail, etc. |

---

## Python Version

The app requires **Python 3.10 or newer**. Python 3.12 is recommended because it is widely supported by current packaging tools and macOS app builds.

Check your current version:

```bash
python3 --version
```

If your installed Python is too old, install a newer one and point setup at it:

```bash
# Homebrew
brew install python@3.12
PYTHON="$(brew --prefix python@3.12)/bin/python3.12" ./setup.sh
```

Or install Python 3.12 from [python.org](https://www.python.org/downloads/macos/) and run:

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 ./setup.sh
```

If `.venv` was already created with the wrong Python version, recreate it:

```bash
rm -rf .venv
PYTHON="$(brew --prefix python@3.12)/bin/python3.12" ./setup.sh
```

With `pyenv`, the equivalent is:

```bash
pyenv install 3.12
pyenv local 3.12
rm -rf .venv
./setup.sh
```

---

## macOS App

A self-contained `.app` bundle is available for macOS. It opens in its own native window (WKWebView) and does not require a browser.

```bash
# Build the .app (requires PyInstaller and pywebview)
./build_app.sh

# The app appears in dist/EmailAssistant.app
# Config and local data are stored in ~/Library/Application Support/Email Assistant/.
```

Keyboard shortcuts in the app window:
- `Cmd +` / `Cmd -` — zoom in / out
- `Cmd 0` — reset zoom

---

## Quick Start (browser mode)

```bash
# 1. Clone the repo
git clone https://github.com/Sumidu/email-assistant && cd email-assistant

# 2. Run setup (creates venv, installs deps)
chmod +x setup.sh run.sh
./setup.sh

# Optional: also upgrade pip during setup
UPGRADE_PIP=1 ./setup.sh

# 3. Start the assistant
./run.sh

# 4. Open in browser
open http://localhost:5100
```

---

## Developer Workflow

Developer tooling is configured in `pyproject.toml`.

```bash
# Install app + developer tools
python -m pip install -e ".[dev]"

# Run the smoke checks used by CI
pytest
ruff check .
python -m py_compile main.py launcher.py app/*.py app/routes/*.py modules/*.py
node --check static/js/app.js
sphinx-build -b html docs docs/_build/html
```

Developer documentation starts at `docs/index.md` and links to the OpenSpec
requirements under `openspec/`.

---

## Configuration

Config is stored at `~/Library/Application Support/Email Assistant/config.json` — **outside the repo**, so it survives updates and rebuilds. On first run a default file is created automatically and legacy data from `~/email_assistant` is copied into the new macOS locations.

Open **Settings (⚙)** in the UI to configure accounts and one or more AI providers without editing JSON manually.

Key fields:

| Field | Notes |
|---|---|
| `accounts[].imap.server` | Your IMAP hostname |
| `accounts[].imap.sent_folder` | `"Sent Items"` (Outlook), `"Sent"` (Gmail/Fastmail). Use Settings → Discover Folders to find the exact name. |
| `accounts[].imap.spam_folder` | Remote spam/junk folder used by the Spam action. If unset, the app tries to detect a server folder marked Junk/Spam. |
| `accounts[].imap.fetch_limit` | Max emails to fetch per folder (default 300) |
| `llms[].base_url` | Base URL of each OpenAI-compatible LLM backend |
| `llms[].model` | Model identifier. For LM Studio with one model loaded, any string works. |
| `llms[].api_key` | Leave blank for local providers. Required for OpenAI, Anthropic via LiteLLM, etc. |
| `default_llm_id` | Provider selected by default |
| `app.active_llm_id` | Provider currently selected in the UI dropdown |

### LLM provider presets

| Preset | Base URL | Notes |
|---|---|---|
| LM Studio | `http://localhost:1234` | Load a model and enable the local server |
| Ollama | `http://localhost:11434` | `ollama serve` |
| LiteLLM proxy | `http://localhost:4000` | `litellm --model anthropic/...` |
| OpenAI | `https://api.openai.com` | Requires API key |

### Secrets

IMAP passwords and API keys are stored in the **macOS Keychain** (service `com.emailassistant.app`). They are never written to `config.json` or the git repo.

### IMAP notes

- **Outlook / Office 365**: Enable IMAP in Outlook settings → Mail → Sync email. If MFA is on, generate an **App Password** in Microsoft account security settings.
- **Gmail**: Enable IMAP in Gmail settings → See all settings → Forwarding and POP/IMAP. Use an App Password if 2FA is on.

---

## How It Works

```
IMAP server
    │
    ▼
[SYNC] ──► SQLite DB (~/Library/Application Support/Email Assistant/emails.db)
                │
                ▼
[BUILD KNOWLEDGE] ──► LLM analyses sent mail + inbox
                       ──► iCloud Drive/Email Assistant/Knowledge/
                           _writing_style.md      (your writing style, auto)
                           contact@example.com.md (per-sender profile, auto)
                           about_me.md            (manual — pin to always include)
                │
                ▼
[Select email] ──► context auto-selected (pinned + style + sender + recipients)
                ──► Chat with LLM: draft appears on left, conversation on right
                ──► Add/remove context files manually at any time
```

Knowledge generation is **incremental** — only emails added since the last build are processed.

### Knowledge Base

Knowledge files are standard Markdown with Obsidian-compatible YAML frontmatter. Email Assistant stores metadata such as contact email, aliases, wildcard match patterns, generating LLM, timestamp, and tags directly in the `.md` file, while keeping the existing sidecar metadata as an internal index. The app hides frontmatter in its own viewer/editor content and reads it back when files are edited in Obsidian.

---

## UI Guide

| Element | Action |
|---|---|
| `SYNC ALL` | Fetch latest emails from all accounts |
| `KNOWLEDGE` | Build/update writing style and contact profiles |
| `VIEW KB` | Browse, edit, pin, or delete knowledge files |
| `Generate` | Ask the LLM to draft a reply to the selected email |
| `+ Context` | Pick additional knowledge files to include in the prompt |
| Context tags | Amber tags show active context — click × to remove any |
| `Copy` | Copy the current draft to clipboard |
| Chat input | Chat with the LLM — ask questions, request edits, save notes |
| `⏵⏸⏸` (debug) | View full LLM request/response log |
| Settings (⚙) | Configure accounts and AI provider |

### Knowledge Base

- **Pin** any file to always include it in every prompt — useful for an "about me" file or company info.
- **Purge contacts** removes all auto-generated contact profiles without affecting manual or pinned files.
- The LLM can query the KB itself mid-turn (`<kb_list/>`, `<kb_read filename="x.md"/>`) to decide where to store new information.

---

## Privacy

- All email data stays on your machine (`~/Library/Application Support/Email Assistant/`).
- Secrets (passwords, API keys) are stored in the macOS Keychain — never on disk in plain text.
- The SQLite database and knowledge files live outside the repo and are git-ignored.
- When using a remote LLM API (OpenAI, etc.), email snippets are sent to that API — use a local provider (LM Studio, Ollama) for full privacy.
- No email is ever sent by this tool.
