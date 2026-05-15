import email.utils
from datetime import datetime
from typing import Optional


def parse_email_date_ts(value: str) -> Optional[float]:
    try:
        parsed = email.utils.parsedate_to_datetime(value)
        if parsed is None:
            return None
        return parsed.timestamp()
    except Exception:
        return None


def local_date_start_ts(value: str) -> Optional[float]:
    try:
        return datetime.strptime(value, "%Y-%m-%d").timestamp()
    except (TypeError, ValueError):
        return None

