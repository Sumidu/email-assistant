"""
knowledge_builder.py
Reads all emails from the DB and uses LM Studio to create markdown knowledge
files per contact and a global writing-style guide.
"""

import email.utils
import fnmatch
import json
import os
import re
from datetime import datetime

import requests

from app import llm_providers
from app import prompt_defaults

from . import database
from . import llm_logger

KNOWLEDGE_DIR = os.path.expanduser("~/email_assistant/knowledge")
PINS_PATH = os.path.join(KNOWLEDGE_DIR, "_pinned.json")
METADATA_PATH = os.path.join(KNOWLEDGE_DIR, "_metadata.json")


class KnowledgeBuilder:
    def __init__(self, config: dict):
        self.config = config
        self._last_llm = None
        os.makedirs(KNOWLEDGE_DIR, exist_ok=True)

    # ---- LLM call ----------------------------------------------------------

    def _call_llm(self, system: str, user: str, max_tokens: int = 2000) -> str:
        lm = llm_providers.get_active_llm(self.config)
        self._last_llm = {
            "id": lm.get("id", ""),
            "name": lm.get("name", ""),
            "model": lm.get("model", ""),
            "base_url": lm.get("base_url", ""),
        }
        model = lm.get("model", "local-model")
        url = f"{lm['base_url']}/v1/chat/completions"
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
        if lm.get("api_key"):
            headers["Authorization"] = f"Bearer {lm['api_key']}"
        resp = requests.post(url, json=payload, headers=headers, timeout=180)
        resp.raise_for_status()
        response = resp.json()["choices"][0]["message"]["content"]
        llm_logger.log("knowledge", system, user, response, model=model)
        return response

    def _current_llm_metadata(self, source: str) -> dict:
        lm = self._last_llm or llm_providers.get_active_llm(self.config)
        return {
            "source": source,
            "llm_id": lm.get("id", ""),
            "llm_name": lm.get("name", ""),
            "model": lm.get("model", ""),
            "base_url": lm.get("base_url", ""),
            "generated_at": datetime.now().isoformat(),
        }

    def _load_metadata(self) -> dict:
        if not os.path.exists(METADATA_PATH):
            return {}
        try:
            with open(METADATA_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_metadata(self, metadata: dict) -> None:
        os.makedirs(KNOWLEDGE_DIR, exist_ok=True)
        with open(METADATA_PATH, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, sort_keys=True)

    def _set_file_metadata(self, filename: str, source: str) -> None:
        metadata = self._load_metadata()
        metadata[filename] = self._current_llm_metadata(source)
        self._save_metadata(metadata)

    @staticmethod
    def _normalize_match_patterns(patterns) -> list[str]:
        if isinstance(patterns, str):
            patterns = re.split(r"[\n,]+", patterns)
        result = []
        for pattern in patterns or []:
            pattern = str(pattern or "").strip().lower()
            if pattern and pattern not in result:
                result.append(pattern)
        return result

    @staticmethod
    def _normalize_aliases(aliases) -> list[str]:
        if isinstance(aliases, str):
            aliases = re.split(r"[\n,]+", aliases)
        result = []
        for alias in aliases or []:
            alias = str(alias or "").strip().lower()
            if alias and "@" in alias and alias not in result:
                result.append(alias)
        return result

    @staticmethod
    def _pattern_matches_address(pattern: str, addr: str) -> bool:
        addr = (addr or "").lower()
        pattern = (pattern or "").lower()
        if not addr or "@" not in addr or not pattern:
            return False
        domain = addr.split("@", 1)[1]
        if "@" in pattern:
            return fnmatch.fnmatch(addr, pattern)
        return fnmatch.fnmatch(domain, pattern.lstrip("@"))

    def _pattern_files_for_address(self, addr: str) -> list[str]:
        metadata = self._load_metadata()
        matches = []
        for fname, meta in metadata.items():
            if not fname.endswith(".md"):
                continue
            patterns = self._normalize_match_patterns(meta.get("match_patterns", []))
            if any(self._pattern_matches_address(pattern, addr) for pattern in patterns):
                if os.path.exists(os.path.join(KNOWLEDGE_DIR, os.path.basename(fname))):
                    matches.append(os.path.basename(fname))
        return matches

    def _alias_files_for_address(self, addr: str) -> list[str]:
        addr = (addr or "").lower()
        metadata = self._load_metadata()
        matches = []
        for fname, meta in metadata.items():
            aliases = self._normalize_aliases(meta.get("aliases", []))
            if addr in aliases and os.path.exists(os.path.join(KNOWLEDGE_DIR, os.path.basename(fname))):
                matches.append(os.path.basename(fname))
        return matches

    def _metadata_files_for_address(self, addr: str) -> list[tuple[str, str]]:
        result = []
        seen = set()
        for fname in self._alias_files_for_address(addr):
            if fname not in seen:
                result.append((fname, "alias"))
                seen.add(fname)
        for fname in self._pattern_files_for_address(addr):
            if fname not in seen:
                result.append((fname, "wildcard"))
                seen.add(fname)
        return result

    def _remove_file_metadata(self, filename: str) -> None:
        metadata = self._load_metadata()
        if filename in metadata:
            metadata.pop(filename, None)
            self._save_metadata(metadata)

    @staticmethod
    def _metadata_template(source: str = "manual") -> dict:
        return {
            "source": source,
            "llm_id": "",
            "llm_name": "",
            "model": "",
            "base_url": "",
            "generated_at": datetime.now().isoformat(),
        }

    @staticmethod
    def _unique_values(*values) -> list[str]:
        result = []
        for group in values:
            for value in group or []:
                value = str(value or "").strip().lower()
                if value and value not in result:
                    result.append(value)
        return result

    @staticmethod
    def _infer_alias_from_filename(filename: str) -> str:
        stem = os.path.basename(filename).replace(".md", "").lower()
        if "@" in stem:
            return stem
        if "_" not in stem:
            return ""
        local, domain = stem.rsplit("_", 1)
        if "." not in domain:
            return ""
        return f"{local}@{domain}"

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

    def _sent_folders(self) -> set[str]:
        folders = {"Sent Items", "Sent"}
        for acct in self.config.get("accounts", []):
            imap = acct.get("imap", {})
            if imap.get("sent_folder"):
                folders.add(imap["sent_folder"])
            for folder in imap.get("sync_folders", []):
                if folder.get("role") == "sent" and folder.get("name"):
                    folders.add(folder["name"])
        return folders

    def _recipient_addresses(self, recipients) -> list[str]:
        if isinstance(recipients, str):
            try:
                recipients = json.loads(recipients)
            except Exception:
                recipients = []
        result = []
        for recipient in recipients or []:
            if isinstance(recipient, dict):
                addr = recipient.get("email", "")
            else:
                _, addr = self._addr(str(recipient))
            addr = (addr or "").lower()
            if addr and "@" in addr:
                result.append(addr)
        return result

    def contact_filename(self, addr: str) -> str:
        return self._safe_filename((addr or "").lower()) + ".md"

    def contact_knowledge_exists(self, addr: str) -> bool:
        if not addr or "@" not in addr:
            return False
        return os.path.exists(os.path.join(KNOWLEDGE_DIR, self.contact_filename(addr)))

    def contact_for_email(self, email_row: dict) -> dict:
        if not email_row:
            return {}
        sent = email_row.get("folder") in self._sent_folders()
        if sent:
            recipients = self._recipient_addresses(email_row.get("recipients", []))
            addr = recipients[0] if recipients else ""
            name = addr
        else:
            addr, name = self._addr(email_row.get("sender", ""))
        if not addr or "@" not in addr:
            return {}
        return {"email": addr.lower(), "name": name or addr}

    def knowledge_matches_for_email(self, email_row: dict) -> list[dict]:
        candidates = []
        sender_addr, sender_name = self._addr(email_row.get("sender", ""))
        if sender_addr and "@" in sender_addr:
            candidates.append({"email": sender_addr, "name": sender_name or sender_addr})
        for addr in self._recipient_addresses(email_row.get("recipients", [])):
            candidates.append({"email": addr, "name": addr})

        seen = set()
        matches = []
        for candidate in candidates:
            addr = candidate["email"].lower()
            if addr in seen:
                continue
            if self.contact_knowledge_exists(addr):
                seen.add(addr)
                matches.append({
                    "email": addr,
                    "name": candidate.get("name") or addr,
                    "file": self.contact_filename(addr),
                })
            for fname, match_type in self._metadata_files_for_address(addr):
                key = f"{addr}:{fname}"
                if key in seen:
                    continue
                seen.add(key)
                matches.append({
                    "email": addr,
                    "name": candidate.get("name") or addr,
                    "file": fname,
                    "match": match_type,
                })
        return matches

    def exact_sender_knowledge_matches_for_email(self, email_row: dict) -> list[dict]:
        sender_addr, sender_name = self._addr((email_row or {}).get("sender", ""))
        sender_addr = (sender_addr or "").lower()
        if not sender_addr or "@" not in sender_addr:
            return []
        if not self.contact_knowledge_exists(sender_addr):
            return []
        return [{
            "email": sender_addr,
            "name": sender_name or sender_addr,
            "file": self.contact_filename(sender_addr),
            "match": "sender",
        }]

    @staticmethod
    def _clean_generated_markdown(content: str) -> str:
        content = content or ""
        fence_re = re.compile(r"```(?:markdown|md)\s*\n([\s\S]*?)```", re.IGNORECASE)
        fences = list(fence_re.finditer(content))
        if len(fences) > 1:
            headings = []
            for match in fences:
                heading = re.search(r"^\s{0,3}#{1,6}\s+(.+)$", match.group(1), flags=re.MULTILINE)
                if heading:
                    headings.append(heading.group(1).strip().lower())
            if len(headings) == len(fences) and all(h == headings[0] for h in headings):
                first = fences[0]
                last = fences[-1]
                content = content[:first.start()] + first.group(1).strip() + "\n" + content[last.end():]
                return content.strip()
        return fence_re.sub(lambda m: m.group(1).strip() + "\n", content).strip()

    # ---- knowledge builders ------------------------------------------------

    def build_style_knowledge(self, sent_emails: list) -> dict:
        if not sent_emails:
            return {"success": False, "error": "No sent emails found"}

        sample = sent_emails[:60]
        snippets = "\n\n---EMAIL---\n".join(
            f"Subject: {e.get('subject','')}\n{e.get('body_text','')[:500]}"
            for e in sample
        )

        prompts = prompt_defaults.ensure_prompts(self.config)
        system = prompts["knowledge_style_system"]
        user = prompt_defaults.render_prompt(
            prompts["knowledge_style_user"],
            {"snippets": snippets[:9000]},
        )
        try:
            content = self._clean_generated_markdown(self._call_llm(system, user, max_tokens=2500))
            path = os.path.join(KNOWLEDGE_DIR, "_writing_style.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"# Writing Style Guide\n\n")
                f.write(f"*Generated: {datetime.now():%Y-%m-%d %H:%M}*\n\n")
                f.write(content)
            self._set_file_metadata("_writing_style.md", "writing_style")
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

        prompts = prompt_defaults.ensure_prompts(self.config)
        system = prompts["knowledge_contact_system"]
        user = prompt_defaults.render_prompt(
            prompts["knowledge_contact_user"],
            {
                "addr": addr,
                "display_name": data.get("name", "Unknown"),
                "received_count": len(data["emails"]),
                "replied_count": len(data["my_replies"]),
                "from_text": from_text[:3500],
                "reply_text": reply_text[:2000],
            },
        )
        try:
            content = self._clean_generated_markdown(self._call_llm(system, user, max_tokens=1200))
            fname = self._safe_filename(addr) + ".md"
            path  = os.path.join(KNOWLEDGE_DIR, fname)
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"# Contact: {data.get('name', addr)}\n\n")
                f.write(f"**Email:** {addr}  \n")
                f.write(f"**Received:** {len(data['emails'])} | **Replied:** {len(data['my_replies'])}  \n")
                f.write(f"*Generated: {datetime.now():%Y-%m-%d %H:%M}*\n\n")
                f.write(content)
            self._set_file_metadata(fname, "contact_profile")
            return {"success": True, "contact": addr, "file": path}
        except Exception as exc:
            return {"success": False, "contact": addr, "error": str(exc)}

    def build_contact_for_email(self, email_id: str, progress_callback=None) -> dict:
        selected = database.get_email_by_id(email_id)
        contact = self.contact_for_email(selected)
        if not contact:
            return {"success": False, "error": "Could not infer a contact for this email"}

        addr = contact["email"]
        all_emails = database.get_all_emails()
        sent_folders = self._sent_folders()
        data = {"name": contact.get("name", addr), "emails": [], "my_replies": []}

        for email_row in all_emails:
            sender_addr, sender_name = self._addr(email_row.get("sender", ""))
            if sender_addr == addr:
                data["emails"].append(email_row)
                if sender_name and data["name"] == addr:
                    data["name"] = sender_name
            if email_row.get("folder") in sent_folders and addr in self._recipient_addresses(email_row.get("recipients", [])):
                data["my_replies"].append(email_row)

        if progress_callback:
            progress_callback(f"Building knowledge for {addr} from {len(data['emails'])} received and {len(data['my_replies'])} sent emails...")
        if not data["emails"] and not data["my_replies"]:
            return {"success": False, "contact": addr, "error": "No emails found for this contact"}
        return self.build_contact_knowledge(addr, data)

    # ---- main entry point --------------------------------------------------

    def build(self, progress_callback=None) -> dict:
        new_emails = database.get_unprocessed_kb_emails()
        if not new_emails:
            return {"success": True, "skipped": True,
                    "message": "No new emails since last build. Knowledge is up to date."}

        all_emails = database.get_all_emails()

        sent_folders = self._sent_folders()

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
        )

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
            loaded_paths.add(contact_path)

        for fname, match_type in self._metadata_files_for_address(sender_email):
            fpath = os.path.join(KNOWLEDGE_DIR, fname)
            if os.path.exists(fpath) and fpath not in loaded_paths:
                with open(fpath, "r", encoding="utf-8") as f:
                    label = fname.replace(".md", "").replace("_", " ").title()
                    prefix = "Alias" if match_type == "alias" else "Wildcard"
                    knowledge.append((f"{prefix}: {label}", f.read()))
                loaded_paths.add(fpath)

        return knowledge

    def get_knowledge_for_email(self, sender_email: str, subject: str = "", body: str = "") -> list[tuple[str, str]]:
        """Like get_knowledge_for_sender but also injects KB files for other
        people mentioned in the email (matched by name appearing in filename
        or the first 400 chars of a contact file)."""
        knowledge = self.get_knowledge_for_sender(sender_email)
        loaded_paths = {os.path.join(KNOWLEDGE_DIR, f) for f in os.listdir(KNOWLEDGE_DIR)
                        if os.path.join(KNOWLEDGE_DIR, f) in
                        {os.path.join(KNOWLEDGE_DIR, self._safe_filename(sender_email.lower()) + ".md"),
                         os.path.join(KNOWLEDGE_DIR, "_writing_style.md")}}
        # build set of loaded paths from what get_knowledge_for_sender returned
        loaded_paths = set()
        for fname in self.get_pinned():
            loaded_paths.add(os.path.join(KNOWLEDGE_DIR, os.path.basename(fname)))
        loaded_paths.add(os.path.join(KNOWLEDGE_DIR, "_writing_style.md"))
        loaded_paths.add(os.path.join(KNOWLEDGE_DIR, self._safe_filename(sender_email.lower()) + ".md"))
        for fname, _ in self._metadata_files_for_address(sender_email):
            loaded_paths.add(os.path.join(KNOWLEDGE_DIR, fname))

        # Extract candidate names: capitalised words 3+ chars from subject + first 1500 chars of body
        text = f"{subject} {body[:1500]}"
        candidates = set(re.findall(r'\b[A-Z][a-zA-Z]{2,}\b', text))
        # Remove common non-name words
        stopwords = {"The","This","That","From","Dear","Kind","Best","With","Your","Please","Thank","Also","Have","Will"}
        candidates -= stopwords

        if not candidates:
            return knowledge

        for fname in sorted(os.listdir(KNOWLEDGE_DIR)):
            if not fname.endswith(".md") or fname.startswith("_"):
                continue
            fpath = os.path.join(KNOWLEDGE_DIR, fname)
            if fpath in loaded_paths:
                continue
            fname_lower = fname.lower()
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    content = f.read()
                head = content[:400].lower()
                for name in candidates:
                    if name.lower() in fname_lower or name.lower() in head:
                        label = fname.replace(".md", "").replace("_", " ").title()
                        knowledge.append((f"Related: {label}", content))
                        loaded_paths.add(fpath)
                        break
            except Exception:
                pass

        return knowledge

    def list_knowledge_files(self) -> list[dict]:
        pinned = set(self.get_pinned())
        metadata = self._load_metadata()
        result = []
        for fname in sorted(os.listdir(KNOWLEDGE_DIR)):
            if not fname.endswith(".md"):
                continue
            fpath = os.path.join(KNOWLEDGE_DIR, fname)
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
            result.append({"name": fname, "path": fpath, "content": content,
                            "pinned": fname in pinned,
                            "metadata": metadata.get(fname, {})})
        return result

    def suggested_context(self, sender_email: str, recipient_emails=None) -> list:
        """Return filenames that should be pre-selected for an email:
        pinned files + _writing_style + sender contact + recipient contacts."""
        suggested = []
        seen = set()

        def _add(fname):
            if fname not in seen and os.path.exists(os.path.join(KNOWLEDGE_DIR, fname)):
                suggested.append(fname)
                seen.add(fname)

        for fname in self.get_pinned():
            _add(os.path.basename(fname))
        _add("_writing_style.md")
        _add(self._safe_filename(sender_email.lower()) + ".md")
        for fname, _ in self._metadata_files_for_address(sender_email):
            _add(fname)
        for addr in (recipient_emails or []):
            _add(self._safe_filename(addr.lower()) + ".md")
            for fname, _ in self._metadata_files_for_address(addr):
                _add(fname)
        return suggested

    def load_knowledge_file(self, filename: str):
        fpath = os.path.join(KNOWLEDGE_DIR, os.path.basename(filename))
        if not fpath.endswith(".md") or not os.path.exists(fpath):
            return None
        with open(fpath, "r", encoding="utf-8") as f:
            return f.read()

    def save_knowledge_file(self, filename: str, content: str, source: str = "manual", match_patterns=None, aliases=None) -> dict:
        if not filename.endswith(".md"):
            filename += ".md"
        filename = self._safe_filename(filename.replace(".md", "")) + ".md"
        fpath = os.path.join(KNOWLEDGE_DIR, filename)
        existed = os.path.exists(fpath)
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(content)
        metadata = self._load_metadata()
        if source != "manual":
            metadata[filename] = self._current_llm_metadata(source)
        elif not existed:
            metadata.setdefault(filename, self._metadata_template("manual"))
        if match_patterns is not None:
            metadata.setdefault(filename, self._metadata_template("manual"))
            metadata[filename]["match_patterns"] = self._normalize_match_patterns(match_patterns)
        if aliases is not None:
            metadata.setdefault(filename, self._metadata_template("manual"))
            metadata[filename]["aliases"] = self._normalize_aliases(aliases)
        self._save_metadata(metadata)
        return {"success": True, "name": filename}

    def rename_knowledge_file(self, filename: str, new_filename: str) -> dict:
        old_name = os.path.basename(filename)
        if not new_filename.endswith(".md"):
            new_filename += ".md"
        new_name = self._safe_filename(new_filename.replace(".md", "")) + ".md"
        if old_name == new_name:
            return {"success": True, "name": old_name}
        old_path = os.path.join(KNOWLEDGE_DIR, old_name)
        new_path = os.path.join(KNOWLEDGE_DIR, new_name)
        if not old_path.endswith(".md") or not os.path.exists(old_path):
            return {"success": False, "error": "File not found"}
        if os.path.exists(new_path):
            return {"success": False, "error": "Target name already exists"}
        os.rename(old_path, new_path)

        metadata = self._load_metadata()
        if old_name in metadata:
            metadata[new_name] = metadata.pop(old_name)
            self._save_metadata(metadata)

        pinned = [new_name if os.path.basename(p) == old_name else p for p in self.get_pinned()]
        self.set_pinned(pinned)
        return {"success": True, "name": new_name}

    def merge_knowledge_files(self, target: str, source: str) -> dict:
        target_name = os.path.basename(target)
        source_name = os.path.basename(source)
        if target_name == source_name:
            return {"success": False, "error": "Choose two different entries"}
        target_path = os.path.join(KNOWLEDGE_DIR, target_name)
        source_path = os.path.join(KNOWLEDGE_DIR, source_name)
        if not target_path.endswith(".md") or not os.path.exists(target_path):
            return {"success": False, "error": "Target file not found"}
        if not source_path.endswith(".md") or not os.path.exists(source_path):
            return {"success": False, "error": "Source file not found"}

        with open(target_path, "r", encoding="utf-8") as f:
            target_content = f.read().rstrip()
        with open(source_path, "r", encoding="utf-8") as f:
            source_content = f.read().strip()
        merged_content = f"{target_content}\n\n---\n\n## Merged from {source_name}\n\n{source_content}\n"
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(merged_content)

        metadata = self._load_metadata()
        target_meta = metadata.setdefault(target_name, self._metadata_template("manual"))
        source_meta = metadata.get(source_name, {})
        inferred_alias = self._infer_alias_from_filename(source_name)
        target_meta["aliases"] = self._unique_values(
            target_meta.get("aliases", []),
            source_meta.get("aliases", []),
            [inferred_alias] if inferred_alias else [],
        )
        target_meta["match_patterns"] = self._unique_values(
            target_meta.get("match_patterns", []),
            source_meta.get("match_patterns", []),
        )
        metadata.pop(source_name, None)
        self._save_metadata(metadata)

        os.remove(source_path)
        pinned = [p for p in self.get_pinned() if os.path.basename(p) != source_name]
        if source_name in [os.path.basename(p) for p in self.get_pinned()] and target_name not in pinned:
            pinned.append(target_name)
        self.set_pinned(pinned)
        return {"success": True, "target": target_name, "removed": source_name}

    def delete_knowledge_file(self, filename: str) -> dict:
        fpath = os.path.join(KNOWLEDGE_DIR, os.path.basename(filename))
        if not fpath.endswith(".md") or not os.path.exists(fpath):
            return {"success": False, "error": "File not found"}
        os.remove(fpath)
        self._remove_file_metadata(os.path.basename(filename))
        return {"success": True}

    def delete_knowledge_by_llm(self, llm_id: str) -> dict:
        metadata = self._load_metadata()
        deleted = []
        for fname, meta in list(metadata.items()):
            if meta.get("llm_id") != llm_id:
                continue
            fpath = os.path.join(KNOWLEDGE_DIR, os.path.basename(fname))
            if fpath.endswith(".md") and os.path.exists(fpath):
                os.remove(fpath)
                deleted.append(fname)
            metadata.pop(fname, None)

        if deleted:
            pinned = [p for p in self.get_pinned() if os.path.basename(p) not in deleted]
            self.set_pinned(pinned)
        self._save_metadata(metadata)
        return {"success": True, "deleted": deleted, "count": len(deleted)}
