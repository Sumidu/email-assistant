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

    # ---- fetching ----------------------------------------------------------

    def _fetch_folder(self, conn, folder_name: str, limit: int) -> int:
        try:
            status, _ = conn.select(f'"{folder_name}"', readonly=True)
            if status != "OK":
                print(f"[IMAP:{self.account_id}] Could not select folder: {folder_name!r}")
                return 0
        except Exception as exc:
            print(f"[IMAP:{self.account_id}] select error for {folder_name!r}: {exc}")
            return 0

        _, data = conn.search(None, "ALL")
        uids = data[0].split()
        uids = uids[-limit:]
        count = 0

        for uid in reversed(uids):
            try:
                _, msg_data = conn.fetch(uid, "(RFC822)")
                raw = msg_data[0][1]
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
                })
                count += 1

            except Exception as exc:
                print(f"[IMAP:{self.account_id}] Error on uid {uid}: {exc}")
                continue

        return count

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
            role = "other"
            if raw.upper() == inbox_name.upper():
                role = "inbox"
            elif raw.upper() == sent_name.upper():
                role = "sent"
            folders.append({
                "name":    raw,
                "role":    role,
                "checked": raw in sync_names or role in ("inbox", "sent"),
            })

        return sorted(folders, key=lambda f: (f["role"] != "inbox", f["role"] != "sent", f["name"].lower()))

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

    def sync(self, progress_callback=None) -> dict:
        results: dict = {"folders": {}}
        try:
            if progress_callback:
                progress_callback(f"[{self.account_name}] Connecting…")
            conn = self._connect()

            limit   = int(self.imap_cfg.get("fetch_limit", 300))
            folders = self._folders_to_sync()

            for f in folders:
                fname = f["name"]
                if progress_callback:
                    progress_callback(f"[{self.account_name}] Fetching «{fname}»…")
                count = self._fetch_folder(conn, fname, limit)
                results["folders"][fname] = count

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
