"""
EmailService.send_email_with_pdf() had no way to report success/failure
back to its caller at all -- send_email() itself already supported a
callback(success, message) parameter, but the PDF-attachment alias never
accepted or forwarded one, which is why scheduler_service.py had nothing
to hook a real completion signal into.
"""

from unittest.mock import MagicMock, patch

from cbpos.core.services.email_service import EmailService


class TestSendEmailWithPdfForwardsCallback:
    def test_callback_is_forwarded_to_send_email(self):
        callback = MagicMock()

        with patch.object(EmailService, "send_email") as mock_send_email:
            EmailService.send_email_with_pdf("a@b.com", "Subject", "Body", "/tmp/report.pdf", callback=callback)

        mock_send_email.assert_called_once_with("a@b.com", "Subject", "Body", "/tmp/report.pdf", callback=callback)

    def test_callback_defaults_to_none(self):
        with patch.object(EmailService, "send_email") as mock_send_email:
            EmailService.send_email_with_pdf("a@b.com", "Subject", "Body", "/tmp/report.pdf")

        mock_send_email.assert_called_once_with("a@b.com", "Subject", "Body", "/tmp/report.pdf", callback=None)
