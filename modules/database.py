import sqlite3
import json
import os
import email.utils
import re
from datetime import datetime, timedelta
from typing import Optional

from app import paths
from modules import triage_store

DB_PATH = str(paths.DB_PATH)
FINISHED_FOLDER = "Finished"


def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def init_db():
    conn = get_connection()

    def email_columns():
        return [r[1] for r in conn.execute("PRAGMA table_info(emails)").fetchall()]

    def ensure_email_column(name: str, ddl: str):
        if name not in email_columns():
            conn.execute(f"ALTER TABLE emails ADD COLUMN {ddl}")

    # Create the current schema for fresh installs. Existing databases are
    # migrated below before any indexes rely on newer columns.
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS emails (
            id          TEXT PRIMARY KEY,
            account_id  TEXT NOT NULL DEFAULT 'default',
            folder      TEXT,
            subject     TEXT,
            sender      TEXT,
            recipients  TEXT,
            date        TEXT,
            date_ts     REAL,
            body_text   TEXT,
            body_html   TEXT,
            message_id  TEXT,
            in_reply_to TEXT,
            references_header TEXT,
            thread_id   TEXT,
            fetched_at  TEXT,
            kb_processed_at TEXT,
            done_at     TEXT,
            original_folder TEXT,
            imap_uid    INTEGER,
            uidvalidity TEXT,
            is_read     INTEGER DEFAULT 1,
            is_flagged  INTEGER DEFAULT 0,
            flags_synced_at TEXT,
            email_importance INTEGER,
            email_importance_note TEXT,
            email_importance_updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS sync_state (
            account_id    TEXT NOT NULL,
            folder        TEXT NOT NULL,
            uidvalidity   TEXT,
            last_seen_uid INTEGER DEFAULT 0,
            last_sync_at  TEXT,
            PRIMARY KEY (account_id, folder)
        );
        CREATE TABLE IF NOT EXISTS calendar_events (
            account_id  TEXT NOT NULL,
            uid         TEXT NOT NULL,
            occurrence  TEXT NOT NULL,
            title       TEXT,
            start_ts    REAL NOT NULL,
            end_ts      REAL NOT NULL,
            start_iso   TEXT NOT NULL,
            end_iso     TEXT NOT NULL,
            all_day     INTEGER DEFAULT 0,
            location    TEXT,
            description TEXT,
            source      TEXT,
            updated_at  TEXT,
            PRIMARY KEY (account_id, uid, occurrence)
        );
        CREATE TABLE IF NOT EXISTS processed_actions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            email_id    TEXT,
            account_id  TEXT,
            action      TEXT NOT NULL,
            created_at  TEXT NOT NULL
        );
    """)

    ensure_email_column("account_id", "account_id TEXT NOT NULL DEFAULT 'default'")
    ensure_email_column("date_ts", "date_ts REAL")
    ensure_email_column("kb_processed_at", "kb_processed_at TEXT")
    ensure_email_column("done_at", "done_at TEXT")
    ensure_email_column("original_folder", "original_folder TEXT")
    ensure_email_column("imap_uid", "imap_uid INTEGER")
    ensure_email_column("uidvalidity", "uidvalidity TEXT")
    ensure_email_column("references_header", "references_header TEXT")
    ensure_email_column("thread_id", "thread_id TEXT")
    ensure_email_column("is_read", "is_read INTEGER DEFAULT 1")
    ensure_email_column("is_flagged", "is_flagged INTEGER DEFAULT 0")
    ensure_email_column("flags_synced_at", "flags_synced_at TEXT")
    ensure_email_column("email_importance", "email_importance INTEGER")
    ensure_email_column("email_importance_note", "email_importance_note TEXT")
    ensure_email_column("email_importance_updated_at", "email_importance_updated_at TEXT")

    conn.executescript("""
        CREATE INDEX IF NOT EXISTS idx_emails_folder ON emails(folder);
        CREATE INDEX IF NOT EXISTS idx_emails_date   ON emails(date);
        CREATE INDEX IF NOT EXISTS idx_emails_account  ON emails(account_id);
        CREATE INDEX IF NOT EXISTS idx_emails_acct_fld ON emails(account_id, folder);
        CREATE INDEX IF NOT EXISTS idx_emails_imap_uid ON emails(account_id, folder, uidvalidity, imap_uid);
        CREATE INDEX IF NOT EXISTS idx_emails_thread ON emails(account_id, thread_id);
        CREATE INDEX IF NOT EXISTS idx_emails_acct_fld_thread ON emails(account_id, folder, thread_id);
        CREATE INDEX IF NOT EXISTS idx_emails_importance ON emails(email_importance);
        CREATE INDEX IF NOT EXISTS idx_calendar_events_account_start ON calendar_events(account_id, start_ts);
        CREATE INDEX IF NOT EXISTS idx_processed_actions_created ON processed_actions(created_at);
        CREATE INDEX IF NOT EXISTS idx_processed_actions_action ON processed_actions(action, created_at);
    """)

    # Migrate: prefix existing IDs with 'default::' to match the composite-ID scheme
    needs_prefix = conn.execute(
        "SELECT COUNT(*) FROM emails WHERE account_id = 'default' AND id NOT LIKE 'default::%'"
    ).fetchone()[0]
    if needs_prefix:
        conn.execute(
            "UPDATE emails SET id = 'default::' || id "
            "WHERE account_id = 'default' AND id NOT LIKE 'default::%'"
        )
        conn.commit()

    rows = conn.execute(
        "SELECT id, date FROM emails WHERE date_ts IS NULL AND date IS NOT NULL AND date != ''"
    ).fetchall()
    if rows:
        conn.executemany(
            "UPDATE emails SET date_ts = ? WHERE id = ?",
            [(_parse_email_date_ts(row["date"]), row["id"]) for row in rows],
        )
        conn.commit()

    _backfill_thread_ids(conn)

    conn.commit()
    conn.close()


def _parse_email_date_ts(value: str) -> Optional[float]:
    try:
        parsed = email.utils.parsedate_to_datetime(value)
        if parsed is None:
            return None
        if parsed.tzinfo is None:
            return parsed.timestamp()
        return parsed.timestamp()
    except Exception:
        return None


def _local_date_start_ts(value: str) -> Optional[float]:
    try:
        return datetime.strptime(value, "%Y-%m-%d").timestamp()
    except (TypeError, ValueError):
        return None


def _message_id_tokens(value: str) -> list[str]:
    if not value:
        return []
    tokens = re.findall(r"<[^>]+>", value)
    if not tokens and value.strip():
        tokens = [value.strip()]
    cleaned = []
    for token in tokens:
        token = token.strip().strip("<>").strip().lower()
        if token and token not in cleaned:
            cleaned.append(token)
    return cleaned


def _thread_seed(message_id: str = "", in_reply_to: str = "", references_header: str = "") -> str:
    refs = _message_id_tokens(references_header)
    if refs:
        return refs[0]
    replies = _message_id_tokens(in_reply_to)
    if replies:
        return replies[0]
    own = _message_id_tokens(message_id)
    return own[0] if own else (message_id or "").strip().lower()


def _thread_id_for(account_id: str, seed: str) -> str:
    return f"{account_id}::{seed}" if seed else f"{account_id}::unknown"


def _backfill_thread_ids(conn) -> None:
    rows = conn.execute(
        """SELECT id, account_id, message_id, in_reply_to, references_header
           FROM emails
           WHERE thread_id IS NULL OR thread_id = ''"""
    ).fetchall()
    if not rows:
        return
    by_account = {}
    for row in rows:
        by_account.setdefault(row["account_id"] or "default", []).append(row)
    updates = []
    for account_id, acct_rows in by_account.items():
        own_keys = {}
        for row in acct_rows:
            for key in _message_id_tokens(row["message_id"]):
                own_keys[key] = row

        resolving = set()
        resolved = {}

        def root_for(row):
            if row["id"] in resolved:
                return resolved[row["id"]]
            if row["id"] in resolving:
                return _thread_seed(row["message_id"], row["in_reply_to"], row["references_header"])
            resolving.add(row["id"])
            refs = _message_id_tokens(row["references_header"])
            if refs:
                root = refs[0]
            else:
                replies = _message_id_tokens(row["in_reply_to"])
                parent = own_keys.get(replies[0]) if replies else None
                root = root_for(parent) if parent else _thread_seed(row["message_id"], row["in_reply_to"], row["references_header"])
            resolving.discard(row["id"])
            resolved[row["id"]] = root
            return root

        for row in acct_rows:
            updates.append((_thread_id_for(account_id, root_for(row)), row["id"]))
    if updates:
        conn.executemany("UPDATE emails SET thread_id = ? WHERE id = ?", updates)


def _parent_thread_id(conn, account_id: str, in_reply_to: str) -> str:
    for token in _message_id_tokens(in_reply_to):
        row = conn.execute(
            """SELECT thread_id FROM emails
               WHERE account_id = ?
                 AND lower(trim(replace(replace(message_id, '<', ''), '>', ''))) = ?
                 AND thread_id IS NOT NULL
                 AND thread_id != ''
               LIMIT 1""",
            (account_id, token),
        ).fetchone()
        if row and row["thread_id"]:
            return row["thread_id"]
    return ""


def save_email(data):
    conn = get_connection()
    existing = conn.execute(
        "SELECT done_at, original_folder, email_importance, email_importance_note, email_importance_updated_at FROM emails WHERE id = ?",
        (data["id"],),
    ).fetchone()
    done_at = existing["done_at"] if existing else None
    original_folder = existing["original_folder"] if existing else None
    email_importance = existing["email_importance"] if existing else None
    email_importance_note = existing["email_importance_note"] if existing else None
    email_importance_updated_at = existing["email_importance_updated_at"] if existing else None
    folder = FINISHED_FOLDER if done_at else data.get("folder", "")
    if done_at and not original_folder:
        original_folder = data.get("folder", "")
    account_id = data.get("account_id", "default")
    references_header = data.get("references_header", "")
    thread_id = data.get("thread_id") or ""
    if not thread_id and not references_header:
        thread_id = _parent_thread_id(conn, account_id, data.get("in_reply_to", ""))
    if not thread_id:
        thread_id = _thread_id_for(
            account_id,
            _thread_seed(
                data.get("message_id", ""),
                data.get("in_reply_to", ""),
                references_header,
            ),
        )

    conn.execute(
        """INSERT OR REPLACE INTO emails
           (id, folder, subject, sender, recipients, date, date_ts,
            body_text, body_html, message_id, in_reply_to, references_header, thread_id, fetched_at, account_id,
            done_at, original_folder, imap_uid, uidvalidity, is_read, is_flagged, flags_synced_at,
            email_importance, email_importance_note, email_importance_updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            data["id"],
            folder,
            data.get("subject", ""),
            data.get("sender", ""),
            json.dumps(data.get("recipients", [])),
            data.get("date", ""),
            _parse_email_date_ts(data.get("date", "")),
            data.get("body_text", "")[:12000],
            data.get("body_html", "")[:24000],
            data.get("message_id", ""),
            data.get("in_reply_to", ""),
            references_header,
            thread_id,
            datetime.now().isoformat(),
            account_id,
            done_at,
            original_folder,
            data.get("imap_uid"),
            data.get("uidvalidity", ""),
            1 if data.get("is_read", True) else 0,
            1 if data.get("is_flagged", False) else 0,
            datetime.now().isoformat(),
            email_importance,
            email_importance_note,
            email_importance_updated_at,
        ),
    )
    conn.commit()
    conn.close()


def _apply_importance_filter(where: list[str], params: list, importance=None) -> None:
    importance = str(importance or "").strip().lower()
    if not importance:
        return
    if importance == "unrated":
        where.append("email_importance IS NULL")
        return
    try:
        rating = int(importance)
    except (TypeError, ValueError):
        return
    if 1 <= rating <= 5:
        where.append("email_importance = ?")
        params.append(rating)


def _apply_status_filter(where: list[str], status=None) -> None:
    status = str(status or "").strip().lower()
    if status == "unread":
        where.append("is_read = 0")
    elif status == "flagged":
        where.append("is_flagged = 1")
    elif status in ("unread_flagged", "flagged_unread"):
        where.append("is_read = 0")
        where.append("is_flagged = 1")


def get_emails(folder="INBOX", limit=60, offset=0, account_id=None, search="", importance=None, status=None):
    conn = get_connection()
    search = (search or "").strip()
    where = ["folder = ?"]
    params = [folder]
    if account_id:
        where.append("account_id = ?")
        params.append(account_id)
    if search:
        like = f"%{search}%"
        where.append(
            """(
                subject LIKE ? COLLATE NOCASE OR
                sender LIKE ? COLLATE NOCASE OR
                recipients LIKE ? COLLATE NOCASE OR
                body_text LIKE ? COLLATE NOCASE
            )"""
        )
        params.extend([like, like, like, like])
    _apply_importance_filter(where, params, importance)
    _apply_status_filter(where, status)
    params.extend([limit, offset])
    sql = f"""SELECT id, folder, subject, sender, recipients, date, message_id, account_id, is_read, is_flagged, email_importance
              FROM emails WHERE {' AND '.join(where)}
              ORDER BY COALESCE(date_ts, strftime('%s', fetched_at), 0) DESC
              LIMIT ? OFFSET ?"""
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_email_threads(folder="INBOX", limit=60, offset=0, account_id=None, search="", importance=None, status=None, sent_folders=None):
    conn = get_connection()
    search = (search or "").strip()
    where = ["folder = ?"]
    params = [folder]
    if account_id:
        where.append("account_id = ?")
        params.append(account_id)
    if search:
        like = f"%{search}%"
        where.append(
            """(
                subject LIKE ? COLLATE NOCASE OR
                sender LIKE ? COLLATE NOCASE OR
                recipients LIKE ? COLLATE NOCASE OR
                body_text LIKE ? COLLATE NOCASE
            )"""
        )
        params.extend([like, like, like, like])
    _apply_importance_filter(where, params, importance)
    _apply_status_filter(where, status)
    sent_folders = set(sent_folders or [])
    sent_case = " OR ".join(["allm.folder = ?" for _ in sent_folders])
    sent_expr = f"SUM(CASE WHEN {sent_case} THEN 1 ELSE 0 END)" if sent_case else "0"
    sql = f"""
        WITH matched AS (
            SELECT *, ROW_NUMBER() OVER (
                PARTITION BY COALESCE(thread_id, id)
                ORDER BY COALESCE(date_ts, strftime('%s', fetched_at), 0) DESC
            ) AS rn
            FROM emails
            WHERE {' AND '.join(where)}
        ),
        agg AS (
            SELECT COALESCE(allm.thread_id, allm.id) AS thread_key,
                   COUNT(*) AS thread_count,
                   {sent_expr} AS sent_count,
                   SUM(CASE WHEN NOT ({sent_case or '0'}) THEN 1 ELSE 0 END) AS received_count,
                   MAX(CASE WHEN allm.is_read = 0 THEN 1 ELSE 0 END) AS thread_unread,
                   MAX(CASE WHEN allm.is_flagged = 1 THEN 1 ELSE 0 END) AS thread_flagged,
                   MAX(COALESCE(allm.date_ts, strftime('%s', allm.fetched_at), 0)) AS thread_latest_ts
            FROM emails allm
            WHERE allm.account_id = COALESCE(?, allm.account_id)
              AND COALESCE(allm.thread_id, allm.id) IN (SELECT COALESCE(thread_id, id) FROM matched)
            GROUP BY COALESCE(allm.thread_id, allm.id)
        )
        SELECT matched.id, matched.folder, matched.subject, matched.sender, matched.recipients,
               matched.date, matched.message_id, matched.account_id, matched.is_read,
               matched.is_flagged, matched.email_importance, COALESCE(matched.thread_id, matched.id) AS thread_id,
               agg.thread_count, agg.sent_count, agg.received_count,
               agg.thread_unread, agg.thread_flagged
        FROM matched
        JOIN agg ON agg.thread_key = COALESCE(matched.thread_id, matched.id)
        WHERE matched.rn = 1
        ORDER BY agg.thread_latest_ts DESC
        LIMIT ? OFFSET ?
    """
    sql_params = [*params, *sent_folders, *sent_folders, account_id, int(limit), int(offset)]
    rows = conn.execute(sql, sql_params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_email_flags_by_uid(account_id: str, folder: str, uidvalidity: str, imap_uid: int, is_read: bool, is_flagged: bool) -> None:
    conn = get_connection()
    conn.execute(
        """UPDATE emails
              SET is_read = ?,
                  is_flagged = ?,
                  flags_synced_at = ?
           WHERE account_id = ?
             AND uidvalidity = ?
             AND imap_uid = ?
             AND (folder = ? OR original_folder = ?)""",
        (1 if is_read else 0, 1 if is_flagged else 0, datetime.now().isoformat(), account_id, uidvalidity, imap_uid, folder, folder),
    )
    conn.commit()
    conn.close()


def update_email_flags_batch(account_id: str, folder: str, uidvalidity: str, uid_flags: dict[int, dict]) -> int:
    if not uidvalidity or not uid_flags:
        return 0
    conn = get_connection()
    now = datetime.now().isoformat()
    rows = [
        (
            1 if flags.get("is_read") else 0,
            1 if flags.get("is_flagged") else 0,
            now,
            account_id,
            uidvalidity,
            int(uid),
            folder,
            folder,
        )
        for uid, flags in uid_flags.items()
    ]
    cur = conn.executemany(
        """UPDATE emails
              SET is_read = ?,
                  is_flagged = ?,
                  flags_synced_at = ?
           WHERE account_id = ?
             AND uidvalidity = ?
             AND imap_uid = ?
             AND (folder = ? OR original_folder = ?)""",
        rows,
    )
    conn.commit()
    conn.close()
    return int(cur.rowcount or 0)


def update_email_importance(email_id: str, rating: int, note: str = "") -> bool:
    rating = max(1, min(5, int(rating or 3)))
    conn = get_connection()
    cur = conn.execute(
        """UPDATE emails
           SET email_importance = ?,
               email_importance_note = ?,
               email_importance_updated_at = ?
           WHERE id = ?""",
        (rating, (note or "")[:1000], datetime.now().isoformat(), email_id),
    )
    conn.commit()
    conn.close()
    return cur.rowcount > 0


def _email_filter_where(folder: str, account_id=None, search="", importance=None, status=None) -> tuple[list[str], list]:
    where = ["folder = ?"]
    params = [folder]
    if account_id:
        where.append("account_id = ?")
        params.append(account_id)
    search = (search or "").strip()
    if search:
        like = f"%{search}%"
        where.append(
            """(
                subject LIKE ? COLLATE NOCASE OR
                sender LIKE ? COLLATE NOCASE OR
                recipients LIKE ? COLLATE NOCASE OR
                body_text LIKE ? COLLATE NOCASE
            )"""
        )
        params.extend([like, like, like, like])
    _apply_importance_filter(where, params, importance)
    _apply_status_filter(where, status)
    return where, params


def count_emails_for_finish(folder: str, account_id=None, search="", importance=None, status=None) -> int:
    conn = get_connection()
    where, params = _email_filter_where(folder, account_id=account_id, search=search, importance=importance, status=status)
    where.append("done_at IS NULL")
    count = conn.execute(
        f"SELECT COUNT(*) FROM emails WHERE {' AND '.join(where)}",
        params,
    ).fetchone()[0]
    conn.close()
    return int(count or 0)


def mark_filtered_emails_done(folder: str, account_id=None, search="", importance=None, status=None) -> dict:
    conn = get_connection()
    where, params = _email_filter_where(folder, account_id=account_id, search=search, importance=importance, status=status)
    where.append("done_at IS NULL")
    ts = datetime.now().isoformat()
    affected = conn.execute(
        f"SELECT id, folder FROM emails WHERE {' AND '.join(where)}",
        params,
    ).fetchall()
    cur = conn.execute(
        f"""UPDATE emails
            SET folder = ?, done_at = ?, original_folder = COALESCE(original_folder, ?)
            WHERE {' AND '.join(where)}""",
        [FINISHED_FOLDER, ts, folder, *params],
    )
    conn.commit()
    conn.close()
    triage_store.record_done_batch([
        {"email_id": r["id"], "done_at": ts, "original_folder": r["folder"]}
        for r in affected
    ])
    return {"success": True, "count": int(cur.rowcount or 0), "folder": FINISHED_FOLDER}

def get_email_by_id(email_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM emails WHERE id = ?", (email_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_thread_emails(account_id: str, thread_id: str) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        """SELECT *
           FROM emails
           WHERE account_id = ?
             AND COALESCE(thread_id, id) = ?
           ORDER BY COALESCE(date_ts, strftime('%s', fetched_at), 0) ASC""",
        (account_id, thread_id),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def search_emails_for_todos(
    folder="INBOX",
    account_id=None,
    search="",
    start_date="",
    end_date="",
    email_id="",
    limit=250,
):
    conn = get_connection()
    where = []
    params = []
    if email_id:
        where.append("id = ?")
        params.append(email_id)
    else:
        where.append("folder = ?")
        params.append(folder)
    if account_id:
        where.append("account_id = ?")
        params.append(account_id)
    search = (search or "").strip()
    if search:
        like = f"%{search}%"
        where.append(
            """(
                subject LIKE ? COLLATE NOCASE OR
                sender LIKE ? COLLATE NOCASE OR
                recipients LIKE ? COLLATE NOCASE OR
                body_text LIKE ? COLLATE NOCASE
            )"""
        )
        params.extend([like, like, like, like])
    if start_date:
        where.append("date_ts >= strftime('%s', ?)")
        params.append(start_date)
    if end_date:
        where.append("date_ts < strftime('%s', date(?, '+1 day'))")
        params.append(end_date)
    params.append(limit)
    rows = conn.execute(
        f"""SELECT id, folder, subject, sender, recipients, date, body_text, account_id
            FROM emails
            WHERE {' AND '.join(where)}
            ORDER BY COALESCE(date_ts, strftime('%s', fetched_at), 0) DESC
            LIMIT ?""",
        params,
    ).fetchall()
    count_params = params[:-1]
    total = conn.execute(
        f"SELECT COUNT(*) FROM emails WHERE {' AND '.join(where)}",
        count_params,
    ).fetchone()[0]
    conn.close()
    return {"rows": [dict(r) for r in rows], "total": total}


def email_uid_exists(account_id: str, folder: str, uidvalidity: str, imap_uid: int) -> bool:
    conn = get_connection()
    row = conn.execute(
        """SELECT 1 FROM emails
           WHERE account_id = ?
             AND uidvalidity = ?
             AND imap_uid = ?
             AND (folder = ? OR original_folder = ?)
           LIMIT 1""",
        (account_id, uidvalidity, imap_uid, folder, folder),
    ).fetchone()
    conn.close()
    return row is not None


def get_tracked_imap_uids(account_id: str, folder: str, uidvalidity: str, limit: int = 20000) -> list[int]:
    if not uidvalidity:
        return []
    conn = get_connection()
    rows = conn.execute(
        """SELECT imap_uid FROM emails
           WHERE account_id = ?
             AND uidvalidity = ?
             AND imap_uid IS NOT NULL
             AND (folder = ? OR original_folder = ?)
           ORDER BY imap_uid
           LIMIT ?""",
        (account_id, uidvalidity, folder, folder, int(limit or 20000)),
    ).fetchall()
    conn.close()
    return [int(row["imap_uid"]) for row in rows if row["imap_uid"] is not None]


def remove_missing_remote_emails(account_id: str, folder: str, uidvalidity: str, remote_uids: set[int]) -> int:
    """Delete local rows whose tracked IMAP UID no longer exists remotely.

    Rows in the local Finished folder are still tied to their original IMAP
    folder via original_folder. If the remote UID disappears there, the local
    Finished copy should disappear too; if it still exists remotely, it stays
    local-only and is not moved back to the inbox.
    """
    if not uidvalidity:
        return 0
    conn = get_connection()
    rows = conn.execute(
        """SELECT id, imap_uid FROM emails
           WHERE account_id = ?
             AND uidvalidity = ?
             AND imap_uid IS NOT NULL
             AND (folder = ? OR original_folder = ?)""",
        (account_id, uidvalidity, folder, folder),
    ).fetchall()
    stale_ids = [
        row["id"]
        for row in rows
        if row["imap_uid"] is not None and int(row["imap_uid"]) not in remote_uids
    ]
    if stale_ids:
        conn.executemany("DELETE FROM emails WHERE id = ?", [(eid,) for eid in stale_ids])
        conn.commit()
    conn.close()
    return len(stale_ids)


def get_sync_state(account_id: str, folder: str) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM sync_state WHERE account_id = ? AND folder = ?",
        (account_id, folder),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def save_sync_state(account_id: str, folder: str, uidvalidity: str, last_seen_uid: int) -> None:
    conn = get_connection()
    conn.execute(
        """INSERT OR REPLACE INTO sync_state
           (account_id, folder, uidvalidity, last_seen_uid, last_sync_at)
           VALUES (?, ?, ?, ?, ?)""",
        (account_id, folder, uidvalidity, int(last_seen_uid or 0), datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def mark_email_done(email_id: str) -> dict:
    conn = get_connection()
    row = conn.execute(
        "SELECT id, folder, done_at FROM emails WHERE id = ?",
        (email_id,),
    ).fetchone()
    if not row:
        conn.close()
        return {"success": False, "error": "Email not found"}
    if row["done_at"]:
        conn.close()
        return {"success": True, "already_done": True}

    ts = datetime.now().isoformat()
    original_folder = row["folder"]
    conn.execute(
        "UPDATE emails SET folder = ?, done_at = ?, original_folder = ? WHERE id = ?",
        (FINISHED_FOLDER, ts, original_folder, email_id),
    )
    conn.commit()
    conn.close()
    triage_store.record_done(email_id, ts, original_folder)
    return {"success": True, "folder": FINISHED_FOLDER, "done_at": ts}


def unmark_email_done(email_id: str) -> dict:
    conn = get_connection()
    row = conn.execute(
        "SELECT id, folder, done_at, original_folder FROM emails WHERE id = ?",
        (email_id,),
    ).fetchone()
    if not row:
        conn.close()
        return {"success": False, "error": "Email not found"}
    target_folder = row["original_folder"] or "INBOX"
    conn.execute(
        "UPDATE emails SET folder = ?, done_at = NULL, original_folder = NULL WHERE id = ?",
        (target_folder, email_id),
    )
    conn.commit()
    conn.close()
    triage_store.record_undone(email_id)
    return {"success": True, "folder": target_folder}


def move_email_local_folder(email_id: str, folder: str) -> dict:
    conn = get_connection()
    row = conn.execute("SELECT id FROM emails WHERE id = ?", (email_id,)).fetchone()
    if not row:
        conn.close()
        return {"success": False, "error": "Email not found"}
    conn.execute(
        "UPDATE emails SET folder = ?, done_at = NULL, original_folder = NULL WHERE id = ?",
        (folder, email_id),
    )
    conn.commit()
    conn.close()
    return {"success": True, "folder": folder}


def delete_email_local(email_id: str) -> dict:
    conn = get_connection()
    cur = conn.execute("DELETE FROM emails WHERE id = ?", (email_id,))
    conn.commit()
    conn.close()
    return {"success": cur.rowcount > 0}


def record_processed_action(action: str, email_id: str = "", account_id: str = "") -> None:
    ts = datetime.now().isoformat()
    conn = get_connection()
    conn.execute(
        """INSERT INTO processed_actions (email_id, account_id, action, created_at)
           VALUES (?, ?, ?, ?)""",
        (email_id, account_id, action, ts),
    )
    conn.commit()
    conn.close()
    if action == "spam":
        triage_store.record_spam(email_id, account_id, ts)


def get_all_emails():
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM emails ORDER BY COALESCE(date_ts, strftime('%s', fetched_at), 0) DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_unfinished_emails_for_summary(start_date: str, end_date: str, account_id=None, excluded_folders=None, limit=120) -> dict:
    conn = get_connection()
    where = ["done_at IS NULL", "folder != ?"]
    params = [FINISHED_FOLDER]
    for folder in excluded_folders or []:
        if folder:
            where.append("folder != ?")
            params.append(folder)
    if account_id:
        where.append("account_id = ?")
        params.append(account_id)
    start_ts = _local_date_start_ts(start_date)
    end_ts = _local_date_start_ts(end_date)
    if start_ts is not None:
        where.append("date_ts >= ?")
        params.append(start_ts)
    if end_ts is not None:
        where.append("date_ts < ?")
        params.append(end_ts + timedelta(days=1).total_seconds())
    total = conn.execute(
        f"SELECT COUNT(*) FROM emails WHERE {' AND '.join(where)}",
        params,
    ).fetchone()[0]
    rows = conn.execute(
        f"""SELECT id, account_id, folder, subject, sender, recipients, date, body_text, is_read, email_importance
            FROM emails
            WHERE {' AND '.join(where)}
            ORDER BY COALESCE(date_ts, strftime('%s', fetched_at), 0) DESC
            LIMIT ?""",
        [*params, int(limit or 120)],
    ).fetchall()
    conn.close()
    return {"rows": [dict(r) for r in rows], "total": int(total or 0)}


def get_unprocessed_kb_emails():
    """Return emails not yet included in a knowledge build."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM emails WHERE kb_processed_at IS NULL "
        "ORDER BY COALESCE(date_ts, strftime('%s', fetched_at), 0) DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_emails_kb_processed(ids: list):
    if not ids:
        return
    conn = get_connection()
    ts = datetime.now().isoformat()
    conn.executemany(
        "UPDATE emails SET kb_processed_at = ? WHERE id = ?",
        [(ts, eid) for eid in ids],
    )
    conn.commit()
    conn.close()


def get_finished_today_count() -> int:
    conn = get_connection()
    count = conn.execute(
        "SELECT COUNT(*) FROM emails WHERE done_at >= datetime('now', 'localtime', 'start of day')"
    ).fetchone()[0]
    conn.close()
    return int(count or 0)


def get_processed_today_count() -> dict:
    conn = get_connection()
    finished = conn.execute(
        "SELECT COUNT(*) FROM emails WHERE done_at >= datetime('now', 'localtime', 'start of day')"
    ).fetchone()[0]
    spam = conn.execute(
        """SELECT COUNT(*) FROM processed_actions
           WHERE action = 'spam'
             AND created_at >= datetime('now', 'localtime', 'start of day')"""
    ).fetchone()[0]
    conn.close()
    finished = int(finished or 0)
    spam = int(spam or 0)
    return {"processed_today": finished + spam, "finished_today": finished, "spam_today": spam}


def get_completion_history(days: int = 30) -> list:
    """Return daily finished+spam counts for the last `days` days (including today)."""
    conn = get_connection()
    finished_rows = conn.execute(
        """SELECT date(done_at, 'localtime') as day, COUNT(*) as cnt
           FROM emails
           WHERE done_at >= datetime('now', 'localtime', ? || ' days')
           GROUP BY day""",
        (f"-{days}",),
    ).fetchall()
    spam_rows = conn.execute(
        """SELECT date(created_at, 'localtime') as day, COUNT(*) as cnt
           FROM processed_actions
           WHERE action = 'spam'
             AND created_at >= datetime('now', ? || ' days')
           GROUP BY day""",
        (f"-{days}",),
    ).fetchall()
    conn.close()

    finished_by_day = {r[0]: r[1] for r in finished_rows}
    spam_by_day = {r[0]: r[1] for r in spam_rows}

    from datetime import date, timedelta
    today = date.today()
    result = []
    for i in range(days - 1, -1, -1):
        d = (today - timedelta(days=i)).isoformat()
        result.append({
            "date": d,
            "finished": finished_by_day.get(d, 0),
            "spam": spam_by_day.get(d, 0),
            "total": finished_by_day.get(d, 0) + spam_by_day.get(d, 0),
        })
    return result


def get_email_count(account_id=None):
    conn = get_connection()
    if account_id:
        n = conn.execute("SELECT COUNT(*) FROM emails WHERE account_id = ?", (account_id,)).fetchone()[0]
    else:
        n = conn.execute("SELECT COUNT(*) FROM emails").fetchone()[0]
    conn.close()
    return n


def get_account_stats(account_id: str) -> dict:
    conn = get_connection()
    row = conn.execute(
        """SELECT COUNT(*) AS count,
                  COALESCE(SUM(LENGTH(body_text)), 0) AS body_text_bytes,
                  COALESCE(SUM(LENGTH(body_html)), 0) AS body_html_bytes
           FROM emails WHERE account_id = ?""",
        (account_id,),
    ).fetchone()
    folder_rows = conn.execute(
        "SELECT folder, COUNT(*) AS count FROM emails WHERE account_id = ? GROUP BY folder ORDER BY count DESC",
        (account_id,),
    ).fetchall()
    state_rows = conn.execute(
        "SELECT folder, uidvalidity, last_seen_uid, last_sync_at FROM sync_state WHERE account_id = ?",
        (account_id,),
    ).fetchall()
    conn.close()
    db_size = os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0
    account_bytes = int(row["body_text_bytes"] or 0) + int(row["body_html_bytes"] or 0)
    return {
        "email_count": int(row["count"] or 0),
        "body_text_bytes": int(row["body_text_bytes"] or 0),
        "body_html_bytes": int(row["body_html_bytes"] or 0),
        "approx_account_bytes": account_bytes,
        "database_file_bytes": db_size,
        "folders": [dict(r) for r in folder_rows],
        "sync_state": [dict(r) for r in state_rows],
    }


def get_folders(account_id=None):
    """Return list of {folder, count, account_id} sorted by account_id, count desc."""
    conn = get_connection()
    if account_id:
        rows = conn.execute(
            "SELECT folder, COUNT(*) as count, account_id FROM emails "
            "WHERE account_id = ? GROUP BY folder ORDER BY count DESC",
            (account_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT folder, COUNT(*) as count, account_id FROM emails "
            "GROUP BY account_id, folder ORDER BY account_id, count DESC"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def replace_calendar_events(account_id: str, events: list[dict], start_ts: float, end_ts: float) -> None:
    conn = get_connection()
    conn.execute(
        "DELETE FROM calendar_events WHERE account_id = ? AND start_ts >= ? AND start_ts <= ?",
        (account_id, start_ts, end_ts),
    )
    rows = []
    now = datetime.now().isoformat()
    for event in events:
        rows.append((
            account_id,
            event.get("uid", ""),
            event.get("occurrence", event.get("start_iso", "")),
            event.get("title", ""),
            float(event.get("start_ts", 0)),
            float(event.get("end_ts", 0)),
            event.get("start_iso", ""),
            event.get("end_iso", ""),
            1 if event.get("all_day") else 0,
            event.get("location", ""),
            event.get("description", ""),
            event.get("source", ""),
            now,
        ))
    conn.executemany(
        """INSERT OR REPLACE INTO calendar_events
           (account_id, uid, occurrence, title, start_ts, end_ts, start_iso, end_iso,
            all_day, location, description, source, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )
    conn.commit()
    conn.close()


def get_calendar_events(account_id=None, start_ts=None, end_ts=None, limit=500):
    conn = get_connection()
    query = "SELECT * FROM calendar_events WHERE 1=1"
    params = []
    if account_id:
        query += " AND account_id = ?"
        params.append(account_id)
    if start_ts is not None:
        query += " AND end_ts >= ?"
        params.append(float(start_ts))
    if end_ts is not None:
        query += " AND start_ts <= ?"
        params.append(float(end_ts))
    query += " ORDER BY start_ts ASC LIMIT ?"
    params.append(int(limit))
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def init_triage_sync() -> None:
    """Sync triage state between local DB and the iCloud triage.json file.

    First run (file absent): export all local done/spam state to create the
    cloud file.  Subsequent runs: apply cloud state to the local DB so that
    triage decisions made on another device take effect here.
    """
    if not triage_store.exists():
        # First time — seed the cloud file from the local DB.
        conn = get_connection()
        done_rows = conn.execute(
            "SELECT id, done_at, original_folder FROM emails WHERE done_at IS NOT NULL"
        ).fetchall()
        spam_rows = conn.execute(
            "SELECT email_id, account_id, created_at FROM processed_actions WHERE action = 'spam'"
        ).fetchall()
        conn.close()
        triage_store.save_raw({
            "done": {
                r["id"]: {"done_at": r["done_at"], "original_folder": r["original_folder"] or "INBOX"}
                for r in done_rows
            },
            "spam": [
                {"email_id": r["email_id"], "account_id": r["account_id"], "created_at": r["created_at"]}
                for r in spam_rows
            ],
        })
        return

    data = triage_store.load()
    cloud_done: dict = data.get("done", {})
    cloud_spam: list = data.get("spam", [])

    conn = get_connection()

    # Emails done in cloud but not locally → mark done
    for email_id, state in cloud_done.items():
        row = conn.execute("SELECT done_at FROM emails WHERE id = ?", (email_id,)).fetchone()
        if row and not row["done_at"]:
            conn.execute(
                "UPDATE emails SET folder = ?, done_at = ?, original_folder = COALESCE(original_folder, ?) WHERE id = ?",
                (FINISHED_FOLDER, state["done_at"], state.get("original_folder", "INBOX"), email_id),
            )

    # Emails done locally but not in cloud → unmark (propagate unmark from another device)
    local_done = conn.execute(
        "SELECT id, original_folder FROM emails WHERE done_at IS NOT NULL"
    ).fetchall()
    for row in local_done:
        if row["id"] not in cloud_done:
            conn.execute(
                "UPDATE emails SET folder = ?, done_at = NULL, original_folder = NULL WHERE id = ?",
                (row["original_folder"] or "INBOX", row["id"]),
            )

    # Spam records in cloud but not locally → insert for daily counts
    for sp in cloud_spam:
        exists = conn.execute(
            "SELECT id FROM processed_actions WHERE email_id = ? AND action = 'spam' AND created_at = ?",
            (sp.get("email_id", ""), sp.get("created_at", "")),
        ).fetchone()
        if not exists:
            conn.execute(
                "INSERT INTO processed_actions (email_id, account_id, action, created_at) VALUES (?, ?, 'spam', ?)",
                (sp.get("email_id", ""), sp.get("account_id", ""), sp.get("created_at", "")),
            )

    conn.commit()
    conn.close()
