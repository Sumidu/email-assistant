"""
triage_store.py — iCloud-synced triage state (done/spam).

Reads and writes a small JSON file at TRIAGE_PATH so that email triage
decisions (mark done, unmark done, spam) propagate across devices via
iCloud Drive.  Falls back to Application Support when iCloud is absent.
"""

import json
import os
import tempfile
from threading import Lock

from app import paths

TRIAGE_PATH = str(paths.TRIAGE_PATH)
_lock = Lock()


def _read() -> dict:
    try:
        with open(TRIAGE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"done": {}, "spam": []}


def _write(data: dict) -> None:
    dir_ = os.path.dirname(TRIAGE_PATH)
    os.makedirs(dir_, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=dir_, suffix=".tmp", delete=False, encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        tmp = f.name
    os.replace(tmp, TRIAGE_PATH)


def exists() -> bool:
    return os.path.exists(TRIAGE_PATH)


def load() -> dict:
    with _lock:
        return _read()


def save_raw(data: dict) -> None:
    with _lock:
        _write(data)


def record_done(email_id: str, done_at: str, original_folder: str) -> None:
    with _lock:
        data = _read()
        data.setdefault("done", {})[email_id] = {
            "done_at": done_at,
            "original_folder": original_folder,
        }
        _write(data)


def record_done_batch(entries: list) -> None:
    """entries: list of {email_id, done_at, original_folder}"""
    if not entries:
        return
    with _lock:
        data = _read()
        done = data.setdefault("done", {})
        for e in entries:
            done[e["email_id"]] = {
                "done_at": e["done_at"],
                "original_folder": e["original_folder"],
            }
        _write(data)


def record_undone(email_id: str) -> None:
    with _lock:
        data = _read()
        data.setdefault("done", {}).pop(email_id, None)
        _write(data)


def record_spam(email_id: str, account_id: str, created_at: str) -> None:
    with _lock:
        data = _read()
        spam = data.setdefault("spam", [])
        if not any(s.get("email_id") == email_id and s.get("created_at") == created_at for s in spam):
            spam.append({"email_id": email_id, "account_id": account_id, "created_at": created_at})
        _write(data)
