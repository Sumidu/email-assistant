from flask import Blueprint, jsonify, request

from app import runtime as rt
from app.task_runner import clear_activity_log, get_activity_log, get_task_status as task_status_snapshot, run_background


bp = Blueprint("tasks", __name__, url_prefix="/api")


@bp.route("/sync", methods=["POST"])
def sync():
    body = request.get_json(silent=True) or {}
    account_id = body.get("account_id")
    full_resync = bool(body.get("full_resync"))

    if account_id:
        fetcher = rt.fetchers.get(account_id)
        if not fetcher:
            return jsonify({"error": "Account not found"}), 404
        started = run_background(fetcher.sync, full_resync)
    else:
        started = run_background(rt.sync_all, full_resync)

    if not started:
        return jsonify({"error": "A task is already running"}), 409
    return jsonify({"status": "started"})


@bp.route("/task_status")
def get_task_status():
    return jsonify(task_status_snapshot())


@bp.route("/activity_log")
def activity_log():
    return jsonify(get_activity_log())


@bp.route("/activity_log/clear", methods=["POST"])
def clear_log():
    clear_activity_log()
    return jsonify({"success": True})
