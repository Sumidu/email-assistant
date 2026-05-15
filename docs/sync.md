# IMAP Sync

Normal sync is optimized for responsiveness. It fetches only new UIDs after the
stored `last_seen_uid`, then refreshes read/star flags for the recent window.
Full Resync is the repair path for stale deletions, old flag changes, and
missing local mail.

## Normal Sync

- Select the configured folder read-only.
- Reuse stored UIDVALIDITY and `last_seen_uid` when valid.
- Search only `UID <last_seen+1>:*` for delta fetches.
- On first sync, use the configured fetch limit.
- Refresh recent flags for the last seven days.
- Skip full remote UID audit and stale deletion cleanup.

## Full Resync

- Reads the remote UID list for the folder.
- Removes local messages whose tracked remote UID disappeared.
- Refreshes known read/star flags broadly.
- Fetches missing messages according to full-resync behavior.

Related behavior requirements live in the IMAP synchronization section of
`openspec/specs/email-assistant/spec.md`.
