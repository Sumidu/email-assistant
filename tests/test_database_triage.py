import copy

from modules import database, triage_store


def test_init_triage_sync_keeps_local_finished_when_cloud_is_missing_entry(monkeypatch, tmp_path):
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "emails.db"))
    monkeypatch.setattr(triage_store, "exists", lambda: True)

    cloud_state = {"done": {}, "spam": []}
    saved_states = []
    monkeypatch.setattr(triage_store, "load", lambda: copy.deepcopy(cloud_state))
    monkeypatch.setattr(triage_store, "save_raw", lambda data: saved_states.append(copy.deepcopy(data)))

    database.init_db()
    conn = database.get_connection()
    conn.execute(
        """INSERT INTO emails
           (id, account_id, folder, subject, sender, recipients, date, done_at, original_folder)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        ("acct::<msg-1>", "acct", database.FINISHED_FOLDER, "Done mail", "a@example.com", "[]", "", "2026-05-15T10:00:00", "INBOX"),
    )
    conn.commit()
    conn.close()

    database.init_triage_sync()

    conn = database.get_connection()
    row = conn.execute("SELECT folder, done_at, original_folder FROM emails WHERE id = ?", ("acct::<msg-1>",)).fetchone()
    conn.close()

    assert row["folder"] == database.FINISHED_FOLDER
    assert row["done_at"] == "2026-05-15T10:00:00"
    assert row["original_folder"] == "INBOX"
    assert saved_states[-1]["done"]["acct::<msg-1>"]["original_folder"] == "INBOX"
