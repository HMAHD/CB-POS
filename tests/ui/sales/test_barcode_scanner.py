"""
UI-052 (#546): the global BarcodeScanner event filter returned True for
every Enter key press, so returnPressed never fired in any text field
app-wide (manager PIN, Stock Take add, refund lookup, ...). Enter must
only be consumed when it completes a genuine scanner burst.
"""

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QAbstractItemView, QApplication, QDialog, QLineEdit, QPushButton, QTableWidget

from cbpos.infrastructure.hardware.scanner import BarcodeScanner

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture
def scanner_and_field():
    app = QApplication.instance()
    scanner = BarcodeScanner(app)
    field = QLineEdit()
    scans: list[str] = []
    returns: list[str] = []
    scanner.barcode_scanned.connect(scans.append)
    field.returnPressed.connect(lambda: returns.append(field.text()))
    yield scanner, field, scans, returns
    app.removeEventFilter(scanner)


class TestBarcodeScannerEnter:
    def test_human_enter_reaches_the_field_and_is_not_a_scan(self, scanner_and_field):
        _scanner, field, scans, returns = scanner_and_field
        QTest.keyClick(field, Qt.Key.Key_5)
        QTest.qWait(120)  # human pause, longer than the scanner speed window
        QTest.keyClick(field, Qt.Key.Key_Return)

        assert returns == ["5"]
        assert scans == []

    def test_enter_on_empty_field_reaches_the_field(self, scanner_and_field):
        _scanner, field, scans, returns = scanner_and_field
        QTest.keyClick(field, Qt.Key.Key_Enter)

        assert returns == [""]
        assert scans == []

    def test_burst_into_text_field_is_submitted_by_the_field_not_routed(self, scanner_and_field):
        """Scan typed into a QLineEdit submits via its own returnPressed (Sales search,
        Stock Take add, scanner test); routing it to the view too would double-handle it."""
        _scanner, field, scans, returns = scanner_and_field
        QTest.keyClicks(field, "4791234567890")
        QTest.keyClick(field, Qt.Key.Key_Return)

        assert returns == ["4791234567890"]
        assert scans == []

    def test_burst_with_no_text_field_focused_is_routed_as_a_scan(self, scanner_and_field):
        scanner, _field, scans, _returns = scanner_and_field
        button = QPushButton()
        QTest.keyClicks(button, "4791234567890")
        QTest.keyClick(button, Qt.Key.Key_Return)

        assert scans == ["4791234567890"]
        assert scanner.buffer == ""

    def test_readonly_field_does_not_swallow_scan(self, scanner_and_field):
        _scanner, field, scans, _returns = scanner_and_field
        field.setReadOnly(True)
        QTest.keyClicks(field, "4791234567890")
        QTest.keyClick(field, Qt.Key.Key_Return)

        assert scans == ["4791234567890"]

    def test_burst_into_a_scan_passthrough_editor_is_routed_as_a_scan(self, scanner_and_field):
        """A quantity cell editor (Stock Take Counted) opts out of keeping Enter, so a
        scan landing there is routed to the view instead of committed as a quantity (#547)."""
        _scanner, field, scans, returns = scanner_and_field
        field.setProperty(BarcodeScanner.SCAN_PASSTHROUGH_PROPERTY, True)
        QTest.keyClicks(field, "4791234567890")
        QTest.keyClick(field, Qt.Key.Key_Return)

        assert scans == ["4791234567890"]
        assert returns == []

    def test_human_enter_in_a_scan_passthrough_editor_still_reaches_it(self, scanner_and_field):
        _scanner, field, scans, returns = scanner_and_field
        field.setProperty(BarcodeScanner.SCAN_PASSTHROUGH_PROPERTY, True)
        QTest.keyClick(field, Qt.Key.Key_7)
        QTest.qWait(120)
        QTest.keyClick(field, Qt.Key.Key_Return)

        assert returns == ["7"]
        assert scans == []


@pytest.fixture
def table_with_enter_shortcut():
    """A focused table whose Enter is a widget shortcut (Stock Take History, #594)."""
    table = QTableWidget(1, 1)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)  # like History
    fired: list[int] = []
    shortcut = QShortcut(QKeySequence(Qt.Key.Key_Return), table)
    shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
    shortcut.activated.connect(lambda: fired.append(1))
    table.show()
    table.activateWindow()
    QTest.qWaitForWindowActive(table)
    table.setFocus()
    yield table, fired
    table.hide()
    table.deleteLater()


class TestBarcodeScannerVsEnterShortcut:
    def test_burst_is_routed_as_a_scan_not_taken_by_the_shortcut(self, scanner_and_field, table_with_enter_shortcut):
        """#548: a scan on a widget with an Enter shortcut used to fire the shortcut
        and lose the scan."""
        scanner, _field, scans, _returns = scanner_and_field
        table, fired = table_with_enter_shortcut

        QTest.keyClicks(table, "4791234567890")
        QTest.keyClick(table, Qt.Key.Key_Return)

        assert scans == ["4791234567890"]
        assert fired == []
        assert scanner.buffer == ""

    def test_human_enter_still_fires_the_shortcut(self, scanner_and_field, table_with_enter_shortcut):
        _scanner, _field, scans, _returns = scanner_and_field
        table, fired = table_with_enter_shortcut

        QTest.keyClick(table, Qt.Key.Key_Return)

        assert fired == [1]
        assert scans == []

    def test_modal_dialog_enter_shortcut_keeps_its_enter(self, scanner_and_field):
        """Behind a modal (payment, quantity) the scan must not reach the view; the
        dialog's own Enter shortcut keeps the key, as before #548."""
        _scanner, _field, scans, _returns = scanner_and_field
        dialog = QDialog()
        dialog.setModal(True)
        button = QPushButton(dialog)
        fired: list[int] = []
        QShortcut(QKeySequence(Qt.Key.Key_Return), dialog).activated.connect(lambda: fired.append(1))
        dialog.show()
        dialog.activateWindow()
        QTest.qWaitForWindowActive(dialog)
        button.setFocus()
        try:
            QTest.keyClicks(button, "4791234567890")
            QTest.keyClick(button, Qt.Key.Key_Return)
        finally:
            dialog.hide()
            dialog.deleteLater()

        assert fired == [1]
        assert scans == []

    def test_issue_890_scan_with_modal_open_not_emitted(self, scanner_and_field):
        """With a modal dialog open and a focused QPushButton (no shortcut), scan burst emits nothing (#890)."""
        _scanner, _field, scans, _returns = scanner_and_field
        dialog = QDialog()
        dialog.setModal(True)
        button = QPushButton("OK", dialog)
        clicks: list[int] = []
        button.clicked.connect(lambda: clicks.append(1))
        dialog.show()
        dialog.activateWindow()
        QTest.qWaitForWindowActive(dialog)
        button.setFocus()
        try:
            QTest.keyClicks(button, "4791234567890")
            QTest.keyClick(button, Qt.Key.Key_Return)
        finally:
            dialog.hide()
            dialog.deleteLater()

        assert scans == []
        assert clicks == [1]

    def test_issue_841_focus_on_nested_button_emits_exact_code(self, scanner_and_field):
        """#841: with focus on a nested QPushButton, scan keypresses propagate up
        parent widgets. Each key must be buffered once, emitting the exact barcode."""
        from PyQt6.QtWidgets import QVBoxLayout, QWidget

        _scanner, _field, scans, _returns = scanner_and_field
        window = QWidget()
        outer_layout = QVBoxLayout(window)
        panel = QWidget()
        outer_layout.addWidget(panel)
        inner_layout = QVBoxLayout(panel)
        button = QPushButton("Action", panel)
        inner_layout.addWidget(button)

        window.show()
        window.activateWindow()
        QTest.qWaitForWindowActive(window)
        button.setFocus()

        try:
            QTest.keyClicks(button, "4791234567890")
            QTest.keyClick(button, Qt.Key.Key_Return)
        finally:
            window.hide()
            window.deleteLater()

        assert scans == ["4791234567890"]

    def test_issue_841_repeated_digits_barcode_emitted_accurately(self, scanner_and_field):
        """#841: a barcode with genuine repeated digits ('444777999') must not be
        deduplicated into single digits."""
        from PyQt6.QtWidgets import QVBoxLayout, QWidget

        _scanner, _field, scans, _returns = scanner_and_field
        window = QWidget()
        outer_layout = QVBoxLayout(window)
        panel = QWidget()
        outer_layout.addWidget(panel)
        inner_layout = QVBoxLayout(panel)
        button = QPushButton("Action", panel)
        inner_layout.addWidget(button)

        window.show()
        window.activateWindow()
        QTest.qWaitForWindowActive(window)
        button.setFocus()

        try:
            QTest.keyClicks(button, "444777999")
            QTest.keyClick(button, Qt.Key.Key_Return)
        finally:
            window.hide()
            window.deleteLater()

        assert scans == ["444777999"]

    def test_issue_841_ordinary_keyboard_typing_not_a_false_scan(self, scanner_and_field):
        """#841: ordinary slow human typing outside a text field does not become a scan."""
        _scanner, _field, scans, _returns = scanner_and_field
        button = QPushButton("Action")
        button.show()
        button.activateWindow()
        QTest.qWaitForWindowActive(button)
        button.setFocus()

        try:
            for char in "1234":
                key = getattr(Qt.Key, f"Key_{char}")
                QTest.keyClick(button, key)
                QTest.qWait(120)  # slow human typing > 50ms buffer window
            QTest.keyClick(button, Qt.Key.Key_Return)
        finally:
            button.hide()
            button.deleteLater()

        assert scans == []
