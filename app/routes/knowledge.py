import glob
import os

from flask import Blueprint, jsonify, request

from app import runtime as rt
from app.task_runner import run_background, task_status
from modules import database
from modules import knowledge_builder


bp = Blueprint("knowledge", __name__, url_prefix="/api")


@bp.route("/build_knowledge", methods=["POST"])
def build_knowledge():
    if task_status["running"]:
        return jsonify({"error": "A task is already running"}), 409
    run_background(rt.kb.build)
    return jsonify({"status": "started"})


@bp.route("/knowledge_stats")
def knowledge_stats():
    return jsonify({
        "total_messages": database.get_email_count(),
        "new_messages": len(database.get_unprocessed_kb_emails()),
    })


@bp.route("/email/<path:email_id>/build_contact_knowledge", methods=["POST"])
def build_contact_knowledge(email_id):
    if task_status["running"]:
        return jsonify({"error": "A task is already running"}), 409
    email_row = database.get_email_by_id(email_id)
    if not email_row:
        return jsonify({"error": "Email not found"}), 404
    contact = rt.kb.contact_for_email(email_row)
    if not contact:
        return jsonify({"error": "Could not infer a contact for this email"}), 400
    run_background(rt.kb.build_contact_for_email, email_id)
    return jsonify({"status": "started", "contact": contact})


@bp.route("/knowledge_files")
def knowledge_files():
    return jsonify(rt.kb.list_knowledge_files())


@bp.route("/knowledge_files", methods=["POST"])
def create_knowledge_file():
    data = request.json
    if not data or "filename" not in data:
        return jsonify({"error": "Missing filename"}), 400
    result = rt.kb.save_knowledge_file(
        data["filename"],
        data.get("content", ""),
        source=data.get("source", "manual"),
        match_patterns=data.get("match_patterns"),
        aliases=data.get("aliases"),
    )
    return jsonify(result)


@bp.route("/knowledge_files/<path:filename>", methods=["PUT"])
def update_knowledge_file(filename):
    data = request.json
    if not data or "content" not in data:
        return jsonify({"error": "Missing content"}), 400
    target_name = data.get("filename")
    if target_name and target_name != filename:
        rename_result = rt.kb.rename_knowledge_file(filename, target_name)
        if not rename_result.get("success"):
            return jsonify(rename_result), 400
        filename = rename_result["name"]
    result = rt.kb.save_knowledge_file(
        filename,
        data["content"],
        source=data.get("source", "manual"),
        match_patterns=data.get("match_patterns"),
        aliases=data.get("aliases"),
    )
    return jsonify(result)


@bp.route("/knowledge_files/merge", methods=["POST"])
def merge_knowledge_files():
    data = request.json or {}
    result = rt.kb.merge_knowledge_files(data.get("target", ""), data.get("source", ""))
    status = 200 if result.get("success") else 400
    return jsonify(result), status


@bp.route("/knowledge_files/<path:filename>", methods=["DELETE"])
def delete_knowledge_file(filename):
    return jsonify(rt.kb.delete_knowledge_file(filename))


@bp.route("/knowledge_files/by_llm/<path:llm_id>", methods=["DELETE"])
def delete_knowledge_by_llm(llm_id):
    return jsonify(rt.kb.delete_knowledge_by_llm(llm_id))


@bp.route("/purge_contacts", methods=["POST"])
def purge_contacts():
    deleted = []
    for path in glob.glob(os.path.join(knowledge_builder.KNOWLEDGE_DIR, "*.md")):
        fname = os.path.basename(path)
        if not fname.startswith("_"):
            rt.kb.delete_knowledge_file(fname)
            deleted.append(fname)

    pinned = rt.kb.get_pinned()
    new_pinned = [p for p in pinned if p.startswith("_") or p not in deleted]
    if len(new_pinned) != len(pinned):
        rt.kb.set_pinned(new_pinned)

    return jsonify({"success": True, "deleted": deleted, "count": len(deleted)})


@bp.route("/knowledge_pins", methods=["GET"])
def get_knowledge_pins():
    return jsonify(rt.kb.get_pinned())


@bp.route("/knowledge_pins", methods=["POST"])
def set_knowledge_pins():
    data = request.json
    if not isinstance(data, list):
        return jsonify({"error": "Expected a list of filenames"}), 400
    return jsonify(rt.kb.set_pinned(data))
