"""
Email notification via Azure Communication Services (ACS) Email.
Falls back to Gmail SMTP when ACS returns HTTP 429 (TooManyRequests).
"""

from __future__ import annotations

import base64
import logging
import smtplib
from email import encoders as _email_encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


def send_report(
    *,
    to: list[str],
    subject: str,
    html_body: str,
    attachment_name: str,
    attachment_bytes: bytes,
    acs_connection_string: str,
    acs_sender_address: str,
    gmail_user: str = "",
    gmail_app_password: str = "",
) -> None:
    """Send the Excel report via ACS Email; fall back to Gmail SMTP on 429."""
    if not to:
        logger.warning("[notify] No recipients configured; skipping notification")
        return

    if not acs_connection_string or not acs_sender_address:
        logger.warning("[notify] ACS not configured; trying Gmail SMTP fallback")
        _send_via_gmail(
            to=to,
            subject=subject,
            html_body=html_body,
            attachment_name=attachment_name,
            attachment_bytes=attachment_bytes,
            gmail_user=gmail_user,
            gmail_app_password=gmail_app_password,
        )
        return

    _send_via_acs(
        to=to,
        subject=subject,
        html_body=html_body,
        attachment_name=attachment_name,
        attachment_bytes=attachment_bytes,
        acs_connection_string=acs_connection_string,
        acs_sender_address=acs_sender_address,
        gmail_user=gmail_user,
        gmail_app_password=gmail_app_password,
    )


def _send_via_acs(
    *,
    to: list[str],
    subject: str,
    html_body: str,
    attachment_name: str,
    attachment_bytes: bytes,
    acs_connection_string: str,
    acs_sender_address: str,
    gmail_user: str,
    gmail_app_password: str,
) -> None:
    from azure.communication.email import EmailClient  # type: ignore
    from azure.core.exceptions import HttpResponseError  # type: ignore

    message = {
        "senderAddress": acs_sender_address,
        "recipients": {"to": [{"address": addr} for addr in to]},
        "content": {"subject": subject, "html": html_body},
        "attachments": [
            {
                "name": attachment_name,
                "contentType": (
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                ),
                "contentInBase64": base64.b64encode(attachment_bytes).decode("ascii"),
            }
        ],
    }

    logger.info(
        "[notify] Sending via ACS Email — to=%r  attachment=%r", to, attachment_name
    )
    try:
        client = EmailClient.from_connection_string(acs_connection_string)
        poller = client.begin_send(message)
        result = poller.result()
        logger.info("[notify] ACS Email sent — message_id=%s", result.get("id", "N/A"))
    except HttpResponseError as exc:
        if exc.status_code == 429:
            logger.warning(
                "[notify] ACS TooManyRequests (429) — falling back to Gmail SMTP"
            )
            _send_via_gmail(
                to=to,
                subject=subject,
                html_body=html_body,
                attachment_name=attachment_name,
                attachment_bytes=attachment_bytes,
                gmail_user=gmail_user,
                gmail_app_password=gmail_app_password,
            )
        else:
            raise


def _send_via_gmail(
    *,
    to: list[str],
    subject: str,
    html_body: str,
    attachment_name: str,
    attachment_bytes: bytes,
    gmail_user: str,
    gmail_app_password: str,
) -> None:
    """Send via Gmail SMTP using an App Password."""
    if not gmail_user or not gmail_app_password:
        logger.warning(
            "[notify] GMAIL_USER / GMAIL_APP_PASSWORD not set; cannot use Gmail fallback"
        )
        return

    msg = MIMEMultipart()
    msg["From"] = gmail_user
    msg["To"] = ", ".join(to)
    msg["Subject"] = subject
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    part = MIMEBase("application", "octet-stream")
    part.set_payload(attachment_bytes)
    _email_encoders.encode_base64(part)
    part.add_header("Content-Disposition", "attachment", filename=attachment_name)
    msg.attach(part)

    logger.info(
        "[notify] Sending via Gmail SMTP — to=%r  attachment=%r", to, attachment_name
    )
    with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.login(gmail_user, gmail_app_password)
        smtp.sendmail(gmail_user, to, msg.as_string())
    logger.info("[notify] Gmail SMTP sent — to=%r", to)
