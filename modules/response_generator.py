"""
response_generator.py
Chat-based email assistant using an XML tag protocol to separate
the email draft from conversational responses.

Tag protocol:
  <draft>...</draft>         — the email to put in the draft panel (optional per turn)
  <chat>...</chat>           — conversational reply shown in the chat panel (always)
  <kb_save filename="x">    — save/update a knowledge file (optional)
  </kb_save>
  <kb_list/>                 — query: list all KB files (app replies, LLM continues)
  <kb_read filename="x.md"/> — query: read a specific KB file (app replies, LLM continues)
"""

import email.utils
import re

import requests

from app import llm_providers
from app import prompt_defaults

from .knowledge_builder import KnowledgeBuilder, KNOWLEDGE_DIR
from . import llm_logger

import os


_MAX_KB_HOPS = 3  # max KB query round-trips per turn


class ResponseGenerator:
    def __init__(self, config: dict):
        self.config = config
        self.kb     = KnowledgeBuilder(config)

    # ── LLM calls ────────────────────────────────────────────────────────────

    def _call_messages(self, messages: list, max_tokens: int = 2000) -> str:
        lm = llm_providers.get_active_llm(self.config)
        model = lm.get("model", "local-model")
        url   = f"{lm['base_url']}/v1/chat/completions"
        payload = {
            "model":       model,
            "messages":    messages,
            "max_tokens":  max_tokens,
            "temperature": 0.7,
        }
        headers = {}
        if lm.get("api_key"):
            headers["Authorization"] = f"Bearer {lm['api_key']}"
        resp = requests.post(url, json=payload, headers=headers, timeout=180)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _sender_email(sender_str: str) -> str:
        addrs = email.utils.getaddresses([sender_str])
        return addrs[0][1].lower() if addrs else sender_str.lower()

    @staticmethod
    def _email_context(data: dict) -> str:
        body = data.get("body_text") or ""
        return (
            f"Subject: {data.get('subject', '')}\n"
            f"From: {data.get('sender', '')}\n"
            f"Date: {data.get('date', '')}\n\n"
            f"{body[:2500]}"
        )

    def _build_system(self, knowledge: list) -> str:
        kb_text = ""
        for title, content in knowledge:
            kb_text += f"\n\n=== {title} ===\n{content[:2000]}"
        prompts = prompt_defaults.ensure_prompts(self.config)
        return prompt_defaults.render_prompt(
            prompts["response_system"],
            {"kb_text": kb_text},
        )

    @staticmethod
    def _parse(raw: str) -> dict:
        """Extract draft / chat / kb_save / kb_query from a tagged response."""
        def _tag(name, text):
            m = re.search(rf"<{name}[^>]*>(.*?)</{name}>", text, re.DOTALL)
            return m.group(1).strip() if m else None

        draft  = _tag("draft", raw)
        chat   = _tag("chat",  raw)
        kb_m   = re.search(
            r'<kb_save\s+filename=["\']?([^"\'>\s]+)["\']?>(.*?)</kb_save>',
            raw, re.DOTALL
        )
        kb_save = {"filename": kb_m.group(1), "content": kb_m.group(2).strip()} if kb_m else None

        # KB query tags (self-closing)
        kb_query = None
        if re.search(r'<kb_list\s*/?>', raw):
            kb_query = {"action": "list"}
        else:
            m = re.search(r'<kb_read\s+filename=["\']?([^"\'>\s/]+)["\']?\s*/?>', raw)
            if m:
                kb_query = {"action": "read", "filename": m.group(1)}

        # Fallback: model ignored the format — treat whole response as chat
        if not chat and not kb_query:
            chat = raw.strip()

        return {"draft": draft, "chat": chat, "kb_save": kb_save,
                "kb_query": kb_query, "raw": raw}

    def _fulfill_kb_query(self, query: dict) -> str:
        """Execute a KB query and return the result as a string to inject."""
        if query["action"] == "list":
            try:
                files = sorted(os.listdir(KNOWLEDGE_DIR))
                md_files = [f for f in files if f.endswith(".md")]
                if not md_files:
                    return "<kb_result>Knowledge base is empty.</kb_result>"
                listing = "\n".join(md_files)
                return f"<kb_result>\n{listing}\n</kb_result>"
            except Exception as exc:
                return f"<kb_result>Error listing KB: {exc}</kb_result>"

        if query["action"] == "read":
            content = self.kb.load_knowledge_file(query["filename"])
            if content is None:
                return f"<kb_result>File not found: {query['filename']}</kb_result>"
            return f"<kb_result filename=\"{query['filename']}\">\n{content}\n</kb_result>"

        return "<kb_result>Unknown query.</kb_result>"

    # ── Public API ────────────────────────────────────────────────────────────

    def chat(self, email_data: dict, messages: list, kb_files=None) -> dict:
        """
        Multi-turn chat. `messages` is the full conversation history
        [{role: "user"|"assistant", content: "..."}].
        `kb_files` is the explicit list of KB filenames to load (chosen by frontend).
        Returns {draft, chat, kb_save, knowledge_used}.
        """
        knowledge = []
        seen = set()
        for filename in (kb_files or []):
            content = self.kb.load_knowledge_file(filename)
            if content is not None and filename not in seen:
                label = filename.replace(".md", "").replace("_", " ").title()
                knowledge.append((label, content))
                seen.add(filename)
        system = self._build_system(knowledge)

        email_ctx = f"=== EMAIL BEING REPLIED TO ===\n{self._email_context(email_data)}"
        full_messages = (
            [{"role": "system",    "content": system}]
            + [{"role": "user",    "content": email_ctx}]
            + [{"role": "assistant","content": "<chat>Understood. How can I help?</chat>"}]
            + messages
        )

        try:
            result = None
            for hop in range(_MAX_KB_HOPS + 1):
                raw    = self._call_messages(full_messages)
                result = self._parse(raw)
                llm_logger.log("chat", system, str(full_messages[-1:]), raw,
                               model=llm_providers.get_active_llm(self.config).get("model", ""))

                if not result["kb_query"] or hop == _MAX_KB_HOPS:
                    break

                # Fulfill the KB query and continue the conversation
                kb_result = self._fulfill_kb_query(result["kb_query"])
                full_messages.append({"role": "assistant", "content": raw})
                full_messages.append({"role": "user",      "content": kb_result})

            result["knowledge_used"] = [t for t, _ in knowledge]
            return result

        except Exception as exc:
            return {
                "draft": None,
                "chat":  f"[Error: {exc}]",
                "kb_save": None,
                "kb_query": None,
                "knowledge_used": [],
                "raw": "",
            }
