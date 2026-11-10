"""Tests for #842: Print results belong to their job.

After one reprint from Management -> Documents, the hidden Document view must
not react to later print jobs or drawer kicks.
"""

from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QMessageBox

from cbpos.infrastructure.hardware.escpos_driver import PrintWorker
from cbpos.ui.views.document_view import DocumentBrowserView

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture(autouse=True)
def clean_print_worker():
    PrintWorker.shutdown()
    yield
    PrintWorker.shutdown()


@pytest.fixture
def dummy_printer():
    printer = MagicMock()
    printer.connect.return_value = True
    return printer


def test_issue_842_document_view_ignores_other_jobs(db_session, qtbot, dummy_printer):
    """Reprint once, then queue unrelated receipt and kick jobs.
    DocumentBrowserView must show success exactly once for its own reprint,
    and 0 popups for unrelated jobs.
    """
    worker = PrintWorker(printer=dummy_printer)
    PrintWorker._instance = worker

    view = DocumentBrowserView()
    view.current_doc = {"type": "sale", "id": 1, "document_number": "REC-842"}

    dummy_reprint_job = MagicMock()
    dummy_reprint_job.commands = [{"type": "text", "val": "reprint"}]

    dummy_user = MagicMock(id=1)
    with (
        patch("cbpos.core.utils.permission_helper.check_permission_with_override", return_value=dummy_user),
        patch(
            "cbpos.core.services.receipt_reprint_service.ReceiptReprintService.reprint", return_value=dummy_reprint_job
        ),
        patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=dummy_user),
        patch.object(QMessageBox, "information") as mock_info,
        patch.object(QMessageBox, "critical") as mock_crit,
    ):
        # 1. Trigger reprint from DocumentBrowserView
        view.reprint_document()

        # Wait for reprint job to complete
        reprint_job_id = getattr(view, "_reprint_job_id", None)
        assert reprint_job_id is not None, "DocumentBrowserView must store _reprint_job_id"

        qtbot.waitUntil(lambda: mock_info.call_count == 1, timeout=5000)
        assert mock_crit.call_count == 0

        # 2. Now queue unrelated receipt and drawer kick jobs
        receipt_id = worker.add_job("print_receipt", [{"type": "text", "val": "customer receipt"}])
        kick_id = worker.add_job("kick_drawer", {"manual": True})

        # Wait until the worker has processed both jobs
        results = []
        worker.job_result.connect(lambda jid, ok, msg: results.append(jid))
        qtbot.waitUntil(lambda: receipt_id in results and kick_id in results, timeout=5000)

        # Unrelated jobs must NOT trigger DocumentBrowserView popups!
        assert mock_info.call_count == 1, (
            f"Expected exactly 1 success popup for the reprint, but got {mock_info.call_count} "
            f"(DocumentBrowserView reacted to unrelated jobs!)"
        )
        assert mock_crit.call_count == 0

    view.deleteLater()


def test_issue_842_matching_failure_appears_once(db_session, qtbot):
    """When a reprint job fails, the failure error popup must appear exactly once."""
    worker = PrintWorker(printer=None)
    PrintWorker._instance = worker

    view = DocumentBrowserView()
    view.current_doc = {"type": "sale", "id": 1, "document_number": "REC-FAIL"}

    dummy_reprint_job = MagicMock()
    dummy_reprint_job.commands = [{"type": "text", "val": "reprint"}]

    dummy_user = MagicMock(id=1)
    with (
        patch("cbpos.core.utils.permission_helper.check_permission_with_override", return_value=dummy_user),
        patch(
            "cbpos.core.services.receipt_reprint_service.ReceiptReprintService.reprint", return_value=dummy_reprint_job
        ),
        patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=dummy_user),
        patch("cbpos.infrastructure.hardware.escpos_driver.receipt_printer_configured", return_value=False),
        patch.object(QMessageBox, "information") as mock_info,
        patch.object(QMessageBox, "critical") as mock_crit,
    ):
        view.reprint_document()

        reprint_job_id = getattr(view, "_reprint_job_id", None)
        assert reprint_job_id is not None, "DocumentBrowserView must store _reprint_job_id"

        qtbot.waitUntil(lambda: mock_crit.call_count == 1, timeout=5000)
        assert mock_info.call_count == 0

        # Unrelated failed job
        results = []
        worker.job_result.connect(lambda jid, ok, msg: results.append(jid))
        other_id = worker.add_job("invalid_job_type", [])
        qtbot.waitUntil(lambda: other_id in results, timeout=5000)

        # Failure count remains 1
        assert mock_crit.call_count == 1

    view.deleteLater()


def test_issue_842_no_connection_multiplication_after_multiple_reprints(db_session, qtbot, dummy_printer):
    """Multiple reprints must not accumulate duplicate signal connections.
    Each finished reprint job must trigger the success handler exactly once.
    """
    worker = PrintWorker(printer=dummy_printer)
    PrintWorker._instance = worker

    view = DocumentBrowserView()
    view.current_doc = {"type": "sale", "id": 1, "document_number": "REC-MULTI"}

    dummy_reprint_job = MagicMock()
    dummy_reprint_job.commands = [{"type": "text", "val": "reprint"}]

    dummy_user = MagicMock(id=1)
    with (
        patch("cbpos.core.utils.permission_helper.check_permission_with_override", return_value=dummy_user),
        patch(
            "cbpos.core.services.receipt_reprint_service.ReceiptReprintService.reprint", return_value=dummy_reprint_job
        ),
        patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=dummy_user),
        patch.object(QMessageBox, "information") as mock_info,
    ):
        # 1st reprint
        view.reprint_document()
        qtbot.waitUntil(lambda: mock_info.call_count == 1, timeout=5000)

        # 2nd reprint
        view.reprint_document()
        qtbot.waitUntil(lambda: mock_info.call_count == 2, timeout=5000)

        # 3rd reprint
        view.reprint_document()
        qtbot.waitUntil(lambda: mock_info.call_count == 3, timeout=5000)

        assert mock_info.call_count == 3

    view.deleteLater()


def test_issue_842_job_result_carries_id(qtbot, dummy_printer):
    """PrintWorker.add_job returns a unique string job_id, which is carried by job_result."""
    worker = PrintWorker(printer=dummy_printer)
    PrintWorker._instance = worker

    emitted = []
    worker.job_result.connect(lambda jid, ok, msg: emitted.append((jid, ok, msg)))

    job_id = worker.add_job("print_commands", [{"type": "text", "val": "hello"}])
    assert isinstance(job_id, str)
    assert len(job_id) > 0

    qtbot.waitUntil(lambda: len(emitted) == 1, timeout=5000)
    assert emitted[0][0] == job_id
    assert emitted[0][1] is True
