"""
main.py  —  Email Assistant (multi-account)
Run with:  python main.py
Then open: http://localhost:5100
"""

import json
import os
import re
import sys
import threading

from flask import Flask, jsonify, render_template, request

# Resolve base dir so templates are found both in dev and when frozen by PyInstaller
_BASE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))

from modules.imap_fetcher       import IMAPFetcher
from modules.knowledge_builder  import KnowledgeBuilder
from modules.response_generator import ResponseGenerator
from modules                    import database
from modules                    import keychain_store

# ── Config ──────────────────────────────────────────────────────────────────

# When frozen, config.json lives next to the .app (not inside it)
if getattr(sys, "frozen", False):
    _CONFIG_DIR = os.path.dirname(sys.executable)  # .app/Contents/MacOS/
    # Go up to sit beside the .app bundle itself
    _CONFIG_DIR = os.path.abspath(os.path.join(_CONFIG_DIR, "..", "..", ".."))
else:
    _CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_PATH = os.path.join(_CONFIG_DIR, "config.json")

DEFAULT_CONFIG = {
    "accounts": [],
    "lm_studio": {"base_url": "http://localhost:1234", "model": "local-model", "api_key": ""},
    "app":       {"port": 5100},
}


def _load_config() -> dict:
    if not os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2)
        return json.loads(json.dumps(DEFAULT_CONFIG))
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def _save_config():
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(keychain_store.strip_secrets(config), f, indent=2)


def _migrate_config(cfg: dict) -> dict:
    """Migrate single-imap config to accounts array."""
    if "imap" in cfg and "accounts" not in cfg:
        cfg["accounts"] = [{"id": "default", "name": "Default", "imap": cfg.pop("imap")}]
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    if "accounts" not in cfg:
        cfg["accounts"] = []
    return cfg


def _make_account_id(name: str, existing_ids: list[str]) -> str:
    slug = re.sub(r"[^\w]+", "_", name.lower()).strip("_") or "account"
    candidate = slug
    i = 2
    while candidate in existing_ids:
        candidate = f"{slug}_{i}"
        i += 1
    return candidate


config = _migrate_config(_load_config())
keychain_store.migrate(config, _save_config)   # move any plaintext secrets → keychain
keychain_store.inject_secrets(config)          # populate in-memory config from keychain

# ── DB init ──────────────────────────────────────────────────────────────────

database.init_db()

# ── Modules ──────────────────────────────────────────────────────────────────

fetchers: dict[str, IMAPFetcher] = {}
kb       = None
resp_gen = None


def _reload_modules():
    global fetchers, kb, resp_gen
    fetchers = {acct["id"]: IMAPFetcher(acct) for acct in config.get("accounts", [])}
    kb       = KnowledgeBuilder(config)
    resp_gen = ResponseGenerator(config)


_reload_modules()

# ── Flask app ────────────────────────────────────────────────────────────────

app = Flask(__name__, template_folder=os.path.join(_BASE_DIR, "templates"))

_task_status: dict = {"running": False, "message": "Idle", "progress": []}


def _bg(fn, *args):
    def runner():
        _task_status["running"]  = True
        _task_status["progress"] = []

        def progress(msg):
            print(f"[BG] {msg}")
            _task_status["message"] = msg
            _task_status["progress"].append(msg)

        try:
            result = fn(*args, progress_callback=progress)
            _task_status["result"]  = result
            _task_status["message"] = "Done"
        except Exception as exc:
            _task_status["result"]  = {"success": False, "error": str(exc)}
            _task_status["message"] = f"Error: {exc}"
        finally:
            _task_status["running"] = False

    threading.Thread(target=runner, daemon=True).start()


def _sync_all(progress_callback=None):
    """Sync every configured account sequentially."""
    combined = {"success": True, "accounts": {}}
    for acct_id, fetcher in fetchers.items():
        result = fetcher.sync(progress_callback=progress_callback)
        combined["accounts"][acct_id] = result
        if not result.get("success"):
            combined["success"] = False
    return combined


# ── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


# --- Accounts ---

@app.route("/api/accounts", methods=["GET"])
def api_accounts_list():
    safe = []
    for acct in config.get("accounts", []):
        a = json.loads(json.dumps(acct))
        if a.get("imap", {}).get("password"):
            a["imap"]["password"] = "••••••••"
        safe.append(a)
    return jsonify(safe)


@app.route("/api/accounts", methods=["POST"])
def api_accounts_create():
    data = request.json
    if not data or "name" not in data:
        return jsonify({"error": "Missing name"}), 400

    existing_ids = [a["id"] for a in config.get("accounts", [])]
    new_id = _make_account_id(data["name"], existing_ids)

    imap_data = data.get("imap", {
        "server": "", "port": 993, "username": "", "password": "",
        "inbox_folder": "INBOX", "sent_folder": "Sent Items", "fetch_limit": 300,
    })
    # Store password in keychain; keep empty string in config
    password = imap_data.pop("password", "") or ""
    keychain_store.set_imap_password(new_id, password)

    account = {"id": new_id, "name": data["name"], "imap": imap_data}
    account["imap"]["password"] = password          # in-memory only
    config.setdefault("accounts", []).append(account)
    _save_config()
    fetchers[new_id] = IMAPFetcher(account)

    safe = json.loads(json.dumps(account))
    safe["imap"]["password"] = "••••••••" if password else ""
    return jsonify({"success": True, "account": safe})


@app.route("/api/accounts/<account_id>", methods=["PUT"])
def api_accounts_update(account_id):
    data = request.json
    if not data:
        return jsonify({"error": "No data"}), 400

    acct = next((a for a in config.get("accounts", []) if a["id"] == account_id), None)
    if not acct:
        return jsonify({"error": "Account not found"}), 404

    if "name" in data:
        acct["name"] = data["name"]
    if "imap" in data:
        for k, v in data["imap"].items():
            if k == "password":
                if v and v != "••••••••":
                    keychain_store.set_imap_password(account_id, v)
                    acct["imap"]["password"] = v   # update in-memory
            else:
                acct["imap"][k] = v

    _save_config()
    fetchers[account_id] = IMAPFetcher(acct)
    _reload_modules()
    return jsonify({"success": True})


@app.route("/api/accounts/<account_id>", methods=["DELETE"])
def api_accounts_delete(account_id):
    accounts = config.get("accounts", [])
    config["accounts"] = [a for a in accounts if a["id"] != account_id]
    fetchers.pop(account_id, None)
    keychain_store.delete_imap_password(account_id)
    _save_config()
    return jsonify({"success": True})


# --- Folders ---

@app.route("/api/folders")
def api_folders():
    account_id = request.args.get("account_id") or None
    return jsonify(database.get_folders(account_id=account_id))


@app.route("/api/imap_folders", methods=["POST"])
def api_imap_discover_folders():
    """Discover IMAP folders using provided credentials (without saving)."""
    data = request.json or {}
    account_id = data.get("account_id")
    if account_id and account_id in fetchers:
        try:
            folders = fetchers[account_id].list_imap_folders()
            return jsonify({"success": True, "folders": folders})
        except Exception as exc:
            return jsonify({"success": False, "error": str(exc)}), 400

    # Temporary connection using supplied credentials
    from modules.imap_fetcher import IMAPFetcher
    tmp_account = {
        "id":   "__tmp__",
        "name": "tmp",
        "imap": {
            "server":       data.get("server", ""),
            "port":         int(data.get("port", 993)),
            "username":     data.get("username", ""),
            "password":     data.get("password", ""),
            "inbox_folder": data.get("inbox_folder", "INBOX"),
            "sent_folder":  data.get("sent_folder", "Sent Items"),
        },
    }
    try:
        folders = IMAPFetcher(tmp_account).list_imap_folders()
        return jsonify({"success": True, "folders": folders})
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 400


# --- Email list / detail ---

@app.route("/api/emails")
def api_emails():
    limit      = int(request.args.get("limit", 60))
    offset     = int(request.args.get("offset", 0))
    account_id = request.args.get("account_id") or None
    folder     = request.args.get("folder") or "INBOX"
    emails     = database.get_emails(folder=folder, limit=limit, offset=offset, account_id=account_id)
    return jsonify(emails)


@app.route("/api/email/<path:email_id>")
def api_email_detail(email_id):
    data = database.get_email_by_id(email_id)
    if not data:
        return jsonify({"error": "Not found"}), 404
    return jsonify(data)


# --- Sync ---

@app.route("/api/sync", methods=["POST"])
def api_sync():
    if _task_status["running"]:
        return jsonify({"error": "A task is already running"}), 409

    body       = request.get_json(silent=True) or {}
    account_id = body.get("account_id")

    if account_id:
        fetcher = fetchers.get(account_id)
        if not fetcher:
            return jsonify({"error": "Account not found"}), 404
        _bg(fetcher.sync)
    else:
        _bg(_sync_all)

    return jsonify({"status": "started"})


# --- Knowledge ---

@app.route("/api/build_knowledge", methods=["POST"])
def api_build_knowledge():
    if _task_status["running"]:
        return jsonify({"error": "A task is already running"}), 409
    _bg(kb.build)
    return jsonify({"status": "started"})


@app.route("/api/knowledge_files")
def api_knowledge_files():
    return jsonify(kb.list_knowledge_files())


@app.route("/api/knowledge_files", methods=["POST"])
def api_knowledge_files_create():
    data = request.json
    if not data or "filename" not in data:
        return jsonify({"error": "Missing filename"}), 400
    result = kb.save_knowledge_file(data["filename"], data.get("content", ""))
    return jsonify(result)


@app.route("/api/knowledge_files/<path:filename>", methods=["PUT"])
def api_knowledge_files_update(filename):
    data = request.json
    if not data or "content" not in data:
        return jsonify({"error": "Missing content"}), 400
    result = kb.save_knowledge_file(filename, data["content"])
    return jsonify(result)


@app.route("/api/knowledge_files/<path:filename>", methods=["DELETE"])
def api_knowledge_files_delete(filename):
    return jsonify(kb.delete_knowledge_file(filename))


@app.route("/api/purge_contacts", methods=["POST"])
def api_purge_contacts():
    """Delete all auto-generated contact knowledge files (non-underscore .md files)."""
    import glob
    from modules.knowledge_builder import KNOWLEDGE_DIR
    deleted = []
    for path in glob.glob(os.path.join(KNOWLEDGE_DIR, "*.md")):
        fname = os.path.basename(path)
        if not fname.startswith("_"):
            os.remove(path)
            deleted.append(fname)
    # Remove purged files from pins
    pinned = kb.get_pinned()
    new_pinned = [p for p in pinned if p.startswith("_") or p not in deleted]
    if len(new_pinned) != len(pinned):
        kb.set_pinned(new_pinned)
    return jsonify({"success": True, "deleted": deleted, "count": len(deleted)})


@app.route("/api/knowledge_pins", methods=["GET"])
def api_knowledge_pins_get():
    return jsonify(kb.get_pinned())


@app.route("/api/knowledge_pins", methods=["POST"])
def api_knowledge_pins_set():
    data = request.json
    if not isinstance(data, list):
        return jsonify({"error": "Expected a list of filenames"}), 400
    return jsonify(kb.set_pinned(data))


@app.route("/api/task_status")
def api_task_status():
    return jsonify(_task_status)


# --- Config (lm_studio / whisper / app sections only) ---

@app.route("/api/config", methods=["GET"])
def api_config_get():
    safe = {k: v for k, v in config.items() if k != "accounts"}
    safe = json.loads(json.dumps(safe))   # deep copy
    if safe.get("lm_studio", {}).get("api_key"):
        safe["lm_studio"]["api_key"] = "••••••••"
    return jsonify(safe)


@app.route("/api/config", methods=["POST"])
def api_config_save():
    data = request.json
    if not data:
        return jsonify({"error": "No data"}), 400
    for section in ("lm_studio", "whisper", "app"):
        if section in data:
            config.setdefault(section, {}).update(data[section])
    # API key lives in keychain; keep in-memory but strip from disk
    api_key = config.get("lm_studio", {}).get("api_key", "")
    if api_key and api_key != "••••••••":
        keychain_store.set_api_key(api_key)
    _save_config()
    _reload_modules()
    return jsonify({"success": True})


# --- Chat / response generation ---

@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.json
    if not data or "email" not in data:
        return jsonify({"error": "Missing email data"}), 400
    result = resp_gen.chat(
        email_data=data["email"],
        messages=data.get("messages", []),
        extra_kb=data.get("extra_kb", []),
    )
    return jsonify(result)



# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = config.get("app", {}).get("port", 5100)
    acct_count = len(config.get("accounts", []))
    print(f"\n Email Assistant — {acct_count} account(s) configured")
    print(f" http://localhost:{port}\n")
    app.run(debug=False, port=port)
