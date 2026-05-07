import json
import re
from datetime import datetime

from flask import Blueprint, jsonify, request
import requests

from app import config_store
from app import llm_providers
from app import paths
from app import prompt_defaults
from app import quick_templates
from app import runtime as rt
from modules import keychain_store


bp = Blueprint("config", __name__, url_prefix="/api")


@bp.route("/config", methods=["GET"])
def get_config():
    prompt_defaults.ensure_prompts(rt.config)
    safe = {k: v for k, v in rt.config.items() if k != "accounts"}
    safe = json.loads(json.dumps(safe))
    if safe.get("lm_studio", {}).get("api_key"):
        safe["lm_studio"]["api_key"] = "••••••••"
    safe["llms"] = [llm_providers.public_provider(p) for p in rt.config.get("llms", [])]
    return jsonify(safe)


@bp.route("/config", methods=["POST"])
def save_config():
    data = request.json
    if not data:
        return jsonify({"error": "No data"}), 400

    if "llms" in data:
        existing = {p["id"]: p for p in rt.config.get("llms", [])}
        incoming = []
        for provider in data.get("llms") or []:
            normalized = llm_providers.normalize_provider(provider)
            api_key = provider.get("api_key", "")
            if api_key == llm_providers.MASK:
                api_key = existing.get(normalized["id"], {}).get("api_key", "")
            normalized["api_key"] = api_key
            incoming.append(normalized)
            if api_key != llm_providers.MASK:
                keychain_store.set_llm_api_key(normalized["id"], api_key)
        rt.config["llms"] = incoming

    if "default_llm_id" in data:
        rt.config["default_llm_id"] = data["default_llm_id"]

    if "prompts" in data:
        prompts = prompt_defaults.prompt_defaults()
        incoming = data.get("prompts") or {}
        for key in prompts:
            if key in incoming:
                prompts[key] = incoming[key]
        rt.config["prompts"] = prompts

    if "quick_templates" in data:
        rt.config["quick_templates"] = quick_templates.normalize_quick_templates(
            data.get("quick_templates")
        )

    for section in ("lm_studio", "whisper", "app"):
        if section in data:
            rt.config.setdefault(section, {}).update(data[section])

    api_key = rt.config.get("lm_studio", {}).get("api_key", "")
    if api_key and api_key != "••••••••":
        keychain_store.set_api_key(api_key)
    llm_providers.ensure_llm_config(rt.config)
    rt.save_config()
    rt.reload_modules()
    return jsonify({"success": True})


@bp.route("/config/portable", methods=["GET"])
def get_portable_config():
    return jsonify(config_store.portable_config(rt.config))


@bp.route("/config/portable/save_icloud", methods=["POST"])
def save_portable_config_to_icloud():
    data = request.json or {}
    envelope = data.get("encrypted_config")
    if not isinstance(envelope, dict):
        return jsonify({"error": "Missing encrypted config"}), 400
    if envelope.get("kind") != "email-assistant-encrypted-portable-config":
        return jsonify({"error": "Unexpected encrypted config format"}), 400

    requested_name = str(data.get("filename") or "").strip()
    if requested_name:
        filename = re.sub(r"[^A-Za-z0-9._-]+", "_", requested_name)
    else:
        stamp = datetime.now().strftime("%Y-%m-%d")
        filename = f"email-assistant-config-{stamp}.encrypted.json"
    if not filename.endswith(".json"):
        filename += ".json"

    paths.ensure_app_dirs()
    target = paths.PORTABLE_CONFIG_DIR / filename
    with open(target, "w", encoding="utf-8") as f:
        json.dump(envelope, f, indent=2)
    return jsonify({
        "success": True,
        "path": str(target),
        "filename": filename,
        "icloud": paths.ICLOUD_DRIVE_DIR.exists(),
    })


@bp.route("/config/portable/import", methods=["POST"])
def import_portable_config():
    data = request.json
    if not data:
        return jsonify({"error": "No config data"}), 400
    try:
        rt.config = config_store.apply_portable_config(rt.config, data)
        rt.save_config()
        rt.reload_modules()
        return jsonify({"success": True})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@bp.route("/prompt_defaults", methods=["GET"])
def get_prompt_defaults():
    return jsonify(prompt_defaults.prompt_defaults())


@bp.route("/quick_template_defaults", methods=["GET"])
def get_quick_template_defaults():
    return jsonify(quick_templates.quick_template_defaults())


@bp.route("/llm/active", methods=["GET"])
def get_active_llm():
    active = llm_providers.get_active_llm(rt.config)
    return jsonify({
        "active_llm_id": active["id"],
        "default_llm_id": rt.config.get("default_llm_id"),
        "llms": [llm_providers.public_provider(p) for p in rt.config.get("llms", [])],
    })


@bp.route("/llm/active", methods=["POST"])
def set_active_llm():
    data = request.json or {}
    llm_id = data.get("active_llm_id")
    ids = [p["id"] for p in rt.config.get("llms", [])]
    if llm_id not in ids:
        return jsonify({"error": "Unknown LLM"}), 400
    rt.config.setdefault("app", {})["active_llm_id"] = llm_id
    rt.save_config()
    rt.reload_modules()
    return jsonify({"success": True, "active_llm_id": llm_id})


@bp.route("/llm/status", methods=["GET"])
def llm_status():
    only_id = request.args.get("id") or ""
    statuses = []
    providers = [
        provider for provider in rt.config.get("llms", [])
        if not only_id or provider.get("id") == only_id
    ]
    if only_id and not providers:
        return jsonify({"error": "Unknown LLM"}), 404
    for provider in providers:
        url = provider.get("base_url", "").rstrip("/") + "/v1/models"
        headers = {}
        if provider.get("api_key"):
            headers["Authorization"] = f"Bearer {provider['api_key']}"
        try:
            resp = requests.get(url, headers=headers, timeout=4)
            ok = 200 <= resp.status_code < 400
            statuses.append({
                "id": provider["id"],
                "ok": ok,
                "status": resp.status_code,
                "error": "" if ok else resp.text[:120],
            })
        except Exception as exc:
            statuses.append({
                "id": provider["id"],
                "ok": False,
                "status": None,
                "error": str(exc),
            })
    return jsonify({"llms": statuses})
