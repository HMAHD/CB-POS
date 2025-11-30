import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from typing import Optional
import os
from PyQt6.QtCore import QThread, pyqtSignal

from cbpos.core.services.config_service import ConfigService


class EmailWorker(QThread):
    """
    Background worker for sending emails.
    """

    finished = pyqtSignal(bool, str)  # Success, Message

    def __init__(
        self,
        to_email: str,
        subject: str,
        body: str,
        attachment_path: Optional[str] = None,
    ):
        super().__init__()
        self.to_email = to_email
        self.subject = subject
        self.body = body
        self.attachment_path = attachment_path

    def run(self):
        try:
            settings = ConfigService.get_all()
            smtp_host = settings.get("smtp_host")
            smtp_port = int(settings.get("smtp_port", 587))
            smtp_user = settings.get("smtp_user")
            smtp_pass = settings.get("smtp_pass")
            smtp_use_ssl = settings.get("smtp_use_ssl", "False").lower() == "true"

            if not all([smtp_host, smtp_user, smtp_pass]):
                self.finished.emit(False, "SMTP settings not configured.")
                return

            msg = MIMEMultipart()
            msg["From"] = smtp_user
            msg["To"] = self.to_email
            msg["Subject"] = self.subject

            msg.attach(MIMEText(self.body, "plain"))

            if self.attachment_path and os.path.exists(self.attachment_path):
                with open(self.attachment_path, "rb") as f:
                    part = MIMEApplication(
                        f.read(), Name=os.path.basename(self.attachment_path)
                    )
                part["Content-Disposition"] = (
                    f'attachment; filename="{os.path.basename(self.attachment_path)}"'  # noqa: E702
                )
                msg.attach(part)

            context = ssl.create_default_context()

            if smtp_use_ssl:
                # Use SMTP_SSL for port 465
                with smtplib.SMTP_SSL(smtp_host, smtp_port, context=context) as server:
                    server.login(smtp_user, smtp_pass)
                    server.send_message(msg)
            else:
                # Use STARTTLS for port 587
                with smtplib.SMTP(smtp_host, smtp_port) as server:
                    server.starttls(context=context)
                    server.login(smtp_user, smtp_pass)
                    server.send_message(msg)

            self.finished.emit(True, "Email sent successfully.")

        except Exception as e:
            self.finished.emit(False, str(e))


class EmailService:
    """
    Service to handle email operations.
    """

    @classmethod
    def send_receipt(
        cls, to_email: str, sale_ref: str, pdf_path: Optional[str] = None
    ) -> EmailWorker:
        """
        Send receipt email in background.
        Returns the worker instance so the caller can connect signals.
        """
        subject = f"Receipt for Order #{sale_ref}"
        body = (
            f"Dear Customer,\n\n"  # noqa: E231
            f"Please find attached your receipt for Order #{sale_ref}.\n\n"
            f"Thank you for shopping with us!"
        )

        worker = EmailWorker(to_email, subject, body, pdf_path)
        # Keep a reference to prevent garbage collection
        cls._workers.append(worker)
        worker.finished.connect(lambda: cls._cleanup_worker(worker))
        worker.start()
        return worker

    @classmethod
    def _cleanup_worker(cls, worker):
        if worker in cls._workers:
            cls._workers.remove(worker)

    _workers = []
