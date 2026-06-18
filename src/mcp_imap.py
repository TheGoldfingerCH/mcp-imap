"""MCP IMAP/SMTP server — multi-account email access for Hermes and MCP-compatible clients."""

import imaplib
import smtplib
import email
import email.mime.text
import email.mime.multipart
import email.header
import os
import json
from typing import Any

# ── Config multi-compte ────────────────────────────────────────────────────────
# Compte par défaut (MAIL_*)
# Comptes supplémentaires : MAIL_<ACCOUNT>_* (ex: MAIL_PRO_HOST, MAIL_PERSO_HOST)

def _missing_env(keys: list[str]) -> list[str]:
    return [key for key in keys if not os.environ.get(key)]


def _get_account_config(account: str | None) -> dict:
    """Retourne la config IMAP/SMTP pour un compte donné (None/default = compte par défaut)."""
    account_name = (account or "default").strip().lower()
    if account_name == "default":
        required = ["MAIL_IMAP_HOST", "MAIL_SMTP_HOST", "MAIL_USER", "MAIL_PASS"]
        missing = _missing_env(required)
        if missing:
            raise ValueError(f"Account 'default' not configured (missing {', '.join(missing)})")
        return {
            "imap_host": os.environ["MAIL_IMAP_HOST"],
            "imap_port": int(os.environ.get("MAIL_IMAP_PORT", "993")),
            "smtp_host": os.environ["MAIL_SMTP_HOST"],
            "smtp_port": int(os.environ.get("MAIL_SMTP_PORT", "587")),
            "user": os.environ["MAIL_USER"],
            "password": os.environ["MAIL_PASS"],
            "mail_from": os.environ.get("MAIL_FROM", os.environ["MAIL_USER"]),
        }

    prefix = f"MAIL_{account_name.upper()}_"
    required = [f"{prefix}IMAP_HOST", f"{prefix}SMTP_HOST", f"{prefix}USER", f"{prefix}PASS"]
    missing = _missing_env(required)
    if missing:
        raise ValueError(f"Account '{account_name}' not configured (missing {', '.join(missing)})")
    return {
        "imap_host": os.environ[f"{prefix}IMAP_HOST"],
        "imap_port": int(os.environ.get(f"{prefix}IMAP_PORT", "993")),
        "smtp_host": os.environ[f"{prefix}SMTP_HOST"],
        "smtp_port": int(os.environ.get(f"{prefix}SMTP_PORT", "587")),
        "user": os.environ[f"{prefix}USER"],
        "password": os.environ[f"{prefix}PASS"],
        "mail_from": os.environ.get(f"{prefix}FROM", os.environ[f"{prefix}USER"]),
    }


def _list_accounts() -> list[str]:
    """Retourne la liste des comptes configurés."""
    accounts = ["default"]
    for key in os.environ:
        if key.startswith("MAIL_") and key.endswith("_IMAP_HOST"):
            name = key[5:-10].lower()  # MAIL_PRO_IMAP_HOST → pro
            if name and name != "default":
                accounts.append(name)
    return accounts


def _imap_connect(cfg: dict) -> imaplib.IMAP4_SSL:
    conn = imaplib.IMAP4_SSL(cfg["imap_host"], cfg["imap_port"])
    conn.socket().settimeout(15)
    conn.login(cfg["user"], cfg["password"])
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
        "body": body[:4000],
    }


def _sanitize_imap_string(value: str) -> str:
    """Échappe les guillemets pour éviter l'injection dans les commandes IMAP."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


# ── Outils MCP ────────────────────────────────────────────────────────────────

def list_accounts() -> list[str]:
    """Liste les comptes mail configurés."""
    return _list_accounts()


def list_folders(account: str | None = None) -> list[str]:
    """Liste les dossiers IMAP disponibles."""
    cfg = _get_account_config(account)
    conn = _imap_connect(cfg)
    _, folders = conn.list()
    conn.logout()
    result = []
    for f in folders:
        if isinstance(f, bytes):
            parts = f.decode().split('"/"')
            if parts:
                result.append(parts[-1].strip().strip('"'))
    return result


def list_emails(folder: str = "INBOX", limit: int = 20, unread_only: bool = False, account: str | None = None) -> list[dict]:
    """Liste les derniers emails d'un dossier."""
    cfg = _get_account_config(account)
    conn = _imap_connect(cfg)
    conn.select(folder)
    criteria = "UNSEEN" if unread_only else "ALL"
    _, data = conn.search(None, criteria)
    ids = data[0].split()
    ids = list(reversed(ids[-limit:]))

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
                "account": account or "default",
            })
    conn.logout()
    return results


def read_email(uid: str, folder: str = "INBOX", account: str | None = None) -> dict:
    """Lit le contenu complet d'un email par son UID."""
    cfg = _get_account_config(account)
    conn = _imap_connect(cfg)
    conn.select(folder)
    _, data = conn.fetch(uid.encode(), "(RFC822)")
    conn.logout()
    if not data or not data[0]:
        return {"error": f"Message {uid} introuvable"}
    raw = data[0][1] if isinstance(data[0], tuple) else data[0]
    result = _parse_message(raw)
    result["account"] = account or "default"
    return result


def search_emails(query: str, folder: str = "INBOX", limit: int = 10, account: str | None = None) -> list[dict]:
    """Recherche des emails par mot-clé (sujet ou expéditeur)."""
    safe_query = _sanitize_imap_string(query)
    cfg = _get_account_config(account)
    conn = _imap_connect(cfg)
    conn.select(folder)
    _, data = conn.search(None, f'OR SUBJECT "{safe_query}" FROM "{safe_query}"')
    ids = list(reversed(data[0].split()[-limit:]))

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
                "account": account or "default",
            })
    conn.logout()
    return results


def send_email(to: str, subject: str, body: str, cc: str = "", account: str | None = None) -> dict:
    """Envoie un email via SMTP."""
    cfg = _get_account_config(account)
    msg = email.mime.multipart.MIMEMultipart()
    msg["From"] = cfg["mail_from"]
    msg["To"] = to
    msg["Subject"] = subject
    if cc:
        msg["Cc"] = cc
    msg.attach(email.mime.text.MIMEText(body, "plain", "utf-8"))

    recipients = [to] + ([cc] if cc else [])
    with smtplib.SMTP(cfg["smtp_host"], cfg["smtp_port"], timeout=15) as server:
        server.ehlo()
        server.starttls()
        server.login(cfg["user"], cfg["password"])
        server.sendmail(cfg["mail_from"], recipients, msg.as_string())

    return {"status": "sent", "to": to, "subject": subject, "account": account or "default"}


def move_email(uid: str, destination: str, folder: str = "INBOX", account: str | None = None) -> dict:
    """Déplace un email vers un autre dossier."""
    cfg = _get_account_config(account)
    conn = _imap_connect(cfg)
    conn.select(folder)
    conn.copy(uid.encode(), destination)
    conn.store(uid.encode(), "+FLAGS", "\\Deleted")
    conn.expunge()
    conn.logout()
    return {"status": "moved", "uid": uid, "to": destination, "account": account or "default"}


def mark_as_read(uid: str, folder: str = "INBOX", account: str | None = None) -> dict:
    """Marque un email comme lu."""
    cfg = _get_account_config(account)
    conn = _imap_connect(cfg)
    conn.select(folder)
    conn.store(uid.encode(), "+FLAGS", "\\Seen")
    conn.logout()
    return {"status": "marked_read", "uid": uid, "account": account or "default"}


# ── Dispatcher MCP (stdin/stdout JSON-RPC) ────────────────────────────────────

TOOLS = {
    "list_accounts": {
        "description": "List all configured mail accounts",
        "parameters": {"type": "object", "properties": {}, "required": []},
        "fn": list_accounts,
    },
    "list_folders": {
        "description": "List available IMAP folders for an account",
        "parameters": {
            "type": "object",
            "properties": {
                "account": {"type": "string", "description": "Account name (omit for default)"},
            },
            "required": [],
        },
        "fn": list_folders,
    },
    "list_emails": {
        "description": "List recent emails from a folder",
        "parameters": {
            "type": "object",
            "properties": {
                "folder": {"type": "string", "default": "INBOX"},
                "limit": {"type": "integer", "default": 20},
                "unread_only": {"type": "boolean", "default": False},
                "account": {"type": "string", "description": "Account name (omit for default)"},
            },
            "required": [],
        },
        "fn": list_emails,
    },
    "read_email": {
        "description": "Read full email content by UID",
        "parameters": {
            "type": "object",
            "properties": {
                "uid": {"type": "string"},
                "folder": {"type": "string", "default": "INBOX"},
                "account": {"type": "string", "description": "Account name (omit for default)"},
            },
            "required": ["uid"],
        },
        "fn": read_email,
    },
    "search_emails": {
        "description": "Search emails by keyword (subject or sender)",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "folder": {"type": "string", "default": "INBOX"},
                "limit": {"type": "integer", "default": 10},
                "account": {"type": "string", "description": "Account name (omit for default)"},
            },
            "required": ["query"],
        },
        "fn": search_emails,
    },
    "send_email": {
        "description": "Send an email via SMTP",
        "parameters": {
            "type": "object",
            "properties": {
                "to": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
                "cc": {"type": "string", "default": ""},
                "account": {"type": "string", "description": "Account name (omit for default)"},
            },
            "required": ["to", "subject", "body"],
        },
        "fn": send_email,
    },
    "move_email": {
        "description": "Move an email to another folder",
        "parameters": {
            "type": "object",
            "properties": {
                "uid": {"type": "string"},
                "destination": {"type": "string"},
                "folder": {"type": "string", "default": "INBOX"},
                "account": {"type": "string", "description": "Account name (omit for default)"},
            },
            "required": ["uid", "destination"],
        },
        "fn": move_email,
    },
    "mark_as_read": {
        "description": "Mark an email as read",
        "parameters": {
            "type": "object",
            "properties": {
                "uid": {"type": "string"},
                "folder": {"type": "string", "default": "INBOX"},
                "account": {"type": "string", "description": "Account name (omit for default)"},
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
                "serverInfo": {"name": "mcp-imap", "version": "1.1.0"},
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
