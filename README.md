# Email Assistant

A local, privacy-first email assistant that runs entirely on your machine.
Reads your emails via IMAP, learns your writing style using a local or remote LLM,
and proposes clean draft responses. **No email is ever sent automatically.**

---

## Requirements

| Dependency | Notes |
|---|---|
| Python 3.10+ | `brew install python` |
| An LLM backend | LM Studio (local), Ollama, LiteLLM proxy, or any OpenAI-compatible API |
| IMAP access | Works with any IMAP server — Outlook, Gmail, Fastmail, etc. |

---

## Quick Start

```bash
# 1. Clone the repo
git clone <repo-url> email_assistant && cd email_assistant

# 2. Set up credentials
cp config.json.example config.json
# Edit config.json — add your IMAP server, username, password, and LLM URL

# 3. Run setup (creates venv, installs deps)
chmod +x setup.sh run.sh
./setup.sh

# 4. Start the assistant
./run.sh

# 5. Open in browser
open http://localhost:5100
```

---

## config.json

Copy `config.json.example` to `config.json` and fill in your details.
`config.json` is git-ignored and will never be committed.

Key fields:

| Field | Notes |
|---|---|
| `accounts[].imap.server` | Your IMAP hostname |
| `accounts[].imap.sent_folder` | `"Sent Items"` (Outlook), `"Sent"` (Gmail/Fastmail). Use the Settings → Account Details → Discover Folders button to find the exact name. |
| `accounts[].imap.fetch_limit` | Max emails to fetch per folder (default 300) |
| `lm_studio.base_url` | Base URL of your LLM backend |
| `lm_studio.model` | Model identifier. For LM Studio with one model loaded, any string works. |
| `lm_studio.api_key` | Leave blank for local providers (LM Studio, Ollama). Required for OpenAI, Anthropic via LiteLLM, etc. |

### LLM provider presets

The Settings → AI Provider tab has presets for common backends:

| Preset | Base URL | Notes |
|---|---|---|
| LM Studio | `http://localhost:1234` | Load a model and enable the local server |
| Ollama | `http://localhost:11434` | `ollama serve` |
| LiteLLM proxy | `http://localhost:4000` | `litellm --model anthropic/...` |
| OpenAI | `https://api.openai.com` | Requires API key |

### IMAP notes

- **Outlook / Office 365**: Enable IMAP in Outlook settings → Mail → Sync email. If MFA is on, generate an **App Password** in Microsoft account security settings.
- **Gmail**: Enable IMAP in Gmail settings → See all settings → Forwarding and POP/IMAP. Use an App Password if 2FA is on.
- The Settings UI can discover all available folders from the server — use it to find the correct sent folder name.

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
                           _writing_style.md      (auto)
                           contact@example.com.md (auto, per sender)
                           about_me.md            (manual, pin to always include)
                │
                ▼
[Select email] ──► LLM reads email + knowledge files
                ──► Draft response shown in UI
                │
                ▼
[Instruction box] ──► Type instruction + Ctrl+Enter to refine
```

Knowledge generation is **incremental** — only emails added since the last build are processed.

---

## UI Guide

| Element | Action |
|---|---|
| `SYNC ALL` | Fetch latest emails from all accounts |
| `KNOWLEDGE` | Build/update writing style and contact profiles |
| `VIEW KB` | Browse, edit, pin, or delete knowledge files |
| `GENERATE` | Draft a response to the selected email |
| `COPY` | Copy draft to clipboard |
| Instruction box | Type a refinement instruction, submit with **Ctrl+Enter** |
| Settings (⚙) | Configure accounts, AI provider, add/remove accounts |

### Knowledge Base

- **Pin** any file (◆ button) to always include it in every prompt — useful for an "about me" file.
- **Purge contacts** removes all auto-generated contact profiles without affecting manual files or the style guide.

---

## Privacy

- All email data stays on your machine (`~/email_assistant/`).
- `config.json` (with credentials) is git-ignored.
- The SQLite database and knowledge files are stored outside the repo.
- When using a remote LLM API (OpenAI, etc.), email snippets are sent to that API — use a local provider if full privacy is required.
- No email is ever sent by this tool.
