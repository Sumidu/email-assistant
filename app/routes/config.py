import json

from flask import Blueprint, jsonify, request
import requests

from app import llm_providers
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
    statuses = []
    for provider in rt.config.get("llms", []):
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
