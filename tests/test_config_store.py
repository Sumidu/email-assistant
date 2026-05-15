from app import config_store


def test_detect_imap_provider_prefers_manual_override():
    result = config_store.detect_imap_provider({
        "provider_override": "outlook",
        "server": "imap.gmail.com",
        "username": "person@gmail.com",
    })

    assert result["id"] == "outlook"
    assert result["confidence"] == "manual"


def test_apply_portable_config_preserves_existing_secrets():
    current = {
        "accounts": [{
            "id": "work",
            "name": "Work",
            "imap": {"password": "secret", "calendar_url": "https://private.example/calendar.ics"},
        }],
        "llms": [{"id": "local", "name": "Local", "base_url": "http://old", "model": "old", "api_key": "sk-secret"}],
        "default_llm_id": "local",
        "app": {},
    }
    incoming = {
        "kind": "email-assistant-portable-config",
        "version": 1,
        "accounts": [{"id": "work", "name": "Work Imported", "imap": {"server": "outlook.office365.com"}}],
        "llms": [{"id": "local", "name": "Local Imported", "base_url": "http://new", "model": "new"}],
        "default_llm_id": "local",
    }

    result = config_store.apply_portable_config(current, incoming)

    assert result["accounts"][0]["imap"]["password"] == "secret"
    assert result["accounts"][0]["imap"]["calendar_url"] == "https://private.example/calendar.ics"
    assert result["llms"][0]["api_key"] == "sk-secret"
    assert result["accounts"][0]["imap"]["detected_provider"]["id"] == "outlook"
