from flask import Blueprint, jsonify, request

from app import runtime as rt
from modules import database
from modules.imap_fetcher import IMAPFetcher


bp = Blueprint("folders", __name__, url_prefix="/api")


@bp.route("/folders")
def folders():
    account_id = request.args.get("account_id") or None
    return jsonify(database.get_folders(account_id=account_id))


@bp.route("/imap_folders", methods=["POST"])
def discover_imap_folders():
    data = request.json or {}
    account_id = data.get("account_id")
    saved_account = next(
        (acct for acct in rt.config.get("accounts", []) if acct.get("id") == account_id),
        None,
    )
    saved_imap = dict(saved_account.get("imap", {})) if saved_account else {}
    imap_data = {
        "server": data.get("server") or saved_imap.get("server", ""),
        "port": int(data.get("port") or saved_imap.get("port", 993)),
        "username": data.get("username") or saved_imap.get("username", ""),
        "password": data.get("password") or saved_imap.get("password", ""),
        "inbox_folder": data.get("inbox_folder") or saved_imap.get("inbox_folder", "INBOX"),
        "sent_folder": data.get("sent_folder") or saved_imap.get("sent_folder", "Sent Items"),
        "spam_folder": data.get("spam_folder") or saved_imap.get("spam_folder", ""),
    }
    if imap_data["password"] == "••••••••":
        imap_data["password"] = saved_imap.get("password", "")

    tmp_account = {
        "id": account_id or "__tmp__",
        "name": saved_account.get("name", "tmp") if saved_account else "tmp",
        "imap": imap_data,
    }
    try:
        folders = IMAPFetcher(tmp_account).list_imap_folders()
        return jsonify({"success": True, "folders": folders})
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
