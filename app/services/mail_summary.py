import json
import re


def compact_email(row: dict) -> str:
    body = re.sub(r"\s+", " ", row.get("body_text") or "").strip()
    recipients = row.get("recipients") or ""
    return "\n".join([
        "BEGIN UNTRUSTED EMAIL CONTENT",
        f"Source number: {row.get('__summary_index')}",
        f"ID: {row.get('id')}",
        f"Folder: {row.get('folder') or ''}",
        f"Read status: {'read' if row.get('is_read') else 'unread'}",
        f"Stored email importance: {row.get('email_importance') or 'unrated'}",
        f"Subject: {row.get('subject') or '(no subject)'}",
        f"From: {row.get('sender') or ''}",
        f"To/Cc: {recipients}",
        f"Date: {row.get('date') or ''}",
        f"Body: {body[:1300]}",
        "END UNTRUSTED EMAIL CONTENT",
    ])


def sent_folders(config: dict) -> set[str]:
    folders = {"Sent", "Sent Items"}
    for account in config.get("accounts", []):
        imap = account.get("imap", {})
        if imap.get("sent_folder"):
            folders.add(imap["sent_folder"])
        for folder in imap.get("sync_folders", []):
            if folder.get("role") == "sent" and folder.get("name"):
                folders.add(folder["name"])
    return folders


def parse_summary_json(raw: str) -> dict:
    text = json_text(raw)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = salvage_summary_json(text)
    return normalize_summary(data)


def json_text(raw: str) -> str:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        text = match.group(0)
    return re.sub(r",\s*([}\]])", r"\1", text)


def salvage_summary_json(text: str) -> dict:
    """Recover complete summary items when a local model returns imperfect JSON."""
    repaired = text
    for _ in range(4):
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            if repaired.count("{") > repaired.count("}"):
                repaired += "}"
            if repaired.count("[") > repaired.count("]"):
                repaired += "]"
            repaired = re.sub(r",\s*([}\]])", r"\1", repaired)

    executive_summary = ""
    match = re.search(r'"executive_summary"\s*:\s*"((?:\\.|[^"\\])*)"', text)
    if match:
        try:
            executive_summary = json.loads(f'"{match.group(1)}"')
        except json.JSONDecodeError:
            executive_summary = match.group(1)

    items = []
    items_match = re.search(r'"items"\s*:\s*\[', text)
    if items_match:
        idx = items_match.end()
        while idx < len(text):
            start = text.find("{", idx)
            if start < 0:
                break
            obj_text, end = balanced_object(text, start)
            if not obj_text:
                break
            try:
                items.append(json.loads(re.sub(r",\s*([}\]])", r"\1", obj_text)))
            except json.JSONDecodeError:
                pass
            idx = end
    if items:
        return {"executive_summary": executive_summary or "Recovered partial summary from malformed model JSON.", "items": items}
    raise ValueError("The LLM returned malformed JSON and no complete summary items could be recovered.")


def balanced_object(text: str, start: int) -> tuple[str, int]:
    depth = 0
    in_string = False
    escape = False
    for idx in range(start, len(text)):
        ch = text[idx]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:idx + 1], idx + 1
    return "", start


def normalize_summary(data: dict) -> dict:
    items = data.get("items") if isinstance(data.get("items"), list) else []
    clean_items = []
    for item in items[:40]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        source_ids = item.get("source_ids") if isinstance(item.get("source_ids"), list) else []
        try:
            importance = int(item.get("importance") or 3)
        except (TypeError, ValueError):
            importance = 3
        clean_items.append({
            "title": title,
            "category": str(item.get("category") or "important_email").strip(),
            "importance": max(1, min(5, importance)),
            "rationale": str(item.get("rationale") or "").strip(),
            "suggested_action": str(item.get("suggested_action") or "").strip(),
            "source_ids": [str(source_id) for source_id in source_ids if str(source_id).strip()][:8],
        })
    return {
        "executive_summary": str(data.get("executive_summary") or "").strip(),
        "items": clean_items,
    }


def rating(value, fallback=3) -> int:
    try:
        parsed = int(value or fallback)
    except (TypeError, ValueError):
        parsed = fallback
    return max(1, min(5, parsed))


def attach_valid_source_ids(summary: dict, rows: list[dict]) -> dict:
    known_ids = {row.get("id"): row for row in rows if row.get("id")}
    by_number = {str(row.get("__summary_index")): row.get("id") for row in rows if row.get("__summary_index")}
    for item in summary.get("items", []):
        raw_ids = item.get("source_ids") if isinstance(item.get("source_ids"), list) else []
        valid = []
        for raw_id in raw_ids:
            source_id = str(raw_id or "").strip().strip("`'\"")
            source_id = re.sub(r"^(?:email|source)\s*#?\s*", "", source_id, flags=re.IGNORECASE).strip()
            if source_id in known_ids:
                valid.append(source_id)
                continue
            if source_id in by_number and by_number[source_id]:
                valid.append(by_number[source_id])
                continue
            partial = next((known_id for known_id in known_ids if source_id and source_id in known_id), None)
            if partial:
                valid.append(partial)
        if not valid:
            inferred = infer_source_id(item, rows)
            if inferred:
                valid.append(inferred)
        item["source_ids"] = list(dict.fromkeys(valid))[:8]
    return summary


def infer_source_id(item: dict, rows: list[dict]) -> str:
    if len(rows) == 1:
        return rows[0].get("id", "")
    haystack = " ".join([
        str(item.get("title") or ""),
        str(item.get("rationale") or ""),
        str(item.get("suggested_action") or ""),
    ]).lower()
    best_score = 0
    best_id = ""
    for row in rows:
        score = 0
        subject = str(row.get("subject") or "").lower()
        sender = str(row.get("sender") or "").lower()
        if subject and subject in haystack:
            score += 5
        for token in re.findall(r"[\w@.-]{4,}", subject + " " + sender):
            if token in haystack:
                score += 1
        if score > best_score:
            best_score = score
            best_id = row.get("id", "")
    return best_id if best_score >= 2 else ""

