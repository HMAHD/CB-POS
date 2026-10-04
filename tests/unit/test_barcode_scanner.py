"""
UI-052 (#546): the global BarcodeScanner event filter returned True for
every Enter key press, so returnPressed never fired in any text field
app-wide (manager PIN, Stock Take add, refund lookup, ...). Enter must
only be consumed when it completes a genuine scanner burst.
"""

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QLineEdit

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

    def test_fast_burst_plus_enter_is_a_scan(self, scanner_and_field):
        _scanner, field, scans, returns = scanner_and_field
        QTest.keyClicks(field, "4791234567890")
        QTest.keyClick(field, Qt.Key.Key_Return)

        assert scans == ["4791234567890"]
        assert returns == []  # scan Enter is consumed, as before
