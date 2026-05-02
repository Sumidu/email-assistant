import re


MASK = "••••••••"


def make_llm_id(name: str, existing_ids: list[str]) -> str:
    slug = re.sub(r"[^\w]+", "_", name.lower()).strip("_") or "llm"
    candidate = slug
    i = 2
    while candidate in existing_ids:
        candidate = f"{slug}_{i}"
        i += 1
    return candidate


def default_provider() -> dict:
    return {
        "id": "lm_studio",
        "name": "LM Studio",
        "base_url": "http://localhost:1234",
        "model": "local-model",
        "api_key": "",
    }


def normalize_provider(provider: dict, fallback_id: str | None = None) -> dict:
    normalized = {
        "id": provider.get("id") or fallback_id or "llm",
        "name": provider.get("name") or provider.get("model") or "LLM",
        "base_url": (provider.get("base_url") or "http://localhost:1234").rstrip("/"),
        "model": provider.get("model") or "local-model",
        "api_key": provider.get("api_key", ""),
    }
    return normalized


def ensure_llm_config(config: dict) -> None:
    """Migrate legacy lm_studio config into the multi-provider shape."""
    if not config.get("llms"):
        legacy = config.get("lm_studio") or {}
        provider = default_provider()
        provider.update({k: v for k, v in legacy.items() if k in provider})
        provider.setdefault("name", "LM Studio")
        config["llms"] = [normalize_provider(provider)]

    used_ids = set()
    normalized = []
    for i, provider in enumerate(config.get("llms", [])):
        candidate = normalize_provider(provider, fallback_id=f"llm_{i+1}")
        if candidate["id"] in used_ids:
            candidate["id"] = make_llm_id(candidate["name"], list(used_ids))
        used_ids.add(candidate["id"])
        normalized.append(candidate)

    if not normalized:
        normalized = [default_provider()]

    config["llms"] = normalized
    ids = [p["id"] for p in normalized]
    if config.get("default_llm_id") not in ids:
        config["default_llm_id"] = ids[0]

    app_config = config.setdefault("app", {})
    if app_config.get("active_llm_id") not in ids:
        app_config["active_llm_id"] = config["default_llm_id"]

    # Keep legacy consumers and old config views coherent.
    config["lm_studio"] = dict(get_default_llm(config))


def get_llm(config: dict, llm_id: str | None) -> dict:
    ensure_llm_config(config)
    for provider in config["llms"]:
        if provider["id"] == llm_id:
            return provider
    return get_default_llm(config)


def get_default_llm(config: dict) -> dict:
    ensure_llm_config(config) if "llms" not in config else None
    default_id = config.get("default_llm_id")
    for provider in config.get("llms", []):
        if provider["id"] == default_id:
            return provider
    return config.get("llms", [default_provider()])[0]


def get_active_llm(config: dict) -> dict:
    ensure_llm_config(config)
    return get_llm(config, config.get("app", {}).get("active_llm_id"))


def public_provider(provider: dict) -> dict:
    safe = dict(provider)
    if safe.get("api_key"):
        safe["api_key"] = MASK
    return safe
