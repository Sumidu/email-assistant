# Email Assistant

A local, privacy-first email assistant that runs entirely on your machine.
Reads your emails via IMAP, learns your writing style using a local or remote LLM,
and helps you draft replies through a chat interface. **No email is ever sent automatically.**

---

## Requirements

| Dependency | Notes |
|---|---|
| Python 3.9+ | `brew install python` |
| An LLM backend | LM Studio (local), Ollama, LiteLLM proxy, or any OpenAI-compatible API |
| IMAP access | Works with any IMAP server — Outlook, Gmail, Fastmail, etc. |

---

## macOS App

A self-contained `.app` bundle is available for macOS. It opens in its own native window (WKWebView) and does not require a browser.

```bash
# Build the .app (requires PyInstaller and pywebview)
./build_app.sh

# The app appears in dist/EmailAssistant.app
# Config and data are stored in ~/email_assistant/ — they survive app updates.
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

# 3. Start the assistant
./run.sh

# 4. Open in browser
open http://localhost:5100
```

---

## Configuration

Config is stored at `~/email_assistant/config.json` — **outside the repo**, so it survives updates and rebuilds. On first run a default file is created automatically.

Open **Settings (⚙)** in the UI to configure accounts and the AI provider without editing JSON manually.

Key fields:

| Field | Notes |
|---|---|
| `accounts[].imap.server` | Your IMAP hostname |
| `accounts[].imap.sent_folder` | `"Sent Items"` (Outlook), `"Sent"` (Gmail/Fastmail). Use Settings → Discover Folders to find the exact name. |
| `accounts[].imap.fetch_limit` | Max emails to fetch per folder (default 300) |
| `lm_studio.base_url` | Base URL of your LLM backend |
| `lm_studio.model` | Model identifier. For LM Studio with one model loaded, any string works. |
| `lm_studio.api_key` | Leave blank for local providers. Required for OpenAI, Anthropic via LiteLLM, etc. |

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
[SYNC] ──► SQLite DB (~/email_assistant/emails.db)
                │
                ▼
[BUILD KNOWLEDGE] ──► LLM analyses sent mail + inbox
                       ──► ~/email_assistant/knowledge/
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

- All email data stays on your machine (`~/email_assistant/`).
- Secrets (passwords, API keys) are stored in the macOS Keychain — never on disk in plain text.
- The SQLite database and knowledge files live outside the repo and are git-ignored.
- When using a remote LLM API (OpenAI, etc.), email snippets are sent to that API — use a local provider (LM Studio, Ollama) for full privacy.
- No email is ever sent by this tool.
