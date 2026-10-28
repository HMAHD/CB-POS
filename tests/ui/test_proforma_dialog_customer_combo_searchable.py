"""
The Proforma dialog's Customer field had setEditable(True) with nothing
else - no QCompleter, no setInsertPolicy, no placeholder - so it looked
searchable (a text cursor, invites typing) but never actually filtered
anything. That's worse than a plain non-editable combo: it invites an
interaction that then silently does nothing. Same fix already proven for
Purchasing's supplier combos (#280) and payment_dialog.py's customer combo.
"""

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QComboBox

from cbpos.core.models import Customer
from cbpos.ui.dialogs.proforma_dialog import ProformaDialog

pytestmark = pytest.mark.usefixtures("qapp")


def _make_customer(db_session, name):
    customer = Customer(name=name)
    db_session.add(customer)
    db_session.flush()
    return customer


class TestProformaCustomerComboIsSearchable:
    def test_has_no_insert_policy_so_typing_cant_add_bogus_entries(self, db_session):
        dialog = ProformaDialog()
        assert dialog.customer_combo.insertPolicy() == QComboBox.InsertPolicy.NoInsert

    def test_has_a_completer_with_contains_matching(self, db_session):
        dialog = ProformaDialog()
        completer = dialog.customer_combo.completer()
        assert completer is not None
        assert completer.filterMode() == Qt.MatchFlag.MatchContains

    def test_selecting_a_customer_by_name_still_resolves_its_id(self, db_session):
        customer = _make_customer(db_session, "Searchable Customer Co")
        dialog = ProformaDialog()

        index = dialog.customer_combo.findText(customer.name)
        assert index >= 0
        dialog.customer_combo.setCurrentIndex(index)

        assert dialog.customer_combo.currentData() == customer.id
