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
    if account_id and account_id in rt.fetchers:
        try:
            folders = rt.fetchers[account_id].list_imap_folders()
            return jsonify({"success": True, "folders": folders})
        except Exception as exc:
            return jsonify({"success": False, "error": str(exc)}), 400

    tmp_account = {
        "id": "__tmp__",
        "name": "tmp",
        "imap": {
            "server": data.get("server", ""),
            "port": int(data.get("port", 993)),
            "username": data.get("username", ""),
            "password": data.get("password", ""),
            "inbox_folder": data.get("inbox_folder", "INBOX"),
            "sent_folder": data.get("sent_folder", "Sent Items"),
        },
    }
    try:
        folders = IMAPFetcher(tmp_account).list_imap_folders()
        return jsonify({"success": True, "folders": folders})
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
