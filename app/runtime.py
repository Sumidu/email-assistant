from modules import database, keychain_store
from modules.imap_fetcher import IMAPFetcher
from modules.knowledge_builder import KnowledgeBuilder
from modules.response_generator import ResponseGenerator

from app import config_store


config: dict = {}
fetchers: dict[str, IMAPFetcher] = {}
kb: KnowledgeBuilder | None = None
resp_gen: ResponseGenerator | None = None


def init(base_dir: str) -> None:
    global config
    config_store.migrate_config_location(base_dir)
    config = config_store.migrate_config(config_store.load_config())
    keychain_store.migrate(config, save_config)
    keychain_store.inject_secrets(config)
    database.init_db()
    reload_modules()


def save_config() -> None:
    config_store.save_config(config)


def reload_modules() -> None:
    global fetchers, kb, resp_gen
    fetchers = {acct["id"]: IMAPFetcher(acct) for acct in config.get("accounts", [])}
    kb = KnowledgeBuilder(config)
    resp_gen = ResponseGenerator(config)


def sync_all(progress_callback=None) -> dict:
    combined = {"success": True, "accounts": {}}
    for acct_id, fetcher in fetchers.items():
        result = fetcher.sync(progress_callback=progress_callback)
        combined["accounts"][acct_id] = result
        if not result.get("success"):
            combined["success"] = False
    return combined
