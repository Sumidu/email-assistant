import json
import re
import uuid
from datetime import UTC, datetime

from app.llm_client import _extract_json


def compact_email(row: dict) -> str:
    body = re.sub(r"\s+", " ", row.get("body_text") or "").strip()
    return (
        "BEGIN UNTRUSTED EMAIL CONTENT\n"
        f"ID: {row.get('id')}\n"
        f"Subject: {row.get('subject') or '(no subject)'}\n"
        f"From: {row.get('sender') or ''}\n"
        f"Date: {row.get('date') or ''}\n"
        f"Body: {body[:1400]}\n"
        "END UNTRUSTED EMAIL CONTENT"
    )


def email_preview(row: dict) -> dict:
    body = re.sub(r"\s+", " ", row.get("body_text") or "").strip()
    return {
        "id": row.get("id"),
        "subject": row.get("subject") or "(no subject)",
        "sender": row.get("sender") or "",
        "date": row.get("date") or "",
        "body": body[:1800],
    }


def parse_todos(raw: str) -> list[dict]:
    data = _extract_json(raw or "")
    if data is None:
        return []
    if isinstance(data, dict):
        data = data.get("todos", [])
    if not isinstance(data, list):
        return []
    cleaned = []
    for item in data[:40]:
        if isinstance(item, str):
            cleaned.append({"title": item, "details": "", "source_ids": []})
            continue
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or item.get("todo") or "").strip()
        if not title:
            continue
        tags = item.get("tags")
        if isinstance(tags, str):
            tags = [tag.strip() for tag in re.split(r"[,#]", tags) if tag.strip()]
        elif not isinstance(tags, list):
            tags = []
        cleaned.append({
            "title": title,
            "description": str(item.get("description") or item.get("details") or "").strip(),
            "due_date": str(item.get("due_date") or item.get("due") or "").strip(),
            "tags": [str(tag).strip() for tag in tags if str(tag).strip()],
            "location": str(item.get("location") or "").strip(),
            "source_ids": item.get("source_ids") if isinstance(item.get("source_ids"), list) else [],
        })
    return cleaned


def ics_escape(value: str) -> str:
    return (
        str(value or "")
        .replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace(",", "\\,")
        .replace(";", "\\;")
    )


def render_ics(todos: list[dict]) -> str:
    now = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Email Assistant//Todo Export//EN",
        "CALSCALE:GREGORIAN",
    ]
    for item in todos:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        uid = f"{uuid.uuid4().hex}@email-assistant.local"
        due = str(item.get("due_date") or item.get("due") or "").strip()
        tags = item.get("tags") if isinstance(item.get("tags"), list) else []
        description = str(item.get("description") or item.get("details") or "").strip()
        location = str(item.get("location") or "").strip()
        lines.extend([
            "BEGIN:VTODO",
            f"UID:{uid}",
            f"DTSTAMP:{now}",
            f"SUMMARY:{ics_escape(title)}",
        ])
        if description:
            lines.append(f"DESCRIPTION:{ics_escape(description)}")
        if location:
            lines.append(f"LOCATION:{ics_escape(location)}")
        if tags:
            lines.append(f"CATEGORIES:{ics_escape(','.join(str(tag) for tag in tags if str(tag).strip()))}")
        if re.match(r"^\d{4}-\d{2}-\d{2}$", due):
            lines.append(f"DUE;VALUE=DATE:{due.replace('-', '')}")
        elif due:
            lines.append(f"X-EMAIL-ASSISTANT-DUE-TEXT:{ics_escape(due)}")
        lines.append("END:VTODO")
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
