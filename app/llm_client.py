"""
llm_client.py
Single entry point for all LLM HTTP calls. Handles think-tag stripping,
JSON extraction, markdown fence removal, and retry on transient errors.
"""

import re
import time

import requests

from app import llm_providers
from modules import llm_logger

_RETRY_STATUSES = {429, 503}
_THINK_TAGS = ("think", "thinking", "reasoning", "analysis")
_THINK_RE = re.compile(
    r"<\s*(?:" + "|".join(_THINK_TAGS) + r")\b[^>]*>[\s\S]*?<\s*/\s*(?:"
    + "|".join(_THINK_TAGS) + r")\s*>",
    re.IGNORECASE,
)
_FENCE_RE = re.compile(r"```(?:markdown|md|json)?\s*\n?([\s\S]*?)```", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _http_call(lm: dict, system: str, user: str, max_tokens: int, temperature: float,
               json_mode: bool = False) -> str:
    """Single HTTP request with retry on transient errors. Returns raw content string."""
    model = lm.get("model", "local-model")
    url = f"{lm['base_url']}/v1/chat/completions"
    headers = {}
    if lm.get("api_key"):
        headers["Authorization"] = f"Bearer {lm['api_key']}"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    last_exc = None
    for attempt in range(3):
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=180)
            if resp.status_code == 400 and json_mode:
                payload.pop("response_format", None)
                resp = requests.post(url, json=payload, headers=headers, timeout=180)
            if resp.status_code in _RETRY_STATUSES and attempt < 2:
                time.sleep(2 ** attempt)
                continue
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except (requests.ConnectionError, requests.Timeout) as exc:
            last_exc = exc
            if attempt < 2:
                time.sleep(2 ** attempt)
                continue
            raise
    raise last_exc  # type: ignore[misc]


def _strip_think_tags(text: str) -> str:
    return _THINK_RE.sub("", text or "").strip()


def _strip_fences(text: str) -> str:
    """Remove markdown code fences, returning inner content."""
    fences = list(_FENCE_RE.finditer(text))
    if not fences:
        return text.strip()
    if len(fences) == 1:
        return _FENCE_RE.sub(lambda m: m.group(1).strip() + "\n", text).strip()
    # Multiple fences — check if they're redundant wrappers for the same content
    headings = []
    for m in fences:
        h = re.search(r"^\s{0,3}#{1,6}\s+(.+)$", m.group(1), flags=re.MULTILINE)
        if h:
            headings.append(h.group(1).strip().lower())
    if len(headings) == len(fences) and all(h == headings[0] for h in headings):
        first, last = fences[0], fences[-1]
        return (text[: first.start()] + first.group(1).strip() + "\n" + text[last.end() :]).strip()
    return _FENCE_RE.sub(lambda m: m.group(1).strip() + "\n", text).strip()


def _extract_json(text: str) -> "dict | list | None":
    """
    Scan text for balanced JSON objects/arrays, try each longest-first.
    Handles code fences and leading prose before the JSON payload.
    """
    # Strip code fences first to catch ```json ... ``` wrappers
    candidates: list[str] = []
    for m in re.finditer(r"```(?:json)?\s*([\s\S]*?)```", text, re.IGNORECASE):
        candidates.append(m.group(1).strip())

    # Balanced bracket scan
    for start, opening in [(i, c) for i, c in enumerate(text) if c in "[{"]:
        closing = "]" if opening == "[" else "}"
        depth = 0
        in_string = False
        escaped = False
        for pos in range(start, len(text)):
            char = text[pos]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == opening:
                depth += 1
            elif char == closing:
                depth -= 1
                if depth == 0:
                    candidates.append(text[start : pos + 1].strip())
                    break

    import json
    for candidate in sorted(candidates, key=len, reverse=True):
        try:
            return json.loads(candidate)
        except Exception:
            continue
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _resolve_lm(config: dict) -> dict:
    return llm_providers.get_active_llm(config)


def call(system: str, user: str, config: dict, *,
         max_tokens: int = 2000, temperature: float = 0.3, tag: str = "knowledge") -> str:
    """Make an LLM call and return plain text with think tags stripped."""
    lm = _resolve_lm(config)
    raw = _http_call(lm, system, user, max_tokens, temperature)
    result = _strip_think_tags(raw)
    llm_logger.log(tag, system, user, result, model=lm.get("model", ""))
    return result


def call_json(system: str, user: str, config: dict, *,
              max_tokens: int = 1000, tag: str = "knowledge",
              json_mode: bool = False) -> "dict | list | None":
    """Make an LLM call and return a parsed JSON object/array, or None on failure."""
    lm = _resolve_lm(config)
    raw = _http_call(lm, system, user, max_tokens, 0.2, json_mode=json_mode)
    cleaned = _strip_think_tags(raw)
    result = _extract_json(cleaned)
    llm_logger.log(tag, system, user, raw, model=lm.get("model", ""))
    return result


def call_markdown(system: str, user: str, config: dict, *,
                  max_tokens: int = 2000, tag: str = "knowledge") -> str:
    """Make an LLM call and return cleaned markdown (think tags + code fences stripped)."""
    lm = _resolve_lm(config)
    raw = _http_call(lm, system, user, max_tokens, 0.3)
    result = _strip_fences(_strip_think_tags(raw))
    llm_logger.log(tag, system, user, result, model=lm.get("model", ""))
    return result


def call_messages(messages: list, config: dict, *,
                  max_tokens: int = 2000, temperature: float = 0.7,
                  tag: str = "chat") -> str:
    """Make an LLM call with a full message list (for multi-turn conversations)."""
    lm = _resolve_lm(config)
    model = lm.get("model", "local-model")
    url = f"{lm['base_url']}/v1/chat/completions"
    headers = {}
    if lm.get("api_key"):
        headers["Authorization"] = f"Bearer {lm['api_key']}"
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    last_exc = None
    for attempt in range(3):
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=180)
            if resp.status_code in _RETRY_STATUSES and attempt < 2:
                time.sleep(2 ** attempt)
                continue
            resp.raise_for_status()
            result = resp.json()["choices"][0]["message"]["content"]
            llm_logger.log(tag, str(messages), "", result, model=model)
            return _strip_think_tags(result)
        except (requests.ConnectionError, requests.Timeout) as exc:
            last_exc = exc
            if attempt < 2:
                time.sleep(2 ** attempt)
                continue
            raise
    raise last_exc  # type: ignore[misc]


def active_lm_metadata(config: dict) -> dict:
    """Return a snapshot of the active LLM provider for metadata recording."""
    lm = _resolve_lm(config)
    return {
        "id": lm.get("id", ""),
        "name": lm.get("name", ""),
        "model": lm.get("model", ""),
        "base_url": lm.get("base_url", ""),
    }
