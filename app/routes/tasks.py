from flask import Blueprint, jsonify, request

from app import runtime as rt
from app.task_runner import run_background, task_status


bp = Blueprint("tasks", __name__, url_prefix="/api")


@bp.route("/sync", methods=["POST"])
def sync():
    if task_status["running"]:
        return jsonify({"error": "A task is already running"}), 409

    body = request.get_json(silent=True) or {}
    account_id = body.get("account_id")
    full_resync = bool(body.get("full_resync"))

    if account_id:
        fetcher = rt.fetchers.get(account_id)
        if not fetcher:
            return jsonify({"error": "Account not found"}), 404
        run_background(fetcher.sync, full_resync)
    else:
        run_background(rt.sync_all, full_resync)

    return jsonify({"status": "started"})


@bp.route("/task_status")
def get_task_status():
    return jsonify(task_status)
