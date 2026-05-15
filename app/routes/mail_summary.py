import re
from datetime import datetime

import requests
from flask import Blueprint, jsonify, request

from app import llm_providers
from app import prompt_defaults
from app import runtime as rt
from app.services import mail_summary as mail_summary_service
from modules import database
from modules import llm_logger


bp = Blueprint("mail_summary", __name__, url_prefix="/api")
PREFERENCES_FILE = "mail_summary_preferences.md"


def _compact_email(row: dict) -> str:
    return mail_summary_service.compact_email(row)


def _summary_knowledge_context() -> str:
    if not rt.kb:
        return ""
    chunks = []
    for item in rt.kb.list_knowledge_files():
        name = item.get("name", "")
        category = item.get("category", "")
        if category != "other":
            continue
        full = rt.kb.read_knowledge_file(name) if hasattr(rt.kb, "read_knowledge_file") else {}
        content = (full.get("content") or item.get("content") or "").strip()
        if not content:
            continue
        chunks.append(
            f"=== BEGIN UNTRUSTED KNOWLEDGE BASE CONTENT: {name} ===\n"
            f"{content[:2200]}\n"
            f"=== END UNTRUSTED KNOWLEDGE BASE CONTENT: {name} ==="
        )
    return "\n\n".join(chunks)[:9000]


def _sent_folders() -> set[str]:
    return mail_summary_service.sent_folders(rt.config)


def _parse_summary_json(raw: str) -> dict:
    return mail_summary_service.parse_summary_json(raw)


def _json_text(raw: str) -> str:
    return mail_summary_service.json_text(raw)


def _salvage_summary_json(text: str) -> dict:
    return mail_summary_service.salvage_summary_json(text)


def _balanced_object(text: str, start: int) -> tuple[str, int]:
    return mail_summary_service.balanced_object(text, start)


def _normalize_summary(data: dict) -> dict:
    return mail_summary_service.normalize_summary(data)


def _rating(value, fallback=3) -> int:
    return mail_summary_service.rating(value, fallback)


def _email_learning_context(source_ids: list[str]) -> list[str]:
    lines = []
    for source_id in source_ids[:6]:
        row = database.get_email_by_id(source_id)
        if not row:
            continue
        body = re.sub(r"\s+", " ", row.get("body_text") or "").strip()
        lines.extend([
            f"  - Email: {source_id}",
            f"    Subject: {row.get('subject') or '(no subject)'}",
            f"    From: {row.get('sender') or ''}",
            f"    Folder: {row.get('folder') or ''}",
            f"    Read status: {'read' if row.get('is_read') else 'unread'}",
            f"    Body signal: {body[:500]}",
        ])
    return lines


def _attach_valid_source_ids(summary: dict, rows: list[dict]) -> dict:
    return mail_summary_service.attach_valid_source_ids(summary, rows)


def _infer_source_id(item: dict, rows: list[dict]) -> str:
    return mail_summary_service.infer_source_id(item, rows)


@bp.route("/mail_summary", methods=["POST"])
def mail_summary():
    data = request.get_json(silent=True) or {}
    start_date = str(data.get("start_date") or "").strip()
    end_date = str(data.get("end_date") or "").strip()
    account_id = str(data.get("account_id") or "").strip() or None
    if not start_date or not end_date:
        return jsonify({"success": False, "error": "Choose a start and end date."}), 400

    found = database.get_unfinished_emails_for_summary(
        start_date,
        end_date,
        account_id=account_id,
        excluded_folders=_sent_folders(),
        limit=120,
    )
    rows = found["rows"]
    for idx, row in enumerate(rows, start=1):
        row["__summary_index"] = idx
    if not rows:
        return jsonify({
            "success": True,
            "summary": {"executive_summary": "No unfinished emails found in this timeframe.", "items": []},
            "matched": found["total"],
            "analyzed": 0,
        })

    prompts = prompt_defaults.ensure_prompts(rt.config)
    system = prompt_defaults.with_untrusted_context_rules(prompts["mail_summary_system"])
    knowledge = _summary_knowledge_context()
    email_text = "\n\n--- EMAIL ---\n\n".join(_compact_email(row) for row in rows)
    user_prompt = f"""Timeframe: {start_date} to {end_date}
Matched unfinished emails: {found["total"]}
Emails included below: {len(rows)}
Each email has a Source number and an ID. In source_ids, prefer the exact ID. If you cannot safely copy the exact ID, use the Source number as a string.

KNOWLEDGE ABOUT WHAT MATTERS TO THE USER:
{knowledge or "(No priority knowledge found.)"}

BEGIN UNTRUSTED EMAIL COLLECTION
{email_text[:24000]}
END UNTRUSTED EMAIL COLLECTION
"""

    lm = llm_providers.get_active_llm(rt.config)
    model = lm.get("model", "local-model")
    url = f"{lm['base_url']}/v1/chat/completions"
    headers = {}
    if lm.get("api_key"):
        headers["Authorization"] = f"Bearer {lm['api_key']}"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_prompt},
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": 4000,
        "temperature": 0.2,
    }
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=180)
        if resp.status_code == 400 and "response_format" in payload:
            payload.pop("response_format", None)
            resp = requests.post(url, json=payload, headers=headers, timeout=180)
        resp.raise_for_status()
        raw_summary = resp.json()["choices"][0]["message"]["content"]
        llm_logger.log("mail_summary", system, user_prompt, raw_summary, model=model)
        structured = _attach_valid_source_ids(_parse_summary_json(raw_summary), rows)
        return jsonify({
            "success": True,
            "summary": structured,
            "matched": found["total"],
            "analyzed": len(rows),
            "truncated": found["total"] > len(rows),
        })
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@bp.route("/mail_summary/feedback", methods=["POST"])
def mail_summary_feedback():
    data = request.get_json(silent=True) or {}
    items = data.get("items") if isinstance(data.get("items"), list) else []
    timeframe = data.get("timeframe") if isinstance(data.get("timeframe"), dict) else {}
    if not items:
        return jsonify({"success": False, "error": "No rated summary items to save."}), 400

    email_updates = 0
    lines = [
        "## Mail summary feedback",
        "",
        f"Updated: {datetime.now():%Y-%m-%d %H:%M}",
        f"Timeframe: {timeframe.get('start_date', '')} to {timeframe.get('end_date', '')}",
        "",
        "Use these user ratings to prioritize future mail summaries. The specific email/item rating is stored on the source email rows for later filtering. The topic rating below says whether the broader topic matters even if the individual notification was not important. High topic ratings should make related future emails more visible; low specific-item ratings should de-emphasize similar low-signal notifications with similar sender, subject, or body patterns.",
        "",
    ]
    for item in items[:40]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        email_rating = _rating(item.get("email_importance") or item.get("user_importance") or item.get("importance"))
        topic_rating = _rating(item.get("topic_importance") or item.get("importance"))
        source_ids = item.get("source_ids", []) if isinstance(item.get("source_ids"), list) else []
        source_ids = [str(source_id) for source_id in source_ids if str(source_id).strip()][:8]
        note = "; ".join(
            part for part in [
                f"Mail summary: {title}",
                f"Category: {item.get('category', '')}",
                f"Rationale: {item.get('rationale', '')}",
                f"Suggested action: {item.get('suggested_action', '')}",
            ]
            if part.strip()
        )
        for source_id in source_ids:
            if database.update_email_importance(source_id, email_rating, note=note):
                email_updates += 1
        lines.extend([
            f"### {title}",
            f"- Topic importance rating: {topic_rating}/5",
            f"- Specific source email importance rating: {email_rating}/5 (stored on source email rows)",
            f"- Summary category: {item.get('category', '')}",
            f"- Model rationale: {item.get('rationale', '')}",
            f"- Suggested action: {item.get('suggested_action', '')}",
            f"- Source email IDs: {', '.join(source_ids)}",
            "- Signals for future classification:",
            *_email_learning_context(source_ids),
            "",
        ])

    existing = rt.kb.load_knowledge_file(PREFERENCES_FILE) if rt.kb else ""
    content = (existing.rstrip() + "\n\n" if existing else "# Mail Summary Preferences\n\n") + "\n".join(lines)
    result = rt.kb.save_knowledge_file(PREFERENCES_FILE, content, source="manual") if rt.kb else {"success": False, "error": "Knowledge base unavailable"}
    if result.get("success"):
        result["email_importance_updates"] = email_updates
    status = 200 if result.get("success") else 500
    return jsonify(result), status
