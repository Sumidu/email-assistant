## 1. Database Layer

- [x] 1.1 Add `clear_stale_flags(account_id, folder, uidvalidity, flagged_uid_set)` to `modules/database.py`
  - Accepts a Python `set[int]` of UIDs currently flagged on the server
  - If set is non-empty: `UPDATE emails SET is_flagged=0 WHERE account_id=? AND folder=? AND uidvalidity=? AND is_flagged=1 AND imap_uid NOT IN (?...)`
  - If set is empty: `UPDATE emails SET is_flagged=0 WHERE account_id=? AND folder=? AND uidvalidity=? AND is_flagged=1`
  - Returns count of rows updated

## 2. IMAP Fetcher

- [x] 2.1 Refactor `_sync_flagged_uids()` in `modules/imap_fetcher.py`
  - Remove the early return when `flagged_uids` is empty (must still proceed to clear local flags)
  - Collect all decoded integer UIDs into a `flagged_uid_set: set[int]` as chunks are processed
  - After all chunks: call `database.clear_stale_flags(self.account_id, folder_name, uidvalidity, flagged_uid_set)`
  - Return combined count of updates + clears

## 3. Verification

- [x] 3.1 Flag an email, sync, confirm `is_flagged=1` locally
- [x] 3.2 Unflag the same email remotely, sync again, confirm `is_flagged=0` locally
- [x] 3.3 With zero flagged emails on server, confirm all local `is_flagged` rows are cleared
