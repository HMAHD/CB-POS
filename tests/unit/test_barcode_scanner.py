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
from PyQt6.QtWidgets import QAbstractItemView, QApplication, QLineEdit, QPushButton, QTableWidget

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
