"""
Tests for PrintWorker's singleton lifetime.

PrintWorker.run() loops until stop() is called (by design -- add_job() keeps
reusing the same running thread for jobs queued later, per its own comment).
Every call site used to do `worker = PrintWorker()` as a local variable with
no persistent reference, so the thread was still running when that variable
went out of scope at the end of the calling function. PyQt/Qt aborts the
whole process in that situation ("QThread: Destroyed while thread is still
running") -- this is not a catchable Python exception, so it crashed the
app on every completed sale (receipt print + drawer kick), on every receipt
reprint, and on every label/statement print. See PrintWorker.instance().

A real reproduction of the old crash has to run in a subprocess, since it
aborts the whole process it runs in (there's no way to catch that from
inside the same pytest run without killing the test run itself).
"""

import subprocess
import sys

from cbpos.infrastructure.hardware.escpos_driver import PrintWorker

# A cold child import of PyQt6 + cbpos takes 6 s+ under parallel load (#683).
_CHILD_TIMEOUT_S = 90


class TestPrintWorkerSingleton:
    def teardown_method(self):
        PrintWorker.shutdown()

    def test_instance_returns_the_same_object(self, qapp):
        first = PrintWorker.instance()
        second = PrintWorker.instance()
        assert first is second

    def test_shutdown_stops_and_clears_the_shared_instance(self, qapp):
        worker = PrintWorker.instance()
        worker.add_job("print_receipt", ["test"])
        assert worker.isRunning()

        PrintWorker.shutdown()

        assert PrintWorker._instance is None
        assert not worker.isRunning()

    def test_instance_after_shutdown_creates_a_fresh_worker(self, qapp):
        first = PrintWorker.instance()
        PrintWorker.shutdown()
        second = PrintWorker.instance()
        assert first is not second

    def test_shutdown_with_no_instance_created_is_a_no_op(self, qapp):
        PrintWorker.shutdown()  # nothing created yet in this test
        assert PrintWorker._instance is None


class TestPrintWorkerProcessLifetime:
    """Subprocess-level regression tests -- these actually crash the
    subprocess (not this test process) if the underlying bug reappears."""

    def test_bare_print_worker_dies_with_its_last_python_reference(self, qapp):
        """A bare PrintWorker() has no Qt parent, so Python owns it: when its
        last Python reference goes, sip deletes the C++ QThread with it."""
        from PyQt6 import sip

        worker = PrintWorker()
        try:
            assert worker.parent() is None
            assert sip.ispyowned(worker)
        finally:
            sip.delete(worker)  # never started, so deleting it is safe

    def test_locally_scoped_print_worker_would_abort_the_process(self):
        """Documents the exact bug: destroying a bare PrintWorker() while its
        thread runs aborts the process -- what happens when its only Python
        reference goes out of scope (see the ownership test above).

        Dropping the reference itself is racy (#683): once the thread enters
        run(), that frame holds ``self`` and the drop deletes nothing. So the
        child waits until the thread really runs, then deletes the C++ object
        directly -- the same destructor the lost reference would call.
        """
        script = (
            "import sys; from PyQt6.QtWidgets import QApplication; from PyQt6 import sip; "
            "app = QApplication(sys.argv); "
            "from cbpos.infrastructure.hardware.escpos_driver import PrintWorker; "
            "worker = PrintWorker(); worker.add_job('print_receipt', ['x']); "
            "assert worker.isRunning(); "
            "sip.delete(worker); "
            "print('NOT_ABORTED')"
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            env={"QT_QPA_PLATFORM": "offscreen", "PATH": "/usr/bin:/bin"},
            timeout=_CHILD_TIMEOUT_S,
        )
        assert result.returncode != 0
        assert "still running" in result.stderr
        assert "NOT_ABORTED" not in result.stdout

    def test_shared_print_worker_does_not_abort_the_process(self):
        """The fix: going through PrintWorker.instance() instead keeps the
        thread alive on the class, so it survives the caller's function
        returning, and the process exits cleanly."""
        script = (
            "import sys; from PyQt6.QtWidgets import QApplication; "
            "app = QApplication(sys.argv); "
            "from cbpos.infrastructure.hardware.escpos_driver import PrintWorker; "
            "worker = PrintWorker.instance(); worker.add_job('print_receipt', ['x']); "
            "worker = None; import gc; gc.collect(); "
            "from PyQt6.QtCore import QTimer; "
            "QTimer.singleShot(300, lambda: (PrintWorker.shutdown(), app.quit())); app.exec(); "
            "print('CLEAN_EXIT')"
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            env={"QT_QPA_PLATFORM": "offscreen", "PATH": "/usr/bin:/bin"},
            timeout=_CHILD_TIMEOUT_S,
        )
        assert result.returncode == 0
        assert "CLEAN_EXIT" in result.stdout
