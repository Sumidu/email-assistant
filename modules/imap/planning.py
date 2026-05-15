from datetime import datetime, timedelta


def search_uids(conn, mode: str, limit: int, since_date: str, last_seen_uid: int) -> list[bytes]:
    if last_seen_uid > 0:
        status, data = conn.uid("search", None, "UID", f"{last_seen_uid + 1}:*")
    elif mode == "since" and since_date:
        try:
            parsed = datetime.fromisoformat(since_date).strftime("%d-%b-%Y")
        except Exception:
            parsed = since_date
        status, data = conn.uid("search", None, "SINCE", parsed)
    else:
        status, data = conn.uid("search", None, "ALL")
    if status != "OK" or not data:
        return []
    uids = data[0].split()
    if mode == "recent" and limit > 0 and last_seen_uid <= 0:
        uids = uids[-limit:]
    return uids


def search_recent_uids(conn, days: int = 7) -> list[bytes]:
    since = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")
    status, data = conn.uid("search", None, "SINCE", since)
    if status != "OK" or not data:
        return []
    return data[0].split()

