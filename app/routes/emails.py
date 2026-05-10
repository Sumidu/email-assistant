from flask import Blueprint, jsonify, request

from app import runtime as rt
from modules import database


bp = Blueprint("emails", __name__, url_prefix="/api")


def _sent_folders_for(account_id=None):
    folders = set()
    for account in rt.config.get("accounts", []):
        if account_id and account.get("id") != account_id:
            continue
        imap = account.get("imap", {})
        if imap.get("sent_folder"):
            folders.add(imap["sent_folder"])
        for folder in imap.get("sync_folders", []):
            if folder.get("role") == "sent" and folder.get("name"):
                folders.add(folder["name"])
    return sorted(folders)


@bp.route("/emails")
def emails():
    limit = int(request.args.get("limit", 60))
    offset = int(request.args.get("offset", 0))
    account_id = request.args.get("account_id") or None
    folder = request.args.get("folder") or "INBOX"
    search = request.args.get("q") or ""
    importance = request.args.get("importance") or ""
    status = request.args.get("status") or ""
    rows = database.get_email_threads(
        folder=folder,
        limit=limit,
        offset=offset,
        account_id=account_id,
        search=search,
        importance=importance,
        status=status,
        sent_folders=_sent_folders_for(account_id),
    )
    if rt.kb:
        for row in rows:
            row["knowledge_matches"] = rt.kb.exact_sender_knowledge_matches_for_email(row)
    return jsonify(rows)


@bp.route("/email/<path:email_id>")
def email_detail(email_id):
    data = database.get_email_by_id(email_id)
    if not data:
        return jsonify({"error": "Not found"}), 404
    return jsonify(data)


@bp.route("/thread/<path:thread_id>")
def thread_detail(thread_id):
    account_id = request.args.get("account_id") or None
    if not account_id:
        email_id = request.args.get("email_id") or ""
        row = database.get_email_by_id(email_id) if email_id else None
        account_id = row.get("account_id") if row else None
    if not account_id:
        return jsonify({"error": "Missing account_id"}), 400
    rows = database.get_thread_emails(account_id, thread_id)
    if not rows:
        return jsonify({"error": "Thread not found"}), 404
    return jsonify({"thread_id": thread_id, "account_id": account_id, "emails": rows})


@bp.route("/email/<path:email_id>/done", methods=["POST"])
def mark_email_done(email_id):
    result = database.mark_email_done(email_id)
    status = 200 if result.get("success") else 404
    return jsonify(result), status


@bp.route("/email/<path:email_id>/done", methods=["DELETE"])
def unmark_email_done(email_id):
    result = database.unmark_email_done(email_id)
    status = 200 if result.get("success") else 404
    return jsonify(result), status


@bp.route("/emails/bulk_done", methods=["POST"])
def bulk_mark_emails_done():
    data = request.get_json(silent=True) or {}
    folder = data.get("folder") or "INBOX"
    account_id = data.get("account_id") or None
    search = data.get("q") or ""
    importance = data.get("importance") or ""
    status_filter = data.get("status") or ""
    if data.get("dry_run"):
        return jsonify({
            "success": True,
            "count": database.count_emails_for_finish(folder, account_id=account_id, search=search, importance=importance, status=status_filter),
        })
    return jsonify(database.mark_filtered_emails_done(folder, account_id=account_id, search=search, importance=importance, status=status_filter))


@bp.route("/email/<path:email_id>/spam", methods=["POST"])
def mark_email_spam(email_id):
    data = database.get_email_by_id(email_id)
    if not data:
        return jsonify({"success": False, "error": "Email not found"}), 404
    fetcher = rt.fetchers.get(data.get("account_id"))
    if not fetcher:
        return jsonify({"success": False, "error": "Account not found"}), 404
    result = fetcher.move_email_to_spam(email_id)
    status = 200 if result.get("success") else 400
    return jsonify(result), status


@bp.route("/stats/today")
def today_stats():
    return jsonify(database.get_processed_today_count())


@bp.route("/stats/history")
def completion_history():
    from flask import request as req
    days = min(max(int(req.args.get("days", 30)), 7), 90)
    return jsonify(database.get_completion_history(days))
