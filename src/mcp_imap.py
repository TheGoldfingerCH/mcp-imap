"""MCP IMAP/SMTP server — accès mail depuis Hermes via imaplib/smtplib natifs."""

import imaplib
import smtplib
import email
import email.mime.text
import email.mime.multipart
import email.header
import os
import json
from datetime import datetime
from typing import Any

# ── Config depuis environnement ────────────────────────────────────────────────
IMAP_HOST = os.environ.get("MAIL_IMAP_HOST", "")
IMAP_PORT = int(os.environ.get("MAIL_IMAP_PORT", "993"))
SMTP_HOST = os.environ.get("MAIL_SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("MAIL_SMTP_PORT", "587"))
MAIL_USER = os.environ.get("MAIL_USER", "")
MAIL_PASS = os.environ.get("MAIL_PASS", "")
MAIL_FROM = os.environ.get("MAIL_FROM", MAIL_USER)


def _imap_connect() -> imaplib.IMAP4_SSL:
    conn = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    conn.socket().settimeout(15)
    conn.login(MAIL_USER, MAIL_PASS)
    return conn


def _decode_header(value: str) -> str:
    parts = email.header.decode_header(value)
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return "".join(decoded)


def _parse_message(raw: bytes) -> dict:
    msg = email.message_from_bytes(raw)
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and not part.get("Content-Disposition"):
                payload = part.get_payload(decode=True)
                if payload:
                    body = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
                    break
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            body = payload.decode(msg.get_content_charset() or "utf-8", errors="replace")

    return {
        "subject": _decode_header(msg.get("Subject", "")),
        "from": _decode_header(msg.get("From", "")),
        "to": _decode_header(msg.get("To", "")),
        "date": msg.get("Date", ""),
        "message_id": msg.get("Message-ID", ""),
        "body": body[:4000],  # limite pour le contexte MCP
    }


# ── Outils MCP ────────────────────────────────────────────────────────────────

def list_folders() -> list[str]:
    """Liste les dossiers IMAP disponibles."""
    conn = _imap_connect()
    _, folders = conn.list()
    conn.logout()
    result = []
    for f in folders:
        if isinstance(f, bytes):
            parts = f.decode().split('"/"')
            if parts:
                result.append(parts[-1].strip().strip('"'))
    return result


def list_emails(folder: str = "INBOX", limit: int = 20, unread_only: bool = False) -> list[dict]:
    """Liste les derniers emails d'un dossier."""
    conn = _imap_connect()
    conn.select(folder)
    criteria = "UNSEEN" if unread_only else "ALL"
    _, data = conn.search(None, criteria)
    ids = data[0].split()
    ids = ids[-limit:]  # les plus récents
    ids = list(reversed(ids))

    results = []
    for uid in ids:
        _, msg_data = conn.fetch(uid, "(BODY[HEADER.FIELDS (FROM TO SUBJECT DATE MESSAGE-ID)])")
        if msg_data and msg_data[0]:
            raw = msg_data[0][1] if isinstance(msg_data[0], tuple) else msg_data[0]
            msg = email.message_from_bytes(raw)
            results.append({
                "uid": uid.decode(),
                "subject": _decode_header(msg.get("Subject", "")),
                "from": _decode_header(msg.get("From", "")),
                "date": msg.get("Date", ""),
                "message_id": msg.get("Message-ID", ""),
            })
    conn.logout()
    return results


def read_email(uid: str, folder: str = "INBOX") -> dict:
    """Lit le contenu complet d'un email par son UID."""
    conn = _imap_connect()
    conn.select(folder)
    _, data = conn.fetch(uid.encode(), "(RFC822)")
    conn.logout()
    if not data or not data[0]:
        return {"error": f"Message {uid} introuvable"}
    raw = data[0][1] if isinstance(data[0], tuple) else data[0]
    return _parse_message(raw)


def _sanitize_imap_string(value: str) -> str:
    """Échappe les guillemets pour éviter l'injection dans les commandes IMAP."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def search_emails(query: str, folder: str = "INBOX", limit: int = 10) -> list[dict]:
    """Recherche des emails par mot-clé (sujet ou expéditeur)."""
    safe_query = _sanitize_imap_string(query)
    conn = _imap_connect()
    conn.select(folder)
    _, data = conn.search(None, f'OR SUBJECT "{safe_query}" FROM "{safe_query}"')
    ids = data[0].split()[-limit:]
    ids = list(reversed(ids))

    results = []
    for uid in ids:
        _, msg_data = conn.fetch(uid, "(BODY[HEADER.FIELDS (FROM TO SUBJECT DATE MESSAGE-ID)])")
        if msg_data and msg_data[0]:
            raw = msg_data[0][1] if isinstance(msg_data[0], tuple) else msg_data[0]
            msg = email.message_from_bytes(raw)
            results.append({
                "uid": uid.decode(),
                "subject": _decode_header(msg.get("Subject", "")),
                "from": _decode_header(msg.get("From", "")),
                "date": msg.get("Date", ""),
            })
    conn.logout()
    return results


def send_email(to: str, subject: str, body: str, cc: str = "") -> dict:
    """Envoie un email via SMTP."""
    msg = email.mime.multipart.MIMEMultipart()
    msg["From"] = MAIL_FROM
    msg["To"] = to
    msg["Subject"] = subject
    if cc:
        msg["Cc"] = cc
    msg.attach(email.mime.text.MIMEText(body, "plain", "utf-8"))

    recipients = [to] + ([cc] if cc else [])
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
        server.ehlo()
        server.starttls()
        server.login(MAIL_USER, MAIL_PASS)
        server.sendmail(MAIL_FROM, recipients, msg.as_string())

    return {"status": "sent", "to": to, "subject": subject}


def move_email(uid: str, destination: str, folder: str = "INBOX") -> dict:
    """Déplace un email vers un autre dossier."""
    conn = _imap_connect()
    conn.select(folder)
    conn.copy(uid.encode(), destination)
    conn.store(uid.encode(), "+FLAGS", "\\Deleted")
    conn.expunge()
    conn.logout()
    return {"status": "moved", "uid": uid, "to": destination}


def mark_as_read(uid: str, folder: str = "INBOX") -> dict:
    """Marque un email comme lu."""
    conn = _imap_connect()
    conn.select(folder)
    conn.store(uid.encode(), "+FLAGS", "\\Seen")
    conn.logout()
    return {"status": "marked_read", "uid": uid}


# ── Dispatcher MCP (stdin/stdout JSON-RPC) ────────────────────────────────────

TOOLS = {
    "list_folders": {
        "description": "Liste les dossiers IMAP disponibles",
        "parameters": {"type": "object", "properties": {}, "required": []},
        "fn": list_folders,
    },
    "list_emails": {
        "description": "Liste les derniers emails d'un dossier",
        "parameters": {
            "type": "object",
            "properties": {
                "folder": {"type": "string", "default": "INBOX"},
                "limit": {"type": "integer", "default": 20},
                "unread_only": {"type": "boolean", "default": False},
            },
            "required": [],
        },
        "fn": list_emails,
    },
    "read_email": {
        "description": "Lit le contenu complet d'un email par son UID",
        "parameters": {
            "type": "object",
            "properties": {
                "uid": {"type": "string"},
                "folder": {"type": "string", "default": "INBOX"},
            },
            "required": ["uid"],
        },
        "fn": read_email,
    },
    "search_emails": {
        "description": "Recherche des emails par mot-clé (sujet ou expéditeur)",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "folder": {"type": "string", "default": "INBOX"},
                "limit": {"type": "integer", "default": 10},
            },
            "required": ["query"],
        },
        "fn": search_emails,
    },
    "send_email": {
        "description": "Envoie un email",
        "parameters": {
            "type": "object",
            "properties": {
                "to": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
                "cc": {"type": "string", "default": ""},
            },
            "required": ["to", "subject", "body"],
        },
        "fn": send_email,
    },
    "move_email": {
        "description": "Déplace un email vers un autre dossier",
        "parameters": {
            "type": "object",
            "properties": {
                "uid": {"type": "string"},
                "destination": {"type": "string"},
                "folder": {"type": "string", "default": "INBOX"},
            },
            "required": ["uid", "destination"],
        },
        "fn": move_email,
    },
    "mark_as_read": {
        "description": "Marque un email comme lu",
        "parameters": {
            "type": "object",
            "properties": {
                "uid": {"type": "string"},
                "folder": {"type": "string", "default": "INBOX"},
            },
            "required": ["uid"],
        },
        "fn": mark_as_read,
    },
}


def _handle(request: dict) -> dict:
    method = request.get("method", "")
    req_id = request.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0", "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "mcp-imap", "version": "1.0.0"},
                "capabilities": {"tools": {}},
            },
        }

    if method == "tools/list":
        tools_list = [
            {
                "name": name,
                "description": spec["description"],
                "inputSchema": spec["parameters"],
            }
            for name, spec in TOOLS.items()
        ]
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": tools_list}}

    if method == "tools/call":
        tool_name = request.get("params", {}).get("name", "")
        args = request.get("params", {}).get("arguments", {})
        if tool_name not in TOOLS:
            return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Tool '{tool_name}' not found"}}
        try:
            result = TOOLS[tool_name]["fn"](**args)
            return {
                "jsonrpc": "2.0", "id": req_id,
                "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
            }
        except Exception as e:
            return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32603, "message": str(e)}}

    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Method '{method}' not found"}}


def main():
    import sys
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue
        response = _handle(request)
        print(json.dumps(response), flush=True)


if __name__ == "__main__":
    main()
