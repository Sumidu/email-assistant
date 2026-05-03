import re
import html
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse, urlunparse
import xml.etree.ElementTree as ET

import requests
from requests.auth import HTTPBasicAuth
from requests_ntlm import HttpNtlmAuth

from . import database


SYNC_PAST_DAYS = 92
SYNC_FUTURE_DAYS = 183


def _hostname_from_email(username: str) -> str:
    username = (username or "").strip()
    return username.split("@", 1)[1].lower() if "@" in username else ""


def probe_exchange(account: dict) -> dict:
    imap = account.get("imap", {})
    username = imap.get("username", "")
    domain = _hostname_from_email(username)
    server = (imap.get("server") or "").strip().lower()
    candidates = []
    if domain:
        candidates.extend([
            f"https://autodiscover.{domain}/autodiscover/autodiscover.xml",
            f"https://{domain}/autodiscover/autodiscover.xml",
            f"https://mail.{domain}/EWS/Exchange.asmx",
            f"https://{domain}/EWS/Exchange.asmx",
        ])
    if server:
        candidates.append(f"https://{server}/EWS/Exchange.asmx")
    candidates.append("https://outlook.office365.com/EWS/Exchange.asmx")

    seen = set()
    checks = []
    for url in candidates:
        if url in seen:
            continue
        seen.add(url)
        try:
            resp = requests.get(url, timeout=8, allow_redirects=True)
            reachable = resp.status_code in (200, 401, 403, 405)
            checks.append({
                "url": url,
                "status": resp.status_code,
                "reachable": reachable,
                "auth_challenge": resp.status_code in (401, 403),
                "server": resp.headers.get("server", ""),
            })
        except requests.RequestException as exc:
            checks.append({"url": url, "reachable": False, "error": str(exc)})

    reachable_ews = [c for c in checks if "/EWS/" in c["url"] and c.get("reachable")]
    reachable_autodiscover = [c for c in checks if "autodiscover" in c["url"] and c.get("reachable")]
    is_exchange_online = any("outlook.office365.com" in c["url"] and c.get("reachable") for c in checks)
    if is_exchange_online:
        recommendation = "Microsoft Graph OAuth is the preferred route. EWS may answer, but Exchange Online commonly blocks basic auth."
    elif reachable_ews:
        recommendation = "EWS appears reachable. Native Exchange calendar sync may be possible if the server allows EWS authentication."
    elif reachable_autodiscover:
        recommendation = "Autodiscover is reachable. We can try to resolve the EWS endpoint next."
    else:
        recommendation = "No Exchange calendar endpoint was reachable from this machine."

    return {
        "success": bool(reachable_ews or reachable_autodiscover or is_exchange_online),
        "account": account.get("name", account.get("id", "")),
        "domain": domain,
        "exchange_online_hint": is_exchange_online,
        "checks": checks,
        "recommendation": recommendation,
        "graph_note": "Graph calendar sync needs Microsoft OAuth/app registration and Calendars.ReadBasic or Calendars.Read permission.",
    }


def _ews_urls(account: dict) -> list[str]:
    imap = account.get("imap", {})
    username = imap.get("username", "")
    domain = _hostname_from_email(username)
    server = (imap.get("server") or "").strip().lower()
    candidates = []
    if imap.get("ews_url"):
        candidates.append(imap["ews_url"])
    if domain:
        candidates.extend([
            f"https://{domain}/EWS/Exchange.asmx",
            f"https://mail.{domain}/EWS/Exchange.asmx",
            f"https://autodiscover.{domain}/EWS/Exchange.asmx",
        ])
    if server:
        candidates.append(f"https://{server}/EWS/Exchange.asmx")
    candidates.append("https://outlook.office365.com/EWS/Exchange.asmx")
    seen = set()
    result = []
    for url in candidates:
        if url not in seen:
            seen.add(url)
            result.append(url)
    return result


def _ews_get_calendar_folder_xml() -> str:
    return """<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
               xmlns:m="http://schemas.microsoft.com/exchange/services/2006/messages"
               xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types"
               xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Header>
    <t:RequestServerVersion Version="Exchange2013" />
  </soap:Header>
  <soap:Body>
    <m:GetFolder>
      <m:FolderShape>
        <t:BaseShape>IdOnly</t:BaseShape>
        <t:AdditionalProperties>
          <t:FieldURI FieldURI="folder:DisplayName" />
          <t:FieldURI FieldURI="folder:TotalCount" />
        </t:AdditionalProperties>
      </m:FolderShape>
      <m:FolderIds>
        <t:DistinguishedFolderId Id="calendar" />
      </m:FolderIds>
    </m:GetFolder>
  </soap:Body>
</soap:Envelope>"""


def _ews_find_calendar_items_xml(start: datetime, end: datetime) -> str:
    start_utc = start.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    end_utc = end.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
               xmlns:m="http://schemas.microsoft.com/exchange/services/2006/messages"
               xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types"
               xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Header>
    <t:RequestServerVersion Version="Exchange2013" />
  </soap:Header>
  <soap:Body>
    <m:FindItem Traversal="Shallow">
      <m:ItemShape>
        <t:BaseShape>IdOnly</t:BaseShape>
        <t:AdditionalProperties>
          <t:FieldURI FieldURI="item:Subject" />
          <t:FieldURI FieldURI="calendar:Start" />
          <t:FieldURI FieldURI="calendar:End" />
          <t:FieldURI FieldURI="calendar:IsAllDayEvent" />
          <t:FieldURI FieldURI="calendar:Location" />
          <t:FieldURI FieldURI="calendar:LegacyFreeBusyStatus" />
        </t:AdditionalProperties>
      </m:ItemShape>
      <m:CalendarView MaxEntriesReturned="1000" StartDate="{start_utc}" EndDate="{end_utc}" />
      <m:ParentFolderIds>
        <t:DistinguishedFolderId Id="calendar" />
      </m:ParentFolderIds>
    </m:FindItem>
  </soap:Body>
</soap:Envelope>"""


def _ews_create_tasks_xml(todos: list[dict]) -> str:
    items = []
    for todo in todos:
        title = html.escape(str(todo.get("title") or "").strip())
        if not title:
            continue
        description_parts = [str(todo.get("description") or "").strip()]
        location = str(todo.get("location") or "").strip()
        if location:
            description_parts.append(f"Location: {location}")
        tags = todo.get("tags") if isinstance(todo.get("tags"), list) else []
        if tags:
            description_parts.append("Tags: " + ", ".join(str(tag) for tag in tags if str(tag).strip()))
        body = html.escape("\n".join(part for part in description_parts if part))
        due = str(todo.get("due_date") or "").strip()
        due_xml = ""
        if re.match(r"^\d{4}-\d{2}-\d{2}$", due):
            due_xml = f"<t:DueDate>{due}T12:00:00Z</t:DueDate>"
        elif due:
            body = html.escape((html.unescape(body) + f"\nDue: {due}").strip())
        categories = "".join(
            f"<t:String>{html.escape(str(tag).strip())}</t:String>"
            for tag in tags
            if str(tag).strip()
        )
        categories_xml = f"<t:Categories>{categories}</t:Categories>" if categories else ""
        items.append(f"""
          <t:Task>
            <t:Subject>{title}</t:Subject>
            <t:Body BodyType="Text">{body}</t:Body>
            {categories_xml}
            {due_xml}
            <t:Status>NotStarted</t:Status>
          </t:Task>""")
    return f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
               xmlns:m="http://schemas.microsoft.com/exchange/services/2006/messages"
               xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types"
               xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Header>
    <t:RequestServerVersion Version="Exchange2013" />
  </soap:Header>
  <soap:Body>
    <m:CreateItem MessageDisposition="SaveOnly">
      <m:SavedItemFolderId>
        <t:DistinguishedFolderId Id="tasks" />
      </m:SavedItemFolderId>
      <m:Items>
        {"".join(items)}
      </m:Items>
    </m:CreateItem>
  </soap:Body>
</soap:Envelope>"""


def test_ews_calendar(account: dict) -> dict:
    imap = account.get("imap", {})
    username = (imap.get("username") or "").strip()
    password = imap.get("password") or ""
    if not username or not password or password == "••••••••":
        return {"success": False, "error": "Username and saved account password are required for the EWS test."}

    headers = {
        "Content-Type": "text/xml; charset=utf-8",
        "Accept": "text/xml",
        "User-Agent": "EmailAssistant-EWS-Probe/1.0",
    }
    body = _ews_get_calendar_folder_xml().encode("utf-8")
    attempts = []
    for url in _ews_urls(account):
        try:
            resp = requests.post(
                url,
                data=body,
                headers=headers,
                auth=HTTPBasicAuth(username, password),
                timeout=15,
                allow_redirects=True,
            )
            text = resp.text[:1200]
            ok = resp.status_code == 200 and "ResponseClass=\"Success\"" in resp.text
            attempts.append({
                "url": url,
                "status": resp.status_code,
                "success": ok,
                "auth_challenge": resp.status_code in (401, 403),
                "error": "" if ok else _ews_error_summary(text),
            })
            if ok:
                return {
                    "success": True,
                    "url": url,
                    "message": "EWS calendar folder is accessible with the saved account credentials.",
                    "attempts": attempts,
                }
        except requests.RequestException as exc:
            attempts.append({"url": url, "success": False, "error": str(exc)})

    return {
        "success": False,
        "error": "EWS calendar access did not succeed with HTTP Basic authentication. The server may require NTLM, OAuth, VPN, or may block EWS for this account.",
        "attempts": attempts,
    }


def _ntlm_username_variants(username: str) -> list[str]:
    username = username.strip()
    variants = [username]
    if "@" in username:
        local, domain = username.split("@", 1)
        netbios = domain.split(".", 1)[0].upper()
        variants.append(f"{netbios}\\{local}")
    seen = set()
    result = []
    for item in variants:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def test_ews_calendar_ntlm(account: dict) -> dict:
    imap = account.get("imap", {})
    username = (imap.get("username") or "").strip()
    password = imap.get("password") or ""
    if not username or not password or password == "••••••••":
        return {"success": False, "error": "Username and saved account password are required for the NTLM EWS test."}

    headers = {
        "Content-Type": "text/xml; charset=utf-8",
        "Accept": "text/xml",
        "User-Agent": "EmailAssistant-EWS-NTLM-Probe/1.0",
    }
    body = _ews_get_calendar_folder_xml().encode("utf-8")
    attempts = []
    for url in _ews_urls(account):
        for ntlm_user in _ntlm_username_variants(username):
            try:
                resp = requests.post(
                    url,
                    data=body,
                    headers=headers,
                    auth=HttpNtlmAuth(ntlm_user, password),
                    timeout=20,
                    allow_redirects=True,
                )
                text = resp.text[:1200]
                ok = resp.status_code == 200 and "ResponseClass=\"Success\"" in resp.text
                attempts.append({
                    "url": url,
                    "username_format": "domain\\user" if "\\" in ntlm_user else "email",
                    "status": resp.status_code,
                    "success": ok,
                    "auth_challenge": resp.status_code in (401, 403),
                    "error": "" if ok else _ews_error_summary(text),
                })
                if ok:
                    return {
                        "success": True,
                        "url": url,
                        "username_format": "domain\\user" if "\\" in ntlm_user else "email",
                        "message": "EWS calendar folder is accessible with NTLM authentication.",
                        "attempts": attempts,
                    }
            except requests.RequestException as exc:
                attempts.append({
                    "url": url,
                    "username_format": "domain\\user" if "\\" in ntlm_user else "email",
                    "success": False,
                    "error": str(exc),
                })

    return {
        "success": False,
        "error": "EWS calendar access did not succeed with NTLM authentication.",
        "attempts": attempts,
    }


def _ews_error_summary(text: str) -> str:
    for tag in ("MessageText", "ResponseCode", "faultstring"):
        match = re.search(rf"<(?:[^:>]+:)?{tag}[^>]*>(.*?)</(?:[^:>]+:)?{tag}>", text, re.DOTALL)
        if match:
            return re.sub(r"\s+", " ", match.group(1)).strip()[:240]
    return re.sub(r"\s+", " ", text).strip()[:240]


def _xml_text(node, path: str, ns: dict) -> str:
    found = node.find(path, ns)
    return found.text.strip() if found is not None and found.text else ""


def _parse_ews_datetime(value: str) -> datetime | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        if value.endswith("Z"):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.astimezone()
        return parsed
    except ValueError:
        return None


def _parse_ews_calendar_items(xml_text: str, source: str) -> list[dict]:
    ns = {
        "s": "http://schemas.xmlsoap.org/soap/envelope/",
        "m": "http://schemas.microsoft.com/exchange/services/2006/messages",
        "t": "http://schemas.microsoft.com/exchange/services/2006/types",
    }
    root = ET.fromstring(xml_text)
    events = []
    for item in root.findall(".//t:CalendarItem", ns):
        item_id = item.find("t:ItemId", ns)
        uid = item_id.get("Id") if item_id is not None else ""
        change_key = item_id.get("ChangeKey") if item_id is not None else ""
        start = _parse_ews_datetime(_xml_text(item, "t:Start", ns))
        end = _parse_ews_datetime(_xml_text(item, "t:End", ns))
        if not start or not end:
            continue
        all_day = _xml_text(item, "t:IsAllDayEvent", ns).lower() == "true"
        title = _xml_text(item, "t:Subject", ns) or "(busy)"
        location = _xml_text(item, "t:Location", ns)
        busy = _xml_text(item, "t:LegacyFreeBusyStatus", ns)
        events.append({
            "uid": uid or f"{title}:{start.isoformat()}",
            "occurrence": f"{start.isoformat()}:{change_key[:16]}",
            "title": title,
            "start_ts": start.timestamp(),
            "end_ts": end.timestamp(),
            "start_iso": start.isoformat(),
            "end_iso": end.isoformat(),
            "all_day": all_day,
            "location": location,
            "description": f"Free/busy: {busy}" if busy else "",
            "source": f"ews_ntlm:{source}",
        })
    return events


def _chunk_window(start: datetime, end: datetime, days: int = 31):
    cursor = start
    while cursor < end:
        chunk_end = min(cursor + timedelta(days=days), end)
        yield cursor, chunk_end
        cursor = chunk_end


def sync_ews_ntlm_calendar(account: dict, start: datetime, end: datetime, progress_callback=None) -> dict:
    imap = account.get("imap", {})
    username = (imap.get("username") or "").strip()
    password = imap.get("password") or ""
    if not username or not password or password == "••••••••":
        return {"success": False, "error": "Username and saved account password are required for EWS NTLM sync."}

    headers = {
        "Content-Type": "text/xml; charset=utf-8",
        "Accept": "text/xml",
        "User-Agent": "EmailAssistant-EWS-NTLM-Sync/1.0",
    }
    errors = []
    for url in _ews_urls(account):
        for ntlm_user in _ntlm_username_variants(username):
            all_events = []
            ok_chunks = 0
            try:
                for chunk_start, chunk_end in _chunk_window(start, end):
                    if progress_callback:
                        progress_callback(
                            f"[{account.get('name', account['id'])}] EWS {chunk_start.strftime('%Y-%m-%d')}–{chunk_end.strftime('%Y-%m-%d')}…"
                        )
                    resp = requests.post(
                        url,
                        data=_ews_find_calendar_items_xml(chunk_start, chunk_end).encode("utf-8"),
                        headers=headers,
                        auth=HttpNtlmAuth(ntlm_user, password),
                        timeout=30,
                        allow_redirects=True,
                    )
                    if resp.status_code != 200 or "ResponseClass=\"Success\"" not in resp.text:
                        raise RuntimeError(f"HTTP {resp.status_code}: {_ews_error_summary(resp.text[:1200])}")
                    all_events.extend(_parse_ews_calendar_items(resp.text, url))
                    ok_chunks += 1
                database.replace_calendar_events(account["id"], all_events, start.timestamp(), end.timestamp())
                if progress_callback:
                    progress_callback(f"[{account.get('name', account['id'])}] Stored {len(all_events)} EWS calendar events.")
                return {
                    "success": True,
                    "method": "ews_ntlm",
                    "url": url,
                    "username_format": "domain\\user" if "\\" in ntlm_user else "email",
                    "events": len(all_events),
                    "chunks": ok_chunks,
                    "window_start": start.isoformat(),
                    "window_end": end.isoformat(),
                }
            except Exception as exc:
                errors.append({
                    "url": url,
                    "username_format": "domain\\user" if "\\" in ntlm_user else "email",
                    "error": str(exc),
                    "chunks": ok_chunks,
                })
    return {"success": False, "error": "EWS NTLM calendar sync failed.", "attempts": errors}


def create_ews_ntlm_tasks(account: dict, todos: list[dict]) -> dict:
    imap = account.get("imap", {})
    username = (imap.get("username") or "").strip()
    password = imap.get("password") or ""
    todos = [todo for todo in todos if isinstance(todo, dict) and str(todo.get("title") or "").strip()]
    if not todos:
        return {"success": False, "error": "No selected todos to create."}
    if not username or not password or password == "••••••••":
        return {"success": False, "error": "Username and saved account password are required for EWS task creation."}

    headers = {
        "Content-Type": "text/xml; charset=utf-8",
        "Accept": "text/xml",
        "User-Agent": "EmailAssistant-EWS-NTLM-Tasks/1.0",
    }
    body = _ews_create_tasks_xml(todos).encode("utf-8")
    errors = []
    for url in _ews_urls(account):
        for ntlm_user in _ntlm_username_variants(username):
            try:
                resp = requests.post(
                    url,
                    data=body,
                    headers=headers,
                    auth=HttpNtlmAuth(ntlm_user, password),
                    timeout=30,
                    allow_redirects=True,
                )
                ok = resp.status_code == 200 and "ResponseClass=\"Success\"" in resp.text
                if ok:
                    return {
                        "success": True,
                        "method": "ews_ntlm",
                        "url": url,
                        "username_format": "domain\\user" if "\\" in ntlm_user else "email",
                        "created": len(todos),
                    }
                errors.append({
                    "url": url,
                    "username_format": "domain\\user" if "\\" in ntlm_user else "email",
                    "status": resp.status_code,
                    "error": _ews_error_summary(resp.text[:1600]),
                })
            except requests.RequestException as exc:
                errors.append({
                    "url": url,
                    "username_format": "domain\\user" if "\\" in ntlm_user else "email",
                    "error": str(exc),
                })
    return {"success": False, "error": "EWS NTLM task creation failed.", "attempts": errors}


def start_graph_device_code(client_id: str, tenant_id: str = "common") -> dict:
    tenant = (tenant_id or "common").strip()
    url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/devicecode"
    data = {
        "client_id": client_id.strip(),
        "scope": "offline_access User.Read Calendars.ReadBasic",
    }
    resp = requests.post(url, data=data, timeout=20)
    payload = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {"error_description": resp.text}
    if resp.status_code >= 400:
        return {"success": False, "error": payload.get("error_description") or payload.get("error") or resp.text}
    payload["success"] = True
    return payload


def poll_graph_device_code(client_id: str, device_code: str, tenant_id: str = "common") -> dict:
    tenant = (tenant_id or "common").strip()
    url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
    data = {
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        "client_id": client_id.strip(),
        "device_code": device_code,
    }
    resp = requests.post(url, data=data, timeout=20)
    payload = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {"error_description": resp.text}
    if payload.get("error") == "authorization_pending":
        return {"success": False, "pending": True, "error": "Authorization pending."}
    if payload.get("error") == "slow_down":
        return {"success": False, "pending": True, "slow_down": True, "error": "Polling too quickly."}
    if resp.status_code >= 400:
        return {"success": False, "error": payload.get("error_description") or payload.get("error") or resp.text}

    token = payload.get("access_token")
    if not token:
        return {"success": False, "error": "No access token returned."}

    now = datetime.now(timezone.utc)
    end = now + timedelta(days=7)
    params = {
        "startDateTime": now.isoformat().replace("+00:00", "Z"),
        "endDateTime": end.isoformat().replace("+00:00", "Z"),
        "$top": "10",
        "$select": "subject,start,end,isAllDay",
    }
    graph_resp = requests.get(
        "https://graph.microsoft.com/v1.0/me/calendarView",
        headers={"Authorization": f"Bearer {token}", "Prefer": 'outlook.timezone="Europe/Berlin"'},
        params=params,
        timeout=20,
    )
    graph_payload = graph_resp.json() if graph_resp.headers.get("content-type", "").startswith("application/json") else {"error": graph_resp.text}
    if graph_resp.status_code >= 400:
        return {
            "success": False,
            "token_ok": True,
            "error": graph_payload.get("error", {}).get("message") if isinstance(graph_payload.get("error"), dict) else str(graph_payload.get("error")),
        }
    events = graph_payload.get("value", [])
    return {
        "success": True,
        "token_ok": True,
        "event_count": len(events),
        "sample_events": [
            {
                "subject": event.get("subject", "(busy)"),
                "start": event.get("start", {}).get("dateTime"),
                "end": event.get("end", {}).get("dateTime"),
                "all_day": event.get("isAllDay", False),
            }
            for event in events[:3]
        ],
    }


def sync_window(now=None):
    now = now or datetime.now().astimezone()
    start = now - timedelta(days=SYNC_PAST_DAYS)
    end = now + timedelta(days=SYNC_FUTURE_DAYS)
    return start, end


def _clean_ics_url(url: str) -> str:
    url = (url or "").strip()
    if url.startswith("webcal://"):
        parsed = urlparse(url)
        return urlunparse(("https",) + parsed[1:])
    return url


def _unfold_ics(text: str) -> list[str]:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    unfolded = []
    for line in lines:
        if line.startswith((" ", "\t")) and unfolded:
            unfolded[-1] += line[1:]
        else:
            unfolded.append(line)
    return unfolded


def _decode_ics_text(value: str) -> str:
    return (
        value.replace("\\n", "\n")
        .replace("\\N", "\n")
        .replace("\\,", ",")
        .replace("\\;", ";")
        .replace("\\\\", "\\")
        .strip()
    )


def _parse_ics_datetime(raw: str, params: str = "") -> tuple[datetime | None, bool]:
    raw = (raw or "").strip()
    all_day = "VALUE=DATE" in params or re.fullmatch(r"\d{8}", raw or "") is not None
    try:
        if all_day:
            return datetime.strptime(raw[:8], "%Y%m%d").replace(tzinfo=timezone.utc), True
        if raw.endswith("Z"):
            return datetime.strptime(raw, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc), False
        return datetime.strptime(raw[:15], "%Y%m%dT%H%M%S").astimezone(), False
    except Exception:
        return None, all_day


def _split_prop(line: str) -> tuple[str, str, str]:
    left, _, value = line.partition(":")
    name, _, params = left.partition(";")
    return name.upper(), params.upper(), value


def _parse_rrule(value: str) -> dict:
    result = {}
    for part in value.split(";"):
        key, _, val = part.partition("=")
        if key and val:
            result[key.upper()] = val
    return result


def _add_month(dt: datetime, months: int) -> datetime:
    month = dt.month - 1 + months
    year = dt.year + month // 12
    month = month % 12 + 1
    days = [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    return dt.replace(year=year, month=month, day=min(dt.day, days[month - 1]))


def _expand_event(event: dict, window_start: datetime, window_end: datetime) -> list[dict]:
    start = event.get("start")
    end = event.get("end") or (start + timedelta(hours=1) if start else None)
    if not start or not end:
        return []

    rrule = event.get("rrule") or {}
    duration = end - start
    occurrences = []

    if not rrule:
        candidates = [(start, end)]
    else:
        freq = rrule.get("FREQ", "").upper()
        interval = max(1, int(rrule.get("INTERVAL", "1") or 1))
        count = int(rrule.get("COUNT", "0") or 0)
        until = None
        if rrule.get("UNTIL"):
            until, _ = _parse_ics_datetime(rrule["UNTIL"])
        step_days = {"DAILY": 1, "WEEKLY": 7}.get(freq)
        candidates = []
        current = start
        i = 0
        while current <= window_end and i < 1000:
            if (not until or current <= until) and (not count or i < count):
                candidates.append((current, current + duration))
            if count and i >= count - 1:
                break
            if freq == "MONTHLY":
                current = _add_month(current, interval)
            elif step_days:
                current += timedelta(days=step_days * interval)
            else:
                break
            i += 1

    for occ_start, occ_end in candidates:
        if occ_end < window_start or occ_start > window_end:
            continue
        occurrences.append({
            "uid": event.get("uid") or f"{event.get('title', 'event')}:{occ_start.isoformat()}",
            "occurrence": occ_start.isoformat(),
            "title": event.get("title") or "(busy)",
            "start_ts": occ_start.timestamp(),
            "end_ts": occ_end.timestamp(),
            "start_iso": occ_start.isoformat(),
            "end_iso": occ_end.isoformat(),
            "all_day": event.get("all_day", False),
            "location": event.get("location", ""),
            "description": event.get("description", ""),
            "source": event.get("source", "ics"),
        })
    return occurrences


def parse_ics(text: str, window_start: datetime, window_end: datetime, source: str = "ics") -> list[dict]:
    events = []
    current = None
    for line in _unfold_ics(text):
        if line == "BEGIN:VEVENT":
            current = {"source": source}
            continue
        if line == "END:VEVENT" and current is not None:
            events.extend(_expand_event(current, window_start, window_end))
            current = None
            continue
        if current is None or ":" not in line:
            continue
        name, params, value = _split_prop(line)
        if name == "UID":
            current["uid"] = value.strip()
        elif name == "SUMMARY":
            current["title"] = _decode_ics_text(value)
        elif name == "LOCATION":
            current["location"] = _decode_ics_text(value)
        elif name == "DESCRIPTION":
            current["description"] = _decode_ics_text(value)
        elif name == "DTSTART":
            dt, all_day = _parse_ics_datetime(value, params)
            current["start"] = dt
            current["all_day"] = all_day
        elif name == "DTEND":
            dt, all_day = _parse_ics_datetime(value, params)
            current["end"] = dt
            current["all_day"] = current.get("all_day") or all_day
        elif name == "DURATION" and current.get("start"):
            hours = re.search(r"(\d+)H", value)
            minutes = re.search(r"(\d+)M", value)
            current["end"] = current["start"] + timedelta(
                hours=int(hours.group(1)) if hours else 0,
                minutes=int(minutes.group(1)) if minutes else 0,
            )
        elif name == "RRULE":
            current["rrule"] = _parse_rrule(value)
    return events


def sync_account_calendar(account: dict, progress_callback=None) -> dict:
    imap = account.get("imap", {})
    if not imap.get("calendar_enabled"):
        return {"success": False, "error": "Calendar is not enabled for this account."}
    url = _clean_ics_url(imap.get("calendar_url", ""))
    start, end = sync_window()
    provider = imap.get("detected_provider", {}).get("id")
    method = imap.get("calendar_method", "ics")
    if method == "ews_ntlm" or (not url and provider == "outlook"):
        return sync_ews_ntlm_calendar(account, start, end, progress_callback=progress_callback)
    if not url:
        return {"success": False, "error": "Calendar URL is missing."}

    if progress_callback:
        progress_callback(f"[{account.get('name', account['id'])}] Fetching calendar…")
    response = requests.get(url, timeout=45)
    response.raise_for_status()
    events = parse_ics(response.text, start, end, source=urlparse(url).netloc or "ics")
    database.replace_calendar_events(account["id"], events, start.timestamp(), end.timestamp())
    if progress_callback:
        progress_callback(f"[{account.get('name', account['id'])}] Stored {len(events)} calendar events.")
    return {"success": True, "events": len(events), "window_start": start.isoformat(), "window_end": end.isoformat()}


def sync_enabled_calendars(config: dict, account_id: str | None = None, progress_callback=None) -> dict:
    results = {}
    for account in config.get("accounts", []):
        if account_id and account["id"] != account_id:
            continue
        imap = account.get("imap", {})
        provider = imap.get("detected_provider", {}).get("id")
        if provider not in ("outlook", "google") and not imap.get("calendar_enabled"):
            continue
        if not imap.get("calendar_enabled"):
            results[account["id"]] = {"success": False, "error": "Calendar not enabled."}
            continue
        try:
            results[account["id"]] = sync_account_calendar(account, progress_callback=progress_callback)
        except Exception as exc:
            results[account["id"]] = {"success": False, "error": str(exc)}
    return {"success": all(r.get("success") for r in results.values()) if results else False, "accounts": results}


def calendar_context(config: dict, days: int = 30) -> str:
    now = datetime.now().astimezone()
    end = now + timedelta(days=days)
    events = database.get_calendar_events(start_ts=now.timestamp(), end_ts=end.timestamp(), limit=120)
    if not events:
        return ""

    lines = [
        "=== LOCAL CALENDAR CONTEXT ===",
        f"Window: {now.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')}",
        "Use this to reason about availability. Do not invent calendar events.",
    ]
    free_slots = _first_free_slots(events, now, min(end, now + timedelta(days=14)))
    if free_slots:
        lines.append("Suggested free 30-minute slots during weekdays 09:00-17:00:")
        for i, (slot_start, slot_end) in enumerate(free_slots, 1):
            lines.append(f"{i}) {slot_start.strftime('%a %Y-%m-%d %H:%M')}–{slot_end.strftime('%H:%M')}")
        lines.append("Busy events:")
    for event in events:
        start = datetime.fromtimestamp(event["start_ts"]).astimezone()
        end_dt = datetime.fromtimestamp(event["end_ts"]).astimezone()
        if event["all_day"]:
            when = start.strftime("%a %Y-%m-%d all day")
        else:
            when = f"{start.strftime('%a %Y-%m-%d %H:%M')}–{end_dt.strftime('%H:%M')}"
        lines.append(f"- {when}: {event.get('title') or '(busy)'}")
    return "\n".join(lines)


def _first_free_slots(events: list[dict], start: datetime, end: datetime, limit: int = 12) -> list[tuple[datetime, datetime]]:
    busy = []
    for event in events:
        if event.get("all_day"):
            continue
        busy.append((
            datetime.fromtimestamp(event["start_ts"]).astimezone(),
            datetime.fromtimestamp(event["end_ts"]).astimezone(),
        ))
    busy.sort()

    slots = []
    day = start.replace(hour=0, minute=0, second=0, microsecond=0)
    while day <= end and len(slots) < limit:
        if day.weekday() < 5:
            cursor = max(start, day.replace(hour=9))
            work_end = day.replace(hour=17)
            while cursor + timedelta(minutes=30) <= work_end and cursor < end and len(slots) < limit:
                candidate_end = cursor + timedelta(minutes=30)
                overlaps = any(b_start < candidate_end and b_end > cursor for b_start, b_end in busy)
                if not overlaps and candidate_end > start:
                    slots.append((cursor, candidate_end))
                cursor += timedelta(minutes=30)
        day += timedelta(days=1)
    return slots
