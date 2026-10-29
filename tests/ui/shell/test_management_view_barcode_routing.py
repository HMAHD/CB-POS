"""
UI-053 (#547): MainWindow routes a scan to the top-level view's
process_barcode_external, and ManagementView had none -- so a scan on any
Management tab (Stock Take) was silently dropped. ManagementView now
forwards it to its current tab when that tab handles scans.

Calls the method unbound on a stub, so the test doesn't build the real
ManagementView (Dashboard starts background workers).
"""

from types import SimpleNamespace

import pytest
from PyQt6.QtWidgets import QStackedWidget, QWidget

from cbpos.ui.views.management_view import ManagementView

pytestmark = pytest.mark.usefixtures("qapp")


class _ScanTab(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.scans: list[str] = []

    def process_barcode_external(self, barcode: str) -> None:
        self.scans.append(barcode)


@pytest.fixture
def stack():
    widget = QStackedWidget()
    yield widget
    widget.deleteLater()


def test_scan_is_forwarded_to_the_current_tab(stack):
    tab = _ScanTab()
    stack.addWidget(QWidget())
    stack.addWidget(tab)
    stack.setCurrentWidget(tab)

    ManagementView.process_barcode_external(SimpleNamespace(stack=stack), "4791234567890")

    assert tab.scans == ["4791234567890"]


def test_scan_is_ignored_when_the_current_tab_has_no_handler(stack):
    tab = _ScanTab()
    plain = QWidget()
    stack.addWidget(tab)
    stack.addWidget(plain)
    stack.setCurrentWidget(plain)

    ManagementView.process_barcode_external(SimpleNamespace(stack=stack), "4791234567890")

    assert tab.scans == []
