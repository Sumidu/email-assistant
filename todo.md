# Email Assistant Backlog

Effort scale:

- XS: less than 1 hour
- S: 1-3 hours
- M: 0.5-1 day
- L: 1-3 days
- XL: several days or more; needs design/planning

## Bug Fixes

### XS

- [x] Fix progress task minimize/maximize icon
  - Category: Bug / UX
  - Clarification: Show an icon that matches the current state, for example minus for minimize and a clear expand icon for restore/maximize.
  - Notes: Small UI polish.

### S

- [x] Deactivate LLM actions when the active LLM is unavailable
  - Category: Bug / UX
  - Clarification: Disable or warn for `Generate`, chat `Send`, todo conversion, and knowledge update when the active LLM is red/unavailable.
  - Notes: Prevents predictable request failures.

- [x] Prevent Settings modal from closing on outside click
  - Category: Bug / UX
  - Clarification: Settings should only close through explicit actions such as close, escape, save, or cancel.
  - Notes: Prevents accidental loss of partially edited settings.

- [x] Save or preserve account form state before discovering folders
  - Category: Bug / UX
  - Clarification: Folder discovery should use the current form values without losing unsaved edits. Also when clicking on discover before saving, an error occurs.
  - Notes: Especially important for server, username, password, and provider fields.

- [x] Count spam actions as processed mail for today's counter
  - Category: Bug / Metrics
  - Clarification: Moving an email to spam should count as mail processed today.
  - Notes: Consider renaming the counter from `finished today` to `processed today`, or track finished and spam separately.

### M

- [ ] Add detailed logging for inbox sync problems
  - Category: Bug / Debug
  - Clarification: Add a debug mode in settings that logs folder selection, UIDVALIDITY, UID ranges, fetched counts, removed counts, and IMAP errors.
  - Notes: Useful for diagnosing remote/local sync problems.

- [ ] Allow full mailbox resynchronization
  - Category: Bug / Recovery
  - Clarification: Add a safe per-account or per-folder action to reset sync state and re-fetch mail.
  - Notes: Must protect local-only states such as Finished and knowledge metadata from accidental loss.

## Security And Privacy

### M-L

- [ ] Harden protection against email exploits
  - Category: Security
  - Clarification: Strengthen HTML sanitizing, block remote tracking images, remove scripts/styles/event handlers, ensure links open externally, and consider a plain-text mode.
  - Notes: Critical before sharing the app more broadly.

- [ ] Harden prompts against prompt injection and jailbreaks from email content
  - Category: Security / LLM
  - Clarification: Mark email content as untrusted, isolate system instructions from email text, and explicitly instruct the LLM not to follow instructions found inside emails.
  - Notes: Cannot be perfect, but can materially reduce risk.

### L

- [ ] Add sender to spam/block list and bulk-remove related mail
  - Category: Security / Automation
  - Clarification: After marking a sender as spam, optionally auto-remove other local mails from that sender and prevent future knowledge base entries for that sender.
  - Notes: Needs confirmation and clear separation between local policy and remote IMAP actions.

## Features

### S-M

- [ ] Prevent sleep while updating the knowledge base
  - Category: Feature / System
  - Clarification: Use a macOS-compatible keep-awake mechanism while long knowledge tasks run.
  - Notes: Check behavior for both browser mode and packaged `.app`.

- [ ] Generate a general `respond to this email` task button
  - Category: Feature
  - Clarification: Create a todo/reminder to respond to the selected email, ideally with source email reference and optional due date.
  - Notes: Fits well with the existing todo workflow.

- [x] Mark all mails as finished
  - Category: Feature
  - Clarification: Add a bulk action for the current folder/filter with a confirmation that shows the number of affected emails.
  - Notes: Implemented as a current folder/filter bulk action. Remains local-only and does not mutate remote IMAP. Also added per-email Spam/Junk actions in the list view.

- [x] Add theme setting for system dark/light mode
  - Category: Feature / UX
  - Clarification: Add a theme option such as `System`, `Light`, and `Dark`; when `System` is selected, detect `prefers-color-scheme` and update automatically when macOS changes appearance.
  - Notes: Current manual toggle can remain, but should respect the selected theme mode.

### M

- [ ] Add an in-app update checker
  - Category: Feature / Distribution
  - Clarification: Add a Settings/About button that checks GitHub for the latest version. In a git checkout it may offer `git pull --ff-only` plus setup/restart guidance; in the standalone app it should prefer GitHub Releases or open the release page.
  - Notes: Start conservatively with "Check for Updates"; full standalone auto-update requires release artifacts, versioning, and ideally checksum/signature verification.

- [ ] Newsletter detection
  - Category: Feature
  - Clarification: Detect newsletters using headers such as `List-Unsubscribe`, bulk sender patterns, no-reply senders, and frequency heuristics.
  - Notes: Could later be improved with LLM classification.

- [ ] Check and display importance markers
  - Category: Feature
  - Clarification: Read and show headers/flags such as `Importance`, `X-Priority`, or flagged/starred status.
  - Notes: Consider setting a local flag when a task is created from an email.

- [ ] Keep track of the daily counter over the last week
  - Category: Feature / Motivation
  - Clarification: Show recent processing history, for example finished/spam counts per day.
  - Notes: May need a small local stats table or careful aggregation from timestamps.

- [ ] Switch between email accounts
  - Category: Feature / UX
  - Clarification: Allow the user to focus one account at a time instead of showing multiple accounts together.
  - Notes: Helps separate work and private contexts.

### L

- [ ] LLM routing by task
  - Category: Feature / AI
  - Clarification: Configure which model handles draft generation, chat, knowledge updates, todo extraction, and calendar questions.
  - Notes: Include fallback behavior when a configured model is unavailable.

- [ ] Store knowledge base in an iCloud folder
  - Category: Feature / Data
  - Clarification: Make the KB path configurable and support moving existing knowledge files.
  - Notes: Coordinate this with the Obsidian-compatible KB format task so files can move between Email Assistant, iCloud, and external editors without losing metadata.

### M-L

- [ ] ADHD party mode
  - Category: Feature / Motivation
  - Clarification: Trigger celebratory animations when milestones are reached, for example every 100 processed emails.
  - Notes: Should be optional and easy to disable.

### L-XL

- [ ] Full progression system with streaks
  - Category: Feature / Motivation
  - Clarification: Add daily goals, streaks, achievements, and history.
  - Notes: Build on top of reliable daily/weekly counters.

## Developer And Architecture

### M

- [ ] Add a sync debug mode in settings
  - Category: Developer / Observability
  - Clarification: Add log-level controls and structured sync diagnostics.
  - Notes: Overlaps with detailed inbox sync logging above.

### L

- [ ] Refine full mailbox resync architecture
  - Category: Developer / Sync
  - Clarification: Model sync state, local-only actions, remote deletes, UIDVALIDITY resets, and folder roles more explicitly.
  - Notes: Important before broader distribution.

- [x] Make the knowledge base format Obsidian-compatible
  - Category: Developer / Data
  - Clarification: Redesign generated contact/profile Markdown so it can be edited in Obsidian and then read back by Email Assistant without losing aliases, wildcard patterns, source LLM, timestamps, and matching metadata.
  - Notes:
    - Prefer standard Markdown plus YAML frontmatter over app-specific sidecar-only metadata.
    - Add Obsidian-style wikilinks for people and concepts, for example `[[Jane Doe]]` or `[[jane@example.com]]`, so references to other persons are discoverable in the Markdown graph.
    - Decide on stable file naming and display names so Obsidian links remain valid even when a contact has aliases or multiple email addresses.
    - Support round-tripping: edits made in Obsidian should be preserved when Email Assistant updates or regenerates knowledge.
    - Consider a migration path from the current `_metadata.json` sidecar and contact markdown format.
    - Coordinate with the iCloud KB storage task to support moving files back and forth between apps.

## Suggested Implementation Order

1. Prevent Settings outside-close, fix progress icon, and disable LLM actions when unavailable.
2. Harden email exploit handling and prompt-injection resistance.
3. Add sync debug logging and full resync support.
4. Add spam sender policy and newsletter detection.
5. Implement LLM routing by task.
6. Add daily/weekly counters, then ADHD party mode.
7. Revisit iCloud/KB storage architecture.
