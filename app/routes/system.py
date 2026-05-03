import webbrowser
from urllib.parse import urlparse

from flask import Blueprint, jsonify, request


bp = Blueprint("system", __name__, url_prefix="/api")


@bp.route("/open_external", methods=["POST"])
def open_external():
    url = (request.get_json(silent=True) or {}).get("url", "").strip()
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return jsonify({"success": False, "error": "Only http and https links can be opened."}), 400
    webbrowser.open_new_tab(url)
    return jsonify({"success": True})
