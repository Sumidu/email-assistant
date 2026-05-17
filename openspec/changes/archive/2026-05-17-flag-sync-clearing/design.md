## Approach

`SEARCH FLAGGED` returns the *complete* set of currently-flagged UIDs for a folder. This is the authoritative source — anything locally flagged that is not in this set should be cleared.

The fix treats `_sync_flagged_uids` as a full mirror operation: after updating rows that are flagged, subtract the complement.

## Key Decision: Empty Set Behaviour

When `SEARCH FLAGGED` returns zero UIDs, the current code exits early. The correct behaviour is to clear all `is_flagged=1` rows for that folder, because zero flags is a valid server state. The early return is removed.

## Why a Separate DB Function

`update_email_flags_batch` only touches rows it receives — it cannot express "clear everything not in this set." A dedicated `clear_stale_flags` function makes the intent explicit and keeps the SQL contained in the database module.

## Scope Boundary

This fix only affects `is_flagged`. Read state (`is_read`) is handled separately by `_sync_recent_folder_flags` and is not touched here. The `clear_stale_flags` call is scoped to a single account/folder/uidvalidity triple, so multiple accounts and folders are handled independently per sync cycle.
