"""
keychain_store.py
Stores secrets (IMAP passwords, API keys) in the macOS Keychain via the
`keyring` library. Secrets are never written to config.json.

Versioning: KEYCHAIN_VERSION is incremented whenever new fields are moved
into the keychain. migrate() runs each version step in order and updates
config["keychain_version"] so a fresh install skips old steps.
"""

import copy
import keyring
from keyring.errors import KeyringError

from app.llm_providers import MASK

SERVICE          = "com.emailassistant.app"
KEYCHAIN_VERSION = 1   # bump this when adding new secret fields


# ── Low-level helpers ────────────────────────────────────────────────────────

def _set(key: str, value: str):
    keyring.set_password(SERVICE, key, value or "")

def _describe_key(key: str) -> str:
    if key.startswith("account."):
        return "IMAP password"
    if key.startswith("llm.") or key == "lm_studio.api_key":
        return "LLM API key"
    return "secret"

def _get(key: str) -> str:
    try:
        return keyring.get_password(SERVICE, key) or ""
    except KeyringError as exc:
        print(f"[Keychain] Could not read {_describe_key(key)}: {exc}")
        return ""

def _delete(key: str):
    try:
        keyring.delete_password(SERVICE, key)
    except Exception:
        pass


# ── Named accessors ──────────────────────────────────────────────────────────

def _imap_key(account_id: str) -> str:
    return f"account.{account_id}.imap_password"

def get_imap_password(account_id: str) -> str:
    return _get(_imap_key(account_id))

def set_imap_password(account_id: str, password: str):
    _set(_imap_key(account_id), password)

def delete_imap_password(account_id: str):
    _delete(_imap_key(account_id))

def get_api_key() -> str:
    return _get("lm_studio.api_key")

def set_api_key(api_key: str):
    _set("lm_studio.api_key", api_key)

def _llm_api_key_key(llm_id: str) -> str:
    return f"llm.{llm_id}.api_key"

def get_llm_api_key(llm_id: str) -> str:
    return _get(_llm_api_key_key(llm_id))

def set_llm_api_key(llm_id: str, api_key: str):
    _set(_llm_api_key_key(llm_id), api_key)


# ── Migration ────────────────────────────────────────────────────────────────

def migrate(config: dict, save_fn) -> None:
    """
    Run any pending keychain migrations. Each version block is idempotent.
    After all steps, keychain_version in config is updated and saved.
    """
    current = config.get("keychain_version", 0)
    if current >= KEYCHAIN_VERSION:
        return

    # v0 → v1: move IMAP passwords and LM Studio API key into keychain
    if current < 1:
        for acct in config.get("accounts", []):
            pwd = acct.get("imap", {}).get("password", "")
            if pwd and pwd != "••••••••":
                set_imap_password(acct["id"], pwd)
        api_key = config.get("lm_studio", {}).get("api_key", "")
        if api_key and api_key != "••••••••":
            set_api_key(api_key)
        for provider in config.get("llms", []):
            api_key = provider.get("api_key", "")
            if api_key and api_key != MASK:
                set_llm_api_key(provider["id"], api_key)

    # Future migrations go here:
    # if current < 2:
    #     ...

    config["keychain_version"] = KEYCHAIN_VERSION
    save_fn()
    print(f"[Keychain] Migrated to version {KEYCHAIN_VERSION}")


# ── Runtime secret injection ─────────────────────────────────────────────────

def inject_secrets(config: dict) -> None:
    """
    Populate the in-memory config with secrets from the keychain.
    This is called once at startup AFTER migration. The populated values
    are used at runtime but must never be written back to disk.
    """
    for acct in config.get("accounts", []):
        acct.setdefault("imap", {})["password"] = get_imap_password(acct["id"])
    legacy_api_key = get_api_key()
    config.setdefault("lm_studio", {})["api_key"] = legacy_api_key
    for provider in config.get("llms", []):
        provider["api_key"] = get_llm_api_key(provider["id"]) or legacy_api_key


# ── Safe serialisation ───────────────────────────────────────────────────────

def strip_secrets(config: dict) -> dict:
    """
    Return a deep copy of config with all secrets removed.
    Use this whenever writing config to disk.
    """
    safe = copy.deepcopy(config)
    for acct in safe.get("accounts", []):
        acct.get("imap", {}).pop("password", None)
        acct["imap"]["password"] = ""
    safe.get("lm_studio", {}).pop("api_key", None)
    safe.setdefault("lm_studio", {})["api_key"] = ""
    for provider in safe.get("llms", []):
        provider.pop("api_key", None)
        provider["api_key"] = ""
    return safe
