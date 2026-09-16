import logging
import smtplib
import ssl
import threading
from collections.abc import Callable
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from cbpos.core.services.config_service import ConfigService

logger = logging.getLogger(__name__)


def _send_email_task(
    to_email: str,
    subject: str,
    body: str,
    attachment_path: str | None,
    callback: Callable[[bool, str], None] | None,
) -> None:
    """Background task that sends an email via SMTP."""
    config = ConfigService.get_all()
    smtp_host = config.get("smtp_host", "")
    smtp_port = int(config.get("smtp_port", "587"))
    smtp_user = config.get("smtp_user", "")
    smtp_pass = config.get("smtp_pass", "")

    if not all([smtp_host, smtp_port, smtp_user, smtp_pass]):
        if callback:
            callback(False, "SMTP configuration is incomplete.")
        return

    try:
        msg = MIMEMultipart()
        msg["From"] = smtp_user
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        if attachment_path:
            with open(attachment_path, "rb") as f:
                filename = attachment_path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
                part = MIMEApplication(f.read(), Name=filename)
            part.add_header("Content-Disposition", "attachment", filename=filename)
            msg.attach(part)

        context = ssl.create_default_context()
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls(context=context)
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)

        if callback:
            callback(True, "Email sent successfully.")

    except Exception as e:
        logger.error("Failed to send email: %s", e)
        if callback:
            callback(False, str(e))


class EmailService:
    """
    Service for sending emails (reports, alerts) using SMTP.
    Uses threading.Thread for background sending (no PyQt dependency).
    """

    @staticmethod
    def send_email(
        to_email: str,
        subject: str,
        body: str,
        attachment_path: str | None = None,
        callback: Callable[[bool, str], None] | None = None,
    ):
        """
        Send an email in a background thread.

        Args:
            to_email: Recipient email address
            subject: Email subject
            body: Email body (plain text)
            attachment_path: Optional path to a file to attach (e.g. PDF)
            callback: Optional function to call when done: callback(success, message)
        """
        thread = threading.Thread(
            target=_send_email_task,
            args=(to_email, subject, body, attachment_path, callback),
            daemon=True,
        )
        thread.start()

    @staticmethod
    def send_email_with_pdf(
        to_email: str,
        subject: str,
        body: str,
        pdf_path: str,
        callback: Callable[[bool, str], None] | None = None,
    ):
        """Alias for send_email with a PDF attachment."""
        EmailService.send_email(to_email, subject, body, pdf_path, callback=callback)
