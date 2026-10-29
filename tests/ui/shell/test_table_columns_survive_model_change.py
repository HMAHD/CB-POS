"""configure_table_columns modes survive setModel (UI_SYSTEM_AUDIT A1).

Views configure columns in __init__ and set or replace the model on every
load; Qt rebuilds the header sections then, which dropped the modes, so the
Suppliers table fell back to narrow default columns with "Munchee ..." cut.
"""

import gc

import pytest
from PyQt6.QtGui import QStandardItemModel
from PyQt6.QtWidgets import QHeaderView, QTableView

from cbpos.ui.widgets.table_helpers import configure_table_columns

pytestmark = pytest.mark.usefixtures("qapp")
Stretch, Fit = QHeaderView.ResizeMode.Stretch, QHeaderView.ResizeMode.ResizeToContents


def _configured_table() -> QTableView:
    table = QTableView()
    configure_table_columns(table.horizontalHeader(), {0: Fit, 1: Stretch})
    return table  # the helper's own references are gone after return, as in a real view


def test_modes_apply_to_a_model_set_later_and_replaced():
    table = _configured_table()
    gc.collect()

    for _ in range(2):  # first load, then a refresh that replaces the model
        table.setModel(QStandardItemModel(3, 2))
        assert table.horizontalHeader().sectionResizeMode(1) == Stretch
        assert table.horizontalHeader().sectionResizeMode(0) == Fit


def test_supplier_table_hides_internal_id_and_row_gutter(db_session):
    from cbpos.core.services.supplier_service import SupplierService
    from cbpos.ui.views.purchase_view import PurchaseView

    SupplierService.create_supplier("Munchee (Pvt) Ltd")
    view = PurchaseView()
    view.refresh_suppliers()  # a reload replaces the model

    table = view.supplier_table
    assert table.isColumnHidden(0)
    assert not table.verticalHeader().isVisible()
    assert table.horizontalHeader().sectionResizeMode(1) == Stretch
