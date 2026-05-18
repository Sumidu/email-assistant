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

from app import llm_providers
from app import paths
from app import prompt_defaults

from . import database
from . import llm_logger
from modules.knowledge import entity_files as kb_entity_files
from modules.knowledge import frontmatter as kb_frontmatter
from modules.knowledge import matching as kb_matching

KNOWLEDGE_DIR = str(paths.KNOWLEDGE_DIR)
PINS_PATH = os.path.join(KNOWLEDGE_DIR, "_pinned.json")
METADATA_PATH = os.path.join(KNOWLEDGE_DIR, "_metadata.json")
FRONTMATTER_MARKER = kb_frontmatter.FRONTMATTER_MARKER
PEOPLE_DIR_NAME = "People"
OTHER_DIR_NAME = "Other"
PROJECTS_DIR_NAME = "Projects"
COMMITMENTS_DIR_NAME = "Commitments"
MEETINGS_DIR_NAME = "Meetings"


def _set_knowledge_dir(path) -> None:
    global KNOWLEDGE_DIR, PINS_PATH, METADATA_PATH
    KNOWLEDGE_DIR = str(path)
    PINS_PATH = os.path.join(KNOWLEDGE_DIR, "_pinned.json")
    METADATA_PATH = os.path.join(KNOWLEDGE_DIR, "_metadata.json")


class KnowledgeBuilder:
    def __init__(self, config: dict):
        self.config = config
        self._last_llm = None
        _set_knowledge_dir(paths.resolve_knowledge_dir())
        os.makedirs(KNOWLEDGE_DIR, exist_ok=True)
        self._ensure_knowledge_dirs()

    def _ensure_knowledge_dirs(self) -> None:
        os.makedirs(os.path.join(KNOWLEDGE_DIR, PEOPLE_DIR_NAME), exist_ok=True)
        os.makedirs(os.path.join(KNOWLEDGE_DIR, OTHER_DIR_NAME), exist_ok=True)
        os.makedirs(os.path.join(KNOWLEDGE_DIR, PROJECTS_DIR_NAME), exist_ok=True)
        os.makedirs(os.path.join(KNOWLEDGE_DIR, COMMITMENTS_DIR_NAME), exist_ok=True)
        os.makedirs(os.path.join(KNOWLEDGE_DIR, MEETINGS_DIR_NAME), exist_ok=True)

    @staticmethod
    def _knowledge_category(filename: str, metadata: dict | None = None, content: str = "") -> str:
        metadata = metadata or {}
        fname = os.path.basename(filename)
        entity_type = metadata.get("type", "")
        if entity_type == "project":
            return PROJECTS_DIR_NAME
        if entity_type == "commitment":
            return COMMITMENTS_DIR_NAME
        if entity_type == "meeting":
            return MEETINGS_DIR_NAME
        email_value = metadata.get("email") or KnowledgeBuilder._infer_email_from_filename(fname)
        aliases = metadata.get("aliases") if isinstance(metadata.get("aliases"), list) else []
        source = metadata.get("source", "")
        if source == "contact_profile" or aliases or (email_value and fname != "_writing_style.md"):
            return PEOPLE_DIR_NAME
        if not content and fname.startswith("_"):
            return OTHER_DIR_NAME
        if content:
            frontmatter, _ = KnowledgeBuilder._split_frontmatter(content)
            t = frontmatter.get("type", "")
            if t == "project":
                return PROJECTS_DIR_NAME
            if t == "commitment":
                return COMMITMENTS_DIR_NAME
            if t == "meeting":
                return MEETINGS_DIR_NAME
            if t == "contact" or frontmatter.get("email"):
                return PEOPLE_DIR_NAME
        return OTHER_DIR_NAME

    def _knowledge_path(self, filename: str, category: str | None = None) -> str:
        fname = os.path.basename(filename)
        all_cats = ["", PEOPLE_DIR_NAME, OTHER_DIR_NAME, PROJECTS_DIR_NAME, COMMITMENTS_DIR_NAME, MEETINGS_DIR_NAME]
        categories = [category] if category else all_cats
        for cat in categories:
            fpath = os.path.join(KNOWLEDGE_DIR, cat, fname) if cat else os.path.join(KNOWLEDGE_DIR, fname)
            if os.path.exists(fpath):
                return fpath
        target = category or OTHER_DIR_NAME
        return os.path.join(KNOWLEDGE_DIR, target, fname)

    def _knowledge_files(self) -> list[str]:
        files = []
        seen = set()
        all_dirs = ("", PEOPLE_DIR_NAME, OTHER_DIR_NAME, PROJECTS_DIR_NAME, COMMITMENTS_DIR_NAME, MEETINGS_DIR_NAME)
        for cat in all_dirs:
            directory = os.path.join(KNOWLEDGE_DIR, cat) if cat else KNOWLEDGE_DIR
            if not os.path.isdir(directory):
                continue
            for fname in sorted(os.listdir(directory)):
                if fname.endswith(".md") and fname not in seen:
                    files.append(fname)
                    seen.add(fname)
        return files

    def _knowledge_file_exists(self, filename: str) -> bool:
        return os.path.exists(self._knowledge_path(filename))

    def _migrate_knowledge_folders(self) -> None:
        metadata = {}
        if os.path.exists(METADATA_PATH):
            try:
                with open(METADATA_PATH, "r", encoding="utf-8") as f:
                    metadata = json.load(f)
            except Exception:
                metadata = {}
        for fname in sorted(os.listdir(KNOWLEDGE_DIR)):
            src = os.path.join(KNOWLEDGE_DIR, fname)
            if not os.path.isfile(src) or not fname.endswith(".md"):
                continue
            try:
                with open(src, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception:
                content = ""
            category = self._knowledge_category(fname, metadata.get(fname, {}), content)
            dst = os.path.join(KNOWLEDGE_DIR, category, fname)
            if os.path.exists(dst):
                continue
            os.replace(src, dst)

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

    def _load_metadata(self, merge_frontmatter: bool = False) -> dict:
        metadata = {}
        if not os.path.exists(METADATA_PATH):
            metadata = {}
        else:
            try:
                with open(METADATA_PATH, "r", encoding="utf-8") as f:
                    metadata = json.load(f)
            except Exception:
                metadata = {}
        return self._merge_frontmatter_metadata(metadata) if merge_frontmatter else metadata

    def _read_frontmatter_preview(self, filename: str, limit: int = 65536) -> tuple[dict, str, str]:
        """Read enough of a knowledge file for list metadata without loading all iCloud files."""
        fpath = self._knowledge_path(filename)
        with open(fpath, "r", encoding="utf-8") as f:
            sample = f.read(limit)
        frontmatter, body = self._split_frontmatter(sample)
        return frontmatter, body, sample

    def _merge_frontmatter_metadata(self, metadata: dict) -> dict:
        if not os.path.isdir(KNOWLEDGE_DIR):
            return metadata
        for fname in self._knowledge_files():
            if not fname.endswith(".md"):
                continue
            fpath = self._knowledge_path(fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    frontmatter, _ = self._split_frontmatter(f.read())
            except Exception:
                continue
            if not frontmatter:
                continue
            meta = metadata.setdefault(fname, self._metadata_template(frontmatter.get("source") or "manual"))
            for key in ("source", "llm_id", "llm_name", "model", "base_url", "generated_at"):
                if frontmatter.get(key) and not meta.get(key):
                    meta[key] = frontmatter[key]
            for key in ("aliases", "match_patterns"):
                values = frontmatter.get(key)
                if isinstance(values, list) and values:
                    meta[key] = self._unique_values(meta.get(key, []), values)
        return metadata

    def _save_metadata(self, metadata: dict) -> None:
        os.makedirs(KNOWLEDGE_DIR, exist_ok=True)
        self._ensure_knowledge_dirs()
        with open(METADATA_PATH, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, sort_keys=True)

    def _set_file_metadata(self, filename: str, source: str) -> None:
        metadata = self._load_metadata()
        metadata[filename] = self._current_llm_metadata(source)
        self._save_metadata(metadata)
        self._sync_file_frontmatter(filename, metadata[filename])

    def migrate_to_obsidian_format(self) -> dict:
        if not os.path.isdir(KNOWLEDGE_DIR):
            return {"success": True, "updated": 0}
        metadata = self._load_metadata()
        updated = 0
        metadata_changed = False
        for fname in sorted(self._knowledge_files()):
            if not fname.endswith(".md"):
                continue
            fpath = self._knowledge_path(fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    old = f.read()
                if fname not in metadata:
                    metadata[fname] = self._metadata_template("manual")
                    metadata_changed = True
                meta = metadata[fname]
                new = self._compose_markdown(fname, old, meta)
                if new != old:
                    with open(fpath, "w", encoding="utf-8") as f:
                        f.write(new)
                    updated += 1
            except Exception:
                continue
        if updated or metadata_changed:
            try:
                self._save_metadata(metadata)
            except OSError as exc:
                return {"success": False, "updated": updated, "error": str(exc)}
        return {"success": True, "updated": updated}

    # ---- Obsidian links ----------------------------------------------------

    @staticmethod
    def _unwrap_wikilinks(value: str) -> str:
        return kb_frontmatter.unwrap_wikilinks(value)

    @classmethod
    def _unwrap_heading_wikilinks(cls, body: str) -> str:
        return kb_frontmatter.unwrap_heading_wikilinks(body)

    @staticmethod
    def _repair_nested_wikilinks(body: str) -> str:
        return kb_frontmatter.repair_nested_wikilinks(body)

    @staticmethod
    def _clean_link_label(value: str) -> str:
        return kb_frontmatter.clean_link_label(value)

    @staticmethod
    def _name_from_email(value: str) -> str:
        email = str(value or "").strip().lower()
        if "@" not in email:
            return ""
        local = email.split("@", 1)[0]
        parts = [p for p in re.split(r"[._\-]+", local) if len(p) > 1]
        if len(parts) < 2:
            return ""
        return " ".join(p.capitalize() for p in parts[:3])

    @staticmethod
    def _link_term_ok(term: str) -> bool:
        term = str(term or "").strip()
        if not term:
            return False
        if "@" in term:
            return True
        if len(term) < 6:
            return False
        if len(term.split()) < 2:
            return False
        return bool(re.search(r"[A-Za-zÀ-ÖØ-öø-ÿ]", term))

    @staticmethod
    def _unique_preserve_case(values) -> list[str]:
        seen = set()
        result = []
        for value in values or []:
            value = str(value or "").strip()
            key = value.lower()
            if value and key not in seen:
                seen.add(key)
                result.append(value)
        return result

    def _contact_link_index(self) -> list[dict]:
        metadata = self._load_metadata()
        raw_index = []
        for fname in sorted(self._knowledge_files()):
            if not fname.endswith(".md") or fname.startswith("_"):
                continue
            fpath = self._knowledge_path(fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    frontmatter, body = self._split_frontmatter(f.read())
            except Exception:
                continue
            meta = dict(frontmatter)
            meta.update(metadata.get(fname, {}))
            email = meta.get("email") or self._infer_email_from_filename(fname)
            title = self._clean_link_label(meta.get("title") or self._frontmatter_title(fname, body))
            aliases = meta.get("aliases") if isinstance(meta.get("aliases"), list) else []
            terms = [title, email, self._name_from_email(email)]
            terms.extend(aliases)
            for alias in aliases:
                terms.append(self._name_from_email(alias))
            terms = [t for t in self._unique_preserve_case(terms) if self._link_term_ok(t)]
            if not terms:
                continue
            raw_index.append({
                "filename": fname,
                "stem": fname.removesuffix(".md"),
                "label": title or email or fname.removesuffix(".md"),
                "terms": terms,
            })
        term_targets = {}
        for item in raw_index:
            for term in item["terms"]:
                term_targets.setdefault(term.lower(), set()).add(item["stem"])
        index = []
        for item in raw_index:
            filtered_terms = [
                term for term in item["terms"]
                if "@" in term or len(term_targets.get(term.lower(), set())) == 1
            ]
            if filtered_terms:
                next_item = dict(item)
                next_item["terms"] = filtered_terms
                index.append(next_item)
        index.sort(key=lambda item: max(len(t) for t in item["terms"]), reverse=True)
        return index

    def _ambiguous_link_labels(self) -> set[str]:
        metadata = self._load_metadata()
        labels = {}
        for fname in sorted(self._knowledge_files()):
            if not fname.endswith(".md") or fname.startswith("_"):
                continue
            fpath = self._knowledge_path(fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    frontmatter, body = self._split_frontmatter(f.read())
            except Exception:
                continue
            meta = dict(frontmatter)
            meta.update(metadata.get(fname, {}))
            title = self._clean_link_label(meta.get("title") or self._frontmatter_title(fname, body))
            if title:
                labels.setdefault(title.lower(), set()).add(fname.removesuffix(".md"))
        return {label for label, targets in labels.items() if len(targets) > 1}

    def _unlink_ambiguous_labels(self, body: str, ambiguous_labels: set[str]) -> str:
        if not ambiguous_labels:
            return body

        def repl(match):
            target = match.group(1)
            label = match.group(2) or target
            if label.strip().lower() in ambiguous_labels:
                return label
            return match.group(0)

        return re.sub(r"\[\[([^|\]#]+)(?:#[^|\]]+)?(?:\|([^\]]+))?\]\]", repl, body or "")

    @staticmethod
    def _protect_markdown_segments(body: str):
        protected = re.compile(r"(```[\s\S]*?```|^#{1,6}\s+.*$|\[\[[^\]]+\]\]|\[[^\]]+\]\([^)]+\))", re.MULTILINE)
        parts = []
        last = 0
        for match in protected.finditer(body):
            if match.start() > last:
                parts.append((False, body[last:match.start()]))
            parts.append((True, match.group(0)))
            last = match.end()
        if last < len(body):
            parts.append((False, body[last:]))
        return parts

    def _linkify_body(self, filename: str, body: str, index: list[dict]) -> str:
        if not body.strip():
            return body
        own_stem = os.path.basename(filename).removesuffix(".md")
        existing_links = {
            link.split("|", 1)[0].split("#", 1)[0].strip()
            for link in re.findall(r"\[\[([^\]]+)\]\]", body)
        }
        linked_targets = set(existing_links)
        parts = self._protect_markdown_segments(body)

        for contact in index:
            stem = contact["stem"]
            if stem == own_stem or stem in linked_targets:
                continue
            replacement_done = False
            for term in sorted(contact["terms"], key=len, reverse=True):
                escaped = re.escape(term)
                pattern = re.compile(rf"(?<![\w@.\-])({escaped})(?![\w@.\-])", re.IGNORECASE)
                for i, (is_protected, text) in enumerate(parts):
                    if is_protected:
                        continue
                    if not pattern.search(text):
                        continue

                    def repl(match):
                        label = match.group(1)
                        if label.lower() == stem.lower():
                            return f"[[{stem}]]"
                        return f"[[{stem}|{label}]]"

                    parts[i] = (False, pattern.sub(repl, text, count=1))
                    linked_targets.add(stem)
                    replacement_done = True
                    break
                if replacement_done:
                    break
        return "".join(text for _, text in parts)

    def enrich_obsidian_links(self, filenames=None, update_all: bool = False) -> dict:
        if not os.path.isdir(KNOWLEDGE_DIR):
            return {"success": True, "updated": 0}
        index = self._contact_link_index()
        ambiguous_labels = self._ambiguous_link_labels()
        if update_all or filenames is None:
            targets = self._knowledge_files()
        else:
            targets = [os.path.basename(f) for f in filenames if str(f or "").endswith(".md")]
        metadata = self._load_metadata()
        updated = []
        for fname in sorted(set(targets)):
            fpath = self._knowledge_path(fname)
            if not fname.endswith(".md") or not os.path.exists(fpath):
                continue
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    original = f.read()
                _, body = self._split_frontmatter(original)
                original_body = body
                body = self._unlink_ambiguous_labels(body, ambiguous_labels)
                linked_body = self._linkify_body(fname, body, index)
                if linked_body == original_body:
                    continue
                meta = metadata.get(fname, self._metadata_template("manual"))
                updated_content = self._compose_markdown(fname, linked_body, meta)
                with open(fpath, "w", encoding="utf-8") as f:
                    f.write(updated_content)
                updated.append(fname)
            except Exception:
                continue
        return {"success": True, "updated": len(updated), "files": updated}

    @staticmethod
    def _yaml_quote(value) -> str:
        return kb_frontmatter.yaml_quote(value)

    @classmethod
    def _yaml_list(cls, values) -> str:
        return kb_frontmatter.yaml_list(values)

    @staticmethod
    def _parse_frontmatter_value(value: str):
        return kb_frontmatter.parse_frontmatter_value(value)

    @classmethod
    def _split_frontmatter(cls, content: str) -> tuple[dict, str]:
        return kb_frontmatter.split_frontmatter(content)

    @classmethod
    def _strip_frontmatter(cls, content: str) -> str:
        return kb_frontmatter.strip_frontmatter(content)

    @staticmethod
    def _frontmatter_title(filename: str, content: str = "") -> str:
        return kb_frontmatter.frontmatter_title(filename, content)

    @staticmethod
    def _infer_email_from_filename(filename: str) -> str:
        return kb_frontmatter.infer_email_from_filename(filename)

    def _frontmatter_for_file(self, filename: str, metadata: dict, content: str) -> dict:
        existing, body = self._split_frontmatter(content)
        source = metadata.get("source") or existing.get("source") or "manual"
        title = self._clean_link_label(existing.get("title") or self._frontmatter_title(filename, body))
        email = existing.get("email") or self._infer_email_from_filename(filename)
        aliases = self._normalize_aliases(metadata.get("aliases", existing.get("aliases", [])))
        match_patterns = self._normalize_match_patterns(
            metadata.get("match_patterns", existing.get("match_patterns", []))
        )
        tags = existing.get("tags") if isinstance(existing.get("tags"), list) else []
        for tag in ("email-assistant", "knowledge-base"):
            if tag not in tags:
                tags.append(tag)
        if source == "contact_profile" and "contact" not in tags:
            tags.append("contact")
        if filename == "_writing_style.md" and "writing-style" not in tags:
            tags.append("writing-style")

        frontmatter = {
            "title": title,
            "type": "writing_style" if filename == "_writing_style.md" else "contact" if source == "contact_profile" or email else "note",
            "email": email,
            "aliases": aliases,
            "match_patterns": match_patterns,
            "source": source,
            "llm_id": metadata.get("llm_id", existing.get("llm_id", "")),
            "llm_name": metadata.get("llm_name", existing.get("llm_name", "")),
            "model": metadata.get("model", existing.get("model", "")),
            "generated_at": metadata.get("generated_at", existing.get("generated_at", "")),
            "tags": tags,
        }
        return frontmatter

    def _render_frontmatter(self, frontmatter: dict) -> str:
        lines = [FRONTMATTER_MARKER]
        for key in ("title", "type", "email", "aliases", "match_patterns", "source", "llm_id", "llm_name", "model", "generated_at", "tags"):
            value = frontmatter.get(key)
            if key in ("aliases", "match_patterns", "tags"):
                lines.append(f"{key}: {self._yaml_list(value)}")
            elif value:
                lines.append(f"{key}: {self._yaml_quote(value)}")
        lines.append(FRONTMATTER_MARKER)
        return "\n".join(lines) + "\n\n"

    def _compose_markdown(self, filename: str, content: str, metadata: dict) -> str:
        _, body = self._split_frontmatter(content)
        body = self._repair_nested_wikilinks(body)
        body = self._unwrap_heading_wikilinks(body)
        frontmatter = self._frontmatter_for_file(filename, metadata, content)
        return self._render_frontmatter(frontmatter) + body.lstrip("\n")

    def _sync_file_frontmatter(self, filename: str, metadata: dict | None = None) -> None:
        fname = os.path.basename(filename)
        if not fname.endswith(".md"):
            return
        fpath = self._knowledge_path(fname)
        if not os.path.exists(fpath):
            return
        metadata = metadata or self._load_metadata().get(fname, self._metadata_template("manual"))
        with open(fpath, "r", encoding="utf-8") as f:
            content = f.read()
        updated = self._compose_markdown(fname, content, metadata)
        if updated != content:
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(updated)

    @staticmethod
    def _normalize_match_patterns(patterns) -> list[str]:
        return kb_matching.normalize_match_patterns(patterns)

    @staticmethod
    def _normalize_aliases(aliases) -> list[str]:
        return kb_matching.normalize_aliases(aliases)

    @staticmethod
    def _pattern_matches_address(pattern: str, addr: str) -> bool:
        return kb_matching.pattern_matches_address(pattern, addr)

    def _pattern_files_for_address(self, addr: str) -> list[str]:
        metadata = self._load_metadata()
        matches = []
        for fname, meta in metadata.items():
            if not fname.endswith(".md"):
                continue
            patterns = self._normalize_match_patterns(meta.get("match_patterns", []))
            if any(self._pattern_matches_address(pattern, addr) for pattern in patterns):
                if self._knowledge_file_exists(fname):
                    matches.append(os.path.basename(fname))
        return matches

    def _alias_files_for_address(self, addr: str) -> list[str]:
        addr = (addr or "").lower()
        metadata = self._load_metadata()
        matches = []
        for fname, meta in metadata.items():
            aliases = self._normalize_aliases(meta.get("aliases", []))
            if addr in aliases and self._knowledge_file_exists(fname):
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
        return self._knowledge_file_exists(self.contact_filename(addr))

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
        content = KnowledgeBuilder._strip_reasoning_output(content)
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

    @staticmethod
    def _strip_reasoning_output(content: str) -> str:
        """Remove model reasoning blocks that should never enter the KB."""
        content = content or ""
        block_tags = ("think", "thinking", "reasoning", "analysis")
        for tag in block_tags:
            content = re.sub(
                rf"<\s*{tag}\b[^>]*>[\s\S]*?<\s*/\s*{tag}\s*>",
                "",
                content,
                flags=re.IGNORECASE,
            )
            content = re.sub(
                rf"&lt;\s*{tag}\b[^&]*&gt;[\s\S]*?&lt;\s*/\s*{tag}\s*&gt;",
                "",
                content,
                flags=re.IGNORECASE,
            )
        content = re.sub(
            r"```(?:think|thinking|reasoning|analysis)\s*\n[\s\S]*?```",
            "",
            content,
            flags=re.IGNORECASE,
        )
        content = re.sub(r"^\s*(?:thinking|reasoning|analysis)\s*:\s*[\s\S]*?(?=^\s{0,3}#|\Z)", "", content, flags=re.IGNORECASE | re.MULTILINE)
        content = re.sub(r"<\s*/?\s*(?:think|thinking|reasoning|analysis)\b[^>]*>", "", content, flags=re.IGNORECASE)
        content = re.sub(r"&lt;\s*/?\s*(?:think|thinking|reasoning|analysis)\b[^&]*&gt;", "", content, flags=re.IGNORECASE)
        return re.sub(r"\n{3,}", "\n\n", content).strip()

    def clean_existing_reasoning_output(self) -> dict:
        if not os.path.isdir(KNOWLEDGE_DIR):
            return {"success": True, "updated": 0}
        all_metadata = self._load_metadata()
        updated = []
        for fname in sorted(self._knowledge_files()):
            if not fname.endswith(".md"):
                continue
            fpath = self._knowledge_path(fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    original = f.read()
                frontmatter, body = self._split_frontmatter(original)
                cleaned_body = self._strip_reasoning_output(body)
                if frontmatter:
                    metadata = all_metadata.get(fname, self._metadata_template("manual"))
                    cleaned = self._compose_markdown(fname, cleaned_body, metadata)
                else:
                    cleaned = cleaned_body
                if cleaned != original:
                    with open(fpath, "w", encoding="utf-8") as f:
                        f.write(cleaned)
                    updated.append(fname)
            except Exception:
                continue
        return {"success": True, "updated": len(updated), "files": updated}

    # ---- knowledge builders ------------------------------------------------

    def build_style_knowledge(self, sent_emails: list) -> dict:
        if not sent_emails:
            return {"success": False, "error": "No sent emails found"}

        sample = sent_emails[:60]
        snippets = "\n\n---EMAIL---\n".join(
            "BEGIN UNTRUSTED EMAIL CONTENT\n"
            f"Subject: {e.get('subject','')}\n{e.get('body_text','')[:500]}\n"
            "END UNTRUSTED EMAIL CONTENT"
            for e in sample
        )

        prompts = prompt_defaults.ensure_prompts(self.config)
        system = prompt_defaults.with_untrusted_context_rules(prompts["knowledge_style_system"])
        user = prompt_defaults.render_prompt(
            prompts["knowledge_style_user"],
            {"snippets": snippets[:9000]},
        )
        try:
            content = self._clean_generated_markdown(self._call_llm(system, user, max_tokens=2500))
            path = self._knowledge_path("_writing_style.md", OTHER_DIR_NAME)
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"# Writing Style Guide\n\n")
                f.write(f"*Generated: {datetime.now():%Y-%m-%d %H:%M}*\n\n")
                f.write(content)
            self._set_file_metadata("_writing_style.md", "writing_style")
            self.enrich_obsidian_links(["_writing_style.md"])
            return {"success": True, "file": path}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def build_contact_knowledge(self, addr: str, data: dict) -> dict:
        emails_from  = data["emails"][:12]
        my_replies   = data["my_replies"][:12]

        from_text = "\n\n---\n".join(
            "BEGIN UNTRUSTED EMAIL CONTENT\n"
            f"Subject: {e.get('subject','')}\n{e.get('body_text','')[:400]}\n"
            "END UNTRUSTED EMAIL CONTENT"
            for e in emails_from
        )
        reply_text = (
            "\n\n---\n".join(
                "BEGIN UNTRUSTED EMAIL CONTENT\n"
                f"Subject: {e.get('subject','')}\n{e.get('body_text','')[:400]}\n"
                "END UNTRUSTED EMAIL CONTENT"
                for e in my_replies
            )
            if my_replies
            else "No replies on record."
        )

        prompts = prompt_defaults.ensure_prompts(self.config)
        system = prompt_defaults.with_untrusted_context_rules(prompts["knowledge_contact_system"])
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
            path  = self._knowledge_path(fname, PEOPLE_DIR_NAME)
            existed = os.path.exists(path)
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"# Contact: {data.get('name', addr)}\n\n")
                f.write(f"**Email:** {addr}  \n")
                f.write(f"**Received:** {len(data['emails'])} | **Replied:** {len(data['my_replies'])}  \n")
                f.write(f"*Generated: {datetime.now():%Y-%m-%d %H:%M}*\n\n")
                f.write(content)
            self._set_file_metadata(fname, "contact_profile")
            self.enrich_obsidian_links([fname], update_all=not existed)
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

    def build_entities(self, emails: list, progress_callback=None) -> dict:
        from modules.knowledge import entities as kb_entities

        if not emails:
            return {"success": True, "skipped": True, "message": "No unextracted emails."}

        MAX_PER_BUILD = 200
        emails = emails[:MAX_PER_BUILD]
        if progress_callback:
            progress_callback(f"Extracting entities from {len(emails)} email(s)…")

        extractions: list[dict] = []
        extracted_ids: list[str] = []
        for email in emails:
            result = kb_entities.extract_entities_from_email(email, self.config)
            if result:
                extractions.append(result)
            database.mark_entity_extracted([email["id"]])
            extracted_ids.append(email["id"])

        if not extractions:
            return {"success": True, "extracted": 0, "entities": 0}

        if progress_callback:
            progress_callback("Canonicalizing extracted entities…")

        batch = kb_entities.aggregate_entity_batch(extractions)
        existing_slugs = {
            "projects": kb_entity_files.collect_existing_slugs(
                os.path.join(KNOWLEDGE_DIR, PROJECTS_DIR_NAME)
            ),
            "commitments": kb_entity_files.collect_existing_slugs(
                os.path.join(KNOWLEDGE_DIR, COMMITMENTS_DIR_NAME)
            ),
            "meetings": kb_entity_files.collect_existing_slugs(
                os.path.join(KNOWLEDGE_DIR, MEETINGS_DIR_NAME)
            ),
        }
        canon_map = kb_entities.canonicalize_entities(batch, existing_slugs, self.config)

        entity_count = 0
        for project in batch.get("projects", []):
            code_slug = project.get("_slug", "")
            canon_slug = canon_map.get("projects", {}).get(code_slug, code_slug)
            people = [f"[[{p}]]" for p in (project.get("people") or [])]
            obs = [f"{datetime.now():%Y-%m-%d}: {project.get('context', '')}"]
            try:
                self.write_project_file(canon_slug, project.get("name", canon_slug), obs, people)
                entity_count += 1
            except Exception:
                pass

        for commitment in batch.get("commitments", []):
            code_slug = commitment.get("_slug", "")
            canon_slug = canon_map.get("commitments", {}).get(code_slug, code_slug)
            obs = [f"{datetime.now():%Y-%m-%d}: {commitment.get('what', '')}"]
            try:
                self.write_commitment_file(canon_slug, commitment, obs)
                entity_count += 1
            except Exception:
                pass

        for meeting in batch.get("meetings", []):
            code_slug = meeting.get("_slug", "")
            canon_slug = canon_map.get("meetings", {}).get(code_slug, code_slug)
            date = meeting.get("date", "")
            topic = meeting.get("topic", "")
            participants = meeting.get("participants") or []
            obs = [f"{datetime.now():%Y-%m-%d}: {meeting.get('notes', '')}"]
            calendar_link = kb_entities.find_calendar_match(date, topic)
            try:
                self.write_meeting_file(canon_slug, date, topic, participants, obs, calendar_link)
                entity_count += 1
            except Exception:
                pass

        if entity_count and progress_callback:
            progress_callback(f"Wrote {entity_count} entity file(s) from {len(extracted_ids)} email(s).")

        return {
            "success": True,
            "extracted": len(extracted_ids),
            "entities": entity_count,
        }

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

        if contact_results:
            if progress_callback:
                progress_callback("Updating Obsidian links between knowledge entries…")
            self.enrich_obsidian_links(update_all=True)

        database.mark_emails_kb_processed(processed_ids)

        # Pass 2: entity extraction
        unextracted = database.get_unextracted_emails()
        entities_result = self.build_entities(unextracted, progress_callback)

        return {
            "success": True,
            "style": style_result,
            "contacts": contact_results,
            "total_contacts": len(contact_results),
            "new_emails_processed": len(new_emails),
            "entities": entities_result,
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
            fpath = self._knowledge_path(fname)
            if os.path.exists(fpath) and fpath not in loaded_paths:
                with open(fpath, "r", encoding="utf-8") as f:
                    knowledge.append((fname.replace(".md", "").replace("_", " ").title(), self._strip_frontmatter(f.read())))
                loaded_paths.add(fpath)

        # Writing style (unless already pinned)
        style_path = self._knowledge_path("_writing_style.md")
        if os.path.exists(style_path) and style_path not in loaded_paths:
            with open(style_path, "r", encoding="utf-8") as f:
                knowledge.append(("My Writing Style", self._strip_frontmatter(f.read())))
            loaded_paths.add(style_path)

        # Contact profile
        contact_path = self._knowledge_path(self._safe_filename(sender_email.lower()) + ".md")
        if os.path.exists(contact_path) and contact_path not in loaded_paths:
            with open(contact_path, "r", encoding="utf-8") as f:
                knowledge.append(("Contact Profile", self._strip_frontmatter(f.read())))
            loaded_paths.add(contact_path)

        for fname, match_type in self._metadata_files_for_address(sender_email):
            fpath = self._knowledge_path(fname)
            if os.path.exists(fpath) and fpath not in loaded_paths:
                with open(fpath, "r", encoding="utf-8") as f:
                    label = fname.replace(".md", "").replace("_", " ").title()
                    prefix = "Alias" if match_type == "alias" else "Wildcard"
                    knowledge.append((f"{prefix}: {label}", self._strip_frontmatter(f.read())))
                loaded_paths.add(fpath)

        return knowledge

    def get_knowledge_for_email(self, sender_email: str, subject: str = "", body: str = "") -> list[tuple[str, str]]:
        """Like get_knowledge_for_sender but also injects KB files for other
        people mentioned in the email (matched by name appearing in filename
        or the first 400 chars of a contact file)."""
        knowledge = self.get_knowledge_for_sender(sender_email)
        # build set of loaded paths from what get_knowledge_for_sender returned
        loaded_paths = set()
        for fname in self.get_pinned():
            loaded_paths.add(self._knowledge_path(fname))
        loaded_paths.add(self._knowledge_path("_writing_style.md"))
        loaded_paths.add(self._knowledge_path(self._safe_filename(sender_email.lower()) + ".md"))
        for fname, _ in self._metadata_files_for_address(sender_email):
            loaded_paths.add(self._knowledge_path(fname))

        # Extract candidate names: capitalised words 3+ chars from subject + first 1500 chars of body
        text = f"{subject} {body[:1500]}"
        candidates = set(re.findall(r'\b[A-Z][a-zA-Z]{2,}\b', text))
        # Remove common non-name words
        stopwords = {"The","This","That","From","Dear","Kind","Best","With","Your","Please","Thank","Also","Have","Will"}
        candidates -= stopwords

        if not candidates:
            return knowledge

        for fname in sorted(self._knowledge_files()):
            if not fname.endswith(".md") or fname.startswith("_"):
                continue
            fpath = self._knowledge_path(fname)
            if fpath in loaded_paths:
                continue
            fname_lower = fname.lower()
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    content = self._strip_frontmatter(f.read())
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
        if not os.path.isdir(KNOWLEDGE_DIR):
            return result
        for fname in sorted(self._knowledge_files()):
            if not fname.endswith(".md"):
                continue
            fpath = self._knowledge_path(fname)
            meta = metadata.get(fname, {})
            category = self._knowledge_category(fname, meta)
            result.append({"name": fname, "path": fpath, "content": "",
                            "loaded": False,
                            "category": "people" if category == PEOPLE_DIR_NAME else "other",
                            "pinned": fname in pinned,
                            "metadata": meta})
        return result

    def read_knowledge_file(self, filename: str) -> dict:
        fname = os.path.basename(filename)
        if not fname.endswith(".md"):
            return {"success": False, "error": "Invalid knowledge filename"}
        fpath = self._knowledge_path(fname)
        if not os.path.exists(fpath):
            return {"success": False, "error": "Knowledge file not found"}
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
            file_meta, body = self._split_frontmatter(content)
            metadata = self._load_metadata().get(fname, {})
            merged_meta = dict(file_meta)
            merged_meta.update(metadata)
            category = self._knowledge_category(fname, merged_meta, content)
            return {"success": True, "name": fname, "path": fpath, "content": body,
                    "loaded": True,
                    "category": "people" if category == PEOPLE_DIR_NAME else "other",
                    "pinned": fname in set(self.get_pinned()),
                    "metadata": merged_meta}
        except (OSError, UnicodeDecodeError) as exc:
            return {"success": False, "error": str(exc)}

    def suggested_context(self, sender_email: str, recipient_emails=None) -> list:
        """Return filenames that should be pre-selected for an email:
        pinned files + _writing_style + sender contact + recipient contacts."""
        suggested = []
        seen = set()

        def _add(fname):
            if fname not in seen and self._knowledge_file_exists(fname):
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
        fpath = self._knowledge_path(filename)
        if not fpath.endswith(".md") or not os.path.exists(fpath):
            return None
        with open(fpath, "r", encoding="utf-8") as f:
            return self._strip_frontmatter(f.read())

    def save_knowledge_file(self, filename: str, content: str, source: str = "manual", match_patterns=None, aliases=None) -> dict:
        if not filename.endswith(".md"):
            filename += ".md"
        filename = self._safe_filename(filename.replace(".md", "")) + ".md"
        metadata = self._load_metadata()
        existing_path = self._knowledge_path(filename)
        existed = os.path.exists(existing_path)
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
        category = self._knowledge_category(filename, metadata.get(filename, {}), content)
        fpath = self._knowledge_path(filename, category)
        existed = os.path.exists(fpath)
        if existed is False and existing_path != fpath and os.path.exists(existing_path):
            os.remove(existing_path)
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(self._compose_markdown(filename, content, metadata.get(filename, {})))
        self._save_metadata(metadata)
        self.enrich_obsidian_links([filename], update_all=not existed)
        return {"success": True, "name": filename}

    def rename_knowledge_file(self, filename: str, new_filename: str) -> dict:
        old_name = os.path.basename(filename)
        if not new_filename.endswith(".md"):
            new_filename += ".md"
        new_name = self._safe_filename(new_filename.replace(".md", "")) + ".md"
        if old_name == new_name:
            return {"success": True, "name": old_name}
        old_path = self._knowledge_path(old_name)
        if not old_path.endswith(".md") or not os.path.exists(old_path):
            return {"success": False, "error": "File not found"}
        with open(old_path, "r", encoding="utf-8") as f:
            content = f.read()
        metadata = self._load_metadata()
        category = self._knowledge_category(new_name, metadata.get(old_name, {}), content)
        new_path = self._knowledge_path(new_name, category)
        if os.path.exists(new_path):
            return {"success": False, "error": "Target name already exists"}
        os.rename(old_path, new_path)

        if old_name in metadata:
            metadata[new_name] = metadata.pop(old_name)
            self._save_metadata(metadata)
            self._sync_file_frontmatter(new_name, metadata[new_name])

        pinned = [new_name if os.path.basename(p) == old_name else p for p in self.get_pinned()]
        self.set_pinned(pinned)
        self.enrich_obsidian_links(update_all=True)
        return {"success": True, "name": new_name}

    def merge_knowledge_files(self, target: str, source: str) -> dict:
        target_name = os.path.basename(target)
        source_name = os.path.basename(source)
        if target_name == source_name:
            return {"success": False, "error": "Choose two different entries"}
        target_path = self._knowledge_path(target_name)
        source_path = self._knowledge_path(source_name)
        if not target_path.endswith(".md") or not os.path.exists(target_path):
            return {"success": False, "error": "Target file not found"}
        if not source_path.endswith(".md") or not os.path.exists(source_path):
            return {"success": False, "error": "Source file not found"}

        with open(target_path, "r", encoding="utf-8") as f:
            target_content = self._strip_frontmatter(f.read()).rstrip()
        with open(source_path, "r", encoding="utf-8") as f:
            source_content = self._strip_frontmatter(f.read()).strip()
        source_stem = source_name.removesuffix(".md")
        merged_content = f"{target_content}\n\n---\n\n## Merged from [[{source_stem}]]\n\n{source_content}\n"

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
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(self._compose_markdown(target_name, merged_content, target_meta))
        self._save_metadata(metadata)
        self.enrich_obsidian_links([target_name])

        os.remove(source_path)
        pinned = [p for p in self.get_pinned() if os.path.basename(p) != source_name]
        if source_name in [os.path.basename(p) for p in self.get_pinned()] and target_name not in pinned:
            pinned.append(target_name)
        self.set_pinned(pinned)
        return {"success": True, "target": target_name, "removed": source_name}

    def delete_knowledge_file(self, filename: str) -> dict:
        fpath = self._knowledge_path(filename)
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
            fpath = self._knowledge_path(fname)
            if fpath.endswith(".md") and os.path.exists(fpath):
                os.remove(fpath)
                deleted.append(fname)
            metadata.pop(fname, None)

        if deleted:
            pinned = [p for p in self.get_pinned() if os.path.basename(p) not in deleted]
            self.set_pinned(pinned)
        self._save_metadata(metadata)
        return {"success": True, "deleted": deleted, "count": len(deleted)}

    # ---- entity file writers (Pass 2) ---------------------------------------

    def _rewrite_ai_block(self, entity_type: str, existing_block: str, observations: list[str]) -> str:
        prompts = prompt_defaults.ensure_prompts(self.config)
        system = prompts.get("entity_ai_block_system", "")
        user_tpl = prompts.get("entity_ai_block_user", "")
        obs_text = "\n".join(f"- {o}" for o in observations[:15])
        user = prompt_defaults.render_prompt(user_tpl, {
            "entity_type": entity_type,
            "existing_block": existing_block or "(none)",
            "new_observations": obs_text or "(none)",
        })
        return self._call_llm(system, user, max_tokens=800)

    def write_project_file(self, slug: str, name: str, observations: list[str], people_links: list[str]) -> str:
        fname = self._safe_filename(name) + ".md"
        path = os.path.join(KNOWLEDGE_DIR, PROJECTS_DIR_NAME, fname)
        parsed = kb_entity_files.read_entity_file(path)
        new_block = self._rewrite_ai_block("project", parsed["ai_block"], observations)
        fm = parsed["frontmatter"] or {}
        fm.update({
            "type": "project",
            "slug": slug,
            "name": name,
            "status": fm.get("status", "active"),
            "last_ai_update": datetime.now().strftime("%Y-%m-%d"),
        })
        if people_links:
            fm["people"] = people_links
        user_content = parsed["user_content"] or "## Links\n\n## Notes\n"
        kb_entity_files.write_entity_file(path, fm, new_block, user_content)
        return path

    def write_commitment_file(self, slug: str, data: dict, observations: list[str]) -> str:
        safe_name = re.sub(r"[^\w\s-]", "", slug)[:60].strip()
        fname = safe_name + ".md"
        path = os.path.join(KNOWLEDGE_DIR, COMMITMENTS_DIR_NAME, fname)
        parsed = kb_entity_files.read_entity_file(path)
        new_block = self._rewrite_ai_block("commitment", parsed["ai_block"], observations)
        fm = parsed["frontmatter"] or {}
        fm.update({
            "type": "commitment",
            "slug": slug,
            "direction": data.get("direction", "outgoing"),
            "status": fm.get("status", "pending"),
            "last_ai_update": datetime.now().strftime("%Y-%m-%d"),
        })
        if data.get("person"):
            fm["people"] = [f"[[{data['person']}]]"]
        if data.get("deadline"):
            fm["deadline"] = data["deadline"]
        if data.get("certainty"):
            fm["certainty"] = data["certainty"]
        if data.get("project"):
            fm["project"] = f"[[{data['project']}]]"
        user_content = parsed["user_content"] or "## Notes\n"
        kb_entity_files.write_entity_file(path, fm, new_block, user_content)
        return path

    def write_meeting_file(self, slug: str, date: str, topic: str, participants: list[str],
                           observations: list[str], calendar_link: str | None = None) -> str:
        if date and len(date) >= 10:
            date_part = date[:10]
            topic_safe = re.sub(r"[^\w\s-]", "", topic or "Meeting")[:50].strip()
            if topic_safe:
                fname = f"{date_part} {topic_safe}.md"
            elif participants:
                fname = f"{date_part} Meeting with {participants[0]}.md"
            else:
                fname = f"{date_part} Meeting.md"
        elif topic:
            topic_safe = re.sub(r"[^\w\s-]", "", topic)[:50].strip()
            p_str = " ".join(participants[:2]) if participants else ""
            fname = f"Meeting - {topic_safe}{' - ' + p_str if p_str else ''}.md"
        else:
            fname = f"Meeting - {slug}.md"

        path = os.path.join(KNOWLEDGE_DIR, MEETINGS_DIR_NAME, fname)
        parsed = kb_entity_files.read_entity_file(path)
        new_block = self._rewrite_ai_block("meeting", parsed["ai_block"], observations)
        fm = parsed["frontmatter"] or {}
        fm.update({
            "type": "meeting",
            "slug": slug,
            "topic": topic or "",
            "last_ai_update": datetime.now().strftime("%Y-%m-%d"),
        })
        if date:
            fm["date"] = date[:10]
        if participants:
            fm["participants"] = [f"[[{p}]]" for p in participants]
        if calendar_link:
            fm["calendar_event"] = f"[[{calendar_link}]]"

        links_section = "## Links\n"
        if participants:
            links_section += " · ".join(f"[[{p}]]" for p in participants) + "\n"
        if calendar_link:
            links_section += f"\n[[{calendar_link}]]\n"
        user_content = parsed["user_content"] or f"{links_section}\n## Notes\n"
        kb_entity_files.write_entity_file(path, fm, new_block, user_content)
        return path
