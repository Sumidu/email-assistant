# Email Assistant Specification

## Purpose

The Email Assistant is a local-first desktop/web application for reading synced email, generating draft replies with configurable LLM providers, and maintaining a Markdown-based knowledge base about contacts and domains.

The application SHALL help the user triage, understand, archive locally, and draft responses to email. It SHALL NOT send email. It SHALL keep normal reading, syncing, finishing, and drafting local-only, with remote mutations limited to explicit user actions such as moving a message to Spam/Junk or creating Exchange tasks.

## Requirements

### Requirement: Local-first application shell

The application SHALL provide a browser-based UI served by the local Flask application.

#### Scenario: Start the local application

- **WHEN** the application is started with the project run script
- **THEN** it SHALL serve the user interface on port `5100`
- **AND** it SHALL expose API endpoints used by the frontend for email, settings, LLM, knowledge base, logs, and background task operations.

#### Scenario: Start the bundled macOS application

- **WHEN** the application is built as a macOS `.app` bundle
- **THEN** it SHALL start a local Flask server in the background
- **AND** it SHALL open the UI in a native macOS webview window
- **AND** startup SHALL NOT require writing to iCloud knowledge files before the main window appears.

#### Scenario: Preserve runtime data outside the project checkout

- **WHEN** the application reads or writes persistent user data
- **THEN** it SHALL keep local app data in `~/Library/Application Support/Email Assistant`
- **AND** it SHALL keep configuration in `~/Library/Application Support/Email Assistant/config.json`
- **AND** it SHALL keep synced email data in `~/Library/Application Support/Email Assistant/emails.db`
- **AND** it SHALL keep logs in `~/Library/Logs/Email Assistant`
- **AND** it SHALL keep generated knowledge base Markdown files in `~/Library/Mobile Documents/com~apple~CloudDocs/Email Assistant/Knowledge/` when iCloud Drive is available, falling back to `~/Library/Application Support/Email Assistant/Knowledge/`.

#### Scenario: Export portable configuration

- **WHEN** the user exports a portable configuration snapshot
- **THEN** the application SHALL export non-secret account, provider, prompt, template, and sync configuration
- **AND** it SHALL exclude passwords and API keys
- **AND** it SHALL encrypt the export with a user-provided password
- **AND** it SHALL save the encrypted export to the app's iCloud Drive folder when available, falling back to local app storage.

### Requirement: IMAP account configuration

The application SHALL allow the user to configure one or more IMAP accounts.

#### Scenario: Configure an account

- **WHEN** the user opens account settings
- **THEN** the application SHALL allow the user to enter account name, email address, IMAP host, IMAP port, username, password or app password, sent folder, and sync preferences.

#### Scenario: Choose account provider type

- **WHEN** the user configures an account
- **THEN** the application SHALL allow choosing a provider type such as generic IMAP, Gmail, Outlook, Exchange, or iCloud
- **AND** it MAY suggest a provider type from the configured host or address
- **AND** the selected provider type SHALL be available for future calendar or task integrations.

#### Scenario: Discover folders

- **WHEN** the user requests folder discovery for an account
- **THEN** the application SHALL query the IMAP server for available folders
- **AND** it SHALL allow the user to map folders to roles such as inbox, sent, and other synchronized folders.

#### Scenario: Show account storage information

- **WHEN** an account is shown in settings or in the folders overview
- **THEN** the application SHALL expose an information affordance
- **AND** hovering that affordance SHALL show account details such as approximate local storage size and sync metadata where available.

### Requirement: IMAP synchronization

The application SHALL synchronize emails from configured IMAP accounts into the local SQLite database.

#### Scenario: Read-only IMAP access by default

- **WHEN** the application connects to IMAP
- **THEN** it SHALL open folders in read-only mode
- **AND** it SHALL NOT mark messages read
- **AND** it SHALL NOT move, delete, archive, flag, or otherwise mutate messages on the remote server during normal sync, browsing, finishing, knowledge generation, drafting, or todo extraction.

#### Scenario: Sync recent messages

- **WHEN** an account is configured to sync a limited recent set
- **THEN** the application SHALL download at most the configured number of recent messages per configured folder.

#### Scenario: Sync all messages

- **WHEN** an account is configured to sync all messages
- **THEN** the application SHALL incrementally import messages from configured folders
- **AND** it SHALL avoid re-downloading messages that already exist locally.

#### Scenario: Sync messages since a configured date

- **WHEN** an account is configured to sync messages since a date
- **THEN** the application SHALL import only messages from the configured date onward, subject to IMAP server support and local deduplication.

#### Scenario: Incremental sync

- **WHEN** the application has previous sync state for a folder
- **THEN** it SHALL use message identity and sync state to fetch only new or missing messages where possible
- **AND** it SHALL retain local metadata such as finished status when an existing email is encountered again.

#### Scenario: Remove locally cached messages deleted remotely

- **WHEN** a synced remote folder no longer contains a message UID that exists in the local database for that folder and UIDVALIDITY
- **THEN** the application SHALL remove that local email record
- **AND** it SHALL also remove locally finished copies whose original remote message disappeared
- **AND** it SHALL update folder counts and the visible email list so deleted remote messages disappear from the UI after sync.

#### Scenario: Automatic sync

- **WHEN** automatic sync is enabled for an account
- **THEN** the application SHALL periodically check for new messages according to the configured interval
- **AND** it SHALL import only new or missing messages.

#### Scenario: Finished emails are not restored to the active inbox

- **WHEN** an email has been marked finished locally
- **AND** a later sync sees the same remote message again
- **THEN** the application SHALL keep the email in the local Finished folder
- **AND** it SHALL NOT restore it to the active synced folder view.

### Requirement: Email list and folder navigation

The application SHALL provide a navigable email list grouped by local folders and accounts.

#### Scenario: Browse synchronized folders

- **WHEN** the user opens the main view
- **THEN** the application SHALL show synchronized accounts and folders in a sidebar
- **AND** it SHALL include the local Finished folder
- **AND** it SHALL allow the folder section to collapse to preserve horizontal space.

#### Scenario: Use portrait-oriented layouts

- **WHEN** the application viewport is narrow
- **THEN** the layout SHALL remain usable beside another mail client
- **AND** the folder sidebar, email list, email preview, and AI panel SHALL avoid overlapping critical controls.

#### Scenario: Search and load emails

- **WHEN** the user searches emails or loads more messages
- **THEN** the application SHALL query locally stored emails for the selected account and folder
- **AND** it SHALL search across subject, sender, recipients, and plain text body
- **AND** it SHALL NOT limit search scope to only the currently loaded page of visible messages
- **AND** it SHALL keep pagination available for additional matching results
- **AND** it SHALL preserve the selected folder context.

#### Scenario: Show thread rows in the email list

- **WHEN** a selected folder contains multiple local emails belonging to the same conversation thread
- **THEN** the email list SHALL show the newest matching email as the thread row
- **AND** it SHALL show compact received and sent count badges for the thread where counts are available
- **AND** unread and flagged indicators SHALL reflect matching thread state while preserving the selected folder context.

#### Scenario: Resize the email list column

- **WHEN** the user drags the divider at the right edge of the email list
- **THEN** the application SHALL resize the email list column with the mouse
- **AND** it SHALL keep the folder sidebar and main pane usable
- **AND** it SHALL persist the selected width locally across reloads.

#### Scenario: Show knowledge badges

- **WHEN** the sender of an email has an exact knowledge base entry
- **THEN** the email list SHALL show a knowledge base badge for that email
- **AND** the badge SHALL use the knowledge base accent color.

#### Scenario: Avoid recipient-only knowledge badges

- **WHEN** an email only matches knowledge for recipients, CC addresses, or unrelated participants
- **THEN** the email list SHALL NOT show the sender-level knowledge badge
- **AND** this badge behavior SHALL NOT prevent knowledge generation from creating entries for other relevant senders during explicit knowledge update tasks.

#### Scenario: Open matching knowledge from an email badge

- **WHEN** the user clicks a knowledge base badge in the email list
- **THEN** the application SHALL open the knowledge base window
- **AND** it SHALL select the best matching entry for the email sender or related identity.

### Requirement: Calendar synchronization and storage

The application SHALL support local calendar synchronization for accounts with calendar access.

#### Scenario: Configure calendar support for an account

- **WHEN** the user edits an email account
- **THEN** the application SHALL allow the user to choose the account/calendar provider type
- **AND** it SHALL allow enabling or disabling calendar sync for that account
- **AND** it SHALL keep temporary diagnostic calendar test controls out of the normal account settings UI.

#### Scenario: Sync calendar events locally

- **WHEN** calendar sync is enabled for an account
- **THEN** the application SHALL import calendar events into the local SQLite database
- **AND** it SHALL sync a bounded window of approximately the last 3 months through the next 6 months
- **AND** it SHALL store calendar data locally for viewing and LLM context.

#### Scenario: Sync Exchange calendar through EWS NTLM

- **WHEN** an account is configured for Microsoft, Exchange, or Outlook calendar access
- **AND** EWS NTLM access is available
- **THEN** the application SHALL use EWS NTLM to read calendar events
- **AND** it SHALL NOT require Microsoft Graph app registration for this path.

#### Scenario: Preserve local-first calendar behavior

- **WHEN** calendar events are synced
- **THEN** the application SHALL treat calendar access as read-only
- **AND** it SHALL NOT create, edit, delete, invite, or otherwise mutate remote calendar events.

### Requirement: Calendar view

The application SHALL provide a calendar modal for viewing locally synced events.

#### Scenario: Show week calendar

- **WHEN** the user opens the calendar view
- **THEN** the application SHALL show a week-based calendar layout
- **AND** it SHALL fit all seven days inside the modal without requiring horizontal scrolling.

#### Scenario: Show all-day events

- **WHEN** events span a whole day or multiple days
- **THEN** the application SHALL render them in a dedicated all-day row
- **AND** it SHALL NOT allow all-day entries to break alignment of the day headers or timed grid.

#### Scenario: Show overlapping events

- **WHEN** multiple timed events overlap
- **THEN** the application SHALL place them side by side within the relevant day column
- **AND** it SHALL keep each event visually associated with its time range.

#### Scenario: Prioritize event titles

- **WHEN** events are shown in the calendar grid
- **THEN** each event SHALL prioritize the title as the first visible content
- **AND** compact or overlapping events MAY hide time details until hover
- **AND** hovering an event SHALL expand it downward to reveal additional content.

#### Scenario: Select calendar event

- **WHEN** the user clicks a calendar event
- **THEN** the application SHALL update the detail area
- **AND** it SHALL highlight the selected event colorwise
- **AND** it SHALL NOT keep the event expanded after the pointer leaves.

#### Scenario: Show selected event details

- **WHEN** an event is selected
- **THEN** the calendar modal SHALL show a structured detail view at the bottom of the modal
- **AND** the detail view SHALL include title, time, date, account, free/busy state, location, and description where available.

#### Scenario: Highlight today

- **WHEN** the current week contains the current day
- **THEN** the calendar view SHALL subtly highlight the current day column across header, all-day row, and timed grid.

### Requirement: Calendar context for LLM responses

The application SHALL make locally stored calendar information available to LLM-assisted drafting and chat when relevant.

#### Scenario: Ask calendar-aware questions

- **WHEN** the user asks about availability, meeting slots, scheduling, or related calendar topics
- **THEN** the application SHALL include relevant locally synced calendar context in the LLM prompt
- **AND** it SHALL use the calendar data to support answers such as next available meeting slots.

#### Scenario: Calendar context remains local

- **WHEN** calendar context is used for LLM generation
- **THEN** the application SHALL only use locally synced calendar records
- **AND** it SHALL NOT mutate or publish calendar data.

### Requirement: Email preview and local finishing

The application SHALL show the selected email and allow local-only triage actions.

#### Scenario: Open an email

- **WHEN** the user selects an email
- **THEN** the application SHALL show subject, sender, recipients, date, and body
- **AND** it SHALL render email content safely for viewing.

#### Scenario: Open a thread

- **WHEN** the user selects a thread row from the email list
- **THEN** the application SHALL show the locally available emails in that thread in the message pane
- **AND** it SHALL identify the newest matching email as the reply target for actions such as draft generation, knowledge generation, todos, done, and spam
- **AND** it SHALL collapse obvious quoted plain-text history where possible to reduce repeated conversation content.

#### Scenario: Configure thread display order

- **WHEN** the user changes the thread order setting
- **THEN** the application SHALL allow choosing whether the newest email appears at the top or bottom inside an opened thread
- **AND** the default SHALL be newest email at the top
- **AND** the setting SHALL be saved in application configuration.

#### Scenario: Open email links externally

- **WHEN** the user activates a link in email content
- **THEN** the application SHALL open the link in the system default browser
- **AND** it SHALL NOT navigate the application webview away from the local Email Assistant UI.

#### Scenario: Resize preview and AI panes

- **WHEN** the user drags the divider between email preview and AI panel
- **THEN** the application SHALL resize the panes dynamically
- **AND** it SHALL keep controls visible and usable.

#### Scenario: Mark an email finished

- **WHEN** the user marks an email as done or finished
- **THEN** the application SHALL move the email to the local Finished folder
- **AND** it SHALL NOT alter the remote IMAP mailbox.

#### Scenario: Advance after finishing an email

- **WHEN** the selected email is marked finished from the detail view or list view
- **THEN** the application SHALL automatically select the next email in the current list when one exists
- **AND** it SHALL otherwise select a nearby remaining email when possible.

#### Scenario: Unarchive a finished email

- **WHEN** the user views a finished email
- **THEN** the application SHALL offer an unarchive action
- **AND** activating it SHALL remove the local finished marker and return the email to its previous local folder context where possible.

#### Scenario: Move an email to remote spam

- **WHEN** the user explicitly clicks the spam action for a selected email
- **THEN** the application SHALL locate the account's configured or discovered Spam/Junk folder
- **AND** it SHALL verify the tracked IMAP UID and folder UIDVALIDITY before moving the message
- **AND** it SHALL move the message to the remote Spam/Junk folder using IMAP MOVE when supported
- **AND** it SHALL remove the message from the active local UI or move it to the local spam folder if that folder is synchronized
- **AND** it SHALL surface a clear error without deleting local data if the remote move cannot be verified.

### Requirement: Todo discovery from email

The application SHALL help the user find actionable todos in locally stored emails without mutating the remote mailbox.

#### Scenario: Live-filter todo candidates by email scope

- **WHEN** the user opens the todo finder
- **THEN** the default date range SHALL cover the previous 7 days through today
- **AND** the window SHALL live-count matching local emails for the selected account, folder, date range, and search filter without requiring a separate filter click
- **AND** changing the filter fields SHALL refresh the count automatically.

#### Scenario: Find todos for a single email

- **WHEN** the user opens an email
- **THEN** the email detail actions SHALL include a todo action labeled `Find Todos`
- **AND** the action SHALL open the todo finder scoped to exactly that email
- **AND** the date and search filters SHALL be disabled while the finder is scoped to that email
- **AND** the application SHALL start the LLM todo scan directly for that single email without an additional confirmation dialog.

#### Scenario: Confirm LLM todo scanning

- **WHEN** the user starts todo extraction for a multi-email filtered set
- **THEN** the application SHALL show a confirmation dialog
- **AND** the confirmation SHALL warn how many local emails will be individually sent to the selected LLM for scanning.

#### Scenario: Process emails individually

- **WHEN** todo extraction runs
- **THEN** the application SHALL send each selected email to the LLM as an individual request
- **AND** it SHALL avoid generating a todo when the email does not contain a concrete action for the user
- **AND** it SHALL log each LLM request in the local log.

#### Scenario: Show todo extraction progress

- **WHEN** todo extraction is running
- **THEN** the todo finder SHALL show a progress bar, numeric progress such as `10 / 241`, and a preview of the current email being processed.

#### Scenario: Verify a todo candidate against its source email

- **WHEN** todo candidates are displayed
- **THEN** selecting or focusing a candidate SHALL show the source email in the todo finder preview pane where available
- **AND** it SHALL highlight the active candidate.

#### Scenario: Parse todo output safely

- **WHEN** an LLM response contains reasoning, prose, Markdown fences, or malformed non-JSON text
- **THEN** the application SHALL NOT treat each response line as a todo
- **AND** it SHALL only accept structured todo objects that can be parsed from the final JSON output.

#### Scenario: Use reminder-compatible todo fields

- **WHEN** todo candidates are displayed
- **THEN** each todo SHALL include editable fields for title, due date, description, tags, and location.
- **AND** the due date field SHALL use a date picker
- **AND** it SHALL allow an empty date.

#### Scenario: Export todos to a reminder system

- **WHEN** the user selects todo candidates to use
- **THEN** the application SHALL allow exporting the selected todos as a VTODO/iCalendar file for compatible reminder or calendar clients
- **AND** it SHALL allow creating tasks in a selected Exchange account through EWS when EWS NTLM is configured
- **AND** it SHALL ask for explicit confirmation before writing tasks to the remote Exchange account
- **AND** after successful Exchange task creation it SHALL show a success message with a clear close action.

### Requirement: Email triage motivation

The application SHALL show lightweight feedback that helps the user continue processing email.

#### Scenario: Show today's finished mail count

- **WHEN** the main window is visible
- **THEN** the lower-left status area SHALL show how many emails the user has processed today
- **AND** finished and spam actions SHALL contribute to the processed counter
- **AND** the count SHALL update after finishing, unarchiving, or moving emails to spam.

### Requirement: Draft generation and chat

The application SHALL generate draft replies and chat responses from selected email context.

#### Scenario: Generate a draft

- **WHEN** the user asks the application to generate a response for the selected email
- **THEN** the application SHALL call the selected LLM provider with the email content, selected context, configured prompts, and matching knowledge base entries
- **AND** it SHALL display the returned text as a draft
- **AND** it SHALL NOT send the draft.

#### Scenario: Use UTF-8 output

- **WHEN** the LLM produces non-ASCII characters such as German umlauts
- **THEN** the application SHALL preserve and display UTF-8 text in the generated draft and chat output.

#### Scenario: Copy a draft

- **WHEN** the user clicks the copy action
- **THEN** the application SHALL copy the generated draft to the clipboard
- **AND** the copy button SHALL be represented by a copy icon with a tooltip.

#### Scenario: Copy and finish

- **WHEN** the user clicks the copy-and-done action
- **THEN** the application SHALL copy the generated draft to the clipboard
- **AND** it SHALL mark the current email finished locally
- **AND** the button SHALL use a green treatment and communicate copy plus finished semantics.

#### Scenario: Send a chat instruction

- **WHEN** the user enters a message in the AI chat panel
- **THEN** the application SHALL send the instruction to the selected LLM provider using the current email and selected context
- **AND** it SHALL append the response to the chat view.

#### Scenario: Use quick templates

- **WHEN** quick templates are configured
- **THEN** the application SHALL show template buttons near the send controls
- **AND** selecting a template SHALL send the configured user message to the chat.

### Requirement: Quick template configuration

The application SHALL allow the user to configure reusable quick chat templates.

#### Scenario: Configure a quick template

- **WHEN** the user opens quick template settings
- **THEN** the application SHALL allow the user to choose an emoji and enter the user message that will be sent to the chat.

#### Scenario: Reset quick templates

- **WHEN** the user resets quick templates to default
- **THEN** the application SHALL restore at least two templates:
- one affirmative template for confirming or accepting what was proposed
- one negative template for declining or rejecting what was proposed.

### Requirement: LLM provider configuration

The application SHALL support multiple OpenAI-compatible LLM providers.

#### Scenario: Add or edit a provider

- **WHEN** the user opens AI provider settings
- **THEN** the application SHALL allow creating, selecting, editing, and deleting provider configurations
- **AND** each provider SHALL include a display name, base URL, model identifier, API key where needed, and enabled/default state.

#### Scenario: Select active provider

- **WHEN** multiple providers are configured
- **THEN** the main UI SHALL provide a dropdown for choosing the active provider used for generation.

#### Scenario: Configure default provider

- **WHEN** the user marks a provider as default
- **THEN** the application SHALL use that provider as the initial active provider on subsequent launches unless another provider is explicitly selected.

#### Scenario: Show provider availability

- **WHEN** providers are shown in the main UI
- **THEN** the application SHALL show a green or red availability indicator next to each provider
- **AND** the indicator SHALL reflect the result of the latest provider health check.

#### Scenario: Retest active provider availability

- **WHEN** the user clicks the availability indicator for the active LLM provider
- **THEN** the application SHALL run a fresh health check for that provider
- **AND** it SHALL show an intermediate testing state
- **AND** it SHALL update the indicator and status message with the new result.

### Requirement: Knowledge base storage

The application SHALL store knowledge base entries as Markdown files.

#### Scenario: Store per-contact knowledge

- **WHEN** the application generates knowledge for a contact
- **THEN** it SHALL store the content as Markdown in the configured Knowledge directory
- **AND** it SHALL keep the content editable as Markdown.

#### Scenario: Store writing style knowledge

- **WHEN** the application analyzes sent mail for writing style
- **THEN** it SHALL store the writing style guide as `_writing_style.md`.

#### Scenario: Track knowledge metadata

- **WHEN** a knowledge entry is created or updated
- **THEN** the application SHALL record metadata such as the generating LLM, aliases, wildcard patterns, pin state, and timestamps where available.

#### Scenario: Store Obsidian-compatible knowledge metadata

- **WHEN** a knowledge entry is saved as Markdown
- **THEN** the application SHALL include YAML frontmatter compatible with Obsidian properties
- **AND** the frontmatter SHALL include stable metadata such as title, type, contact email, aliases, wildcard match patterns, source, generating LLM, timestamp, and tags where available
- **AND** the application SHALL read aliases and wildcard match patterns back from frontmatter when files are edited outside the app.

#### Scenario: Preserve Obsidian edits

- **WHEN** a user edits a knowledge file in an external Markdown editor such as Obsidian
- **THEN** the application SHALL preserve the Markdown body on subsequent saves
- **AND** it SHALL avoid exposing YAML frontmatter as normal knowledge content in LLM prompts or in-app read mode.

#### Scenario: Enrich contact references with Obsidian links

- **WHEN** a knowledge entry is created, regenerated, renamed, merged, or manually saved
- **THEN** the application SHALL rebuild its contact index from Markdown frontmatter and filenames
- **AND** it SHALL add Obsidian wikilinks for strong mentions of known contacts in Markdown bodies
- **AND** it SHALL avoid modifying YAML frontmatter, headings, code blocks, existing wiki links, or Markdown links
- **AND** it SHALL skip ambiguous display names rather than link to the wrong contact.

#### Scenario: Remove model reasoning from knowledge

- **WHEN** knowledge content is generated, migrated, linked, or saved
- **THEN** the application SHALL remove model reasoning fragments such as `<think>...</think>`, thinking fences, reasoning sections, and analysis tags before storing or showing the entry
- **AND** it SHALL preserve the user-visible Markdown content that remains.

### Requirement: Knowledge base viewing and editing

The application SHALL provide a knowledge base window for viewing, editing, filtering, and deleting entries.

#### Scenario: Render Markdown in read mode

- **WHEN** the user views a knowledge entry without editing
- **THEN** the application SHALL render the Markdown content as formatted content.

#### Scenario: Preserve Markdown in edit mode

- **WHEN** the user edits a knowledge entry
- **THEN** the application SHALL present the raw Markdown text
- **AND** saving SHALL preserve Markdown formatting.

#### Scenario: Search knowledge entries

- **WHEN** the user enters a knowledge base search query
- **THEN** the application SHALL filter entries by file name, display name, Markdown content, aliases, wildcard patterns, and metadata where available.

#### Scenario: Rename a knowledge entry

- **WHEN** the user renames a knowledge entry
- **THEN** the application SHALL update the entry identity and backing Markdown filename or metadata
- **AND** it SHALL preserve content and related metadata.

#### Scenario: Delete individual knowledge entries

- **WHEN** the user deletes a selected knowledge entry
- **THEN** the application SHALL remove that entry without requiring a full purge of all contact knowledge.

#### Scenario: Filter by generating LLM

- **WHEN** the user filters the knowledge base by LLM
- **THEN** the application SHALL show entries generated by the selected LLM
- **AND** it SHALL allow deleting entries generated by a weaker or undesired LLM.

#### Scenario: Purge generated contact knowledge

- **WHEN** the user uses the purge action
- **THEN** the application SHALL remove generated contact knowledge according to the requested scope
- **AND** it SHALL preserve unrelated runtime data.

### Requirement: Knowledge base generation

The application SHALL generate knowledge base entries from locally stored emails.

#### Scenario: Update the full knowledge base

- **WHEN** the user starts a full knowledge base update
- **THEN** the application SHALL ask for confirmation before starting
- **AND** the confirmation SHALL warn that this is a longer task
- **AND** it SHALL show how many messages will be parsed where that count is available.

#### Scenario: Generate knowledge for one contact

- **WHEN** the user clicks generate knowledge for the selected email
- **THEN** the application SHALL find locally stored emails from or to the relevant person
- **AND** it SHALL generate or update the matching knowledge entry for that person only.

#### Scenario: Live-update knowledge badges

- **WHEN** a background knowledge task creates, updates, deletes, renames, or merges entries
- **THEN** the email list knowledge badges SHALL refresh without requiring a full page reload.

### Requirement: Knowledge matching

The application SHALL match knowledge base entries to emails using exact addresses, aliases, and wildcard patterns.

#### Scenario: Exact email match

- **WHEN** an email sender or recipient exactly matches a knowledge entry identity
- **THEN** the application SHALL associate that email with the entry.

#### Scenario: Alias match

- **WHEN** a knowledge entry contains aliases
- **AND** an email sender or recipient matches one of those aliases
- **THEN** the application SHALL associate that email with the canonical entry.

#### Scenario: Wildcard domain match

- **WHEN** a knowledge entry contains a wildcard such as `*.team.example.com`
- **AND** an email address matches that wildcard
- **THEN** the application SHALL associate that email with the wildcard knowledge entry.

#### Scenario: Use matching entries in generation

- **WHEN** the application generates a draft or chat response for an email
- **THEN** it SHALL include exact, alias, wildcard, and pinned knowledge entries that are relevant to the prompt context.

### Requirement: Knowledge entry merge

The application SHALL allow two knowledge entries to be merged into one canonical entry.

#### Scenario: Select entries to merge

- **WHEN** the user selects exactly two knowledge entries
- **THEN** the knowledge base window SHALL enable a merge action.

#### Scenario: Merge entries

- **WHEN** the user merges two selected entries
- **THEN** the application SHALL choose or ask for the surviving entry
- **AND** it SHALL append or combine the Markdown knowledge from the removed entry into the surviving entry
- **AND** it SHALL add an Obsidian wikilink reference to the removed entry name in the merged Markdown body
- **AND** it SHALL add the removed entry identity as an alias of the surviving entry
- **AND** it SHALL merge aliases, wildcard patterns, pinned state, and metadata where possible
- **AND** it SHALL remove the redundant entry from the knowledge base list.

### Requirement: Advanced prompt configuration

The application SHALL allow the user to adjust LLM prompts.

#### Scenario: Edit prompts

- **WHEN** the user opens advanced settings
- **THEN** the application SHALL show configurable prompts used for response generation, instruction following, and knowledge generation.

#### Scenario: Reset prompts

- **WHEN** the user clicks reset to default
- **THEN** the application SHALL restore the built-in default prompts.

### Requirement: Background task progress

The application SHALL show progress for long-running tasks.

#### Scenario: Start a background task

- **WHEN** a sync, knowledge update, or other long task starts
- **THEN** the application SHALL show a task progress window
- **AND** it SHALL report task label, progress, status, and completion or error information.

#### Scenario: Start sync progress minimized

- **WHEN** a synchronization task starts from the main UI
- **THEN** the task progress UI SHOULD start minimized when configured by the application
- **AND** the minimized indicator SHALL remain visible without covering the email preview, draft, or chat input.

#### Scenario: Prevent concurrent background tasks

- **WHEN** one background task is already running
- **AND** another exclusive background task is requested
- **THEN** the application SHALL reject the second task with a busy response.

#### Scenario: Minimize progress window

- **WHEN** the user minimizes the task progress window
- **THEN** the application SHALL show a compact minimized progress indicator
- **AND** it SHALL position the minimized indicator so it does not overlap the AI chat input area.

#### Scenario: Complete a task

- **WHEN** a background task completes
- **THEN** the application SHALL show completion state
- **AND** it SHOULD auto-close or stay minimized in a way that does not obstruct the main workflow.

#### Scenario: Keep status line readable

- **WHEN** a long status or error message is shown in the lower status bar
- **THEN** the status text SHALL truncate or wrap within its allocated area
- **AND** it SHALL NOT overlap neighboring status controls such as the processed counter or LLM selector.

### Requirement: Logs

The application SHALL expose LLM and application activity logs from settings.

#### Scenario: Open logs

- **WHEN** the user opens settings
- **THEN** the logs view SHALL be available from the settings menu
- **AND** the former debug affordance SHALL NOT appear as a misplaced primary UI icon.

#### Scenario: Show readable timestamps

- **WHEN** log entries occurred recently
- **THEN** the logs view SHALL show human-readable relative timestamps
- **AND** it SHALL preserve chronological ordering.

#### Scenario: Preserve full log title

- **WHEN** a log title is truncated in the table
- **THEN** the application SHALL provide a delayed tooltip containing the full title.

#### Scenario: Track unread logs

- **WHEN** new log entries appear
- **THEN** the logs view SHALL mark them unread
- **AND** it SHALL provide a mark-all-as-read action.

#### Scenario: Show token estimates per log entry

- **WHEN** log entries represent LLM calls
- **THEN** the logs view SHALL show estimated input, output, and total token counts for each entry where available.

#### Scenario: Summarize recent token usage

- **WHEN** the user opens the logs view
- **THEN** the application SHALL summarize estimated LLM usage for the last 24 hours and the last 7 days
- **AND** it SHALL show entry count, input tokens, output tokens, and total tokens for those windows where available.

#### Scenario: Refresh logs

- **WHEN** the user refreshes logs
- **THEN** the application SHALL reload log data from the local log source
- **AND** it SHALL preserve the meaning of unread markers where possible.

### Requirement: Settings structure

The application SHALL organize settings to avoid duplicated account detail views.

#### Scenario: Add account

- **WHEN** the user clicks add account
- **THEN** the application SHALL open the account detail form as part of the add/edit workflow
- **AND** it SHALL NOT require a permanent separate top-level Account Details tab.

#### Scenario: Settings tabs

- **WHEN** the settings window is open
- **THEN** it SHALL provide tabs for account management, AI provider configuration, advanced settings, logs, and other configuration groups as needed.

### Requirement: Visual design and accessibility

The application SHALL maintain a modern macOS-compatible visual style with sufficient contrast.

#### Scenario: Light and dark modes

- **WHEN** the user uses the application in light or dark mode
- **THEN** text, icons, buttons, badges, and panels SHALL remain legible
- **AND** important actions SHALL have visible focus, hover, disabled, and active states.

#### Scenario: Knowledge base accent color

- **WHEN** UI elements relate to the knowledge base
- **THEN** they SHALL use the knowledge base accent color consistently, including KB badges, Knowledge buttons, View KB buttons, and Update Knowledge Base controls.
- **AND** email-level knowledge generation actions SHALL use the same knowledge base accent and symbol.

#### Scenario: Todo accent color

- **WHEN** UI elements relate to todo discovery, todo conversion, or Exchange task creation
- **THEN** they SHALL use a dedicated todo accent color distinct from knowledge base orange, confirmation blue, finish green, and error red
- **AND** todo actions SHALL use a todo symbol where compact labeling benefits from visual recognition
- **AND** the todo extraction progress bar SHALL use the todo accent color.

#### Scenario: Finished action color

- **WHEN** an action marks an email finished or done
- **THEN** it SHALL use the finishing accent color.

#### Scenario: Primary generation action

- **WHEN** the Generate action is shown near draft controls
- **THEN** it SHALL use the same orange accent family as the Draft headline.

### Requirement: Safety and privacy

The application SHALL prioritize local privacy and non-destructive behavior.

#### Scenario: No outbound email

- **WHEN** the user generates, copies, or marks a draft done
- **THEN** the application SHALL NOT send email.

#### Scenario: No remote archive

- **WHEN** the user marks an email finished
- **THEN** the application SHALL NOT move, delete, archive, or flag the remote IMAP message.

#### Scenario: Explicit remote mutation boundaries

- **WHEN** the application performs a remote mutation
- **THEN** it SHALL only do so for a user-initiated action that clearly communicates the remote effect
- **AND** currently permitted remote mutations SHALL be limited to moving a selected email to Spam/Junk and creating selected Exchange tasks
- **AND** it SHALL avoid destructive remote deletes.

#### Scenario: Local secrets

- **WHEN** provider API keys or email passwords are stored
- **THEN** the application SHALL avoid exposing full secrets in the UI
- **AND** it SHOULD use local secure storage where available.

#### Scenario: Safe email rendering

- **WHEN** email body content contains HTML
- **THEN** the application SHALL render it in a way that avoids executing unsafe scripts or remote-control content.

### Requirement: Distribution and update planning

The application SHALL support maintainable local development and packaged macOS distribution.

#### Scenario: Build the macOS application

- **WHEN** the user runs the build script
- **THEN** the application SHALL build a macOS `.app` bundle using the configured PyInstaller spec
- **AND** excluded heavyweight optional dependencies SHALL NOT prevent the bundle from starting when those features are not used.

#### Scenario: Track an in-app update feature

- **WHEN** an in-app update checker is planned
- **THEN** the specification and todo list SHALL describe a conservative first version that checks GitHub for a newer release or checkout state
- **AND** standalone automatic updates SHALL require release artifacts, versioning, and checksum or signature verification before replacing local app files.

## Out of Scope

The current system SHALL NOT provide the following behavior unless a future specification adds it:

- Sending email through SMTP or provider APIs.
- Mutating remote IMAP state other than the explicit Spam/Junk move action.
- Remote archive, remote delete, remote flag, or remote mark-as-read operations.
- Multi-user cloud synchronization. iCloud storage is limited to single-user portability of knowledge files and non-secret encrypted configuration exports.
- A hosted web service mode for remote users.
- Guaranteed real-time push email delivery.
