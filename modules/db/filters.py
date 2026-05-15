def apply_importance_filter(where: list[str], params: list, importance=None) -> None:
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


def apply_status_filter(where: list[str], status=None) -> None:
    status = str(status or "").strip().lower()
    if status == "unread":
        where.append("is_read = 0")
    elif status == "flagged":
        where.append("is_flagged = 1")
    elif status in ("unread_flagged", "flagged_unread"):
        where.append("is_read = 0")
        where.append("is_flagged = 1")


def email_filter_where(folder: str, account_id=None, search="", importance=None, status=None) -> tuple[list[str], list]:
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
    apply_importance_filter(where, params, importance)
    apply_status_filter(where, status)
    return where, params

