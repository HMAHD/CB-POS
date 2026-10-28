from unittest.mock import patch

import pytest
from PyQt6.QtCore import QDateTime
from PyQt6.QtWidgets import QApplication, QLabel, QToolButton

from cbpos.ui.views.sales_view import SalesView

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture
def sales_view(db_session):
    view = SalesView()
    yield view
    view.close()
    view.deleteLater()
    QApplication.processEvents()


class TestSalesHeaderClockAndCalculator:
    def test_sales_header_has_clock_and_calculator(self, sales_view):
        assert hasattr(sales_view, "lbl_header_clock")
        assert isinstance(sales_view.lbl_header_clock, QLabel)
        assert sales_view.lbl_header_clock.objectName() == "SalesHeaderClock"

        assert hasattr(sales_view, "btn_calculator")
        assert isinstance(sales_view.btn_calculator, QToolButton)
        assert sales_view.btn_calculator.objectName() == "HeaderCalculatorBtn"

    def test_calculator_button_clicks_open_native_calculator(self, sales_view):
        with patch("cbpos.ui.views.sales_view.open_native_calculator") as mock_calc:
            sales_view.btn_calculator.click()
            mock_calc.assert_called_once()

    def test_clock_updates_display(self, sales_view):
        fixed_dt = QDateTime.fromString("2026-10-18 12:30:45", "yyyy-MM-dd hh:mm:ss")
        with patch("cbpos.ui.views.sales_view.QDateTime") as mock_dt:
            mock_dt.currentDateTime.return_value = fixed_dt
            sales_view._update_clock()
            assert sales_view.lbl_header_clock.text() == fixed_dt.toString("ddd, d MMM yyyy  hh:mm:ss")
