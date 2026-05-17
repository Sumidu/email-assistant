import email.header
import html
import re


def decode_header_value(value: str) -> str:
    if not value:
        return ""
    parts = email.header.decode_header(value)
    result = []
    for raw, charset in parts:
        if isinstance(raw, bytes):
            result.append(raw.decode(charset or "utf-8", errors="replace"))
        else:
            result.append(str(raw))
    return "".join(result)


def html_to_text(raw_html: str) -> str:
    text = re.sub(r"<(script|style)[^>]*>.*?</(script|style)>", "", raw_html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _safe_charset(charset: str) -> str:
    cs = (charset or "utf-8").lower().strip()
    # Non-standard names used by some mail clients for unspecified 8-bit encodings
    if cs in ("unknown-8bit", "unknown", "x-unknown", "x-user-defined"):
        return "latin-1"
    return charset or "utf-8"


def extract_bodies(msg) -> tuple[str, str]:
    plain, htm = "", ""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition", ""))
            if "attachment" in disp:
                continue
            charset = _safe_charset(part.get_content_charset())
            try:
                payload = part.get_payload(decode=True)
                if not payload:
                    continue
                decoded = payload.decode(charset, errors="replace")
                if ctype == "text/plain" and not plain:
                    plain = decoded
                elif ctype == "text/html" and not htm:
                    htm = decoded
            except Exception:
                pass
    else:
        ctype = msg.get_content_type()
        charset = _safe_charset(msg.get_content_charset())
        try:
            payload = msg.get_payload(decode=True)
            if payload:
                decoded = payload.decode(charset, errors="replace")
                if ctype == "text/plain":
                    plain = decoded
                elif ctype == "text/html":
                    htm = decoded
        except Exception:
            pass
    if not plain and htm:
        plain = html_to_text(htm)
    return plain.strip(), htm.strip()


def quote_folder(folder_name: str) -> str:
    escaped = (folder_name or "").replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def fetch_response_flags(fetch_data) -> bytes:
    chunks = []
    for item in fetch_data or []:
        if isinstance(item, tuple):
            chunks.append(item[0] if isinstance(item[0], bytes) else str(item[0]).encode())
        elif isinstance(item, bytes):
            chunks.append(item)
    return b" ".join(chunks)


def flags_from_fetch_response(fetch_data) -> set[bytes]:
    flags_blob = fetch_response_flags(fetch_data)
    match = re.search(br"FLAGS \(([^)]*)\)", flags_blob, flags=re.IGNORECASE)
    return set(match.group(1).lower().split()) if match else set()


def is_read_from_fetch_response(fetch_data) -> bool:
    return b"\\seen" in flags_from_fetch_response(fetch_data)


def is_flagged_from_fetch_response(fetch_data) -> bool:
    return b"\\flagged" in flags_from_fetch_response(fetch_data)


def parse_uid_flags(fetch_data) -> dict[int, dict]:
    parsed = {}
    for item in fetch_data or []:
        if isinstance(item, tuple):
            blob = item[0] if isinstance(item[0], bytes) else str(item[0]).encode()
        elif isinstance(item, bytes):
            blob = item
        else:
            continue
        uid_match = re.search(br"\bUID\s+(\d+)\b", blob, flags=re.IGNORECASE)
        flags_match = re.search(br"FLAGS\s+\(([^)]*)\)", blob, flags=re.IGNORECASE)
        if not uid_match or not flags_match:
            continue
        flags = set(flags_match.group(1).lower().split())
        parsed[int(uid_match.group(1))] = {
            "is_read": b"\\seen" in flags,
            "is_flagged": b"\\flagged" in flags,
        }
    return parsed


def raw_message_from_fetch_response(fetch_data):
    for item in fetch_data or []:
        if isinstance(item, tuple) and item[1]:
            header = item[0] if isinstance(item[0], bytes) else str(item[0]).encode()
            if b"RFC822" in header:
                return item[1]
    return None

