import sqlite3
import json
import os
import email.utils
from datetime import datetime
from typing import Optional

DB_PATH = os.path.expanduser("~/email_assistant/emails.db")
FINISHED_FOLDER = "Finished"


def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()

    # Base table — without account_id so it's safe on both new and existing DBs
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS emails (
            id          TEXT PRIMARY KEY,
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
            fetched_at  TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_emails_folder ON emails(folder);
        CREATE INDEX IF NOT EXISTS idx_emails_date   ON emails(date);
        CREATE TABLE IF NOT EXISTS sync_state (
            account_id    TEXT NOT NULL,
            folder        TEXT NOT NULL,
            uidvalidity   TEXT,
            last_seen_uid INTEGER DEFAULT 0,
            last_sync_at  TEXT,
            PRIMARY KEY (account_id, folder)
        );
    """)

    # Migrate: add account_id column if missing
    cols = [r[1] for r in conn.execute("PRAGMA table_info(emails)").fetchall()]
    if "imap_uid" not in cols:
        conn.execute("ALTER TABLE emails ADD COLUMN imap_uid INTEGER")
        conn.commit()

    cols = [r[1] for r in conn.execute("PRAGMA table_info(emails)").fetchall()]
    if "uidvalidity" not in cols:
        conn.execute("ALTER TABLE emails ADD COLUMN uidvalidity TEXT")
        conn.commit()

    conn.executescript("""
        CREATE INDEX IF NOT EXISTS idx_emails_imap_uid ON emails(account_id, folder, uidvalidity, imap_uid);
    """)

    cols = [r[1] for r in conn.execute("PRAGMA table_info(emails)").fetchall()]
    if "account_id" not in cols:
        conn.execute("ALTER TABLE emails ADD COLUMN account_id TEXT NOT NULL DEFAULT 'default'")
        conn.commit()

    # Now safe to create account-scoped indexes
    conn.executescript("""
        CREATE INDEX IF NOT EXISTS idx_emails_account  ON emails(account_id);
        CREATE INDEX IF NOT EXISTS idx_emails_acct_fld ON emails(account_id, folder);
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
        CREATE INDEX IF NOT EXISTS idx_calendar_events_account_start ON calendar_events(account_id, start_ts);
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

    # Migrate: add kb_processed_at column if missing
    cols = [r[1] for r in conn.execute("PRAGMA table_info(emails)").fetchall()]
    if "kb_processed_at" not in cols:
        conn.execute("ALTER TABLE emails ADD COLUMN kb_processed_at TEXT")
        conn.commit()

    cols = [r[1] for r in conn.execute("PRAGMA table_info(emails)").fetchall()]
    if "date_ts" not in cols:
        conn.execute("ALTER TABLE emails ADD COLUMN date_ts REAL")
        conn.commit()

    cols = [r[1] for r in conn.execute("PRAGMA table_info(emails)").fetchall()]
    if "done_at" not in cols:
        conn.execute("ALTER TABLE emails ADD COLUMN done_at TEXT")
        conn.commit()

    cols = [r[1] for r in conn.execute("PRAGMA table_info(emails)").fetchall()]
    if "original_folder" not in cols:
        conn.execute("ALTER TABLE emails ADD COLUMN original_folder TEXT")
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


def save_email(data):
    conn = get_connection()
    existing = conn.execute(
        "SELECT done_at, original_folder FROM emails WHERE id = ?",
        (data["id"],),
    ).fetchone()
    done_at = existing["done_at"] if existing else None
    original_folder = existing["original_folder"] if existing else None
    folder = FINISHED_FOLDER if done_at else data.get("folder", "")
    if done_at and not original_folder:
        original_folder = data.get("folder", "")

    conn.execute(
        """INSERT OR REPLACE INTO emails
           (id, folder, subject, sender, recipients, date, date_ts,
            body_text, body_html, message_id, in_reply_to, fetched_at, account_id,
            done_at, original_folder, imap_uid, uidvalidity)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
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
            datetime.now().isoformat(),
            data.get("account_id", "default"),
            done_at,
            original_folder,
            data.get("imap_uid"),
            data.get("uidvalidity", ""),
        ),
    )
    conn.commit()
    conn.close()


def get_emails(folder="INBOX", limit=60, offset=0, account_id=None, search=""):
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
    params.extend([limit, offset])
    sql = f"""SELECT id, folder, subject, sender, recipients, date, message_id, account_id
              FROM emails WHERE {' AND '.join(where)}
              ORDER BY COALESCE(date_ts, strftime('%s', fetched_at), 0) DESC
              LIMIT ? OFFSET ?"""
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_email_by_id(email_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM emails WHERE id = ?", (email_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


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
           WHERE account_id = ? AND folder = ? AND uidvalidity = ? AND imap_uid = ?
           LIMIT 1""",
        (account_id, folder, uidvalidity, imap_uid),
    ).fetchone()
    conn.close()
    return row is not None


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
    conn.execute(
        "UPDATE emails SET folder = ?, done_at = ?, original_folder = ? WHERE id = ?",
        (FINISHED_FOLDER, ts, row["folder"], email_id),
    )
    conn.commit()
    conn.close()
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
    return {"success": True, "folder": target_folder}


def get_all_emails():
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM emails ORDER BY COALESCE(date_ts, strftime('%s', fetched_at), 0) DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


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
