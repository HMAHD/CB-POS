"""
The cart's undo toast hardcoded navy/cyan colors via an unconditional
setStyleSheet() call, ignoring the active theme entirely -- in light mode
it rendered as a dark-mode-looking floating overlay clashing with the
white background, and it never updated on a live theme switch the way
every other themed element in this view does (all styled through
dark.qss/light.qss, refreshed automatically by ThemeService).
"""

from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from cbpos.infrastructure.hardware.escpos_driver import PrintWorker
from cbpos.ui.views.sales_view import SalesView

STYLE_DIR = Path(__file__).resolve().parents[2] / "cbpos" / "ui" / "styles"

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture(autouse=True)
def _shutdown_print_worker():
    yield
    PrintWorker.shutdown()


@pytest.fixture
def view(qapp, db_session):
    v = SalesView()
    yield v
    v.deleteLater()


def _make_product(price="200.00"):
    product = MagicMock()
    product.id = 1
    product.name_en = "Test Product"
    product.barcode = "TEST001"
    product.price = Decimal(price)
    product.stock_qty = Decimal("10")
    product.unit = None
    return product


class TestUndoToastHasNoInlineStyle:
    def test_undo_toast_carries_no_hardcoded_stylesheet(self, view):
        assert view.undo_toast.styleSheet() == ""


class TestUndoToastThemedInQss:
    def test_dark_theme_styles_the_undo_toast(self):
        qss = (STYLE_DIR / "dark.qss").read_text()
        assert "QLabel#UndoToast" in qss

    def test_light_theme_styles_the_undo_toast(self):
        qss = (STYLE_DIR / "light.qss").read_text()
        assert "QLabel#UndoToast" in qss
