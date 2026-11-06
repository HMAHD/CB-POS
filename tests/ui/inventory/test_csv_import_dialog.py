"""Tests for CsvImportDialog."""

from pathlib import Path

import pytest

from cbpos.core.services.import_service import ImportService
from cbpos.ui.dialogs.csv_import_dialog import CsvImportDialog

pytestmark = pytest.mark.usefixtures("qapp")


class TestCsvImportDialog:
    def test_preview_step_displays_columns_and_rows(self, monkeypatch, tmp_path: Path):
        csv_file = tmp_path / "preview.csv"
        csv_file.write_text(
            "Barcode,Name,Selling Price,Cost Price,Old Code\n"
            "BC01,Item 1,100.00,50.00,OLD1\n"
            "BC02,Item 2,200.00,120.00,OLD2\n",
            encoding="utf-8",
        )

        service = ImportService()
        dialog = CsvImportDialog(service)

        # Mock QFileDialog to return our CSV
        monkeypatch.setattr(
            "cbpos.ui.dialogs.csv_import_dialog.QFileDialog.getOpenFileName",
            lambda *a, **k: (str(csv_file), "CSV Files (*.csv)"),
        )

        dialog._choose_file()

        # Stack should have advanced to preview page
        assert dialog.stack.currentIndex() == 1
        # Combos created for each header
        assert len(dialog._column_combos) == 5
        assert dialog._column_combos["Selling Price"].currentData() == "price"
        assert dialog._column_combos["Cost Price"].currentData() == "cost"
        assert dialog._column_combos["Old Code"].currentData() == "(ignore)"

        # Preview table should have 2 rows and 5 columns
        assert dialog.preview_table.rowCount() == 2
        assert dialog.preview_table.columnCount() == 5

        # Button text should reflect 2 products
        assert "2" in dialog.btn_import.text()

    def test_duplicate_mapping_shows_warning_and_blocks_import(self, monkeypatch, tmp_path: Path):
        csv_file = tmp_path / "dup.csv"
        csv_file.write_text(
            "Col1,Col2,Price1\n1,2,100\n",
            encoding="utf-8",
        )

        service = ImportService()
        dialog = CsvImportDialog(service)

        monkeypatch.setattr(
            "cbpos.ui.dialogs.csv_import_dialog.QFileDialog.getOpenFileName",
            lambda *a, **k: (str(csv_file), "CSV Files (*.csv)"),
        )
        dialog._choose_file()

        # Manually set two combos to "price"
        c1 = dialog._column_combos["Col1"]
        c2 = dialog._column_combos["Price1"]

        idx_price_1 = c1.findData("price")
        idx_price_2 = c2.findData("price")
        c1.setCurrentIndex(idx_price_1)
        c2.setCurrentIndex(idx_price_2)

        warned = []
        monkeypatch.setattr(
            "cbpos.ui.dialogs.csv_import_dialog.QMessageBox.warning",
            lambda parent, title, text: warned.append(text),
        )

        dialog._start_import()

        assert len(warned) == 1
        assert "Two columns are set to" in warned[0] or "Selling Price" in warned[0]
        # Worker was not started
        assert dialog._csv_worker is None
