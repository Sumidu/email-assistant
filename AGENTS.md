# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Commands

```bash
# Setup (first time)
./setup.sh          # creates venv, installs deps

# Run
./run.sh            # activates venv, starts Flask on :5100

# Manual run
source venv/bin/activate
python main.py

# Install a new dep
pip install <pkg> && pip freeze | grep <pkg> >> requirements.txt
```

No test suite. No linter configured.

## Architecture

Flask app (`main.py`) with four modules and a SQLite backend.

**Data flow:**
1. `IMAPFetcher.sync()` → pulls INBOX + Sent via IMAP → `database.save_email()` → `~/email_assistant/emails.db`
2. `KnowledgeBuilder.build()` → reads all emails from DB → calls LM Studio → writes markdown files to `~/email_assistant/knowledge/`
   - `_writing_style.md` — style guide from sent mail
   - `<email@addr>.md` — per-contact profile (top 40 senders)
3. `ResponseGenerator.generate_response()` → loads matching knowledge files → calls LM Studio → returns draft text
4. `VoiceHandler.transcribe_bytes()` → Whisper (local) → text → fed back into `generate_with_instruction()`

**LM Studio integration:** Both `KnowledgeBuilder` and `ResponseGenerator` call `POST /v1/chat/completions` on `http://localhost:1234` (OpenAI-compatible). Timeout is 180s. Model name is ignored when only one model is loaded.

**Background tasks:** Long operations (sync, build_knowledge) run in a daemon thread via `_bg()` in `main.py`. Frontend polls `/api/task_status` for progress. Only one background task runs at a time (409 if busy).

**No email is ever sent** — the tool is read-only on IMAP (readonly=True) and only drafts responses.

## Config

Config is stored at `~/email_assistant/config.json` (survives app rebuilds).
On first run it is auto-migrated from any old location beside the binary.
Key fields:
- `imap.sent_folder`: `"Sent Items"` for Outlook, `"Sent"` for Gmail
- `lm_studio.model`: ignored when LM Studio has one model loaded; set to `"local-model"` as default

## Runtime data locations

| Path | Contents |
|------|----------|
| `~/email_assistant/emails.db` | SQLite — all fetched emails |
| `~/email_assistant/knowledge/` | Generated markdown knowledge files |
