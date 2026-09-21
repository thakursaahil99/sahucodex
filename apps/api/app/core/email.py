"""Outbound email. `console` is a development mailbox; `smtp` works with any SMTP server (e.g. Mailpit)."""

from __future__ import annotations

import asyncio
import smtplib
import sys
from email.message import EmailMessage
from typing import Protocol

from app.core.config import Settings
from app.core.logging import get_logger

log = get_logger(__name__)


class EmailSender(Protocol):
    async def send(self, to: str, subject: str, body: str) -> None: ...


class ConsoleEmailSender:
    """Prints the message to stdout. Development only — links in the body are credentials,
    so this bypasses the structured logger and is rejected in production by Settings."""

    async def send(self, to: str, subject: str, body: str) -> None:
        sys.stdout.write(
            f"\n===== DEV MAILBOX =====\nTo: {to}\nSubject: {subject}\n\n{body}\n=======================\n"
        )
        sys.stdout.flush()


class SmtpEmailSender:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def send(self, to: str, subject: str, body: str) -> None:
        await asyncio.to_thread(self._send_blocking, to, subject, body)

    def _send_blocking(self, to: str, subject: str, body: str) -> None:
        cfg = self._settings
        message = EmailMessage()
        message["From"] = cfg.email_from
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)
        with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=10) as smtp:
            if cfg.smtp_starttls:
                smtp.starttls()
            if cfg.smtp_username and cfg.smtp_password:
                smtp.login(cfg.smtp_username, cfg.smtp_password.get_secret_value())
            smtp.send_message(message)


def build_email_sender(settings: Settings) -> EmailSender:
    return SmtpEmailSender(settings) if settings.email_backend == "smtp" else ConsoleEmailSender()


async def send_email_safely(sender: EmailSender, to: str, subject: str, body: str) -> None:
    """Background-task wrapper: a mail failure must never surface to the caller."""
    try:
        await sender.send(to, subject, body)
    except Exception as exc:
        log.error("email_send_failed", error=type(exc).__name__)
