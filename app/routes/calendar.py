from datetime import datetime, timedelta

from flask import Blueprint, jsonify, request

from app import runtime as rt
from app import task_runner
from modules import calendar_store
from modules import database


bp = Blueprint("calendar", __name__, url_prefix="/api")


def _calendar_accounts():
    result = []
    for account in rt.config.get("accounts", []):
        imap = account.get("imap", {})
        provider = imap.get("detected_provider", {})
        provider_id = provider.get("id")
        if provider_id in ("outlook", "google") or imap.get("calendar_enabled"):
            result.append({
                "id": account["id"],
                "name": account.get("name", account["id"]),
                "provider": provider,
                "calendar_enabled": bool(imap.get("calendar_enabled")),
                "calendar_url_configured": bool(imap.get("calendar_url")),
            })
    return result


@bp.route("/calendar/accounts")
def calendar_accounts():
    return jsonify(_calendar_accounts())


@bp.route("/calendar/events")
def calendar_events():
    now = datetime.now().astimezone()
    start = request.args.get("start")
    end = request.args.get("end")
    account_id = request.args.get("account_id") or None
    try:
        start_dt = datetime.fromisoformat(start) if start else now - timedelta(days=14)
        end_dt = datetime.fromisoformat(end) if end else now + timedelta(days=45)
    except ValueError:
        return jsonify({"error": "Invalid start or end date"}), 400
    return jsonify(database.get_calendar_events(
        account_id=account_id,
        start_ts=start_dt.timestamp(),
        end_ts=end_dt.timestamp(),
        limit=800,
    ))


@bp.route("/calendar/sync", methods=["POST"])
def sync_calendar():
    body = request.json or {}
    account_id = body.get("account_id")
    if not task_runner.run_background(calendar_store.sync_enabled_calendars, rt.config, account_id):
        return jsonify({"error": "Task already running"}), 409
    return jsonify({"started": True})


@bp.route("/calendar/exchange_probe", methods=["POST"])
def exchange_probe():
    body = request.json or {}
    account_id = body.get("account_id")
    account = next((a for a in rt.config.get("accounts", []) if a["id"] == account_id), None)
    if not account:
        return jsonify({"error": "Account not found"}), 404
    return jsonify(calendar_store.probe_exchange(account))


@bp.route("/calendar/ews_test", methods=["POST"])
def ews_test():
    body = request.json or {}
    account_id = body.get("account_id")
    account = next((a for a in rt.config.get("accounts", []) if a["id"] == account_id), None)
    if not account:
        return jsonify({"error": "Account not found"}), 404
    return jsonify(calendar_store.test_ews_calendar(account))


@bp.route("/calendar/ews_ntlm_test", methods=["POST"])
def ews_ntlm_test():
    body = request.json or {}
    account_id = body.get("account_id")
    account = next((a for a in rt.config.get("accounts", []) if a["id"] == account_id), None)
    if not account:
        return jsonify({"error": "Account not found"}), 404
    result = calendar_store.test_ews_calendar_ntlm(account)
    if result.get("success"):
        imap = account.setdefault("imap", {})
        imap["calendar_enabled"] = True
        imap["calendar_method"] = "ews_ntlm"
        imap["ews_url"] = result.get("url", "")
        rt.save_config()
        rt.reload_modules()
    return jsonify(result)


@bp.route("/calendar/graph_device_code", methods=["POST"])
def graph_device_code():
    body = request.json or {}
    client_id = (body.get("client_id") or "").strip()
    if not client_id:
        return jsonify({"success": False, "error": "Microsoft Graph Client ID is required."}), 400
    tenant_id = (body.get("tenant_id") or "common").strip()
    return jsonify(calendar_store.start_graph_device_code(client_id, tenant_id))


@bp.route("/calendar/graph_poll", methods=["POST"])
def graph_poll():
    body = request.json or {}
    client_id = (body.get("client_id") or "").strip()
    device_code = (body.get("device_code") or "").strip()
    if not client_id or not device_code:
        return jsonify({"success": False, "error": "Client ID and device code are required."}), 400
    tenant_id = (body.get("tenant_id") or "common").strip()
    return jsonify(calendar_store.poll_graph_device_code(client_id, device_code, tenant_id))
