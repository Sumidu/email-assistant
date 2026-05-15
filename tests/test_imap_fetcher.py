from modules.imap_fetcher import IMAPFetcher


class FakeIMAP:
    def __init__(self):
        self.calls = []

    def uid(self, *args):
        self.calls.append(args)
        return "OK", [b"11 12 13"]


def make_fetcher():
    return IMAPFetcher({
        "id": "acct",
        "name": "Account",
        "imap": {"server": "imap.example.com", "username": "u", "password": "p"},
    })


def test_search_uids_uses_delta_when_last_seen_uid_exists():
    conn = FakeIMAP()
    uids = make_fetcher()._search_uids(conn, "recent", 300, "", 10)

    assert uids == [b"11", b"12", b"13"]
    assert conn.calls == [("search", None, "UID", "11:*")]


def test_search_uids_limits_first_recent_sync_to_fetch_limit():
    conn = FakeIMAP()
    uids = make_fetcher()._search_uids(conn, "recent", 2, "", 0)

    assert uids == [b"12", b"13"]
    assert conn.calls == [("search", None, "ALL")]


def test_quote_folder_escapes_backslashes_and_quotes():
    assert IMAPFetcher._quote_folder('Team "Inbox"\\2026') == '"Team \\"Inbox\\"\\\\2026"'
