"""
New Customer dialog's Commercial tab: Credit Limit (QDoubleSpinBox) and
Payment Terms (QSpinBox) used native spin-box steppers with no explicit
width, while TIN (QLineEdit) stretched to fill the form and Price List
(QComboBox) sat at a third width -- no shared column to anchor the eye,
and the spin-box steppers are the same known-broken widget already
migrated away from in product_editor.py's Stock group.
"""

from decimal import Decimal

import pytest
from PyQt6.QtWidgets import QLineEdit

from cbpos.core.models import Customer
from cbpos.ui.dialogs.customer_editor import CustomerEditor

pytestmark = pytest.mark.usefixtures("qapp")


class TestCommercialTabFieldWidgets:
    def test_credit_limit_and_payment_terms_use_line_edit_not_spinbox(self, db_session):
        dialog = CustomerEditor()

        assert isinstance(dialog.limit_input, QLineEdit)
        assert isinstance(dialog.payment_terms_input, QLineEdit)

    def test_commercial_tab_fields_share_a_consistent_minimum_width(self, db_session):
        dialog = CustomerEditor()

        widths = {
            dialog.tax_id_input.minimumWidth(),
            dialog.limit_input.minimumWidth(),
            dialog.payment_terms_input.minimumWidth(),
            dialog.price_list_combo.minimumWidth(),
        }
        assert len(widths) == 1
        assert widths.pop() > 0


class TestCommercialTabDataRoundTrip:
    def test_load_data_populates_credit_limit_and_payment_terms_text(self, db_session):
        customer = Customer(name="Existing Co", credit_limit=Decimal("15000.50"), payment_terms=45)
        db_session.add(customer)
        db_session.flush()

        dialog = CustomerEditor(customer=customer)

        assert dialog.limit_input.text() == "15000.50"
        assert dialog.payment_terms_input.text() == "45"

    def test_save_parses_credit_limit_and_payment_terms_from_text_fields(self, db_session):
        dialog = CustomerEditor()
        dialog.name_input.setText("New Commercial Customer")
        dialog.limit_input.setText("25000.75")
        dialog.payment_terms_input.setText("30")

        dialog.save()

        saved = db_session.query(Customer).filter_by(name="New Commercial Customer").one()
        assert saved.credit_limit == Decimal("25000.75")
        assert saved.payment_terms == 30
