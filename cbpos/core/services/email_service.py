import smtplib
import ssl
import threading
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from typing import Optional, Callable
from cbpos.core.services.config_service import ConfigService


class EmailService:
    """
    Service for sending emails (reports, alerts) using SMTP.
    Runs in a separate thread to avoid blocking the UI.
    """

    @staticmethod
    def send_email(
        to_email: str,
        subject: str,
        body: str,
        attachment_path: Optional[str] = None,
        callback: Optional[Callable[[bool, str], None]] = None,
    ) -> threading.Thread:
        """
        Send an email in a background thread.

        Args:
            to_email: Recipient email address
            subject: Email subject
            body: Email body (plain text)
            attachment_path: Optional path to a file to attach (e.g. PDF)
            callback: Optional function to call when done: callback(success: bool, message: str)

        Returns:
            The Thread object (started).
        """
        thread = threading.Thread(
            target=EmailService._send_email_thread,
            args=(to_email, subject, body, attachment_path, callback),
            daemon=True,
        )
        thread.start()
        return thread

    @staticmethod
    def _send_email_thread(
        to_email: str,
        subject: str,
        body: str,
        attachment_path: Optional[str],
        callback: Optional[Callable[[bool, str], None]],
    ):
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
            # Create Message
            msg = MIMEMultipart()
            msg["From"] = smtp_user
            msg["To"] = to_email
            msg["Subject"] = subject

            msg.attach(MIMEText(body, "plain"))

            # Attach File
            if attachment_path:
                with open(attachment_path, "rb") as f:
                    part = MIMEApplication(f.read(), Name=attachment_path.split("/")[-1])

                # After the file is closed
                filename = attachment_path.split("/")[-1]
                part.add_header("Content-Disposition", "attachment", filename=filename)
                msg.attach(part)

            # Connect and Send
            context = ssl.create_default_context()

            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls(context=context)
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)

            if callback:
                callback(True, "Email sent successfully.")

        except Exception as e:
            if callback:
                callback(False, str(e))

    @staticmethod
    def send_email_with_pdf(to_email: str, subject: str, body: str, pdf_path: str):
        """
        Alias for send_email to match specific requirement.
        """
        return EmailService.send_email(to_email, subject, body, pdf_path)
