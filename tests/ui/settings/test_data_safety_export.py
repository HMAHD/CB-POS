"""Data Safety -> Export: each data type in each format, in every language.

Driven through the view the way a user does: pick a data type and a
format, click Export, choose a folder. The file really gets written (the
data fetchers are stubbed to small frames), and the status line says
what happened.
"""

import threading
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest
from PyQt6.QtCore import QDate
from PyQt6.QtWidgets import QFileDialog, QMessageBox

from cbpos.core.services.data_export_service import DataExportService
from cbpos.i18n import _t, get_language, set_language
from cbpos.ui.views.data_safety_view import DataSafetyView

pytestmark = pytest.mark.usefixtures("qapp")

TYPES = {
    "products": "data_safety.export_type_products",
    "customers": "data_safety.export_type_customers",
    "sales": "data_safety.export_type_sales",
}
FORMATS = {"excel": ("data_safety.export_format_excel", ".xlsx"), "csv": ("data_safety.export_format_csv", ".csv")}


@pytest.fixture(autouse=True)
def restore_language():
    previous = get_language()
    yield
    set_language(previous)


@pytest.fixture
def fetched(monkeypatch):
    """Stub the three data fetchers; record what each was asked for."""
    calls: list[tuple] = []

    def frame(name: str, rows: int) -> pd.DataFrame:
        return pd.DataFrame({"name": [f"{name}-{i}" for i in range(rows)]})

    monkeypatch.setattr(
        DataExportService, "get_products_dataframe", staticmethod(lambda: calls.append(("products",)) or frame("p", 3))
    )
    monkeypatch.setattr(
        DataExportService,
        "get_customers_dataframe",
        staticmethod(lambda: calls.append(("customers",)) or frame("c", 2)),
    )
    monkeypatch.setattr(
        DataExportService,
        "get_sales_dataframe",
        staticmethod(lambda start, end: calls.append(("sales", start, end)) or frame("s", 4)),
    )
    return calls


@pytest.fixture
def out_dir(tmp_path, monkeypatch):
    folder = tmp_path / "exports"
    folder.mkdir()
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: str(folder)))
    return folder


def _make_view(tmp_path, monkeypatch) -> DataSafetyView:
    monkeypatch.setattr(
        "cbpos.core.services.config_service.ConfigService.get",
        lambda key: str(tmp_path) if key == "backup_dir" else None,
    )
    return DataSafetyView()


@pytest.fixture
def view(qapp, db_session, tmp_path, monkeypatch):
    v = _make_view(tmp_path, monkeypatch)
    yield v
    v.deleteLater()


def _choose(view: DataSafetyView, data_key: str, fmt_key: str) -> None:
    view.export_tab.cmb_export_data.setCurrentText(_t(TYPES[data_key]))
    view.export_tab.cmb_export_format.setCurrentText(_t(FORMATS[fmt_key][0]))


def _export(view: DataSafetyView, qtbot) -> None:
    view.export_tab.btn_do_export.click()
    qtbot.waitUntil(lambda: view.export_tab.btn_do_export.isEnabled(), timeout=10_000)


@pytest.mark.parametrize("lang", ["en", "si", "ta"])
@pytest.mark.parametrize("fmt_key", ["excel", "csv"])
@pytest.mark.parametrize("data_key", ["products", "customers", "sales"])
def test_each_type_and_format_writes_its_file(
    lang, data_key, fmt_key, qapp, db_session, tmp_path, monkeypatch, fetched, out_dir, qtbot
):
    set_language(lang)
    view = _make_view(tmp_path, monkeypatch)
    try:
        _choose(view, data_key, fmt_key)

        _export(view, qtbot)

        files = list(out_dir.iterdir())
        assert len(files) == 1
        assert files[0].name.startswith(f"{data_key}_")
        assert files[0].suffix == FORMATS[fmt_key][1]
        assert [c[0] for c in fetched] == [data_key]
        assert view.export_tab.lbl_export_status.property("class") == "credit"
        assert str(files[0]) in view.export_tab.lbl_export_status.text()
        assert view.export_tab.btn_do_export.text() == _t("data_safety.export_btn")
    finally:
        view.deleteLater()


def test_success_status_names_the_row_count_and_type(view, fetched, out_dir, qtbot):
    _choose(view, "customers", "csv")

    _export(view, qtbot)

    text = view.export_tab.lbl_export_status.text()
    assert "2" in text
    assert _t("data_safety.export_type_customers").lower() in text


def test_sales_export_uses_the_whole_chosen_days(view, fetched, out_dir, qtbot):
    _choose(view, "sales", "csv")
    view.export_tab.date_export_from.setDate(QDate(2026, 3, 1))
    view.export_tab.date_export_to.setDate(QDate(2026, 3, 31))

    _export(view, qtbot)

    # Under half-open boundary semantics (#912), the end boundary is exclusive start of next day
    assert fetched == [("sales", datetime(2026, 3, 1, 0, 0, 0), datetime(2026, 4, 1, 0, 0, 0))]


def test_sales_with_from_after_to_warns_and_exports_nothing(view, fetched, monkeypatch):
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: warnings.append(a)))
    asked = []
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: asked.append(a) or ""))
    _choose(view, "sales", "csv")
    view.export_tab.date_export_from.setDate(QDate(2026, 4, 1))
    view.export_tab.date_export_to.setDate(QDate(2026, 3, 1))

    view.export_tab.btn_do_export.click()

    assert len(warnings) == 1
    assert asked == []
    assert fetched == []


def test_cancelling_the_folder_choice_exports_nothing(view, fetched, monkeypatch):
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: ""))
    _choose(view, "products", "excel")

    view.export_tab.btn_do_export.click()

    assert fetched == []
    assert view.export_tab.btn_do_export.isEnabled()


def test_a_failing_fetch_shows_the_error_and_reenables_export(view, out_dir, monkeypatch, qtbot):
    def boom():
        raise RuntimeError("db locked")

    monkeypatch.setattr(DataExportService, "get_products_dataframe", staticmethod(boom))
    _choose(view, "products", "excel")

    _export(view, qtbot)

    assert view.export_tab.btn_do_export.isEnabled()
    assert view.export_tab.lbl_export_status.property("class") == "debit"
    assert "db locked" in view.export_tab.lbl_export_status.text()


def test_a_failing_write_shows_the_error(view, fetched, out_dir, monkeypatch, qtbot):
    from cbpos.core.services.export_service import ExportService

    def boom(self, df, filepath):
        raise OSError("disk full")

    monkeypatch.setattr(ExportService, "export_to_csv", boom)
    _choose(view, "products", "csv")

    _export(view, qtbot)

    assert view.export_tab.lbl_export_status.property("class") == "debit"
    assert "disk full" in view.export_tab.lbl_export_status.text()
    assert list(Path(out_dir).iterdir()) == []


# ── #696: choices are opaque keys, not translated display text ────────────


def test_each_choice_carries_an_opaque_key(view):
    data = [view.export_tab.cmb_export_data.itemData(i) for i in range(view.export_tab.cmb_export_data.count())]
    fmts = [view.export_tab.cmb_export_format.itemData(i) for i in range(view.export_tab.cmb_export_format.count())]

    assert data == ["products", "customers", "sales"]
    assert fmts == ["excel", "csv"]


def test_choice_survives_switching_to_sinhala(view):
    set_language("en")
    _choose(view, "sales", "csv")

    set_language("si")

    assert view.export_tab.cmb_export_data.currentText() == _t("data_safety.export_type_sales")
    assert view.export_tab.cmb_export_format.currentText() == _t("data_safety.export_format_csv")
    assert view.export_tab.export_form.isRowVisible(view.export_tab.date_export_from) is True


def test_sales_export_after_switching_to_sinhala(view, fetched, out_dir, qtbot):
    set_language("en")
    _choose(view, "sales", "csv")
    set_language("si")

    _export(view, qtbot)

    assert [c[0] for c in fetched] == ["sales"]
    assert next(out_dir.iterdir()).suffix == ".csv"


def test_a_relabelled_choice_still_exports_its_type(view, fetched, out_dir, qtbot):
    """A translator's trailing space (or a missing key) must not reroute the export."""
    _choose(view, "products", "csv")
    products = view.export_tab.cmb_export_data.currentIndex()
    view.export_tab.cmb_export_data.setItemText(products, _t("data_safety.export_type_products") + " ")

    _export(view, qtbot)

    assert [c[0] for c in fetched] == ["products"]


# ── #695: the export's context travels with its worker ────────────────────


def test_export_worker_hands_back_the_callers_context(tmp_path):
    from unittest.mock import MagicMock

    from cbpos.ui.workers import ExportWorker

    context = object()
    worker = ExportWorker(MagicMock(), pd.DataFrame(), str(tmp_path / "x.csv"), "X", "csv", context=context)
    received = []
    worker.exported.connect(received.append)

    worker.run()

    assert received == [context]


def test_a_failed_export_hands_back_no_context(tmp_path):
    from unittest.mock import MagicMock

    from cbpos.ui.workers import ExportWorker

    service = MagicMock()
    service.export_to_csv.side_effect = OSError("disk full")
    worker = ExportWorker(service, pd.DataFrame(), str(tmp_path / "x.csv"), "X", "csv", context=object())
    received = []
    worker.exported.connect(received.append)

    worker.run()

    assert received == []


# ── #748: export data fetch runs off the UI thread ────────────────────────


def test_fetch_runs_in_background_worker_thread(view, out_dir, monkeypatch, qtbot):
    fetch_threads = []

    def tracking_fetch():
        fetch_threads.append(threading.current_thread())
        return pd.DataFrame({"name": ["p1", "p2"]})

    monkeypatch.setattr(DataExportService, "get_products_dataframe", staticmethod(tracking_fetch))
    _choose(view, "products", "excel")

    _export(view, qtbot)

    assert len(fetch_threads) == 1
    assert fetch_threads[0] != threading.main_thread()


def test_export_worker_fetches_with_data_key_and_updates_context(tmp_path, monkeypatch):
    from unittest.mock import MagicMock

    from cbpos.ui.views.data_safety.export_tab import ExportContext
    from cbpos.ui.workers import ExportWorker

    monkeypatch.setattr(
        DataExportService,
        "get_products_dataframe",
        staticmethod(lambda: pd.DataFrame({"name": ["p1", "p2", "p3"]})),
    )

    service = MagicMock()
    context = ExportContext(filepath=str(tmp_path / "x.csv"), data_key="products", row_count=0)
    worker = ExportWorker(
        service,
        df=None,
        filepath=str(tmp_path / "x.csv"),
        report_name="Products",
        fmt="csv",
        context=context,
        data_key="products",
    )
    received = []
    worker.exported.connect(received.append)

    worker.run()

    service.export_to_csv.assert_called_once()
    assert len(received) == 1
    assert received[0].row_count == 3


def test_export_worker_emits_error_when_fetch_fails(tmp_path, monkeypatch):
    from unittest.mock import MagicMock

    from cbpos.ui.views.data_safety.export_tab import ExportContext
    from cbpos.ui.workers import ExportWorker

    def boom():
        raise RuntimeError("fetch fail")

    monkeypatch.setattr(DataExportService, "get_products_dataframe", staticmethod(boom))

    service = MagicMock()
    context = ExportContext(filepath=str(tmp_path / "x.csv"), data_key="products", row_count=0)
    worker = ExportWorker(
        service,
        df=None,
        filepath=str(tmp_path / "x.csv"),
        report_name="Products",
        fmt="csv",
        context=context,
        data_key="products",
    )
    errors = []
    worker.error.connect(errors.append)

    worker.run()

    assert len(errors) == 1
    assert "fetch fail" in errors[0]
