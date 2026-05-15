import json
import os
import re

FRONTMATTER_MARKER = "---"


def yaml_quote(value) -> str:
    text = str(value or "")
    return json.dumps(text, ensure_ascii=False)


def yaml_list(values) -> str:
    items = [yaml_quote(v) for v in values or [] if str(v or "").strip()]
    return "[" + ", ".join(items) + "]"


def parse_frontmatter_value(value: str):
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            inner = value[1:-1].strip()
            if not inner:
                return []
            return [v.strip().strip("\"'") for v in inner.split(",") if v.strip()]
    return value.strip("\"'")


def split_frontmatter(content: str) -> tuple[dict, str]:
    if not content.startswith(FRONTMATTER_MARKER + "\n"):
        return {}, content
    end = content.find("\n" + FRONTMATTER_MARKER + "\n", len(FRONTMATTER_MARKER) + 1)
    if end == -1:
        return {}, content
    raw = content[len(FRONTMATTER_MARKER) + 1:end]
    body = content[end + len(FRONTMATTER_MARKER) + 2:]
    data = {}
    for line in raw.splitlines():
        if not line.strip() or line.lstrip().startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = parse_frontmatter_value(value)
    return data, body.lstrip("\n")


def strip_frontmatter(content: str) -> str:
    return split_frontmatter(content)[1]


def unwrap_wikilinks(value: str) -> str:
    value = str(value or "")
    value = re.sub(r"\[\[[^|\]#]+(?:#[^|\]]+)?\|([^\]]+)\]\]", r"\1", value)
    value = re.sub(r"\[\[([^\]#|]+)(?:#[^\]]+)?\]\]", r"\1", value)
    return value


def unwrap_heading_wikilinks(body: str) -> str:
    def repl(match):
        return match.group(1) + unwrap_wikilinks(match.group(2))
    return re.sub(r"^(#{1,6}\s+)(.+)$", repl, body or "", flags=re.MULTILINE)


def repair_nested_wikilinks(body: str) -> str:
    body = body or ""
    nested = re.compile(r"\[\[([^\]|#]+)(#[^\]|]+)?\|\[\[[^\]|#]+(?:#[^\]|]+)?\|([^\]]+)\]\]\]\]")
    previous = None
    while previous != body:
        previous = body
        body = nested.sub(r"[[\1|\3]]", body)
    return body


def clean_link_label(value: str) -> str:
    label = unwrap_wikilinks(value).strip()
    label = re.sub(r"^contact\s*:\s*", "", label, flags=re.IGNORECASE).strip()
    if "," in label:
        parts = [p.strip() for p in label.split(",", 1)]
        if all(parts):
            label = f"{parts[1]} {parts[0]}"
    return re.sub(r"\s+", " ", label).strip()


def frontmatter_title(filename: str, content: str = "") -> str:
    stem = os.path.basename(filename).removesuffix(".md")
    first_heading = re.search(r"^#\s+(.+)$", content, flags=re.MULTILINE)
    if first_heading:
        return first_heading.group(1).strip()
    if stem == "_writing_style":
        return "Writing Style"
    return stem.replace("_", " ").replace(".", " ").title()


def infer_email_from_filename(filename: str) -> str:
    stem = os.path.basename(filename).removesuffix(".md")
    if stem.startswith("_") or "_" not in stem:
        return ""
    local, domain = stem.rsplit("_", 1)
    if "." not in domain:
        return ""
    return f"{local}@{domain}".lower()

