from flask import Blueprint, jsonify
from app.updater import get_state, download_and_install, trigger_check
from app.task_runner import run_background, task_status

bp = Blueprint("update", __name__)


@bp.route("/api/update_status", methods=["GET"])
def update_status():
    return jsonify(get_state())


@bp.route("/api/update/install", methods=["POST"])
def update_install():
    if task_status.get("running"):
        return jsonify({"error": "A task is already running"}), 409
    state = get_state()
    if not state.get("available"):
        return jsonify({"error": "No update available"}), 400
    dmg_url = state.get("dmg_url")
    if not dmg_url:
        return jsonify({"error": "No download URL"}), 400

    def do_install(progress_callback=None):
        download_and_install(dmg_url, progress_cb=progress_callback)

    run_background(do_install)
    return jsonify({"started": True})


@bp.route("/api/update/check", methods=["POST"])
def update_check():
    return jsonify(trigger_check())