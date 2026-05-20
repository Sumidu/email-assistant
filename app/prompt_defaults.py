import os

_PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "prompts")

_REQUIRED_KEYS = [
    "response_system",
    "knowledge_style_system",
    "knowledge_style_user",
    "knowledge_contact_system",
    "knowledge_contact_user",
    "todo_extraction_system",
    "mail_summary_system",
    "entity_extraction_system",
    "entity_extraction_user",
    "entity_canonicalize_system",
    "entity_canonicalize_user",
    "entity_ai_block_system",
    "entity_ai_block_user",
]

_cache: dict | None = None


def load_prompts() -> dict:
    """Load all prompts from app/prompts/*.md. Cached after first call."""
    global _cache
    if _cache is not None:
        return _cache
    prompts = {}
    for fname in os.listdir(_PROMPTS_DIR):
        if fname.endswith(".md"):
            key = fname[:-3]
            with open(os.path.join(_PROMPTS_DIR, fname), "r", encoding="utf-8") as f:
                prompts[key] = f.read()
    for key in _REQUIRED_KEYS:
        if key not in prompts:
            raise RuntimeError(
                f"Required prompt file missing: app/prompts/{key}.md"
            )
    _cache = prompts
    return prompts


def render_prompt(template: str, values: dict) -> str:
    result = template or ""
    for key, value in values.items():
        result = result.replace("{{" + key + "}}", str(value))
    return result
