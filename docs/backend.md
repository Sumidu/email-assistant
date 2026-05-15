# Backend

The backend is a Flask app created by `app.create_app()`. Routes are registered
by feature area and call into long-lived runtime objects from `app.runtime`.

## Important Runtime Objects

- `runtime.config`: migrated application configuration with Keychain secrets
  injected in memory.
- `runtime.fetchers`: one `IMAPFetcher` per configured account.
- `runtime.kb`: knowledge builder for Markdown knowledge files.
- `runtime.resp_gen`: response generator for draft/chat workflows.

## Persistence

`modules.database` owns the SQLite schema and query/update helpers. It also
coordinates with `modules.triage_store` so local finished/spam state can be
persisted and repaired across app starts.

The public import surface is intentionally still `modules.database`. Internals
are being extracted behind that facade into `modules/db` for schema setup,
date/thread helpers, and query filters.

## Route Services

Routes remain the public HTTP boundary. Pure parsing, normalization, and export
helpers should live in `app/services` so they can be tested without Flask, IMAP,
LLM, or network dependencies. Current examples include mail summary JSON/source
matching and todo parsing/ICS rendering.

## Background Tasks

Long-running operations use `app.task_runner.run_background()`. Only one task
runs at a time; `/api/task_status` and `/api/activity_log` expose state to the
frontend.

## Refactor Guidance

Prefer extracting tested helpers before moving route or persistence behavior.
The safest first splits are schema/migrations, email queries, triage state,
sync state, and calendar queries.
