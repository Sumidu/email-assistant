import re


def message_id_tokens(value: str) -> list[str]:
    if not value:
        return []
    tokens = re.findall(r"<[^>]+>", value)
    if not tokens and value.strip():
        tokens = [value.strip()]
    cleaned = []
    for token in tokens:
        token = token.strip().strip("<>").strip().lower()
        if token and token not in cleaned:
            cleaned.append(token)
    return cleaned


def thread_seed(message_id: str = "", in_reply_to: str = "", references_header: str = "") -> str:
    refs = message_id_tokens(references_header)
    if refs:
        return refs[0]
    replies = message_id_tokens(in_reply_to)
    if replies:
        return replies[0]
    own = message_id_tokens(message_id)
    return own[0] if own else (message_id or "").strip().lower()


def thread_id_for(account_id: str, seed: str) -> str:
    return f"{account_id}::{seed}" if seed else f"{account_id}::unknown"

