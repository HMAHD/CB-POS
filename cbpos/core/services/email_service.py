import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from PyQt6.QtCore import QObject, QThread, pyqtSignal
from cbpos.core.services.config_service import ConfigService
import os


class EmailWorker(QObject):
    finished = pyqtSignal(bool, str)  # success, message

    def __init__(self, to_addr, subject, body, attachment_path=None):
        super().__init__()
        self.to_addr = to_addr
        self.subject = subject
        self.body = body
        self.attachment_path = attachment_path

    def run(self):
        config = ConfigService.get_all()
        smtp_host = config.get("smtp_host", "")
        smtp_port = int(config.get("smtp_port", 587))
        smtp_user = config.get("smtp_user", "")
        smtp_pass = config.get("smtp_pass", "")

        if not all([smtp_host, smtp_port, smtp_user, smtp_pass]):
            self.finished.emit(False, "SMTP configuration missing.")
            return

        try:
            msg = MIMEMultipart()
            msg["From"] = smtp_user
            msg["To"] = self.to_addr
            msg["Subject"] = self.subject

            msg.attach(MIMEText(self.body, "plain"))

            if self.attachment_path and os.path.exists(self.attachment_path):
                with open(self.attachment_path, "rb") as f:
                    part = MIMEApplication(f.read(), Name=os.path.basename(self.attachment_path))
                part["Content-Disposition"] = (
                    f'attachment; filename="'  # noqa: E702
                    f'{os.path.basename(self.attachment_path)}"'
                )
                msg.attach(part)

            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls()
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)

            self.finished.emit(True, "Email sent successfully.")

        except Exception as e:
            self.finished.emit(False, str(e))


class EmailService:
    @staticmethod
    def send_email(to_addr, subject, body, attachment_path=None, callback=None):
        """
        Sends an email in a background thread.
        """
        thread = QThread()
        worker = EmailWorker(to_addr, subject, body, attachment_path)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)

        if callback:
            worker.finished.connect(callback)

        # Keep a reference to avoid garbage collection
        # In a real app, manage threads properly (e.g., in a pool or service instance)
        # For now, attaching to the worker itself is a hacky way, better to return the thread
        worker.thread_ref = thread

        thread.start()
        return thread
