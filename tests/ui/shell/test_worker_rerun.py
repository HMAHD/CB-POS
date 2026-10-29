"""
#632 (UI-060): every background worker declared its own ``finished`` signal,
shadowing ``QThread.finished``, and connected it to ``deleteLater``. The custom
signal fires from inside run() -- before the thread has actually stopped -- so
the C++ object could be deleted while still running, and the view's reference
was left pointing at a deleted object. Admin Tools' 15s timeout then called
``isRunning()`` on it and raised ``RuntimeError: wrapped C/C++ object ... has
been deleted``, which is what a second "Test Printer" click hit.
"""

import inspect
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QEvent, QThread

from cbpos.core.constants.hardware import HardwareTestOutcome
from cbpos.core.services.hardware_test_service import HardwareTestResult
from cbpos.ui import workers
from cbpos.ui.views.admin_tools_view import AdminToolsView
from cbpos.ui.views.reports.report_viewer import ReportWorker

pytestmark = pytest.mark.usefixtures("qapp")

_OK = HardwareTestResult(True, HardwareTestOutcome.PRINT_SENT)

WORKER_CLASSES = [
    cls for _, cls in inspect.getmembers(workers, inspect.isclass) if issubclass(cls, QThread) and cls is not QThread
] + [ReportWorker]


@pytest.mark.parametrize("cls", WORKER_CLASSES, ids=lambda c: c.__name__)
def test_worker_does_not_shadow_qthread_finished(cls):
    assert "finished" not in cls.__dict__


def _finished_and_deleted_worker():
    """A real PrinterTestWorker that ran, emitted its result, and deleted itself."""
    worker = workers.PrinterTestWorker()
    results = []
    worker.result.connect(results.append)
    worker.start()
    assert worker.wait(5000)
    # Deliver the queued result/finished signals, then this worker's deferred delete
    # only -- flushing every pending DeferredDelete deletes other tests' objects.
    QCoreApplication.processEvents()
    QCoreApplication.sendPostedEvents(worker, QEvent.Type.DeferredDelete.value)
    return worker, results


def test_printer_test_timeout_after_worker_deleted_itself_does_not_raise():
    """Second "Test Printer" click hit the 15s timeout on a deleted worker (#632).

    Uses a stand-in for the view: building a whole AdminToolsView per test leaked
    widgets/threads past teardown and segfaulted the full suite.
    """
    with patch(
        "cbpos.core.services.hardware_test_service.HardwareTestService.test_receipt_printer",
        return_value=_OK,
    ):
        for _ in range(2):
            worker, results = _finished_and_deleted_worker()
            assert results == [_OK]
            assert sip.isdeleted(worker)

            view = SimpleNamespace(_printer_worker=worker, btn_test_printer=MagicMock(), lbl_printer_status=MagicMock())
            AdminToolsView._on_printer_test_timeout(view)  # must not raise RuntimeError
            view.btn_test_printer.setEnabled.assert_not_called()
