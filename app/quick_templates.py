DEFAULT_QUICK_TEMPLATES = [
    {
        "emoji": "👍",
        "message": "Please write a concise reply confirming or accepting what was proposed.",
    },
    {
        "emoji": "👎",
        "message": "Please write a concise reply declining or rejecting what was proposed.",
    },
]


def quick_template_defaults() -> list[dict]:
    return [dict(t) for t in DEFAULT_QUICK_TEMPLATES]


def normalize_quick_templates(templates) -> list[dict]:
    normalized = []
    for item in templates or []:
        emoji = str((item or {}).get("emoji", "")).strip()[:8]
        message = str((item or {}).get("message", "")).strip()
        if not emoji or not message:
            continue
        normalized.append({"emoji": emoji, "message": message})
    return normalized or quick_template_defaults()


def ensure_quick_templates(config: dict) -> list[dict]:
    config["quick_templates"] = normalize_quick_templates(
        config.get("quick_templates") or quick_template_defaults()
    )
    return config["quick_templates"]
