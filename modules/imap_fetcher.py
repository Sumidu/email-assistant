"""
IMAP fetcher — connects to Outlook (or any IMAP server) and downloads
inbox + sent emails into the local SQLite database.
Each IMAPFetcher instance represents one email account.
"""

import email
import email.header
import email.utils
import hashlib
import html
import imaplib
import re
from datetime import datetime

from . import database


# ---------------------------------------------------------------------------
# Header / body helpers
# ---------------------------------------------------------------------------

def decode_header_value(value: str) -> str:
    if not value:
        return ""
    parts = email.header.decode_header(value)
    result = []
    for raw, charset in parts:
        if isinstance(raw, bytes):
            result.append(raw.decode(charset or "utf-8", errors="replace"))
        else:
            result.append(str(raw))
    return "".join(result)


def html_to_text(raw_html: str) -> str:
    text = re.sub(r"<(script|style)[^>]*>.*?</(script|style)>",
                  "", raw_html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_bodies(msg) -> tuple[str, str]:
    plain, htm = "", ""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition", ""))
            if "attachment" in disp:
                continue
            charset = part.get_content_charset() or "utf-8"
            try:
                payload = part.get_payload(decode=True)
                if not payload:
                    continue
                decoded = payload.decode(charset, errors="replace")
                if ctype == "text/plain" and not plain:
                    plain = decoded
                elif ctype == "text/html" and not htm:
                    htm = decoded
            except Exception:
                pass
    else:
        ctype = msg.get_content_type()
        charset = msg.get_content_charset() or "utf-8"
        try:
            payload = msg.get_payload(decode=True)
            if payload:
                decoded = payload.decode(charset, errors="replace")
                if ctype == "text/plain":
                    plain = decoded
                elif ctype == "text/html":
                    htm = decoded
        except Exception:
            pass
    if not plain and htm:
        plain = html_to_text(htm)
    return plain.strip(), htm.strip()


# ---------------------------------------------------------------------------
# IMAPFetcher — one instance per account
# ---------------------------------------------------------------------------

class IMAPFetcher:
    def __init__(self, account: dict):
        """
        account: one entry from config["accounts"]
        Shape: {"id": str, "name": str, "imap": {...}}
        """
        self.account_id   = account["id"]
        self.account_name = account.get("name", account["id"])
        self.imap_cfg     = account["imap"]

    # ---- connection --------------------------------------------------------

    def _connect(self):
        server = self.imap_cfg["server"]
        port   = int(self.imap_cfg.get("port", 993))
        conn   = imaplib.IMAP4_SSL(server, port)
        conn.login(self.imap_cfg["username"], self.imap_cfg["password"])
        return conn

    @staticmethod
    def _quote_folder(folder_name: str) -> str:
        escaped = (folder_name or "").replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'

    # ---- fetching ----------------------------------------------------------

    def _uidvalidity(self, conn) -> str:
        try:
            data = conn.response("UIDVALIDITY")[1]
            if data and data[0]:
                return data[0].decode() if isinstance(data[0], bytes) else str(data[0])
        except Exception:
            pass
        return ""

    def _search_uids(self, conn, mode: str, limit: int, since_date: str, last_seen_uid: int) -> list[bytes]:
        if last_seen_uid > 0:
            status, data = conn.uid("search", None, "UID", f"{last_seen_uid + 1}:*")
        elif mode == "since" and since_date:
            try:
                parsed = datetime.fromisoformat(since_date).strftime("%d-%b-%Y")
            except Exception:
                parsed = since_date
            status, data = conn.uid("search", None, "SINCE", parsed)
        else:
            status, data = conn.uid("search", None, "ALL")
        if status != "OK" or not data:
            return []
        uids = data[0].split()
        if mode == "recent" and limit > 0 and last_seen_uid <= 0:
            uids = uids[-limit:]
        return uids

    def _all_remote_uids(self, conn) -> set[int] | None:
        status, data = conn.uid("search", None, "ALL")
        if status != "OK" or not data:
            return None
        result = set()
        for uid in data[0].split():
            try:
                result.add(int(uid))
            except (TypeError, ValueError):
                continue
        return result

    @staticmethod
    def _fetch_response_flags(fetch_data) -> bytes:
        chunks = []
        for item in fetch_data or []:
            if isinstance(item, tuple):
                chunks.append(item[0] if isinstance(item[0], bytes) else str(item[0]).encode())
            elif isinstance(item, bytes):
                chunks.append(item)
        return b" ".join(chunks)

    @classmethod
    def _flags_from_fetch_response(cls, fetch_data) -> set[bytes]:
        flags_blob = cls._fetch_response_flags(fetch_data)
        match = re.search(br"FLAGS \(([^)]*)\)", flags_blob, flags=re.IGNORECASE)
        return set(match.group(1).lower().split()) if match else set()

    @classmethod
    def _is_read_from_fetch_response(cls, fetch_data) -> bool:
        return b"\\seen" in cls._flags_from_fetch_response(fetch_data)

    @classmethod
    def _is_flagged_from_fetch_response(cls, fetch_data) -> bool:
        return b"\\flagged" in cls._flags_from_fetch_response(fetch_data)

    @staticmethod
    def _parse_uid_flags(fetch_data) -> dict[int, dict]:
        parsed = {}
        for item in fetch_data or []:
            if isinstance(item, tuple):
                blob = item[0] if isinstance(item[0], bytes) else str(item[0]).encode()
            elif isinstance(item, bytes):
                blob = item
            else:
                continue
            uid_match = re.search(br"\bUID\s+(\d+)\b", blob, flags=re.IGNORECASE)
            flags_match = re.search(br"FLAGS\s+\(([^)]*)\)", blob, flags=re.IGNORECASE)
            if not uid_match or not flags_match:
                continue
            flags = set(flags_match.group(1).lower().split())
            parsed[int(uid_match.group(1))] = {
                "is_read": b"\\seen" in flags,
                "is_flagged": b"\\flagged" in flags,
            }
        return parsed

    def _sync_folder_flags(self, conn, folder_name: str, uidvalidity: str) -> int:
        """Mirror remote IMAP read/flagged state without downloading bodies."""
        if not uidvalidity:
            return 0
        tracked_uids = database.get_tracked_imap_uids(self.account_id, folder_name, uidvalidity)
        if not tracked_uids:
            return 0
        updated = 0
        chunk_size = 200
        for idx in range(0, len(tracked_uids), chunk_size):
            uid_set = ",".join(str(uid) for uid in tracked_uids[idx:idx + chunk_size])
            status, flag_data = conn.uid("fetch", uid_set, "(UID FLAGS)")
            if status != "OK" or not flag_data:
                continue
            uid_flags = self._parse_uid_flags(flag_data)
            updated += database.update_email_flags_batch(self.account_id, folder_name, uidvalidity, uid_flags)
        return updated

    @staticmethod
    def _raw_message_from_fetch_response(fetch_data):
        for item in fetch_data or []:
            if isinstance(item, tuple) and item[1]:
                header = item[0] if isinstance(item[0], bytes) else str(item[0]).encode()
                if b"RFC822" in header:
                    return item[1]
        return None

    def _fetch_folder(self, conn, folder_name: str, limit: int, full_resync: bool = False) -> dict:
        try:
            status, _ = conn.select(f'"{folder_name}"', readonly=True)
            if status != "OK":
                print(f"[IMAP] Could not select folder: {folder_name!r}")
                return {"fetched": 0, "removed": 0, "remote": 0}
        except Exception as exc:
            print(f"[IMAP] select error for {folder_name!r}: {exc}")
            return {"fetched": 0, "removed": 0, "remote": 0}

        uidvalidity = self._uidvalidity(conn)
        remote_uids = self._all_remote_uids(conn)
        removed = 0
        if remote_uids is not None:
            removed = database.remove_missing_remote_emails(self.account_id, folder_name, uidvalidity, remote_uids)
        flags_updated = self._sync_folder_flags(conn, folder_name, uidvalidity)
        mode = "all" if full_resync else self.imap_cfg.get("sync_mode", "recent")
        since_date = self.imap_cfg.get("sync_since", "")
        state = database.get_sync_state(self.account_id, folder_name)
        last_seen_uid = 0
        if not full_resync and state and state.get("uidvalidity") == uidvalidity:
            last_seen_uid = int(state.get("last_seen_uid") or 0)

        uids = self._search_uids(conn, mode, limit, since_date, last_seen_uid)
        count = 0
        max_seen_uid = last_seen_uid

        for uid in reversed(uids):
            try:
                uid_int = int(uid)
                max_seen_uid = max(max_seen_uid, uid_int)
                if uidvalidity and database.email_uid_exists(self.account_id, folder_name, uidvalidity, uid_int):
                    if full_resync:
                        _, flag_data = conn.uid("fetch", uid, "(FLAGS)")
                        database.update_email_flags_by_uid(
                            self.account_id,
                            folder_name,
                            uidvalidity,
                            uid_int,
                            self._is_read_from_fetch_response(flag_data),
                            self._is_flagged_from_fetch_response(flag_data),
                        )
                    continue

                _, msg_data = conn.uid("fetch", uid, "(FLAGS RFC822)")
                is_read = self._is_read_from_fetch_response(msg_data)
                is_flagged = self._is_flagged_from_fetch_response(msg_data)
                raw = self._raw_message_from_fetch_response(msg_data)
                if not raw:
                    raise ValueError("No RFC822 payload returned")
                msg = email.message_from_bytes(raw)

                # Raw message-ID (not yet scoped to account)
                raw_id = (msg.get("Message-ID") or "").strip()
                if not raw_id:
                    raw_id = hashlib.md5(
                        f"{msg.get('Subject','')}{msg.get('Date','')}{msg.get('From','')}".encode()
                    ).hexdigest()

                # Composite ID scoped per account to avoid cross-account collisions
                composite_id = f"{self.account_id}::{raw_id}"

                subject = decode_header_value(msg.get("Subject", ""))
                sender  = decode_header_value(msg.get("From", ""))
                date_str = msg.get("Date", "")

                to_str = decode_header_value(msg.get("To", ""))
                cc_str = decode_header_value(msg.get("Cc", ""))
                recipients = [
                    {"name": n, "email": e}
                    for n, e in email.utils.getaddresses([to_str, cc_str])
                    if e
                ]

                body_text, body_html = extract_bodies(msg)
                storage = self.imap_cfg.get("body_storage", "text_html")
                if storage == "text_only":
                    body_html = ""
                elif storage == "headers_only":
                    body_text, body_html = "", ""

                database.save_email({
                    "id":         composite_id,
                    "account_id": self.account_id,
                    "folder":     folder_name,
                    "subject":    subject,
                    "sender":     sender,
                    "recipients": recipients,
                    "date":       date_str,
                    "body_text":  body_text,
                    "body_html":  body_html,
                    "message_id": raw_id,
                    "in_reply_to": (msg.get("In-Reply-To") or "").strip(),
                    "references_header": (msg.get("References") or "").strip(),
                    "imap_uid":   uid_int,
                    "uidvalidity": uidvalidity,
                    "is_read":    is_read,
                    "is_flagged": is_flagged,
                })
                count += 1

            except Exception as exc:
                print(f"[IMAP] Error on uid {uid}: {exc}")
                continue

        if uids:
            database.save_sync_state(self.account_id, folder_name, uidvalidity, max_seen_uid)
        return {"fetched": count, "removed": removed, "flags_updated": flags_updated, "remote": len(remote_uids) if remote_uids is not None else None}

    # ---- IMAP folder discovery ---------------------------------------------

    def list_imap_folders(self) -> list[dict]:
        """Return all IMAP folders as [{name, role}] where role is inbox/sent/other."""
        conn = self._connect()
        _, data = conn.list()
        conn.logout()

        inbox_name = self.imap_cfg.get("inbox_folder", "INBOX")
        sent_name  = self.imap_cfg.get("sent_folder", "Sent Items")
        sync_names = {f["name"] for f in self.imap_cfg.get("sync_folders", [])}

        folders = []
        for line in data:
            if not line:
                continue
            decoded = line.decode() if isinstance(line, bytes) else line
            # Parse: (\HasNoChildren) "/" "Folder Name"  or  (\HasNoChildren) "/" INBOX
            m = re.search(r'"/" (.+)$', decoded) or re.search(r'"\." (.+)$', decoded)
            if not m:
                continue
            raw = m.group(1).strip().strip('"')
            flags = decoded.split(')', 1)[0].lower()
            raw_lower = raw.lower()
            role = "other"
            if raw.upper() == inbox_name.upper():
                role = "inbox"
            elif raw.upper() == sent_name.upper():
                role = "sent"
            elif "\\junk" in flags or raw_lower in {"junk", "spam", "junk email"} or raw_lower.endswith("/spam") or raw_lower.endswith("/junk"):
                role = "spam"
            folders.append({
                "name":    raw,
                "role":    role,
                "checked": raw in sync_names or role in ("inbox", "sent"),
            })

        return sorted(folders, key=lambda f: (f["role"] != "inbox", f["role"] != "sent", f["name"].lower()))

    def _spam_folder_name(self, conn) -> str:
        configured = (self.imap_cfg.get("spam_folder") or "").strip()
        if configured:
            return configured
        for folder in self.imap_cfg.get("sync_folders", []):
            if folder.get("role") == "spam" and folder.get("name"):
                return folder["name"]

        status, data = conn.list()
        if status != "OK" or not data:
            return ""
        fallback = ""
        for line in data:
            if not line:
                continue
            decoded = line.decode() if isinstance(line, bytes) else line
            m = re.search(r'"/" (.+)$', decoded) or re.search(r'"\." (.+)$', decoded)
            if not m:
                continue
            name = m.group(1).strip().strip('"')
            flags = decoded.split(')', 1)[0].lower()
            lower = name.lower()
            if "\\junk" in flags:
                return name
            if lower in {"junk", "spam", "junk email"}:
                return name
            if lower.endswith("/spam") or lower.endswith("/junk"):
                fallback = fallback or name
        return fallback

    def move_email_to_spam(self, email_id: str) -> dict:
        row = database.get_email_by_id(email_id)
        if not row:
            return {"success": False, "error": "Email not found"}
        if row.get("account_id") != self.account_id:
            return {"success": False, "error": "Email belongs to a different account"}

        source_folder = row.get("original_folder") or row.get("folder") or self.imap_cfg.get("inbox_folder", "INBOX")
        imap_uid = row.get("imap_uid")
        uidvalidity = row.get("uidvalidity") or ""
        if not imap_uid or not uidvalidity:
            return {"success": False, "error": "This email has no tracked IMAP UID. Sync the folder before moving it to spam."}

        conn = self._connect()
        try:
            spam_folder = self._spam_folder_name(conn)
            if not spam_folder:
                return {"success": False, "error": "Could not find a spam/junk folder on the IMAP server."}

            status, _ = conn.select(self._quote_folder(source_folder), readonly=False)
            if status != "OK":
                return {"success": False, "error": f"Could not open source folder: {source_folder}"}

            current_uidvalidity = self._uidvalidity(conn)
            if current_uidvalidity and current_uidvalidity != uidvalidity:
                return {"success": False, "error": "The folder UIDVALIDITY changed. Run sync before moving this email."}

            status, data = conn.uid("search", None, "UID", str(int(imap_uid)))
            if status != "OK" or not data or str(int(imap_uid)).encode() not in data[0].split():
                return {"success": False, "error": "The email was not found on the IMAP server. Run sync first."}

            caps = {c.decode().upper() if isinstance(c, bytes) else str(c).upper() for c in getattr(conn, "capabilities", [])}
            if "MOVE" not in caps:
                cap_status, cap_data = conn.capability()
                if cap_status == "OK" and cap_data:
                    caps = {c.decode().upper() if isinstance(c, bytes) else str(c).upper() for c in cap_data[0].split()}
            if "MOVE" not in caps:
                return {"success": False, "error": "This IMAP server does not advertise UID MOVE. No fallback was attempted to avoid risking message loss."}

            status, data = conn.uid("MOVE", str(int(imap_uid)), self._quote_folder(spam_folder))
            if status != "OK":
                detail = data[0].decode(errors="replace") if data and isinstance(data[0], bytes) else str(data)
                return {"success": False, "error": f"IMAP move failed: {detail}"}

            synced_folders = {f.get("name") for f in self._folders_to_sync()}
            if spam_folder in synced_folders:
                database.move_email_local_folder(email_id, spam_folder)
            else:
                database.delete_email_local(email_id)
            database.record_processed_action("spam", email_id=email_id, account_id=self.account_id)
            return {"success": True, "folder": spam_folder}
        finally:
            try:
                conn.logout()
            except Exception:
                pass

    # ---- public API --------------------------------------------------------

    def _folders_to_sync(self) -> list[dict]:
        """Return list of {name, role} folders configured for sync.
        Falls back to inbox_folder + sent_folder if sync_folders not set."""
        if self.imap_cfg.get("sync_folders"):
            return self.imap_cfg["sync_folders"]
        return [
            {"name": self.imap_cfg.get("inbox_folder", "INBOX"),   "role": "inbox"},
            {"name": self.imap_cfg.get("sent_folder", "Sent Items"), "role": "sent"},
        ]

    def sync(self, full_resync: bool = False, progress_callback=None) -> dict:
        results: dict = {"folders": {}, "full_resync": full_resync}
        try:
            if progress_callback:
                prefix = "Full resync" if full_resync else "Sync"
                progress_callback(f"[{self.account_name}] {prefix}: connecting…")
            conn = self._connect()

            limit   = int(self.imap_cfg.get("fetch_limit", 300))
            folders = self._folders_to_sync()

            for f in folders:
                fname = f["name"]
                if progress_callback:
                    action = "Rescanning all messages in" if full_resync else "Fetching"
                    progress_callback(f"[{self.account_name}] {action} «{fname}»…")
                folder_result = self._fetch_folder(conn, fname, limit, full_resync=full_resync)
                results["folders"][fname] = folder_result
                if progress_callback and folder_result.get("removed"):
                    progress_callback(
                        f"[{self.account_name}] Removed {folder_result['removed']} local message(s) missing from «{fname}»"
                    )

            conn.logout()
            results["success"] = True
            results["total"]   = database.get_email_count(account_id=self.account_id)

        except Exception as exc:
            results["success"] = False
            results["error"]   = str(exc)

        return results

    def get_inbox_emails(self, limit: int = 60, offset: int = 0):
        folder = self.imap_cfg.get("inbox_folder", "INBOX")
        return database.get_emails(folder=folder, limit=limit, offset=offset, account_id=self.account_id)

    def get_emails_by_folder(self, folder: str, limit: int = 60, offset: int = 0):
        return database.get_emails(folder=folder, limit=limit, offset=offset, account_id=self.account_id)

    def get_email_detail(self, email_id: str):
        return database.get_email_by_id(email_id)

    def get_folders(self):
        return database.get_folders(account_id=self.account_id)
