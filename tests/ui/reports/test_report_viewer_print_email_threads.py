"""Reports Print and Email run off the UI thread (#643).

Print laid out the whole report on the UI thread, and Email exported the
PDF there too -- a large report froze the window. Email also said
"sending" before anything was known, and showed its result from a plain
Python thread. Now both run in QThread workers behind the loading overlay,
with the buttons off, and only a confirmed result says it worked.
"""

import os
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtPrintSupport import QPrintDialog, QPrinter

from cbpos.core.services import email_service
from cbpos.i18n import _t
from cbpos.ui.views.reports import report_viewer as rv
from cbpos.ui.workers import ReportEmailWorker, ReportPrintWorker

pytestmark = pytest.mark.usefixtures("qapp")

_DF = pd.DataFrame({"Item": ["Rice", "Dhal"], "Value": [100, 200]})


# --------------------------------------------------------------------------
# Workers
# --------------------------------------------------------------------------


def _pdf_printer(path) -> QPrinter:
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(str(path))
    return printer


class TestReportPrintWorker:
    def test_prints_the_report_in_a_worker_thread(self, qtbot, tmp_path):
        out = tmp_path / "report.pdf"
        worker = ReportPrintWorker(_pdf_printer(out), _DF, "CB POS - Stock", "Generated on:")
        with qtbot.waitSignal(worker.result, timeout=10000):
            worker.start()
        worker.wait()
        assert out.stat().st_size > 0

    def test_a_printer_that_fails_is_an_error_not_a_success(self, qtbot, tmp_path):
        out = tmp_path / "missing_dir" / "report.pdf"  # can't be opened
        worker = ReportPrintWorker(_pdf_printer(out), _DF, "CB POS - Stock", "Generated on:")
        succeeded = []
        worker.result.connect(lambda: succeeded.append(True))
        with qtbot.waitSignal(worker.error, timeout=10000):
            worker.start()
        worker.wait()
        assert not succeeded


class TestReportEmailWorker:
    def _worker(self, export_service=None) -> ReportEmailWorker:
        if export_service is None:
            export_service = MagicMock()
            export_service.export_to_pdf.side_effect = lambda _df, path, _name: open(path, "wb").write(b"%PDF")
        return ReportEmailWorker(export_service, _DF, "Stock / Value", "owner@shop.lk", "Report: Stock", "Body")

    def test_sends_the_pdf_then_reports_the_recipient_and_cleans_up(self, monkeypatch):
        sent = {}

        def _deliver(to, subject, body, attachment):
            sent.update(to=to, subject=subject, attachment=attachment, existed=os.path.exists(attachment))

        monkeypatch.setattr(email_service, "deliver_email", _deliver)
        worker = self._worker()
        results, errors = [], []
        worker.result.connect(results.append)
        worker.error.connect(lambda *a: errors.append(a))

        worker.run()  # body only; threading is QThread's job

        assert results == ["owner@shop.lk"] and errors == []
        assert sent["to"] == "owner@shop.lk" and sent["existed"]
        assert os.path.basename(sent["attachment"]) == "Stock_Value.pdf"
        assert not os.path.exists(os.path.dirname(sent["attachment"]))  # temp copy removed

    def test_missing_smtp_settings_is_reported_as_not_configured(self, monkeypatch):
        def _deliver(*_a):
            raise email_service.EmailNotConfiguredError("no smtp")

        monkeypatch.setattr(email_service, "deliver_email", _deliver)
        worker = self._worker()
        results, errors = [], []
        worker.result.connect(results.append)
        worker.error.connect(lambda *a: errors.append(a))
        worker.run()
        assert results == []
        assert errors == [(ReportEmailWorker.STAGE_NOT_CONFIGURED, "no smtp")]

    def test_server_failure_is_a_send_error(self, monkeypatch):
        def _deliver(*_a):
            raise OSError("connection refused")

        monkeypatch.setattr(email_service, "deliver_email", _deliver)
        worker = self._worker()
        results, errors = [], []
        worker.result.connect(results.append)
        worker.error.connect(lambda *a: errors.append(a))
        worker.run()
        assert results == []
        assert errors == [(ReportEmailWorker.STAGE_SEND, "connection refused")]

    def test_pdf_failure_sends_nothing(self, monkeypatch):
        deliver = MagicMock()
        monkeypatch.setattr(email_service, "deliver_email", deliver)
        export_service = MagicMock()
        export_service.export_to_pdf.side_effect = RuntimeError("disk full")
        worker = self._worker(export_service)
        errors = []
        worker.error.connect(lambda *a: errors.append(a))
        worker.run()
        deliver.assert_not_called()
        assert errors == [(ReportEmailWorker.STAGE_EXPORT, "disk full")]


class TestDeliverEmail:
    def test_incomplete_smtp_settings_raise_not_configured(self, monkeypatch):
        monkeypatch.setattr(email_service.ConfigService, "get_all", lambda: {"smtp_host": "", "smtp_port": "587"})
        with pytest.raises(email_service.EmailNotConfiguredError):
            email_service.deliver_email("a@b.lk", "s", "b")


# --------------------------------------------------------------------------
# ReportViewer wiring
# --------------------------------------------------------------------------


class _FakeWorker(QObject):
    """Stands in for a worker: records its args, never runs."""

    instances: list["_FakeWorker"] = []
    result = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, *args) -> None:
        super().__init__()
        self.args = args
        self.started = False
        _FakeWorker.instances.append(self)

    def start(self) -> None:
        self.started = True


class _FakeEmailWorker(_FakeWorker):
    result = pyqtSignal(str)
    error = pyqtSignal(str, str)
    STAGE_EXPORT = ReportEmailWorker.STAGE_EXPORT
    STAGE_NOT_CONFIGURED = ReportEmailWorker.STAGE_NOT_CONFIGURED
    STAGE_SEND = ReportEmailWorker.STAGE_SEND


class _AcceptingPrintDialog:
    DialogCode = QPrintDialog.DialogCode

    def __init__(self, *_a) -> None:
        pass

    def exec(self):
        return QPrintDialog.DialogCode.Accepted


@pytest.fixture
def viewer(db_session, monkeypatch):
    _FakeWorker.instances = []
    monkeypatch.setattr(rv, "ReportPrintWorker", _FakeWorker)
    monkeypatch.setattr(rv, "ReportEmailWorker", _FakeEmailWorker)
    started = []  # the view must hand its worker to the job registry
    monkeypatch.setattr(rv, "start_background_job", lambda w: (started.append(w), w.start()))
    monkeypatch.setattr(rv, "QMessageBox", MagicMock())
    monkeypatch.setattr("PyQt6.QtPrintSupport.QPrintDialog", _AcceptingPrintDialog)
    monkeypatch.setattr("PyQt6.QtWidgets.QInputDialog.getText", lambda *a, **k: (" owner@shop.lk ", True))
    monkeypatch.setattr("cbpos.core.utils.permission_helper.check_permission_with_override", lambda *a, **k: True)
    view = rv.ReportViewer()
    view.current_report = SimpleNamespace(name="Stock Valuation")
    view._full_df = _DF
    view._test_started_jobs = started
    yield view
    view.deleteLater()


def started_jobs(view) -> list:
    return view._test_started_jobs


def _buttons(view) -> list:
    return [view.btn_print, view.btn_email, view.btn_export_excel, view.btn_export_pdf]


class TestPrintFromViewer:
    def test_print_runs_in_worker_behind_overlay_with_buttons_off(self, viewer):
        viewer.print_report()
        worker = _FakeWorker.instances[-1]
        assert worker.started
        assert started_jobs(viewer) == [worker]
        assert worker.args[1] is _DF
        assert viewer._overlay.isVisibleTo(viewer)
        assert not any(b.isEnabled() for b in _buttons(viewer))
        rv.QMessageBox.information.assert_not_called()  # nothing claimed yet

    def test_success_only_after_the_worker_confirms(self, viewer):
        viewer.print_report()
        _FakeWorker.instances[-1].result.emit()
        assert not viewer._overlay.isVisibleTo(viewer)
        assert all(b.isEnabled() for b in _buttons(viewer))
        args = rv.QMessageBox.information.call_args.args
        assert args[2] == _t("report_viewer.print_sent", name="Stock Valuation")

    def test_failure_shows_an_error_and_re_enables(self, viewer):
        viewer.print_report()
        _FakeWorker.instances[-1].error.emit("jam")
        assert all(b.isEnabled() for b in _buttons(viewer))
        rv.QMessageBox.information.assert_not_called()
        assert rv.QMessageBox.critical.call_args.args[2] == _t("report_viewer.print_failed", error="jam")


class TestEmailFromViewer:
    def test_email_runs_in_worker_and_claims_nothing_until_sent(self, viewer):
        viewer.email_report()
        worker = _FakeWorker.instances[-1]
        assert worker.started
        assert started_jobs(viewer) == [worker]
        assert worker.args[3] == "owner@shop.lk"
        assert viewer._overlay.isVisibleTo(viewer)
        assert not any(b.isEnabled() for b in _buttons(viewer))
        rv.QMessageBox.information.assert_not_called()

    def test_sent_message_after_server_accepts(self, viewer):
        viewer.email_report()
        _FakeWorker.instances[-1].result.emit("owner@shop.lk")
        assert all(b.isEnabled() for b in _buttons(viewer))
        args = rv.QMessageBox.information.call_args.args
        assert args[2] == _t("report_viewer.email_sent", email="owner@shop.lk")

    @pytest.mark.parametrize(
        ("stage", "key"),
        [
            (ReportEmailWorker.STAGE_NOT_CONFIGURED, "report_viewer.email_not_configured"),
            (ReportEmailWorker.STAGE_EXPORT, "report_viewer.email_prepare_failed"),
            (ReportEmailWorker.STAGE_SEND, "report_viewer.email_send_failed"),
        ],
    )
    def test_each_failure_says_what_went_wrong(self, viewer, stage, key):
        viewer.email_report()
        _FakeWorker.instances[-1].error.emit(stage, "boom")
        assert all(b.isEnabled() for b in _buttons(viewer))
        rv.QMessageBox.information.assert_not_called()
        assert rv.QMessageBox.warning.call_args.args[2] == _t(key, error="boom")

    def test_cancelled_prompt_starts_nothing(self, viewer, monkeypatch):
        monkeypatch.setattr("PyQt6.QtWidgets.QInputDialog.getText", lambda *a, **k: ("", False))
        viewer.email_report()
        assert _FakeWorker.instances == []
        assert all(b.isEnabled() for b in _buttons(viewer))
