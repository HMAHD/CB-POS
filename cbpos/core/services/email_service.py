import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from typing import Optional, Callable
from PyQt6.QtCore import QRunnable, QThreadPool, QObject, pyqtSignal
from cbpos.core.services.config_service import ConfigService


class WorkerSignals(QObject):
    """
    Defines the signals available from a running worker thread.
    Supported signals are:
    finished: No data
    error: tuple (exctype, value, traceback.format_exc() )
    result: object data returned from processing, anything
    """

    result = pyqtSignal(bool, str)


class EmailWorker(QRunnable):
    """
    Worker thread for sending emails.
    """

    def __init__(self, to_email, subject, body, attachment_path):
        super().__init__()
        self.to_email = to_email
        self.subject = subject
        self.body = body
        self.attachment_path = attachment_path
        self.signals = WorkerSignals()

    def run(self):
        config = ConfigService.get_all()
        smtp_host = config.get("smtp_host", "")
        smtp_port = int(config.get("smtp_port", "587"))
        smtp_user = config.get("smtp_user", "")
        smtp_pass = config.get("smtp_pass", "")

        if not all([smtp_host, smtp_port, smtp_user, smtp_pass]):
            self.signals.result.emit(False, "SMTP configuration is incomplete.")
            return

        try:
            # Create Message
            msg = MIMEMultipart()
            msg["From"] = smtp_user
            msg["To"] = self.to_email
            msg["Subject"] = self.subject

            msg.attach(MIMEText(self.body, "plain"))

            # Attach File
            if self.attachment_path:
                with open(self.attachment_path, "rb") as f:
                    part = MIMEApplication(f.read(), Name=self.attachment_path.split("/")[-1])

                # After the file is closed
                filename = self.attachment_path.split("/")[-1]
                part.add_header("Content-Disposition", "attachment", filename=filename)
                msg.attach(part)

            # Connect and Send
            context = ssl.create_default_context()

            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls(context=context)
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)

            self.signals.result.emit(True, "Email sent successfully.")

        except Exception as e:
            self.signals.result.emit(False, str(e))


class EmailService:
    """
    Service for sending emails (reports, alerts) using SMTP.
    Uses QThreadPool for thread safety.
    """

    @staticmethod
    def send_email(
        to_email: str,
        subject: str,
        body: str,
        attachment_path: Optional[str] = None,
        callback: Optional[Callable[[bool, str], None]] = None,
    ):
        """
        Send an email in a background thread using QThreadPool.

        Args:
            to_email: Recipient email address
            subject: Email subject
            body: Email body (plain text)
            attachment_path: Optional path to a file to attach (e.g. PDF)
            callback: Optional function to call when done: callback(success: bool, message: str)
        """
        worker = EmailWorker(to_email, subject, body, attachment_path)

        if callback:
            # Connect the signal to the callback
            # Note: The callback must be thread-safe or slot-compatible
            worker.signals.result.connect(callback)

        QThreadPool.globalInstance().start(worker)

    @staticmethod
    def send_email_with_pdf(to_email: str, subject: str, body: str, pdf_path: str):
        """
        Alias for send_email to match specific requirement.
        """
        EmailService.send_email(to_email, subject, body, pdf_path)
