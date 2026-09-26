"""
#420: UnitManagerDialog showed the raw English exception message from
UnitService (str(e)) instead of translating it, unlike other dialogs
(role_manager.py, product_editor.py, category_manager.py) that already
route service errors through translate_error(). Confirms both call
sites now do the same.
"""

from unittest.mock import patch

import pytest
from PyQt6.QtWidgets import QMessageBox, QTableWidgetItem

from cbpos.ui.dialogs.unit_manager import UnitManagerDialog


@pytest.fixture
def dialog(qapp, db_session):
    dlg = UnitManagerDialog()
    yield dlg
    dlg.deleteLater()


class TestServiceErrorsAreTranslated:
    def test_save_shows_the_translated_already_exists_message(self, dialog):
        dialog.txt_name.setText("Kilogram")
        dialog.txt_abbr.setText("kg")

        with patch(
            "cbpos.ui.dialogs.unit_manager.UnitService.create",
            side_effect=ValueError("Unit 'Kilogram' already exists."),
        ):
            with patch("cbpos.ui.dialogs.unit_manager.QMessageBox.warning") as mock_warning:
                dialog._save_unit()

        shown_message = mock_warning.call_args[0][2]
        assert shown_message == "An item with that name already exists."

    def test_delete_shows_the_translated_cannot_delete_message(self, dialog):
        dialog.table.setRowCount(1)
        dialog.table.setItem(0, 0, QTableWidgetItem("1"))
        dialog.table.setItem(0, 1, QTableWidgetItem("Kilogram"))
        dialog.table.setItem(0, 2, QTableWidgetItem("kg"))
        dialog.table.setItem(0, 3, QTableWidgetItem("0"))
        dialog.table.selectRow(0)

        with patch(
            "cbpos.ui.dialogs.unit_manager.UnitService.delete",
            side_effect=ValueError("Cannot delete: 3 product(s) use this unit."),
        ):
            with patch(
                "cbpos.ui.dialogs.unit_manager.QMessageBox.question",
                return_value=QMessageBox.StandardButton.Yes,
            ):
                with patch("cbpos.ui.dialogs.unit_manager.QMessageBox.warning") as mock_warning:
                    dialog._delete_unit()

        shown_message = mock_warning.call_args[0][2]
        assert shown_message == "Cannot delete because it is still in use."
