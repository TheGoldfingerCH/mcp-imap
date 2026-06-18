"""Tests de configuration multi-compte du serveur MCP IMAP."""

from __future__ import annotations

import os

import pytest

from src.mcp_imap import _get_account_config, _list_accounts


def _clear_mail_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(os.environ):
        if key.startswith("MAIL_"):
            monkeypatch.delenv(key, raising=False)


def test_explicit_default_account_uses_base_mail_env(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_mail_env(monkeypatch)
    monkeypatch.setenv("MAIL_IMAP_HOST", "imap.example.com")
    monkeypatch.setenv("MAIL_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("MAIL_USER", "you@example.com")
    monkeypatch.setenv("MAIL_PASS", "secret")

    cfg = _get_account_config("default")

    assert cfg["imap_host"] == "imap.example.com"
    assert cfg["smtp_host"] == "smtp.example.com"
    assert cfg["user"] == "you@example.com"
    assert cfg["password"] == "secret"
    assert cfg["mail_from"] == "you@example.com"


def test_missing_default_account_reports_base_env_key(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_mail_env(monkeypatch)

    with pytest.raises(ValueError) as exc:
        _get_account_config("default")

    assert "Account 'default' not configured" in str(exc.value)
    assert "MAIL_IMAP_HOST" in str(exc.value)
    assert "MAIL_DEFAULT_IMAP_HOST" not in str(exc.value)


def test_list_accounts_does_not_duplicate_default_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_mail_env(monkeypatch)
    monkeypatch.setenv("MAIL_DEFAULT_IMAP_HOST", "imap.example.com")
    monkeypatch.setenv("MAIL_PRO_IMAP_HOST", "imap.pro.example.com")

    assert _list_accounts() == ["default", "pro"]
