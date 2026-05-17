## Why

`_sync_flagged_uids` fetches all UIDs currently marked `\Flagged` on the server and updates their local flag state. However, it never *clears* `is_flagged` for emails that were previously flagged but have since been unflagged remotely — unless those emails fall within the 7-day recent sync window. Old emails whose flags change remain permanently stuck at `is_flagged=1` in the local database until a full resync.

## What Changes

- Add `clear_stale_flags()` to `modules/database.py`: sets `is_flagged=0` for all local rows with `is_flagged=1` whose UID is not in the current server-flagged set (for a given account/folder/uidvalidity). When the flagged set is empty, clears all local flags for that folder scope.
- Refactor `_sync_flagged_uids()` in `modules/imap_fetcher.py`: collect the full set of server-flagged UIDs across all chunks, remove the early-return-on-empty, and call `clear_stale_flags()` at the end so unflagged emails are always corrected.

## Capabilities

### Modified Capabilities

- `imap-sync`: Flag state for old emails now converges with server state on every normal sync, not just during full resync.

## Impact

- **Modified files**: `modules/database.py`, `modules/imap_fetcher.py`
- **No new dependencies**
- **No schema changes** — `is_flagged` column already exists
