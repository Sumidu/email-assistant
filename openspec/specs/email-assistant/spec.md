# Email Assistant Specification

## Purpose

The Email Assistant is a local-first desktop/web application for reading synced email, generating draft replies with configurable LLM providers, and maintaining a Markdown-based knowledge base about contacts and domains.

The application SHALL help the user triage, understand, archive locally, and draft responses to email. It SHALL NOT send email or mutate the remote IMAP mailbox.

## Requirements

### Requirement: Local-first application shell

The application SHALL provide a browser-based UI served by the local Flask application.

#### Scenario: Start the local application

- **WHEN** the application is started with the project run script
- **THEN** it SHALL serve the user interface on port `5100`
- **AND** it SHALL expose API endpoints used by the frontend for email, settings, LLM, knowledge base, logs, and background task operations.

#### Scenario: Preserve runtime data outside the project checkout

- **WHEN** the application reads or writes persistent user data
- **THEN** it SHALL use the user data directory `~/email_assistant`
- **AND** it SHALL keep configuration in `~/email_assistant/config.json`
- **AND** it SHALL keep synced email data in `~/email_assistant/emails.db`
- **AND** it SHALL keep generated knowledge base Markdown files in `~/email_assistant/knowledge/`.

### Requirement: IMAP account configuration

The application SHALL allow the user to configure one or more IMAP accounts.

#### Scenario: Configure an account

- **WHEN** the user opens account settings
- **THEN** the application SHALL allow the user to enter account name, email address, IMAP host, IMAP port, username, password or app password, sent folder, and sync preferences.

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

#### Scenario: Read-only IMAP access

- **WHEN** the application connects to IMAP
- **THEN** it SHALL open folders in read-only mode
- **AND** it SHALL NOT mark messages read
- **AND** it SHALL NOT move, delete, archive, flag, or otherwise mutate messages on the remote server.

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
- **THEN** the application SHALL filter or append email list results while preserving the selected folder context.

#### Scenario: Show knowledge badges

- **WHEN** an email sender, recipient, alias, or matching wildcard has knowledge base data
- **THEN** the email list SHALL show a knowledge base badge for that email
- **AND** the badge SHALL use the knowledge base accent color.

#### Scenario: Open matching knowledge from an email badge

- **WHEN** the user clicks a knowledge base badge in the email list
- **THEN** the application SHALL open the knowledge base window
- **AND** it SHALL select the best matching entry for the email sender or related identity.

### Requirement: Email preview and local finishing

The application SHALL show the selected email and allow local-only triage actions.

#### Scenario: Open an email

- **WHEN** the user selects an email
- **THEN** the application SHALL show subject, sender, recipients, date, and body
- **AND** it SHALL render email content safely for viewing.

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

### Requirement: Knowledge base storage

The application SHALL store knowledge base entries as Markdown files.

#### Scenario: Store per-contact knowledge

- **WHEN** the application generates knowledge for a contact
- **THEN** it SHALL store the content as Markdown in `~/email_assistant/knowledge/`
- **AND** it SHALL keep the content editable as Markdown.

#### Scenario: Store writing style knowledge

- **WHEN** the application analyzes sent mail for writing style
- **THEN** it SHALL store the writing style guide as `_writing_style.md`.

#### Scenario: Track knowledge metadata

- **WHEN** a knowledge entry is created or updated
- **THEN** the application SHALL record metadata such as the generating LLM, aliases, wildcard patterns, pin state, and timestamps where available.

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

#### Scenario: Local secrets

- **WHEN** provider API keys or email passwords are stored
- **THEN** the application SHALL avoid exposing full secrets in the UI
- **AND** it SHOULD use local secure storage where available.

#### Scenario: Safe email rendering

- **WHEN** email body content contains HTML
- **THEN** the application SHALL render it in a way that avoids executing unsafe scripts or remote-control content.

## Out of Scope

The current system SHALL NOT provide the following behavior unless a future specification adds it:

- Sending email through SMTP or provider APIs.
- Mutating remote IMAP state, including remote archive, delete, move, flag, or mark-as-read operations.
- Multi-user cloud synchronization.
- A hosted web service mode for remote users.
- Guaranteed real-time push email delivery.
