"""Unit tests for CustomerSelectionDialog keyboard workflow and full name display."""

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QWidget

from cbpos.core.models import Customer
from cbpos.ui.dialogs.customer_selection_dialog import CustomerSelectionDialog
from cbpos.ui.widgets.action_panel import ActionPanel

pytestmark = pytest.mark.usefixtures("qapp")


def _seed_customers(db_session):
    c1 = Customer(name="Dilini Rathnayake", phone="0721234567")
    c2 = Customer(name="Kasun Perera", phone="0771234567")
    c3 = Customer(name="Amal Silva", phone="0711234567")
    db_session.add_all([c1, c2, c3])
    db_session.flush()
    return c1, c2, c3


class TestCustomerSelectionKeyboardWorkflow:
    def test_search_input_receives_focus_on_show(self, db_session):
        _seed_customers(db_session)
        dialog = CustomerSelectionDialog()
        dialog.show()
        dialog.activateWindow()
        QApplication.setActiveWindow(dialog)
        QTest.qWaitForWindowExposed(dialog)
        QApplication.processEvents()

        assert dialog.search_input.hasFocus()
        dialog.close()

    def test_first_row_is_auto_selected_on_load_and_filter(self, db_session):
        _seed_customers(db_session)
        dialog = CustomerSelectionDialog()
        dialog.show()

        assert dialog.table.rowCount() >= 2
        assert dialog.table.currentRow() == 0

        # When filtered
        dialog.search_input.setText("Perera")
        assert dialog.table.rowCount() == 1
        assert dialog.table.currentRow() == 0
        dialog.close()

    def test_arrow_keys_navigate_table_from_search_input(self, db_session):
        _seed_customers(db_session)
        dialog = CustomerSelectionDialog()
        dialog.show()
        QTest.qWaitForWindowExposed(dialog)

        assert dialog.table.currentRow() == 0

        # Press Down arrow while focus is in search_input
        QTest.keyClick(dialog.search_input, Qt.Key.Key_Down)
        assert dialog.table.currentRow() == 1

        # Press Down arrow again
        QTest.keyClick(dialog.search_input, Qt.Key.Key_Down)
        assert dialog.table.currentRow() == 2

        # Press Up arrow
        QTest.keyClick(dialog.search_input, Qt.Key.Key_Up)
        assert dialog.table.currentRow() == 1
        dialog.close()

    def test_enter_key_in_search_input_selects_current_customer(self, db_session):
        _seed_customers(db_session)
        dialog = CustomerSelectionDialog()
        dialog.show()
        QTest.qWaitForWindowExposed(dialog)

        # Type to filter to Kasun
        dialog.search_input.setText("Kasun")
        assert dialog.table.rowCount() == 1
        assert dialog.table.currentRow() == 0

        # Press Return in search_input
        QTest.keyClick(dialog.search_input, Qt.Key.Key_Return)

        assert dialog.selected_customer is not None
        assert dialog.selected_customer.name == "Kasun Perera"
        assert dialog.result() == dialog.DialogCode.Accepted

    def test_parent_enter_shortcuts_disabled_during_dialog_execution(self, db_session):
        parent = QWidget()
        parent.shortcut_enter = QShortcut(QKeySequence(Qt.Key.Key_Return), parent)
        parent.shortcut_num_enter = QShortcut(QKeySequence(Qt.Key.Key_Enter), parent)
        assert parent.shortcut_enter.isEnabled() is True
        assert parent.shortcut_num_enter.isEnabled() is True

        dialog = CustomerSelectionDialog(parent=parent)

        # Parent enter shortcuts should be disabled while dialog is open
        assert parent.shortcut_enter.isEnabled() is False
        assert parent.shortcut_num_enter.isEnabled() is False

        dialog.reject()

        # Re-enabled after close
        assert parent.shortcut_enter.isEnabled() is True
        assert parent.shortcut_num_enter.isEnabled() is True


class TestCustomerFullNameDisplay:
    def test_action_panel_shows_full_name_without_shortening_initials(self):
        panel = ActionPanel()
        panel.show()

        panel.set_customer_info("Dilini Rathnayake", "0721234567", 200)

        # Must display full name, not "Dilini R"
        assert panel.lbl_customer.text() == "Dilini Rathnayake"

    def test_format_short_name_is_removed_from_formatters(self):
        import cbpos.core.utils.formatters as formatters_mod

        assert not hasattr(formatters_mod, "format_short_name")
