import json
import re
from datetime import datetime

from flask import Blueprint, jsonify, request

from app import llm_providers
from app import prompt_defaults
from app import runtime as rt
from modules import database
from modules import llm_logger


bp = Blueprint("todos", __name__, url_prefix="/api")


def _compact_email(row: dict) -> str:
    body = re.sub(r"\s+", " ", row.get("body_text") or "").strip()
    return (
        f"ID: {row.get('id')}\n"
        f"Subject: {row.get('subject') or '(no subject)'}\n"
        f"From: {row.get('sender') or ''}\n"
        f"Date: {row.get('date') or ''}\n"
        f"Body: {body[:1400]}"
    )


def _parse_todos(raw: str) -> list[dict]:
    text = raw.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        text = match.group(1).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        items = []
        for line in raw.splitlines():
            line = re.sub(r"^\s*[-*]\s+", "", line).strip()
            if line:
                items.append({"title": line, "details": "", "source_ids": []})
        return items[:40]
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
        cleaned.append({
            "title": title,
            "details": str(item.get("details") or item.get("description") or "").strip(),
            "due": str(item.get("due") or item.get("due_date") or "").strip(),
            "source_ids": item.get("source_ids") if isinstance(item.get("source_ids"), list) else [],
        })
    return cleaned


@bp.route("/todos/find", methods=["POST"])
def find_todos():
    data = request.get_json(silent=True) or {}
    folder = data.get("folder") or "INBOX"
    account_id = data.get("account_id") or None
    search = data.get("search") or ""
    start_date = data.get("start_date") or ""
    end_date = data.get("end_date") or ""
    found = database.search_emails_for_todos(
        folder=folder,
        account_id=account_id,
        search=search,
        start_date=start_date,
        end_date=end_date,
        limit=250,
    )
    rows = found["rows"]
    if not rows:
        return jsonify({"todos": [], "matched": 0, "analyzed": 0})

    prompts = prompt_defaults.ensure_prompts(rt.config)
    system_prompt = prompts["todo_extraction_system"]
    model = llm_providers.get_active_llm(rt.config).get("model", "")
    todos = []
    try:
        for row in rows:
            user_prompt = (
                f"Today is {datetime.now().date().isoformat()}. "
                "Analyze exactly this one email. If it contains no concrete action for the user, "
                "return []. If it contains one or more concrete actions, return only those todo "
                "objects and include this email ID in source_ids.\n\n"
                f"{_compact_email(row)}"
            )
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
            raw = rt.resp_gen._call_messages(messages, max_tokens=700)
            llm_logger.log("todos", system_prompt, user_prompt, raw, model=model)
            for todo in _parse_todos(raw):
                if not todo.get("source_ids"):
                    todo["source_ids"] = [row.get("id")]
                todos.append(todo)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 502
    return jsonify({
        "todos": todos[:80],
        "matched": found["total"],
        "analyzed": len(rows),
    })


@bp.route("/todos/preview", methods=["POST"])
def preview_todos():
    data = request.get_json(silent=True) or {}
    found = database.search_emails_for_todos(
        folder=data.get("folder") or "INBOX",
        account_id=data.get("account_id") or None,
        search=data.get("search") or "",
        start_date=data.get("start_date") or "",
        end_date=data.get("end_date") or "",
        limit=250,
    )
    return jsonify({
        "matched": found["total"],
        "analyzed": len(found["rows"]),
        "limit": 250,
    })
