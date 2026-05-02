import copy
import json
import os
import re
import shutil
import sys

from modules import keychain_store
from app import llm_providers
from app import prompt_defaults
from app import quick_templates


DATA_DIR = os.path.expanduser("~/email_assistant")
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")

DEFAULT_CONFIG = {
    "accounts": [],
    "lm_studio": {
        "base_url": "http://localhost:1234",
        "model": "local-model",
        "api_key": "",
    },
    "llms": [llm_providers.default_provider()],
    "default_llm_id": "lm_studio",
    "app": {"port": 5100, "active_llm_id": "lm_studio"},
    "prompts": prompt_defaults.prompt_defaults(),
    "quick_templates": quick_templates.quick_template_defaults(),
}


def migrate_config_location(base_dir: str) -> None:
    """Move config.json from old location beside the binary to ~/email_assistant/."""
    os.makedirs(DATA_DIR, exist_ok=True)
    if os.path.exists(CONFIG_PATH):
        return

    candidates = []
    if getattr(sys, "frozen", False):
        old_dir = os.path.abspath(
            os.path.join(os.path.dirname(sys.executable), "..", "..", "..")
        )
        candidates.append(os.path.join(old_dir, "config.json"))
    candidates.append(os.path.join(base_dir, "config.json"))

    for old_path in candidates:
        if os.path.exists(old_path):
            shutil.copy2(old_path, CONFIG_PATH)
            print(f"[config] Migrated config from {old_path} → {CONFIG_PATH}")
            break


def load_config() -> dict:
    if not os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2)
        return copy.deepcopy(DEFAULT_CONFIG)
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_config(config: dict) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(keychain_store.strip_secrets(config), f, indent=2)


def migrate_config(config: dict) -> dict:
    """Migrate single-imap config to accounts array."""
    if "imap" in config and "accounts" not in config:
        config["accounts"] = [
            {"id": "default", "name": "Default", "imap": config.pop("imap")}
        ]
        save_config(config)
    if "accounts" not in config:
        config["accounts"] = []
    for account in config.get("accounts", []):
        imap = account.setdefault("imap", {})
        imap.setdefault("fetch_limit", 300)
        imap.setdefault("sync_mode", "recent")
        imap.setdefault("sync_since", "")
        imap.setdefault("auto_sync", False)
        imap.setdefault("sync_interval_minutes", 5)
        imap.setdefault("body_storage", "text_html")
    llm_providers.ensure_llm_config(config)
    prompt_defaults.ensure_prompts(config)
    quick_templates.ensure_quick_templates(config)
    return config


def make_account_id(name: str, existing_ids: list[str]) -> str:
    slug = re.sub(r"[^\w]+", "_", name.lower()).strip("_") or "account"
    candidate = slug
    i = 2
    while candidate in existing_ids:
        candidate = f"{slug}_{i}"
        i += 1
    return candidate
