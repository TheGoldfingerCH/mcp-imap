"""Tests du point d'entrée CLI."""

from __future__ import annotations

import os

from src.cli import _load_env


def test_load_env_ignores_missing_file(tmp_path) -> None:
    _load_env(tmp_path / ".env")


def test_load_env_reads_key_values_without_overriding_existing(tmp_path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "# comment",
                "MAIL_IMAP_HOST=imap.example.com",
                "MAIL_USER=from-file@example.com",
                "",
                "INVALID_LINE",
            ]
        )
    )
    monkeypatch.setenv("MAIL_USER", "existing@example.com")

    _load_env(env_file)

    assert os.environ["MAIL_IMAP_HOST"] == "imap.example.com"
    assert os.environ["MAIL_USER"] == "existing@example.com"
