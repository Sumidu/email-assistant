import re
import unicodedata
from datetime import datetime, timedelta, timezone

from app import llm_client, prompt_defaults
from modules import database

_STOPWORDS = frozenset(
    "a an the and or but in on at to for of with is are was were be been have has "
    "had do does did this that it its i me my we our you your he she they them "
    "will can could would should may might shall s t".split()
)


def _slug_from(text: str) -> str:
    text = str(text or "").lower().strip()
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")[:60]


def _commitment_slug(what: str, person: str, deadline: str) -> str:
    parts = [_slug_from(what)[:30], _slug_from(person)[:20]]
    if deadline and len(deadline) >= 7:
        parts.append(deadline[:7])
    return "-".join(p for p in parts if p)


def _project_slug(name: str) -> str:
    return _slug_from(name)


def _meeting_slug(date: str, topic: str) -> str:
    date_part = (date or "")[:10]
    topic_part = _slug_from(topic)[:40]
    if date_part:
        return f"{date_part}-{topic_part}" if topic_part else date_part
    return topic_part or "meeting"


def extract_entities_from_email(email: dict, config: dict) -> dict:
    """Call LLM once per email. Returns {projects, commitments, meetings} or {} on failure."""
    prompts = prompt_defaults.load_prompts()
    system = prompts["entity_extraction_system"]
    user_tpl = prompts["entity_extraction_user"]

    body = (email.get("body_text") or "")[:2000]
    user = prompt_defaults.render_prompt(user_tpl, {
        "sender": email.get("sender", ""),
        "recipients": email.get("recipients", ""),
        "date": email.get("date", ""),
        "subject": email.get("subject", ""),
        "body": body,
    })
    try:
        data = llm_client.call_json(system, user, config, max_tokens=800, tag="knowledge-entities")
        if not isinstance(data, dict):
            return {}
        return {
            "projects": data.get("projects") if isinstance(data.get("projects"), list) else [],
            "commitments": data.get("commitments") if isinstance(data.get("commitments"), list) else [],
            "meetings": data.get("meetings") if isinstance(data.get("meetings"), list) else [],
        }
    except Exception:
        return {}


def canonicalize_entities(batch: dict, existing_slugs: dict[str, dict[str, str]], config: dict) -> dict:
    """
    batch: {projects: [...], commitments: [...], meetings: [...]} (already aggregated, with code-derived slugs)
    existing_slugs: {"projects": {slug: name}, "commitments": {slug: name}, "meetings": {slug: name}}
    Returns mapping {entity_type: {code_slug: canonical_slug}}.
    """
    mapping: dict[str, dict[str, str]] = {"projects": {}, "commitments": {}, "meetings": {}}

    for entity_type in ("projects", "commitments", "meetings"):
        items = batch.get(entity_type, [])
        existing = existing_slugs.get(entity_type, {})
        if not items or not existing:
            for item in items:
                s = item.get("_slug", "")
                if s:
                    mapping[entity_type][s] = s
            continue

        name_to_slug: dict[str, str] = {}
        for item in items:
            s = item.get("_slug", "")
            name = item.get("name") or item.get("what") or item.get("topic") or s
            if s:
                name_to_slug[name] = s

        if not name_to_slug:
            continue

        prompts = prompt_defaults.load_prompts()
        system = prompts["entity_canonicalize_system"]
        user_tpl = prompts["entity_canonicalize_user"]
        extracted_names_str = "\n".join(f"- {n}" for n in name_to_slug)
        existing_str = "\n".join(f"- {slug}: {name}" for slug, name in existing.items())
        user = prompt_defaults.render_prompt(user_tpl, {
            "extracted_names": extracted_names_str,
            "existing_slugs": existing_str,
        })
        try:
            result = llm_client.call_json(system, user, config, max_tokens=400, tag="knowledge-entities")
            if isinstance(result, dict):
                for name, code_slug in name_to_slug.items():
                    matched = result.get(name)
                    mapping[entity_type][code_slug] = matched if (matched and isinstance(matched, str)) else code_slug
                continue
        except Exception:
            pass
        for code_slug in name_to_slug.values():
            mapping[entity_type][code_slug] = code_slug

    return mapping


def aggregate_entity_batch(extractions: list[dict]) -> dict:
    """Merge per-email extraction dicts, adding code-derived slugs. Deduplicates by slug."""
    projects: dict[str, dict] = {}
    commitments: dict[str, dict] = {}
    meetings: dict[str, dict] = {}

    for extraction in extractions:
        for p in extraction.get("projects") or []:
            if not isinstance(p, dict) or not p.get("name"):
                continue
            slug = _project_slug(p["name"])
            if slug not in projects:
                projects[slug] = {**p, "_slug": slug}

        for c in extraction.get("commitments") or []:
            if not isinstance(c, dict) or not c.get("what"):
                continue
            slug = _commitment_slug(c.get("what", ""), c.get("person", ""), c.get("deadline", ""))
            if slug not in commitments:
                commitments[slug] = {**c, "_slug": slug}

        for m in extraction.get("meetings") or []:
            if not isinstance(m, dict):
                continue
            slug = _meeting_slug(m.get("date", ""), m.get("topic", ""))
            if slug not in meetings:
                meetings[slug] = {**m, "_slug": slug}

    return {
        "projects": list(projects.values()),
        "commitments": list(commitments.values()),
        "meetings": list(meetings.values()),
    }


def find_calendar_match(date_str: str, topic: str, account_id: str | None = None) -> str | None:
    """Find a calendar event within ±1 day whose subject overlaps topic by ≥2 non-stopwords."""
    if not date_str or len(date_str) < 8:
        return None
    try:
        day = datetime.fromisoformat(date_str[:10]).replace(tzinfo=timezone.utc)
    except ValueError:
        return None

    start_ts = (day - timedelta(days=1)).timestamp()
    end_ts = (day + timedelta(days=1, hours=23, minutes=59)).timestamp()
    events = database.get_calendar_events_in_window(start_ts, end_ts)
    if account_id:
        events = [e for e in events if e.get("account_id") == account_id]

    topic_tokens = {t for t in re.findall(r"\b[a-z]+\b", topic.lower()) if t not in _STOPWORDS and len(t) > 2}
    if not topic_tokens:
        return None

    best_score = 1
    best_title = None
    for ev in events:
        title = ev.get("title") or ""
        ev_tokens = {t for t in re.findall(r"\b[a-z]+\b", title.lower()) if t not in _STOPWORDS and len(t) > 2}
        score = len(topic_tokens & ev_tokens)
        if score > best_score:
            best_score = score
            best_title = title
    return best_title
