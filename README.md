# mcp-imap

A minimal MCP server for reading and sending emails via IMAP/SMTP — works with any mail provider (Infomaniak, Gmail, iCloud, Proton Bridge, etc.) and supports **multiple accounts** in a single instance.

**Zero external dependencies** — uses Python's built-in `imaplib`, `smtplib` and `email` modules only.

Compatible with [Hermes](https://github.com/NousResearch/hermes-agent), [Claude Desktop](https://claude.ai/download), [Cursor](https://cursor.sh), and any MCP-compatible client.

## Tools

| Tool | Description |
|------|-------------|
| `list_accounts` | List all configured mail accounts |
| `list_folders` | List available IMAP folders |
| `list_emails` | List recent emails (with unread filter) |
| `read_email` | Read full email content by UID |
| `search_emails` | Search emails by keyword (subject or sender) |
| `send_email` | Send an email via SMTP |
| `move_email` | Move email to another folder |
| `mark_as_read` | Mark email as read |

All tools accept an optional `account` parameter to target a specific account (e.g. `"pro"`, `"perso"`). Omit it to use the default account.

## Installation

```bash
git clone https://github.com/TheGoldfingerCH/mcp-imap
cd mcp-imap
cp .env.example .env
# Edit .env with your credentials
```

Python 3.12+ required. No `pip install` needed.

## Multi-account setup

Add as many accounts as you need using the `MAIL_<ACCOUNT>_*` pattern in `.env`:

```env
# Default account
MAIL_USER=you@yourdomain.com
MAIL_PASS=password
MAIL_IMAP_HOST=imap.example.com
MAIL_SMTP_HOST=smtp.example.com

# Second account named "pro"
MAIL_PRO_USER=pro@company.com
MAIL_PRO_PASS=password
MAIL_PRO_IMAP_HOST=imap.company.com
MAIL_PRO_SMTP_HOST=smtp.company.com

# Third account named "perso"
MAIL_PERSO_USER=me@gmail.com
MAIL_PERSO_PASS=app_password
MAIL_PERSO_IMAP_HOST=imap.gmail.com
MAIL_PERSO_SMTP_HOST=smtp.gmail.com
```

Then in the AI chat:
- `list_emails()` → default account inbox
- `list_emails(account="pro")` → pro account inbox
- `send_email(to="...", subject="...", body="...", account="perso")` → send from perso account

## Configuration

Edit `.env`:

```env
MAIL_IMAP_HOST=imap.yourprovider.com
MAIL_IMAP_PORT=993

MAIL_SMTP_HOST=smtp.yourprovider.com
MAIL_SMTP_PORT=587

MAIL_USER=you@yourdomain.com
MAIL_PASS=your_password
MAIL_FROM=you@yourdomain.com
```

### Hermes

Add to `~/.hermes/config.yaml` (or `~/.hermes-prive/config.yaml` for a private instance):

```yaml
mcp_servers:
  - name: imap
    command: python
    args:
      - /path/to/mcp-imap/src/cli.py
    env:
      MAIL_IMAP_HOST: imap.yourprovider.com
      MAIL_IMAP_PORT: "993"
      MAIL_SMTP_HOST: smtp.yourprovider.com
      MAIL_SMTP_PORT: "587"
      MAIL_USER: you@yourdomain.com
      MAIL_PASS: your_password
      MAIL_FROM: you@yourdomain.com
```

### Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "imap": {
      "command": "python",
      "args": ["/path/to/mcp-imap/src/cli.py"],
      "env": {
        "MAIL_IMAP_HOST": "imap.yourprovider.com",
        "MAIL_IMAP_PORT": "993",
        "MAIL_SMTP_HOST": "smtp.yourprovider.com",
        "MAIL_SMTP_PORT": "587",
        "MAIL_USER": "you@yourdomain.com",
        "MAIL_PASS": "your_password",
        "MAIL_FROM": "you@yourdomain.com"
      }
    }
  }
}
```

### Cursor

Add to `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "imap": {
      "command": "python",
      "args": ["/path/to/mcp-imap/src/cli.py"],
      "env": {
        "MAIL_IMAP_HOST": "imap.yourprovider.com",
        "MAIL_IMAP_PORT": "993",
        "MAIL_SMTP_HOST": "smtp.yourprovider.com",
        "MAIL_SMTP_PORT": "587",
        "MAIL_USER": "you@yourdomain.com",
        "MAIL_PASS": "your_password",
        "MAIL_FROM": "you@yourdomain.com"
      }
    }
  }
}
```

## Security

- Credentials are read from environment variables or `.env` — never hardcoded
- `.env` is in `.gitignore` — never commit it
- Only `imaplib`, `smtplib`, `email` (Python stdlib) — no supply chain risk
- Email body is truncated at 4000 chars to protect context window

## Provider examples

| Provider | IMAP host | SMTP host | SMTP port |
|----------|-----------|-----------|-----------|
| Infomaniak | `mail.infomaniak.com` | `mail.infomaniak.com` | 587 |
| Gmail | `imap.gmail.com` | `smtp.gmail.com` | 587 |
| iCloud | `imap.mail.me.com` | `smtp.mail.me.com` | 587 |
| Proton Bridge | `127.0.0.1` | `127.0.0.1` | 1025 |

## License

MIT — © [TheGoldfinch](https://github.com/TheGoldfingerCH)
