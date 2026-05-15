from app.services import mail_summary


def test_parse_summary_json_strips_fences_and_trailing_commas():
    parsed = mail_summary.parse_summary_json(
        """```json
        {
          "executive_summary": "Heads up",
          "items": [
            {"title": "Renewal", "importance": 9, "source_ids": ["1",],},
          ],
        }
        ```"""
    )

    assert parsed["executive_summary"] == "Heads up"
    assert parsed["items"][0]["title"] == "Renewal"
    assert parsed["items"][0]["importance"] == 5


def test_attach_valid_source_ids_maps_source_numbers_and_infers_single_row():
    rows = [
        {"id": "acct::<one>", "__summary_index": 1, "subject": "Renewal", "sender": "billing@example.com"},
        {"id": "acct::<two>", "__summary_index": 2, "subject": "Newsletter", "sender": "news@example.com"},
    ]
    summary = {"items": [{"title": "Billing renewal", "source_ids": ["source 1"]}, {"title": "Newsletter", "source_ids": []}]}

    attached = mail_summary.attach_valid_source_ids(summary, rows)

    assert attached["items"][0]["source_ids"] == ["acct::<one>"]
    assert attached["items"][1]["source_ids"] == ["acct::<two>"]


def test_sent_folders_includes_account_configured_roles():
    folders = mail_summary.sent_folders({
        "accounts": [
            {
                "imap": {
                    "sent_folder": "Sent Mail",
                    "sync_folders": [{"name": "Archive", "role": "archive"}, {"name": "Sent Archive", "role": "sent"}],
                }
            }
        ]
    })

    assert {"Sent", "Sent Items", "Sent Mail", "Sent Archive"}.issubset(folders)

