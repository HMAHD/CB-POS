"""Report jobs survive their view being destroyed (#643 follow-up).

The Reports view held each running worker only in ``self._x_worker``.
Destroying the view (logout, closing Management) mid-job dropped the last
reference, and Qt aborts the process when a running QThread is destroyed
("QThread: Destroyed while thread is still running"). Workers are now
held by ``start_background_job`` until they finish, and a result for a
view that is gone is dropped.
"""

import gc
import subprocess
import sys
import threading
from unittest.mock import MagicMock

import pandas as pd
import pytest
from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QEvent, QThread, pyqtSignal

from cbpos.core.services import email_service
from cbpos.ui import workers
from cbpos.ui.workers import running_background_jobs, start_background_job, wait_for_background_jobs

pytestmark = pytest.mark.usefixtures("qapp")

_CHILD_TIMEOUT_S = 90  # cold PyQt6 + cbpos import is slow under parallel load


def test_destroying_the_view_mid_job_does_not_abort_the_process():
    """Real process check: the abort would kill the child, not this test run."""
    script = r"""
import gc, sys, threading, time
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import QApplication, QWidget
app = QApplication(sys.argv)
from cbpos.ui.workers import running_background_jobs, start_background_job

gate = threading.Event()
results = []

class SlowJob(QThread):
    result = pyqtSignal(str)
    def __init__(self):
        super().__init__()
        self.finished.connect(self.deleteLater)
    def run(self):
        gate.wait(10)
        self.result.emit("done")

class View(QWidget):
    def start_job(self):
        self._worker = SlowJob()
        self._worker.result.connect(self.on_result)
        start_background_job(self._worker)
    def on_result(self, msg):
        results.append(msg)

view = View()
view.start_job()
assert running_background_jobs()[0].isRunning()
view = None  # the view and its C++ object go while the job still runs
gc.collect()
app.processEvents()
gate.set()
end = time.monotonic() + 10
while running_background_jobs() and time.monotonic() < end:
    app.processEvents()
    time.sleep(0.01)
app.processEvents()
assert not running_background_jobs(), "job never finished"
assert results == [], "result reached a destroyed view"
print("JOB_SURVIVED")
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        env={"QT_QPA_PLATFORM": "offscreen", "PATH": "/usr/bin:/bin"},
        timeout=_CHILD_TIMEOUT_S,
    )
    assert "still running" not in result.stderr
    assert result.returncode == 0, result.stderr
    assert "JOB_SURVIVED" in result.stdout


def test_report_viewer_email_job_outlives_the_viewer(db_session, monkeypatch, qtbot):
    """The real Reports view: destroy it mid-email; the job finishes, nothing is shown."""
    from cbpos.ui.views.reports import report_viewer as rv

    gate = threading.Event()
    sent = []

    def _slow_deliver(to, *_a):
        gate.wait(10)
        sent.append(to)

    monkeypatch.setattr(email_service, "deliver_email", _slow_deliver)
    monkeypatch.setattr(rv, "QMessageBox", MagicMock())
    monkeypatch.setattr("PyQt6.QtWidgets.QInputDialog.getText", lambda *a, **k: ("owner@shop.lk", True))
    monkeypatch.setattr("cbpos.core.utils.permission_helper.check_permission_with_override", lambda *a, **k: True)

    view = rv.ReportViewer()
    view.current_report = MagicMock()
    view.current_report.name = "Stock"
    view._full_df = pd.DataFrame({"Item": ["Rice"]})
    view.export_service = MagicMock()
    view.export_service.export_to_pdf.side_effect = lambda _df, path, _name: open(path, "wb").write(b"%PDF")
    view.email_report()
    assert len(running_background_jobs()) == 1

    view.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert sip.isdeleted(view)
    del view
    gc.collect()

    gate.set()
    qtbot.waitUntil(lambda: not running_background_jobs(), timeout=10000)
    QCoreApplication.processEvents()
    assert sent == ["owner@shop.lk"]
    rv.QMessageBox.information.assert_not_called()
    rv.QMessageBox.warning.assert_not_called()


class _GatedJob(QThread):
    done = pyqtSignal()

    def __init__(self, gate: threading.Event) -> None:
        super().__init__()
        self.finished.connect(self.deleteLater)
        self._gate = gate

    def run(self) -> None:
        self._gate.wait(10)
        self.done.emit()


def test_app_exit_waits_for_a_running_job(qtbot):
    gate = threading.Event()
    start_background_job(_GatedJob(gate))
    threading.Timer(0.2, gate.set).start()

    wait_for_background_jobs(timeout_ms=5000)

    assert not any(w.isRunning() for w in running_background_jobs())
    assert workers._jobs is not None and workers._jobs.running() == []


def test_a_job_still_running_at_exit_is_handed_to_cpp_not_destroyed(qtbot):
    gate = threading.Event()
    job = _GatedJob(gate)
    start_background_job(job)
    try:
        wait_for_background_jobs(timeout_ms=50)
        assert job.isRunning()
        assert not sip.ispyowned(job)  # dropping Python refs can't destroy it now
        assert running_background_jobs() == []
    finally:
        gate.set()
        job.wait(5000)
