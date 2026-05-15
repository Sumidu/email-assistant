from modules import database


def _use_temp_db(monkeypatch, tmp_path):
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "emails.db"))
    monkeypatch.setattr(database.triage_store, "record_done", lambda *args, **kwargs: None)
    monkeypatch.setattr(database.triage_store, "record_done_batch", lambda *args, **kwargs: None)
    monkeypatch.setattr(database.triage_store, "record_undone", lambda *args, **kwargs: None)
    monkeypatch.setattr(database.triage_store, "record_spam", lambda *args, **kwargs: None)
    database.init_db()


def _save_email(email_id: str, *, folder="INBOX", date="Fri, 15 May 2026 10:00:00 +0000", **extra):
    data = {
        "id": email_id,
        "account_id": "acct",
        "folder": folder,
        "subject": f"Subject {email_id}",
        "sender": "Sender <sender@example.com>",
        "recipients": [{"email": "me@example.com"}],
        "date": date,
        "body_text": f"Body {email_id}",
        "message_id": f"<{email_id}@example.com>",
        "imap_uid": extra.pop("imap_uid", None),
        "uidvalidity": extra.pop("uidvalidity", ""),
        **extra,
    }
    database.save_email(data)


def test_email_importance_filter_and_unrated(monkeypatch, tmp_path):
    _use_temp_db(monkeypatch, tmp_path)
    _save_email("acct::<important>")
    _save_email("acct::<plain>")

    assert database.update_email_importance("acct::<important>", 5, note="customer escalation")

    five_star = database.get_emails("INBOX", importance="5")
    unrated = database.get_emails("INBOX", importance="unrated")

    assert [row["id"] for row in five_star] == ["acct::<important>"]
    assert [row["id"] for row in unrated] == ["acct::<plain>"]


def test_summary_date_range_excludes_out_of_range_and_finished(monkeypatch, tmp_path):
    _use_temp_db(monkeypatch, tmp_path)
    _save_email("acct::<today>", date="Fri, 15 May 2026 10:00:00 +0000")
    _save_email("acct::<yesterday>", date="Thu, 14 May 2026 10:00:00 +0000")
    _save_email("acct::<done>", date="Fri, 15 May 2026 11:00:00 +0000")
    database.mark_email_done("acct::<done>")

    result = database.get_unfinished_emails_for_summary("2026-05-15", "2026-05-15")

    assert result["total"] == 1
    assert [row["id"] for row in result["rows"]] == ["acct::<today>"]


def test_sync_state_round_trip(monkeypatch, tmp_path):
    _use_temp_db(monkeypatch, tmp_path)

    database.save_sync_state("acct", "INBOX", "42", 123)
    state = database.get_sync_state("acct", "INBOX")

    assert state["account_id"] == "acct"
    assert state["folder"] == "INBOX"
    assert state["uidvalidity"] == "42"
    assert state["last_seen_uid"] == 123


def test_calendar_event_replace_and_query_window(monkeypatch, tmp_path):
    _use_temp_db(monkeypatch, tmp_path)
    database.replace_calendar_events(
        "acct",
        [
            {
                "uid": "meeting",
                "occurrence": "2026-05-15T09:00:00",
                "title": "Planning",
                "start_ts": 100.0,
                "end_ts": 200.0,
                "start_iso": "2026-05-15T09:00:00",
                "end_iso": "2026-05-15T10:00:00",
            }
        ],
        0,
        500,
    )

    rows = database.get_calendar_events("acct", start_ts=50, end_ts=150)

    assert len(rows) == 1
    assert rows[0]["uid"] == "meeting"
    assert rows[0]["title"] == "Planning"
