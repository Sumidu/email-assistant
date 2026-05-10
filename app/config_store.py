import copy
import json
import os
import re
import shutil
import sys

from modules import keychain_store
from app import llm_providers
from app import paths
from app import prompt_defaults
from app import quick_templates


DATA_DIR = str(paths.APP_SUPPORT_DIR)
CONFIG_PATH = str(paths.CONFIG_PATH)

DEFAULT_CONFIG = {
    "accounts": [],
    "lm_studio": {
        "base_url": "http://localhost:1234",
        "model": "local-model",
        "api_key": "",
    },
    "llms": [llm_providers.default_provider()],
    "default_llm_id": "lm_studio",
    "app": {"port": 5100, "active_llm_id": "lm_studio", "theme_mode": "system", "thread_order": "newest_first"},
    "prompts": prompt_defaults.prompt_defaults(),
    "quick_templates": quick_templates.quick_template_defaults(),
}

PORTABLE_CONFIG_VERSION = 1
PORTABLE_ACCOUNT_IMAP_KEYS = {
    "server",
    "port",
    "username",
    "inbox_folder",
    "sent_folder",
    "spam_folder",
    "provider_override",
    "calendar_enabled",
    "calendar_method",
    "ews_url",
    "graph_client_id",
    "graph_tenant_id",
    "fetch_limit",
    "sync_mode",
    "sync_since",
    "auto_sync",
    "sync_interval_minutes",
    "body_storage",
    "sync_folders",
}
PORTABLE_LLM_KEYS = {"id", "name", "base_url", "model"}


def detect_imap_provider(imap: dict) -> dict:
    """Return a conservative provider guess from IMAP host and login identity."""
    override = str(imap.get("provider_override") or "auto").strip().lower()
    manual = {
        "outlook": ("Microsoft / Exchange / Outlook", "Use Microsoft Graph or Exchange EWS for future calendar integration."),
        "google": ("Google / Gmail", "Use Google Calendar for future calendar integration."),
        "generic": ("Generic IMAP", "No calendar provider selected."),
    }
    if override in manual:
        name, reason = manual[override]
        return {"id": override, "name": name, "confidence": "manual", "reason": reason}

    server = str(imap.get("server") or "").strip().lower()
    username = str(imap.get("username") or "").strip().lower()
    domain = username.split("@", 1)[1] if "@" in username else ""
    haystack = " ".join([server, domain])

    outlook_hosts = (
        "outlook.office365.com",
        "imap-mail.outlook.com",
        "imap.outlook.com",
        "office365.com",
        "outlook.com",
        "hotmail.com",
        "live.com",
        "msn.com",
    )
    if any(token in haystack for token in outlook_hosts):
        confidence = "high" if "outlook.office365.com" in server or "outlook.com" in domain else "medium"
        reason = "IMAP host or login domain matches Microsoft Outlook / Microsoft 365."
        return {"id": "outlook", "name": "Microsoft / Exchange / Outlook", "confidence": confidence, "reason": reason}

    if "gmail.com" in haystack or "googlemail.com" in haystack:
        return {"id": "google", "name": "Google / Gmail", "confidence": "high", "reason": "IMAP host or login domain matches Google Mail."}

    if "icloud.com" in haystack or "me.com" in domain or "mac.com" in domain:
        return {"id": "icloud", "name": "Apple iCloud", "confidence": "high", "reason": "IMAP host or login domain matches Apple iCloud Mail."}

    return {"id": "generic", "name": "Generic IMAP", "confidence": "low", "reason": "No known provider pattern matched."}


def apply_account_detection(account: dict) -> dict:
    imap = account.setdefault("imap", {})
    imap["detected_provider"] = detect_imap_provider(imap)
    return account


def migrate_config_location(base_dir: str) -> None:
    """Move config.json from old locations into Application Support."""
    paths.ensure_app_dirs()
    for item in paths.migrate_legacy_data():
        print(f"[storage] Migrated {item['label']} from {item['from']} → {item['to']}")
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


def portable_config(config: dict) -> dict:
    """Return a sync/import friendly config snapshot with secrets removed."""
    accounts = []
    for account in config.get("accounts", []):
        imap = account.get("imap", {})
        safe_imap = {
            key: copy.deepcopy(imap[key])
            for key in PORTABLE_ACCOUNT_IMAP_KEYS
            if key in imap
        }
        accounts.append({
            "id": account.get("id", ""),
            "name": account.get("name", ""),
            "imap": safe_imap,
        })

    llms = []
    for provider in config.get("llms", []):
        llms.append({
            key: copy.deepcopy(provider[key])
            for key in PORTABLE_LLM_KEYS
            if key in provider
        })

    app_config = {
        "port": config.get("app", {}).get("port", 5100),
        "active_llm_id": config.get("app", {}).get("active_llm_id", config.get("default_llm_id", "")),
        "theme_mode": config.get("app", {}).get("theme_mode", "system"),
        "thread_order": config.get("app", {}).get("thread_order", "newest_first"),
    }
    return {
        "kind": "email-assistant-portable-config",
        "version": PORTABLE_CONFIG_VERSION,
        "accounts": accounts,
        "llms": llms,
        "default_llm_id": config.get("default_llm_id", ""),
        "app": app_config,
        "prompts": copy.deepcopy(config.get("prompts", {})),
        "quick_templates": copy.deepcopy(config.get("quick_templates", [])),
    }


def apply_portable_config(current: dict, incoming: dict) -> dict:
    if incoming.get("kind") != "email-assistant-portable-config":
        raise ValueError("Not an Email Assistant portable config.")

    imported = copy.deepcopy(current)

    existing_accounts = {a.get("id"): a for a in current.get("accounts", [])}
    accounts = []
    for account in incoming.get("accounts", []) or []:
        account_id = str(account.get("id") or make_account_id(account.get("name") or "account", [a.get("id") for a in accounts]))
        old_imap = existing_accounts.get(account_id, {}).get("imap", {})
        safe_imap = {
            key: copy.deepcopy(account.get("imap", {}).get(key))
            for key in PORTABLE_ACCOUNT_IMAP_KEYS
            if key in account.get("imap", {})
        }
        if old_imap.get("password"):
            safe_imap["password"] = old_imap["password"]
        if old_imap.get("calendar_url"):
            safe_imap["calendar_url"] = old_imap["calendar_url"]
        accounts.append({
            "id": account_id,
            "name": account.get("name") or account_id,
            "imap": safe_imap,
        })
    imported["accounts"] = accounts

    existing_llms = {p.get("id"): p for p in current.get("llms", [])}
    llms = []
    for provider in incoming.get("llms", []) or []:
        safe_provider = {
            key: copy.deepcopy(provider.get(key))
            for key in PORTABLE_LLM_KEYS
            if key in provider
        }
        provider_id = safe_provider.get("id")
        if provider_id and existing_llms.get(provider_id, {}).get("api_key"):
            safe_provider["api_key"] = existing_llms[provider_id]["api_key"]
        llms.append(safe_provider)
    if llms:
        imported["llms"] = llms

    if "default_llm_id" in incoming:
        imported["default_llm_id"] = incoming.get("default_llm_id") or ""
    if "app" in incoming:
        app_config = imported.setdefault("app", {})
        for key in ("port", "active_llm_id", "theme_mode", "thread_order"):
            if key in incoming["app"]:
                app_config[key] = incoming["app"][key]
    if "prompts" in incoming:
        imported["prompts"] = incoming.get("prompts") or {}
    if "quick_templates" in incoming:
        imported["quick_templates"] = incoming.get("quick_templates") or []

    return migrate_config(imported)


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
        imap.setdefault("provider_override", "auto")
        imap.setdefault("calendar_enabled", False)
        imap.setdefault("calendar_method", "ics")
        imap.setdefault("calendar_url", "")
        imap.setdefault("ews_url", "")
        imap.setdefault("graph_client_id", "")
        imap.setdefault("graph_tenant_id", "common")
        imap.setdefault("inbox_folder", "INBOX")
        imap.setdefault("sent_folder", "Sent Items")
        imap.setdefault("spam_folder", "")
        imap.setdefault("fetch_limit", 300)
        imap.setdefault("sync_mode", "recent")
        imap.setdefault("sync_since", "")
        imap.setdefault("auto_sync", False)
        imap.setdefault("sync_interval_minutes", 5)
        imap.setdefault("body_storage", "text_html")
        apply_account_detection(account)
    llm_providers.ensure_llm_config(config)
    prompt_defaults.ensure_prompts(config)
    quick_templates.ensure_quick_templates(config)
    app = config.setdefault("app", {})
    theme_mode = str(app.get("theme_mode") or "system").lower()
    app["theme_mode"] = theme_mode if theme_mode in {"system", "light", "dark"} else "system"
    thread_order = str(app.get("thread_order") or "newest_first").lower()
    app["thread_order"] = thread_order if thread_order in {"newest_first", "oldest_first"} else "newest_first"
    return config


def make_account_id(name: str, existing_ids: list[str]) -> str:
    slug = re.sub(r"[^\w]+", "_", name.lower()).strip("_") or "account"
    candidate = slug
    i = 2
    while candidate in existing_ids:
        candidate = f"{slug}_{i}"
        i += 1
    return candidate
