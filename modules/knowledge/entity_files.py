import os
import re

from modules.knowledge import frontmatter as kb_frontmatter

AI_BLOCK_START = "<!-- ai-managed -->"
AI_BLOCK_END = "<!-- /ai-managed -->"

_AI_BLOCK_RE = re.compile(
    r"<!-- ai-managed -->(.*?)<!-- /ai-managed -->",
    re.DOTALL,
)


def parse_entity_file(content: str) -> dict:
    """Split a file into frontmatter dict, ai_block string, and user_content string."""
    frontmatter, body = kb_frontmatter.split_frontmatter(content)
    m = _AI_BLOCK_RE.search(body)
    if m:
        ai_block = m.group(1).strip()
        before = body[: m.start()].strip()
        after = body[m.end() :].strip()
        user_content = "\n\n".join(part for part in (before, after) if part)
    else:
        ai_block = ""
        user_content = body.strip()
    return {"frontmatter": frontmatter, "ai_block": ai_block, "user_content": user_content}


def render_entity_file(frontmatter: dict, ai_block: str, user_content: str) -> str:
    """Reassemble a file from its three parts."""
    lines = ["---"]
    for k, v in frontmatter.items():
        if isinstance(v, list):
            lines.append(f"{k}: {kb_frontmatter.yaml_list(v)}")
        else:
            lines.append(f"{k}: {kb_frontmatter.yaml_quote(v)}")
    lines.append("---")
    lines.append("")
    lines.append(AI_BLOCK_START)
    if ai_block:
        lines.append(ai_block)
    lines.append(AI_BLOCK_END)
    if user_content:
        lines.append("")
        lines.append(user_content)
    lines.append("")
    return "\n".join(lines)


def read_entity_file(path: str) -> dict:
    """Read and parse an entity file, returning {frontmatter, ai_block, user_content}."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        return {"frontmatter": {}, "ai_block": "", "user_content": ""}
    return parse_entity_file(content)


def write_entity_file(path: str, frontmatter: dict, ai_block: str, user_content: str) -> None:
    """Write an entity file, creating parent directories as needed."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    content = render_entity_file(frontmatter, ai_block, user_content)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def collect_existing_slugs(entity_dir: str) -> dict[str, str]:
    """Return {slug: display_name} for all .md files in entity_dir."""
    result = {}
    if not os.path.isdir(entity_dir):
        return result
    for fname in os.listdir(entity_dir):
        if not fname.endswith(".md"):
            continue
        path = os.path.join(entity_dir, fname)
        parsed = read_entity_file(path)
        fm = parsed["frontmatter"]
        slug = fm.get("slug") or os.path.splitext(fname)[0]
        name = fm.get("name") or fm.get("what") or fm.get("topic") or slug
        result[str(slug)] = str(name)
    return result
