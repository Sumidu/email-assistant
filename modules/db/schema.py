EMAIL_COLUMNS = [
    ("account_id", "account_id TEXT NOT NULL DEFAULT 'default'"),
    ("date_ts", "date_ts REAL"),
    ("kb_processed_at", "kb_processed_at TEXT"),
    ("done_at", "done_at TEXT"),
    ("original_folder", "original_folder TEXT"),
    ("imap_uid", "imap_uid INTEGER"),
    ("uidvalidity", "uidvalidity TEXT"),
    ("references_header", "references_header TEXT"),
    ("thread_id", "thread_id TEXT"),
    ("is_read", "is_read INTEGER DEFAULT 1"),
    ("is_flagged", "is_flagged INTEGER DEFAULT 0"),
    ("flags_synced_at", "flags_synced_at TEXT"),
    ("email_importance", "email_importance INTEGER"),
    ("email_importance_note", "email_importance_note TEXT"),
    ("email_importance_updated_at", "email_importance_updated_at TEXT"),
]

BASE_SCHEMA_SQL = """
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
    CREATE TABLE IF NOT EXISTS entity_extraction_log (
        email_id     TEXT PRIMARY KEY REFERENCES emails(id),
        extracted_at TEXT NOT NULL
    );
"""

INDEX_SQL = """
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
"""


def current_email_columns(conn) -> list[str]:
    return [r[1] for r in conn.execute("PRAGMA table_info(emails)").fetchall()]


def ensure_email_column(conn, existing_columns: list[str], name: str, ddl: str) -> None:
    if name not in existing_columns:
        conn.execute(f"ALTER TABLE emails ADD COLUMN {ddl}")
        existing_columns.append(name)


def ensure_current_schema(conn) -> None:
    conn.executescript(BASE_SCHEMA_SQL)
    columns = current_email_columns(conn)
    for name, ddl in EMAIL_COLUMNS:
        ensure_email_column(conn, columns, name, ddl)
    conn.executescript(INDEX_SQL)

