"""
response_generator.py
Chat-based email assistant using an XML tag protocol to separate
the email draft from conversational responses.

Tag protocol:
  <draft>...</draft>       — the email to put in the draft panel (optional per turn)
  <chat>...</chat>         — conversational reply shown in the chat panel (always)
  <kb_save filename="x">  — save/update a knowledge file (optional)
  </kb_save>
"""

import email.utils
import re

import requests

from .knowledge_builder import KnowledgeBuilder
from . import llm_logger


_ASCII_RULE = (
    "CRITICAL: Use ASCII characters ONLY inside <draft>. No Unicode, no smart quotes, "
    "no en-dashes, no em-dashes, no ellipsis character. "
    "Use straight quotes (\") and hyphens (-) instead of typographic alternatives."
)

_SYSTEM_PROMPT = """\
You are an email assistant helping the user draft and refine email replies.

RESPONSE FORMAT — you MUST always use these XML tags:

<draft>
[The complete email draft. Include ONLY when providing or updating a draft.
Omit this tag entirely if the user is just asking a question.]
</draft>
<chat>
[Your conversational reply — explanations, questions, suggestions, reasoning.
ALWAYS include this tag.]
</chat>

Optionally, to save something to the knowledge base:
<kb_save filename="short_slug">
[Markdown content to save as a knowledge file]
</kb_save>

RULES:
- <chat> is REQUIRED in every response.
- <draft> is optional — only include it when you are setting or changing the email draft.
- Inside <draft>: {ascii_rule}
- Inside <chat>: write naturally, reasoning is welcome.
- Match the user's established tone, greeting, and sign-off exactly.
- Never add placeholders like [Your Name] unless the style guide uses them.
- Keep drafts concise and natural — never sound like a template.

{kb_text}"""


class ResponseGenerator:
    def __init__(self, config: dict):
        self.config = config
        self.lm     = config["lm_studio"]
        self.kb     = KnowledgeBuilder(config)

    # ── LLM calls ────────────────────────────────────────────────────────────

    def _call_messages(self, messages: list, max_tokens: int = 2000) -> str:
        model = self.lm.get("model", "local-model")
        url   = f"{self.lm['base_url']}/v1/chat/completions"
        payload = {
            "model":       model,
            "messages":    messages,
            "max_tokens":  max_tokens,
            "temperature": 0.7,
        }
        headers = {}
        if self.lm.get("api_key"):
            headers["Authorization"] = f"Bearer {self.lm['api_key']}"
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
        return _SYSTEM_PROMPT.format(ascii_rule=_ASCII_RULE, kb_text=kb_text)

    @staticmethod
    def _parse(raw: str) -> dict:
        """Extract draft / chat / kb_save from a tagged response."""
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

        # Fallback: model ignored the format — treat whole response as chat
        if not chat:
            chat = raw.strip()

        return {"draft": draft, "chat": chat, "kb_save": kb_save, "raw": raw}

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
        system    = self._build_system(knowledge)

        email_ctx = f"=== EMAIL BEING REPLIED TO ===\n{self._email_context(email_data)}"
        full_messages = (
            [{"role": "system",    "content": system}]
            + [{"role": "user",    "content": email_ctx}]
            + [{"role": "assistant","content": "<chat>Understood. How can I help?</chat>"}]
            + messages
        )

        try:
            raw    = self._call_messages(full_messages)
            result = self._parse(raw)
            result["knowledge_used"] = [t for t, _ in knowledge]
            llm_logger.log("chat", system, str(messages[-1:]), raw, model=self.lm.get("model",""))
            return result
        except Exception as exc:
            return {
                "draft": None,
                "chat":  f"[Error: {exc}]",
                "kb_save": None,
                "knowledge_used": [],
                "raw": "",
            }
