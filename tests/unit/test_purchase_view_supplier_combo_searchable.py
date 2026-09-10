"""
New GRN's supplier combo and GRN History's supplier filter were both
plain QComboBox() - no setEditable(True), no QCompleter anywhere - hard
to use once a shop has 100+ suppliers. payment_dialog.py's customer combo
already proves the fix: setEditable + setInsertPolicy(NoInsert) + a
QCompleter with MatchContains. Applied the same recipe here.
"""

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QComboBox

from cbpos.core.models import Supplier
from cbpos.ui.views.purchase_view import PurchaseView

pytestmark = pytest.mark.usefixtures("qapp")


def _make_supplier(db_session, name):
    supplier = Supplier(company_name=name)
    db_session.add(supplier)
    db_session.flush()
    return supplier


class TestGrnSupplierComboIsSearchable:
    def test_is_editable_with_no_insert_policy(self, db_session):
        view = PurchaseView()
        assert view.supplier_combo.isEditable() is True
        assert view.supplier_combo.insertPolicy() == QComboBox.InsertPolicy.NoInsert

    def test_has_a_completer_with_contains_matching(self, db_session):
        view = PurchaseView()
        completer = view.supplier_combo.completer()
        assert completer is not None
        assert completer.filterMode() == Qt.MatchFlag.MatchContains

    def test_selecting_a_supplier_by_name_still_resolves_its_id(self, db_session):
        supplier = _make_supplier(db_session, "Searchable Supplier Co")
        view = PurchaseView()

        index = view.supplier_combo.findText(supplier.company_name)
        assert index >= 0
        view.supplier_combo.setCurrentIndex(index)

        assert view.supplier_combo.currentData() == supplier.id


class TestHistorySupplierComboIsSearchable:
    def test_is_editable_with_no_insert_policy(self, db_session):
        view = PurchaseView()
        assert view.history_supplier_combo.isEditable() is True
        assert view.history_supplier_combo.insertPolicy() == QComboBox.InsertPolicy.NoInsert

    def test_has_a_completer_with_contains_matching(self, db_session):
        view = PurchaseView()
        completer = view.history_supplier_combo.completer()
        assert completer is not None
        assert completer.filterMode() == Qt.MatchFlag.MatchContains
