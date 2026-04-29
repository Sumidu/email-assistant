import sqlite3
import json
import os
from datetime import datetime

DB_PATH = os.path.expanduser("~/email_assistant/emails.db")


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
            body_text   TEXT,
            body_html   TEXT,
            message_id  TEXT,
            in_reply_to TEXT,
            fetched_at  TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_emails_folder ON emails(folder);
        CREATE INDEX IF NOT EXISTS idx_emails_date   ON emails(date);
    """)

    # Migrate: add account_id column if missing
    cols = [r[1] for r in conn.execute("PRAGMA table_info(emails)").fetchall()]
    if "account_id" not in cols:
        conn.execute("ALTER TABLE emails ADD COLUMN account_id TEXT NOT NULL DEFAULT 'default'")
        conn.commit()

    # Now safe to create account-scoped indexes
    conn.executescript("""
        CREATE INDEX IF NOT EXISTS idx_emails_account  ON emails(account_id);
        CREATE INDEX IF NOT EXISTS idx_emails_acct_fld ON emails(account_id, folder);
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

    conn.close()


def save_email(data):
    conn = get_connection()
    conn.execute(
        """INSERT OR REPLACE INTO emails
           (id, folder, subject, sender, recipients, date,
            body_text, body_html, message_id, in_reply_to, fetched_at, account_id)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            data["id"],
            data.get("folder", ""),
            data.get("subject", ""),
            data.get("sender", ""),
            json.dumps(data.get("recipients", [])),
            data.get("date", ""),
            data.get("body_text", "")[:12000],
            data.get("body_html", "")[:24000],
            data.get("message_id", ""),
            data.get("in_reply_to", ""),
            datetime.now().isoformat(),
            data.get("account_id", "default"),
        ),
    )
    conn.commit()
    conn.close()


def get_emails(folder="INBOX", limit=60, offset=0, account_id=None):
    conn = get_connection()
    if account_id:
        rows = conn.execute(
            """SELECT id, folder, subject, sender, recipients, date, message_id, account_id
               FROM emails WHERE folder = ? AND account_id = ?
               ORDER BY date DESC LIMIT ? OFFSET ?""",
            (folder, account_id, limit, offset),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT id, folder, subject, sender, recipients, date, message_id, account_id
               FROM emails WHERE folder = ?
               ORDER BY date DESC LIMIT ? OFFSET ?""",
            (folder, limit, offset),
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_email_by_id(email_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM emails WHERE id = ?", (email_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_emails():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM emails ORDER BY date DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_unprocessed_kb_emails():
    """Return emails not yet included in a knowledge build."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM emails WHERE kb_processed_at IS NULL ORDER BY date DESC"
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


def get_email_count(account_id=None):
    conn = get_connection()
    if account_id:
        n = conn.execute("SELECT COUNT(*) FROM emails WHERE account_id = ?", (account_id,)).fetchone()[0]
    else:
        n = conn.execute("SELECT COUNT(*) FROM emails").fetchone()[0]
    conn.close()
    return n


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
