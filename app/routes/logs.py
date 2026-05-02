import os

from flask import Blueprint, jsonify

from modules.llm_logger import LOG_PATH


bp = Blueprint("logs", __name__, url_prefix="/api")


@bp.route("/llm_log")
def llm_log():
    if not os.path.exists(LOG_PATH):
        return jsonify({"entries": []})
    with open(LOG_PATH, encoding="utf-8") as f:
        raw = f.read()
    entries = [e.strip() for e in raw.split("=" * 80) if e.strip()]
    return jsonify({"entries": list(reversed(entries[-30:]))})
