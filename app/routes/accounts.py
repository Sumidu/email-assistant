import json

from flask import Blueprint, jsonify, request

from app import config_store
from app import runtime as rt
from modules import database
from modules import keychain_store
from modules.imap_fetcher import IMAPFetcher


bp = Blueprint("accounts", __name__, url_prefix="/api")


@bp.route("/accounts", methods=["GET"])
def list_accounts():
    safe = []
    for acct in rt.config.get("accounts", []):
        account = json.loads(json.dumps(acct))
        if account.get("imap", {}).get("password"):
            account["imap"]["password"] = "••••••••"
        if account.get("imap", {}).get("calendar_url"):
            account["imap"]["calendar_url"] = "••••••••"
        safe.append(account)
    return jsonify(safe)


@bp.route("/accounts", methods=["POST"])
def create_account():
    data = request.json
    if not data or "name" not in data:
        return jsonify({"error": "Missing name"}), 400

    existing_ids = [a["id"] for a in rt.config.get("accounts", [])]
    new_id = config_store.make_account_id(data["name"], existing_ids)

    imap_data = data.get(
        "imap",
        {
            "server": "",
            "port": 993,
            "username": "",
            "password": "",
            "inbox_folder": "INBOX",
            "sent_folder": "Sent Items",
            "provider_override": "auto",
            "calendar_enabled": False,
            "calendar_method": "ics",
            "calendar_url": "",
            "ews_url": "",
            "graph_client_id": "",
            "graph_tenant_id": "common",
            "fetch_limit": 300,
            "sync_mode": "recent",
            "sync_since": "",
            "auto_sync": False,
            "sync_interval_minutes": 5,
            "body_storage": "text_html",
        },
    )
    password = imap_data.pop("password", "") or ""
    keychain_store.set_imap_password(new_id, password)

    account = {"id": new_id, "name": data["name"], "imap": imap_data}
    config_store.apply_account_detection(account)
    account["imap"]["password"] = password
    rt.config.setdefault("accounts", []).append(account)
    config_store.apply_account_detection(acct)
    rt.save_config()
    rt.fetchers[new_id] = IMAPFetcher(account)

    safe = json.loads(json.dumps(account))
    safe["imap"]["password"] = "••••••••" if password else ""
    return jsonify({"success": True, "account": safe})


@bp.route("/accounts/<account_id>", methods=["PUT"])
def update_account(account_id):
    data = request.json
    if not data:
        return jsonify({"error": "No data"}), 400

    acct = next((a for a in rt.config.get("accounts", []) if a["id"] == account_id), None)
    if not acct:
        return jsonify({"error": "Account not found"}), 404

    if "name" in data:
        acct["name"] = data["name"]
    if "imap" in data:
        for k, v in data["imap"].items():
            if k == "password":
                if v and v != "••••••••":
                    keychain_store.set_imap_password(account_id, v)
                    acct["imap"]["password"] = v
            elif k == "calendar_url" and v == "••••••••":
                continue
            else:
                acct["imap"][k] = v

    rt.save_config()
    rt.fetchers[account_id] = IMAPFetcher(acct)
    rt.reload_modules()
    return jsonify({"success": True})


@bp.route("/accounts/<account_id>/stats", methods=["GET"])
def account_stats(account_id):
    if not any(a["id"] == account_id for a in rt.config.get("accounts", [])):
        return jsonify({"error": "Account not found"}), 404
    return jsonify(database.get_account_stats(account_id))


@bp.route("/accounts/<account_id>", methods=["DELETE"])
def delete_account(account_id):
    accounts = rt.config.get("accounts", [])
    rt.config["accounts"] = [a for a in accounts if a["id"] != account_id]
    rt.fetchers.pop(account_id, None)
    keychain_store.delete_imap_password(account_id)
    rt.save_config()
    return jsonify({"success": True})
