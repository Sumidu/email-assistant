# Email Assistant Priority List

## Priority Summary (reorder lines to set priority)

1. Harden protection against email exploits
2. Harden prompts against prompt injection and jailbreaks from email content
3. Add detailed logging for inbox sync problems
4. Allow full mailbox resynchronization
5. Add sender to spam/block list and bulk-remove related mail
6. Prevent sleep while updating the knowledge base
7. Generate a general `respond to this email` task button
8. Mark all mails as finished
9. Add theme setting for system dark/light mode
10. Add an in-app update checker
11. Newsletter detection
12. Check and display importance markers
13. Keep track of the daily counter over the last week
14. Switch between email accounts
15. LLM routing by task
16. Store knowledge base in an iCloud folder
17. ADHD party mode
18. Full progression system with streaks
19. Add sync debug mode in settings
20. Refine full mailbox resync architecture

---

## Bug Fixes

### 1. Add detailed logging for inbox sync problems
- **Category:** Bug / Debug
- **Clarification:** Add a debug mode in settings that logs folder selection, UIDVALIDITY, UID ranges, fetched counts, removed counts, and IMAP errors.
- **Notes:** Useful for diagnosing remote/local sync problems.

### 2. Allow full mailbox resynchronization
- **Category:** Bug / Recovery
- **Clarification:** Add a safe per-account or per-folder action to reset sync state and re-fetch mail.
- **Notes:** Must protect local-only states such as Finished and knowledge metadata from accidental loss.

---

## Security And Privacy

### 3. Harden protection against email exploits
- **Category:** Security
- **Clarification:** Strengthen HTML sanitizing, block remote tracking images, remove scripts/styles/event handlers, ensure links open externally, and consider a plain-text mode.
- **Notes:** Critical before sharing the app more broadly.

### 4. Harden prompts against prompt injection and jailbreaks from email content
- **Category:** Security / LLM
- **Clarification:** Mark email content as untrusted, isolate system instructions from email text, and explicitly instruct the LLM not to follow instructions found inside emails.
- **Notes:** Cannot be perfect, but can materially reduce risk.

### 5. Add sender to spam/block list and bulk-remove related mail
- **Category:** Security / Automation
- **Clarification:** After marking a sender as spam, optionally auto-remove other local mails from that sender and prevent future knowledge base entries for that sender.
- **Notes:** Needs confirmation and clear separation between local policy and remote IMAP actions.

---

## Features

### 6. Prevent sleep while updating the knowledge base
- **Category:** Feature / System
- **Clarification:** Use a macOS-compatible keep-awake mechanism while long knowledge tasks run.
- **Notes:** Check behavior for both browser mode and packaged `.app`.

### 7. Generate a general `respond to this email` task button
- **Category:** Feature
- **Clarification:** Create a todo/reminder to respond to the selected email, ideally with source email reference and optional due date.
- **Notes:** Fits well with the existing todo workflow.

### 8. Mark all mails as finished
- **Category:** Feature
- **Clarification:** Add a bulk action for the current folder/filter with a confirmation that shows the number of affected emails.
- **Notes:** Should remain local-only and not mutate remote IMAP.

### 9. Add theme setting for system dark/light mode
- **Category:** Feature / UX
- **Clarification:** Add a theme option such as `System`, `Light`, and `Dark`; when `System` is selected, detect `prefers-color-scheme` and update automatically when macOS changes appearance.
- **Notes:** Current manual toggle can remain, but should respect the selected theme mode.

### 10. Add an in-app update checker
- **Category:** Feature / Distribution
- **Clarification:** Add a Settings/About button that checks GitHub for the latest version. In a git checkout it may offer `git pull --ff-only` plus setup/restart guidance; in the standalone app it should prefer GitHub Releases or open the release page.
- **Notes:** Start conservatively with "Check for Updates"; full standalone auto-update requires release artifacts, versioning, and ideally checksum/signature verification.

### 11. Newsletter detection
- **Category:** Feature
- **Clarification:** Detect newsletters using headers such as `List-Unsubscribe`, bulk sender patterns, no-reply senders, and frequency heuristics.
- **Notes:** Could later be improved with LLM classification.

### 12. Check and display importance markers
- **Category:** Feature
- **Clarification:** Read and show headers/flags such as `Importance`, `X-Priority`, or flagged/starred status.
- **Notes:** Consider setting a local flag when a task is created from an email.

### 13. Keep track of the daily counter over the last week
- **Category:** Feature / Motivation
- **Clarification:** Show recent processing history, for example finished/spam counts per day.
- **Notes:** May need a small local stats table or careful aggregation from timestamps.

### 14. Switch between email accounts
- **Category:** Feature / UX
- **Clarification:** Allow the user to focus one account at a time instead of showing multiple accounts together.
- **Notes:** Helps separate work and private contexts.

### 15. LLM routing by task
- **Category:** Feature / AI
- **Clarification:** Configure which model handles draft generation, chat, knowledge updates, todo extraction, and calendar questions.
- **Notes:** Include fallback behavior when a configured model is unavailable.

### 16. Store knowledge base in an iCloud folder
- **Category:** Feature / Data
- **Clarification:** Make the KB path configurable and support moving existing knowledge files.
- **Notes:** Coordinate this with the Obsidian-compatible KB format task so files can move between Email Assistant, iCloud, and external editors without losing metadata.

### 17. ADHD party mode
- **Category:** Feature / Motivation
- **Clarification:** Trigger celebratory animations when milestones are reached, for example every 100 processed emails.
- **Notes:** Should be optional and easy to disable.

### 18. Full progression system with streaks
- **Category:** Feature / Motivation
- **Clarification:** Add daily goals, streaks, achievements, and history.
- **Notes:** Build on top of reliable daily/weekly counters.

---

## Developer And Architecture

### 19. Add a sync debug mode in settings
- **Category:** Developer / Observability
- **Clarification:** Add log-level controls and structured sync diagnostics.
- **Notes:** Overlaps with detailed inbox sync logging above.

### 20. Refine full mailbox resync architecture
- **Category:** Developer / Sync
- **Clarification:** Model sync state, local-only actions, remote deletes, UIDVALIDITY resets, and folder roles more explicitly.
- **Notes:** Important before broader distribution.