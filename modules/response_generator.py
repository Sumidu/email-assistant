"""
response_generator.py
Uses LM Studio to propose ASCII-only email responses, grounded in knowledge files.
"""

import email.utils

import requests

from .knowledge_builder import KnowledgeBuilder
from . import llm_logger


_ASCII_RULE = (
    "CRITICAL: Use ASCII characters ONLY. No Unicode, no smart quotes, "
    "no en-dashes, no em-dashes, no ellipsis character, no accented letters. "
    "Use straight quotes (\") and hyphens (-) instead of typographic alternatives."
)


class ResponseGenerator:
    def __init__(self, config: dict):
        self.config  = config
        self.lm      = config["lm_studio"]
        self.kb      = KnowledgeBuilder(config)

    # ---- LLM call ----------------------------------------------------------

    def _call_llm(self, system: str, user: str, max_tokens: int = 1500) -> str:
        model = self.lm.get("model", "local-model")
        url = f"{self.lm['base_url']}/v1/chat/completions"
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            "max_tokens": max_tokens,
            "temperature": 0.7,
        }
        headers = {}
        if self.lm.get("api_key"):
            headers["Authorization"] = f"Bearer {self.lm['api_key']}"
        resp = requests.post(url, json=payload, headers=headers, timeout=180)
        resp.raise_for_status()
        response = resp.json()["choices"][0]["message"]["content"]
        llm_logger.log("response", system, user, response, model=model)
        return response

    # ---- helpers -----------------------------------------------------------

    @staticmethod
    def _sender_email(sender_str: str) -> str:
        addrs = email.utils.getaddresses([sender_str])
        return addrs[0][1].lower() if addrs else sender_str.lower()

    @staticmethod
    def _email_context(data: dict) -> str:
        body = data.get("body_text") or ""
        return (
            f"Subject: {data.get('subject','')}\n"
            f"From: {data.get('sender','')}\n"
            f"Date: {data.get('date','')}\n\n"
            f"{body[:2500]}"
        )

    def _build_system(self, sender_email: str, extra_rules: str = "", knowledge: list = None) -> str:
        if knowledge is None:
            knowledge = self.kb.get_knowledge_for_sender(sender_email)
        kb_text = ""
        for title, content in knowledge:
            kb_text += f"\n\n=== {title} ===\n{content[:2000]}"

        return f"""You are a ghostwriter drafting email responses on behalf of the user.

{_ASCII_RULE}

Rules:
- Output ONLY the email response text — no preamble, no meta-commentary.
- Match the user's established tone, greeting style, and sign-off exactly.
- Be natural and concise. Never sound like a template.
- Do NOT add placeholders like [Your Name] unless the style guide uses them.
{extra_rules}
{kb_text}"""

    # ---- public API --------------------------------------------------------

    def generate_response(self, email_data: dict) -> dict:
        sender = self._sender_email(email_data.get("sender", ""))
        knowledge = self.kb.get_knowledge_for_sender(sender)
        system = self._build_system(sender, knowledge=knowledge)
        user   = (
            f"Draft a reply to this email:\n\n{self._email_context(email_data)}"
        )
        try:
            text = self._call_llm(system, user)
            return {"response": text, "knowledge_used": [t for t, _ in knowledge]}
        except Exception as exc:
            return {"response": f"[Error generating response: {exc}]", "knowledge_used": []}

    def generate_with_instruction(
        self,
        email_data: dict,
        instruction: str,
        current_response: str = "",
    ) -> dict:
        sender = self._sender_email(email_data.get("sender", ""))
        knowledge = self.kb.get_knowledge_for_sender(sender)
        extra  = f"- Instruction to follow precisely: {instruction}"
        system = self._build_system(sender, extra_rules=extra, knowledge=knowledge)

        if current_response.strip():
            user = (
                f"Original email:\n{self._email_context(email_data)}\n\n"
                f"Current draft:\n{current_response}\n\n"
                f"Instruction: {instruction}\n\n"
                f"Apply the instruction and rewrite the response:"
            )
        else:
            user = (
                f"Original email:\n{self._email_context(email_data)}\n\n"
                f"Instruction: {instruction}\n\n"
                f"Write a response that follows this instruction:"
            )

        try:
            text = self._call_llm(system, user)
            return {"response": text, "knowledge_used": [t for t, _ in knowledge]}
        except Exception as exc:
            return {"response": f"[Error: {exc}]", "knowledge_used": []}
