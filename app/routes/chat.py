import email.utils

from flask import Blueprint, jsonify, request

from app import runtime as rt


bp = Blueprint("chat", __name__, url_prefix="/api")


@bp.route("/chat", methods=["POST"])
def chat():
    data = request.json
    if not data or "email" not in data:
        return jsonify({"error": "Missing email data"}), 400
    result = rt.resp_gen.chat(
        email_data=data["email"],
        messages=data.get("messages", []),
        kb_files=data.get("kb_files", []),
        thread_emails=data.get("thread_emails", []),
    )
    return jsonify(result)


@bp.route("/suggested_context", methods=["POST"])
def suggested_context():
    data = request.json or {}
    sender = data.get("sender", "")
    recipients = data.get("recipients", [])

    def _addr(s):
        addrs = email.utils.getaddresses([s])
        return addrs[0][1].lower() if addrs else s.lower()

    sender_addr = _addr(sender)
    recipient_addrs = [
        _addr(r.get("email", r) if isinstance(r, dict) else r) for r in recipients
    ]
    files = rt.kb.suggested_context(sender_addr, recipient_addrs)
    return jsonify(files)
