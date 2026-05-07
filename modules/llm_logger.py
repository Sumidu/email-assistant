"""
LLM request/response logger.
Writes all LLM calls to the app log directory for debugging.
"""

import os
from datetime import datetime

from app import paths

LOG_PATH = str(paths.LLM_LOG_PATH)


def log(kind: str, system: str, user: str, response: str, model: str = ""):
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
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
