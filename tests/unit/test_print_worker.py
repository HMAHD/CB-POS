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

    def test_locally_scoped_print_worker_would_abort_the_process(self):
        """Documents the exact bug: a bare PrintWorker(), never reused
        through .instance(), aborts the process once its only Python
        reference goes out of scope while the thread is still running."""
        script = (
            "import sys; from PyQt6.QtWidgets import QApplication; "
            "app = QApplication(sys.argv); "
            "from cbpos.infrastructure.hardware.escpos_driver import PrintWorker; "
            "worker = PrintWorker(); worker.add_job('print_receipt', ['x']); "
            "worker = None; import gc; gc.collect(); "
            "from PyQt6.QtCore import QTimer; QTimer.singleShot(300, app.quit); app.exec()"
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            env={"QT_QPA_PLATFORM": "offscreen", "PATH": "/usr/bin:/bin"},
            timeout=15,
        )
        assert result.returncode != 0
        assert "still running" in result.stderr

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
            timeout=15,
        )
        assert result.returncode == 0
        assert "CLEAN_EXIT" in result.stdout
