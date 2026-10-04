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
from unittest.mock import patch

import pytest
from PyQt6.QtCore import QCoreApplication, QEvent, QThread

from cbpos.ui import workers
from cbpos.ui.views.admin_tools_view import AdminToolsView
from cbpos.ui.views.reports.report_viewer import ReportWorker

pytestmark = pytest.mark.usefixtures("qapp")

WORKER_CLASSES = [
    cls for _, cls in inspect.getmembers(workers, inspect.isclass) if issubclass(cls, QThread) and cls is not QThread
] + [ReportWorker]


@pytest.mark.parametrize("cls", WORKER_CLASSES, ids=lambda c: c.__name__)
def test_worker_does_not_shadow_qthread_finished(cls):
    assert "finished" not in cls.__dict__


def _run_to_completion(view: AdminToolsView) -> None:
    worker = view._printer_worker
    assert worker.wait(5000)
    # Deliver the queued result/finished signals, then this worker's deferred delete
    # only -- flushing every pending DeferredDelete deletes other tests' objects (segfault).
    QCoreApplication.processEvents()
    QCoreApplication.sendPostedEvents(worker, QEvent.Type.DeferredDelete.value)


def test_printer_test_runs_twice_without_runtime_error(db_session):
    view = AdminToolsView()
    with (
        patch(
            "cbpos.core.services.hardware_test_service.HardwareTestService.test_receipt_printer",
            return_value=(True, "ok"),
        ),
        patch("cbpos.ui.views.admin_tools_view.QTimer.singleShot"),
    ):
        for _ in range(2):
            view._test_printer()
            _run_to_completion(view)
            # The 15s timeout firing after the worker is gone must not touch a deleted object.
            view._on_printer_test_timeout()
            assert view.btn_test_printer.isEnabled()
            assert view.lbl_printer_status.text() == "ok"
