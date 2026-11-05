import logging
import os
import shutil
import smtplib
import ssl
import tempfile
import threading
from collections.abc import Callable
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from PyQt6.QtCore import QThread, pyqtSignal

from cbpos.core.services.config_service import ConfigService
from cbpos.core.utils.validators import is_valid_email
from cbpos.i18n import translate_in

logger = logging.getLogger(__name__)

# A dead server must fail the send, not hang its thread forever.
_SMTP_TIMEOUT_S = 30


class EmailNotConfiguredError(Exception):
    """SMTP settings are missing, so no email can be sent."""


def deliver_email(
    to_email: str,
    subject: str,
    body: str,
    attachment_path: str | None = None,
) -> None:
    """Send an email via SMTP on the calling thread, blocking until the server accepts it.

    Call from a worker thread only -- it blocks on the network.

    Args:
        to_email: Recipient email address.
        subject: Email subject.
        body: Email body (plain text).
        attachment_path: Optional path to a file to attach (e.g. PDF).

    Raises:
        EmailNotConfiguredError: SMTP host, user or password is not set.
        Exception: Any SMTP, network or file error; nothing was sent.
    """
    config = ConfigService.get_all()
    smtp_host = config.get("smtp_host", "")
    try:
        smtp_port = int(config.get("smtp_port", "587"))
    except (ValueError, TypeError):
        smtp_port = 587
    smtp_user = config.get("smtp_user", "")
    smtp_pass = config.get("smtp_pass", "")

    if not all([smtp_host, smtp_port, smtp_user, smtp_pass]):
        raise EmailNotConfiguredError("SMTP configuration is incomplete.")

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
    with smtplib.SMTP(smtp_host, smtp_port, timeout=_SMTP_TIMEOUT_S) as server:
        server.starttls(context=context)
        server.login(smtp_user, smtp_pass)
        server.send_message(msg)


def _send_email_task(
    to_email: str,
    subject: str,
    body: str,
    attachment_path: str | None,
    callback: Callable[[bool, str], None] | None,
) -> None:
    """Background task that sends an email via SMTP."""
    try:
        deliver_email(to_email, subject, body, attachment_path)
    except EmailNotConfiguredError as e:
        if callback:
            callback(False, str(e))
        return
    except Exception as e:
        logger.error("Failed to send email: %s", e)
        if callback:
            callback(False, str(e))
        return

    if callback:
        callback(True, "Email sent successfully.")


class EmailReceiptWorker(QThread):
    """Generates A4 invoice PDF and emails it in a background QThread (#792)."""

    finished = pyqtSignal(bool, str)

    def __init__(self, sale_or_id: Any, to_email: str) -> None:
        super().__init__()
        self.finished.connect(self.deleteLater)
        self.sale_or_id = sale_or_id
        self.to_email = (to_email or "").strip()
        self.result_status: tuple[bool, str] | None = None

    def _emit_finished(self, ok: bool, msg: str) -> None:
        self.result_status = (ok, msg)
        self.finished.emit(ok, msg)

    def run(self) -> None:
        """Generate A4 invoice PDF and deliver via SMTP in background."""
        temp_dir = tempfile.mkdtemp(prefix="cbpos_receipt_email_")
        try:
            if not is_valid_email(self.to_email):
                self._emit_finished(False, "Invalid email address.")
                return

            sale = None
            if isinstance(self.sale_or_id, int):
                from cbpos.core.services.sale_query_service import SaleQueryService

                sale = SaleQueryService.get_sale_details(self.sale_or_id)
                if not sale:
                    self._emit_finished(False, f"Sale {self.sale_or_id} not found.")
                    return
            elif isinstance(self.sale_or_id, str):
                from cbpos.core.database import Database
                from cbpos.core.models import Sale
                from cbpos.core.services.sale_query_service import SaleQueryService

                db = Database()
                with db.get_session() as session:
                    found = session.query(Sale).filter(Sale.document_number == self.sale_or_id).first()
                    sale_id = found.id if found else None
                if sale_id:
                    sale = SaleQueryService.get_sale_details(sale_id)
                else:
                    self._emit_finished(False, f"Sale {self.sale_or_id} not found.")
                    return
            else:
                sale = self.sale_or_id

            lang = ConfigService.get("receipt_language") or "en"
            shop_name = ConfigService.get("receipt_shop_name") or ConfigService.get("shop_name") or "CB POS"
            doc_no = getattr(sale, "document_number", "") or str(getattr(sale, "id", ""))

            subject = translate_in(lang, "email.receipt_subject", doc=doc_no, shop=shop_name)
            body = translate_in(lang, "email.receipt_body", doc=doc_no, shop=shop_name, website="ceybyte.com")

            from cbpos.core.services.invoice_service import InvoiceService

            pdf_path = os.path.join(temp_dir, f"{doc_no or 'receipt'}.pdf")
            InvoiceService.generate_pdf(sale, pdf_path)

            deliver_email(self.to_email, subject, body, pdf_path)
            self._emit_finished(True, "")
        except EmailNotConfiguredError as e:
            self._emit_finished(False, str(e))
        except Exception as e:
            logger.error("Failed to email receipt: %s", e)
            self._emit_finished(False, str(e))
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


class EmailService:
    """
    Service for sending emails (reports, alerts, receipts) using SMTP.
    """

    @staticmethod
    def is_configured() -> bool:
        """Return True if SMTP settings are fully configured."""
        config = ConfigService.get_all()
        return bool(
            config.get("smtp_host") and config.get("smtp_port") and config.get("smtp_user") and config.get("smtp_pass")
        )

    @staticmethod
    def send_receipt(
        sale_or_id: Any,
        to_email: str | None = None,
        callback: Callable[[bool, str], None] | None = None,
    ) -> EmailReceiptWorker:
        """Send receipt PDF to to_email in a background worker thread (#792).

        Supports send_receipt(sale_id, to_email) or send_receipt(to_email, sale_id).
        """
        if isinstance(sale_or_id, str) and "@" in sale_or_id and to_email is not None:
            actual_sale = to_email
            actual_email = sale_or_id
        else:
            actual_sale = sale_or_id
            actual_email = to_email or ""

        worker = EmailReceiptWorker(actual_sale, actual_email)
        if callback:
            worker.finished.connect(callback)
        worker.start()
        return worker

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
