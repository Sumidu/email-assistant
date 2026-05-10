"""
LLM request/response logger.
Writes all LLM calls to the app log directory for debugging.
"""

import os
from datetime import datetime

from app import paths

LOG_PATH = str(paths.LLM_LOG_PATH)
_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
_BACKUP_COUNT = 3


def _rotate_if_needed():
    if not os.path.exists(LOG_PATH):
        return
    if os.path.getsize(LOG_PATH) < _MAX_BYTES:
        return
    for i in range(_BACKUP_COUNT - 1, 0, -1):
        src = f"{LOG_PATH}.{i}"
        dst = f"{LOG_PATH}.{i + 1}"
        if os.path.exists(src):
            os.replace(src, dst)
    os.replace(LOG_PATH, f"{LOG_PATH}.1")


def log(kind: str, system: str, user: str, response: str, model: str = ""):
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    _rotate_if_needed()
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sep = "=" * 80
    bar = "─" * 40
    entry = (
        f"\n{sep}\n"
        f"[{ts}]  kind={kind}  model={model}\n"
        f"{bar} SYSTEM\n{system}\n"
        f"{bar} USER\n{user}\n"
        f"{bar} RESPONSE\n{response}\n"
    )
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(entry)
