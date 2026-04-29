"""
knowledge_builder.py
Reads all emails from the DB and uses LM Studio to create markdown knowledge
files per contact and a global writing-style guide.
"""

import email.utils
import json
import os
import re
from datetime import datetime

import requests

from . import database
from . import llm_logger

KNOWLEDGE_DIR = os.path.expanduser("~/email_assistant/knowledge")
PINS_PATH = os.path.join(KNOWLEDGE_DIR, "_pinned.json")


class KnowledgeBuilder:
    def __init__(self, config: dict):
        self.config = config
        self.lm = config["lm_studio"]
        os.makedirs(KNOWLEDGE_DIR, exist_ok=True)

    # ---- LLM call ----------------------------------------------------------

    def _call_llm(self, system: str, user: str, max_tokens: int = 2000) -> str:
        model = self.lm.get("model", "local-model")
        url = f"{self.lm['base_url']}/v1/chat/completions"
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            "max_tokens": max_tokens,
            "temperature": 0.3,
        }
        headers = {}
        if self.lm.get("api_key"):
            headers["Authorization"] = f"Bearer {self.lm['api_key']}"
        resp = requests.post(url, json=payload, headers=headers, timeout=180)
        resp.raise_for_status()
        response = resp.json()["choices"][0]["message"]["content"]
        llm_logger.log("knowledge", system, user, response, model=model)
        return response

    # ---- helpers -----------------------------------------------------------

    @staticmethod
    def _addr(sender_str: str) -> tuple[str, str]:
        """Return (email_addr_lower, display_name)."""
        addrs = email.utils.getaddresses([sender_str])
        if addrs:
            return addrs[0][1].lower(), addrs[0][0]
        return sender_str.lower(), ""

    @staticmethod
    def _safe_filename(addr: str) -> str:
        return re.sub(r"[^\w\-_.]", "_", addr)

    # ---- knowledge builders ------------------------------------------------

    def build_style_knowledge(self, sent_emails: list) -> dict:
        if not sent_emails:
            return {"success": False, "error": "No sent emails found"}

        sample = sent_emails[:60]
        snippets = "\n\n---EMAIL---\n".join(
            f"Subject: {e.get('subject','')}\n{e.get('body_text','')[:500]}"
            for e in sample
        )

        system = (
            "You are an email communication analyst. Analyse the sent emails below and "
            "produce a comprehensive writing-style guide in markdown. "
            "Be specific and detailed — this guide will be used by an AI to ghost-write "
            "replies that sound exactly like the author."
        )
        user = f"""Analyse these sent emails and produce a markdown writing-style guide.

{snippets[:9000]}

Include sections for:
## Overall Communication Style
## Typical Greetings and Openings
## Typical Closings and Sign-offs
## Tone and Formality Level
## Sentence Structure and Length
## Common Phrases and Vocabulary
## Emoji / Punctuation Habits
## Language Patterns to Replicate
"""
        try:
            content = self._call_llm(system, user, max_tokens=2500)
            path = os.path.join(KNOWLEDGE_DIR, "_writing_style.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"# Writing Style Guide\n\n")
                f.write(f"*Generated: {datetime.now():%Y-%m-%d %H:%M}*\n\n")
                f.write(content)
            return {"success": True, "file": path}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def build_contact_knowledge(self, addr: str, data: dict) -> dict:
        emails_from  = data["emails"][:12]
        my_replies   = data["my_replies"][:12]

        from_text = "\n\n---\n".join(
            f"Subject: {e.get('subject','')}\n{e.get('body_text','')[:400]}"
            for e in emails_from
        )
        reply_text = (
            "\n\n---\n".join(
                f"Subject: {e.get('subject','')}\n{e.get('body_text','')[:400]}"
                for e in my_replies
            )
            if my_replies
            else "No replies on record."
        )

        system = (
            "You are an email relationship analyst. Based on the email exchange, "
            "write a concise, factual markdown contact profile. "
            "Be practical — this will be used to personalise AI-generated replies."
        )
        user = f"""Create a contact profile for: {addr}
Display name: {data.get('name','Unknown')}
Emails received: {len(data['emails'])} | Replies sent: {len(data['my_replies'])}

EMAILS FROM THIS PERSON:
{from_text[:3500]}

MY REPLIES TO THEM:
{reply_text[:2000]}

Profile sections:
## Who This Person Is
## Main Topics They Write About
## Their Tone and Communication Style
## How I Typically Respond to Them
## Key Context / Patterns to Remember
"""
        try:
            content = self._call_llm(system, user, max_tokens=1200)
            fname = self._safe_filename(addr) + ".md"
            path  = os.path.join(KNOWLEDGE_DIR, fname)
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"# Contact: {data.get('name', addr)}\n\n")
                f.write(f"**Email:** {addr}  \n")
                f.write(f"**Received:** {len(data['emails'])} | **Replied:** {len(data['my_replies'])}  \n")
                f.write(f"*Generated: {datetime.now():%Y-%m-%d %H:%M}*\n\n")
                f.write(content)
            return {"success": True, "contact": addr, "file": path}
        except Exception as exc:
            return {"success": False, "contact": addr, "error": str(exc)}

    # ---- main entry point --------------------------------------------------

    def build(self, progress_callback=None) -> dict:
        new_emails = database.get_unprocessed_kb_emails()
        if not new_emails:
            return {"success": True, "skipped": True,
                    "message": "No new emails since last build. Knowledge is up to date."}

        all_emails = database.get_all_emails()

        sent_folders = {
            acct["imap"].get("sent_folder", "Sent Items")
            for acct in self.config.get("accounts", [])
        }
        if not sent_folders:
            sent_folders = {"Sent Items", "Sent"}

        new_sent  = [e for e in new_emails if e["folder"] in sent_folders]
        new_inbox = [e for e in new_emails if e["folder"] not in sent_folders]

        all_sent  = [e for e in all_emails if e["folder"] in sent_folders]

        # Track IDs to mark processed after successful build
        processed_ids = [e["id"] for e in new_emails]

        style_result = {"success": True, "skipped": True}
        if new_sent:
            if progress_callback:
                progress_callback(f"Analysing writing style ({len(new_sent)} new sent emails)…")
            style_result = self.build_style_knowledge(all_sent)
        else:
            if progress_callback:
                progress_callback("Writing style up to date — skipping.")

        # Contacts with NEW inbox emails (use ALL their emails for the full profile)
        new_inbox_senders: set = set()
        for e in new_inbox:
            addr, _ = self._addr(e.get("sender", ""))
            if addr and "@" in addr:
                new_inbox_senders.add(addr)

        if not new_inbox_senders and not new_sent:
            database.mark_emails_kb_processed(processed_ids)
            return {"success": True, "style": style_result,
                    "contacts": [], "total_contacts": 0}

        # Build full contact data from ALL emails (so profiles are comprehensive)
        contacts: dict = {}
        for e in [x for x in all_emails if x["folder"] not in sent_folders]:
            addr, name = self._addr(e.get("sender", ""))
            if addr and "@" in addr and addr in new_inbox_senders:
                if addr not in contacts:
                    contacts[addr] = {"name": name, "emails": [], "my_replies": []}
                contacts[addr]["emails"].append(e)

        for e in all_sent:
            recs = e.get("recipients", "[]")
            if isinstance(recs, str):
                recs = json.loads(recs)
            for r in recs:
                a = r.get("email", "").lower()
                if a in contacts:
                    contacts[a]["my_replies"].append(e)

        sorted_contacts = sorted(
            contacts.items(), key=lambda x: len(x[1]["emails"]), reverse=True
        )[:40]

        contact_results = []
        for i, (addr, data) in enumerate(sorted_contacts):
            if progress_callback:
                progress_callback(
                    f"Building profile {i+1}/{len(sorted_contacts)}: {addr}…"
                )
            contact_results.append(self.build_contact_knowledge(addr, data))

        database.mark_emails_kb_processed(processed_ids)

        return {
            "success": True,
            "style": style_result,
            "contacts": contact_results,
            "total_contacts": len(contact_results),
            "new_emails_processed": len(new_emails),
        }

    # ---- pin management ----------------------------------------------------

    def get_pinned(self) -> list[str]:
        if not os.path.exists(PINS_PATH):
            return []
        try:
            with open(PINS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def set_pinned(self, filenames: list[str]) -> dict:
        os.makedirs(KNOWLEDGE_DIR, exist_ok=True)
        with open(PINS_PATH, "w", encoding="utf-8") as f:
            json.dump(filenames, f)
        return {"success": True, "pinned": filenames}

    # ---- retrieval ---------------------------------------------------------

    def get_knowledge_for_sender(self, sender_email: str) -> list[tuple[str, str]]:
        knowledge = []
        loaded_paths: set[str] = set()

        # Always load pinned files first
        for fname in self.get_pinned():
            fpath = os.path.join(KNOWLEDGE_DIR, os.path.basename(fname))
            if os.path.exists(fpath) and fpath not in loaded_paths:
                with open(fpath, "r", encoding="utf-8") as f:
                    knowledge.append((fname.replace(".md", "").replace("_", " ").title(), f.read()))
                loaded_paths.add(fpath)

        # Writing style (unless already pinned)
        style_path = os.path.join(KNOWLEDGE_DIR, "_writing_style.md")
        if os.path.exists(style_path) and style_path not in loaded_paths:
            with open(style_path, "r", encoding="utf-8") as f:
                knowledge.append(("My Writing Style", f.read()))
            loaded_paths.add(style_path)

        # Contact profile
        contact_path = os.path.join(
            KNOWLEDGE_DIR, self._safe_filename(sender_email.lower()) + ".md"
        )
        if os.path.exists(contact_path) and contact_path not in loaded_paths:
            with open(contact_path, "r", encoding="utf-8") as f:
                knowledge.append(("Contact Profile", f.read()))

        return knowledge

    def list_knowledge_files(self) -> list[dict]:
        pinned = set(self.get_pinned())
        result = []
        for fname in sorted(os.listdir(KNOWLEDGE_DIR)):
            if not fname.endswith(".md"):
                continue
            fpath = os.path.join(KNOWLEDGE_DIR, fname)
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
            result.append({"name": fname, "path": fpath, "content": content,
                            "pinned": fname in pinned})
        return result

    def save_knowledge_file(self, filename: str, content: str) -> dict:
        if not filename.endswith(".md"):
            filename += ".md"
        filename = self._safe_filename(filename.replace(".md", "")) + ".md"
        fpath = os.path.join(KNOWLEDGE_DIR, filename)
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(content)
        return {"success": True, "name": filename}

    def delete_knowledge_file(self, filename: str) -> dict:
        fpath = os.path.join(KNOWLEDGE_DIR, os.path.basename(filename))
        if not fpath.endswith(".md") or not os.path.exists(fpath):
            return {"success": False, "error": "File not found"}
        os.remove(fpath)
        return {"success": True}
