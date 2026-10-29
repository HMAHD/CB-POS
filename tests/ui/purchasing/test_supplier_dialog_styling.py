"""
SupplierDialog was the one dialog in the whole app (of ~15 checked) that
never called setObjectName() at all, so it fell back to bare generic
widget rules with no dedicated QSS block, no setMinimumSize()/resize(),
and Save/Cancel were appended as just another form row instead of a real
button bar. Payment Terms also used a raw QSpinBox -- the exact widget
class this app's own product_editor.py comment documents as breaking
under QSS.
"""

from decimal import Decimal

import pytest
from PyQt6.QtWidgets import QLineEdit

from cbpos.core.models import Supplier
from cbpos.ui.views.purchase_view import SupplierDialog

pytestmark = pytest.mark.usefixtures("qapp")


class TestSupplierDialogStyling:
    def test_has_an_object_name_for_qss_targeting(self, db_session):
        dialog = SupplierDialog()
        assert dialog.objectName() == "SupplierDialog"

    def test_has_an_explicit_minimum_size(self, db_session):
        dialog = SupplierDialog()
        assert dialog.minimumWidth() > 0
        assert dialog.minimumHeight() > 0

    def test_save_and_cancel_have_the_apps_standard_button_object_names(self, db_session):
        dialog = SupplierDialog()
        assert dialog.save_btn.objectName() == "BtnSave"
        assert dialog.cancel_btn.objectName() == "BtnCancel"


class TestPaymentTermsFieldWidget:
    def test_payment_terms_uses_line_edit_not_spinbox(self, db_session):
        dialog = SupplierDialog()
        assert isinstance(dialog.payment_terms_input, QLineEdit)

    def test_load_data_populates_payment_terms_text_for_an_existing_supplier(self, db_session):
        supplier = Supplier(company_name="Existing Supplier Co", payment_terms=45, current_payable=Decimal("0"))
        db_session.add(supplier)
        db_session.flush()

        dialog = SupplierDialog(supplier=supplier)

        assert dialog.payment_terms_input.text() == "45"

    def test_get_data_parses_payment_terms_from_the_text_field(self, db_session):
        dialog = SupplierDialog()
        dialog.company_input.setText("New Supplier Co")
        dialog.payment_terms_input.setText("30")

        data = dialog.get_data()

        assert data["payment_terms"] == 30

    def test_get_data_falls_back_to_zero_on_empty_payment_terms(self, db_session):
        dialog = SupplierDialog()
        dialog.company_input.setText("New Supplier Co")
        dialog.payment_terms_input.setText("")

        data = dialog.get_data()

        assert data["payment_terms"] == 0
