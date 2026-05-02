import os
import re
from datetime import datetime, timedelta

from flask import Blueprint, jsonify

from modules.llm_logger import LOG_PATH


bp = Blueprint("logs", __name__, url_prefix="/api")


def _estimate_tokens(text: str) -> int:
    if not text:
        return 0
    words = re.findall(r"\w+|[^\w\s]", text, flags=re.UNICODE)
    by_words = int(len(words) * 1.3)
    by_chars = int(len(text) / 4)
    return max(1, max(by_words, by_chars))


def _section(entry: str, name: str) -> str:
    marker = "─" * 40 + f" {name}"
    start = entry.find(marker)
    if start < 0:
        return ""
    start += len(marker)
    next_start = entry.find("─" * 40, start)
    return entry[start: next_start if next_start >= 0 else len(entry)].strip()


def _parse_entry(entry: str) -> dict:
    header = (entry.splitlines() or [""])[0].strip()
    match = re.match(r"^\[(.*?)\]\s+kind=([^\s]+)\s+model=(.*)$", header)
    timestamp = match.group(1) if match else ""
    date = None
    if timestamp:
        try:
            date = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            date = None
    system = _section(entry, "SYSTEM")
    user = _section(entry, "USER")
    response = _section(entry, "RESPONSE")
    input_tokens = _estimate_tokens("\n\n".join([system, user]).strip())
    output_tokens = _estimate_tokens(response)
    return {
        "text": entry,
        "header": header,
        "timestamp": timestamp,
        "kind": match.group(2) if match else "log",
        "model": (match.group(3) if match else "").strip(),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "_date": date,
    }


def _summary(entries: list[dict], since: datetime) -> dict:
    selected = [e for e in entries if e.get("_date") and e["_date"] >= since]
    return {
        "entries": len(selected),
        "input_tokens": sum(e["input_tokens"] for e in selected),
        "output_tokens": sum(e["output_tokens"] for e in selected),
        "total_tokens": sum(e["total_tokens"] for e in selected),
    }


@bp.route("/llm_log")
def llm_log():
    if not os.path.exists(LOG_PATH):
        empty = {"entries": 0, "input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        return jsonify({"entries": [], "summary": {"last_24h": empty, "last_7d": empty}})
    with open(LOG_PATH, encoding="utf-8") as f:
        raw = f.read()
    entries = [_parse_entry(e.strip()) for e in raw.split("=" * 80) if e.strip()]
    now = datetime.now()
    summary = {
        "last_24h": _summary(entries, now - timedelta(hours=24)),
        "last_7d": _summary(entries, now - timedelta(days=7)),
    }
    visible = []
    for entry in reversed(entries[-100:]):
        clean = {k: v for k, v in entry.items() if not k.startswith("_")}
        visible.append(clean)
    return jsonify({"entries": visible, "summary": summary})
