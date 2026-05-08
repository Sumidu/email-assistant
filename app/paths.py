import os
import shutil
from pathlib import Path


APP_NAME = "Email Assistant"

HOME = Path.home()
LEGACY_DIR = HOME / "email_assistant"

APP_SUPPORT_DIR = HOME / "Library" / "Application Support" / APP_NAME
LOG_DIR = HOME / "Library" / "Logs" / APP_NAME
CACHE_DIR = HOME / "Library" / "Caches" / APP_NAME

ICLOUD_DRIVE_DIR = HOME / "Library" / "Mobile Documents" / "com~apple~CloudDocs"
CLOUD_APP_DIR = ICLOUD_DRIVE_DIR / APP_NAME
PORTABLE_CONFIG_DIR = (
    CLOUD_APP_DIR / "Config"
    if ICLOUD_DRIVE_DIR.exists()
    else APP_SUPPORT_DIR / "Portable Config"
)
DEFAULT_KNOWLEDGE_DIR = (
    CLOUD_APP_DIR / "Knowledge"
    if ICLOUD_DRIVE_DIR.exists()
    else APP_SUPPORT_DIR / "Knowledge"
)
FALLBACK_KNOWLEDGE_DIRS = [
    CLOUD_APP_DIR / "Knowledge",
    APP_SUPPORT_DIR / "Knowledge",
    LEGACY_DIR / "knowledge",
]

CONFIG_PATH = APP_SUPPORT_DIR / "config.json"
DB_PATH = APP_SUPPORT_DIR / "emails.db"
LLM_LOG_PATH = LOG_DIR / "llm_requests.log"


def _has_markdown_files(path: Path) -> bool:
    if not path.is_dir():
        return False
    try:
        return any(item.is_file() and item.suffix.lower() == ".md" for item in path.iterdir())
    except OSError:
        return False


def resolve_knowledge_dir() -> Path:
    """Prefer the standard KB path, unless it is empty and an older path is not."""
    if _has_markdown_files(DEFAULT_KNOWLEDGE_DIR):
        return DEFAULT_KNOWLEDGE_DIR
    for path in FALLBACK_KNOWLEDGE_DIRS:
        if path == DEFAULT_KNOWLEDGE_DIR:
            continue
        if _has_markdown_files(path):
            return path
    return DEFAULT_KNOWLEDGE_DIR


KNOWLEDGE_DIR = resolve_knowledge_dir()


def ensure_app_dirs() -> None:
    for path in (APP_SUPPORT_DIR, LOG_DIR, CACHE_DIR, KNOWLEDGE_DIR, PORTABLE_CONFIG_DIR):
        path.mkdir(parents=True, exist_ok=True)


def _copy_file_if_missing(src: Path, dst: Path, label: str, migrated: list[dict]) -> None:
    if not src.exists() or dst.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    migrated.append({"label": label, "from": str(src), "to": str(dst)})


def _merge_dir_if_present(src: Path, dst: Path, label: str, migrated: list[dict]) -> None:
    if not src.exists() or not src.is_dir():
        return
    dst.mkdir(parents=True, exist_ok=True)
    copied = 0
    for item in src.iterdir():
        target = dst / item.name
        if target.exists():
            continue
        if item.is_dir():
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)
        copied += 1
    if copied:
        migrated.append({"label": label, "from": str(src), "to": str(dst), "copied": copied})


def migrate_legacy_data() -> list[dict]:
    """Copy legacy ~/email_assistant data into macOS-standard locations.

    The old directory is intentionally kept as a backup. We copy only when the
    destination is missing, so a newer migrated install is not overwritten by
    stale legacy files.
    """
    ensure_app_dirs()
    migrated: list[dict] = []
    if not LEGACY_DIR.exists():
        return migrated

    _copy_file_if_missing(LEGACY_DIR / "config.json", CONFIG_PATH, "config", migrated)
    _copy_file_if_missing(LEGACY_DIR / "emails.db", DB_PATH, "mail database", migrated)
    _copy_file_if_missing(LEGACY_DIR / "llm_requests.log", LLM_LOG_PATH, "LLM log", migrated)
    _merge_dir_if_present(LEGACY_DIR / "knowledge", KNOWLEDGE_DIR, "knowledge base", migrated)
    return migrated
