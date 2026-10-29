"""Tests for Issue #539 ([REC-05]): Show Contacts tab only for business customers,
prompt on unticking business with contacts present, and hide VAT/TIN for individuals.
"""

from unittest.mock import patch

import pytest
from PyQt6.QtWidgets import QMessageBox

from cbpos.core.models import Customer, CustomerContact
from cbpos.core.services.tax_service import TaxService
from cbpos.ui.dialogs.customer_editor import CustomerEditor

pytestmark = pytest.mark.usefixtures("qapp")


class TestCustomerEditorBusinessContactsVisibility:
    def test_new_individual_customer_hides_contacts_tab_and_tax_fields(self, db_session):
        dialog = CustomerEditor()

        assert not dialog.is_company_chk.isChecked()
        contacts_idx = dialog.tabs.indexOf(dialog.tab_contacts)
        assert not dialog.tabs.isTabVisible(contacts_idx)

        assert dialog._lbl_tin.isHidden()
        assert dialog.tax_id_input.isHidden()
        assert dialog._lbl_vat.isHidden()
        assert dialog.vat_input.isHidden()

    def test_checking_is_company_shows_contacts_tab_and_tax_fields(self, db_session):
        dialog = CustomerEditor()

        with patch.object(TaxService, "is_vat_active", return_value=True):
            dialog.is_company_chk.setChecked(True)

            contacts_idx = dialog.tabs.indexOf(dialog.tab_contacts)
            assert dialog.tabs.isTabVisible(contacts_idx)

            assert not dialog._lbl_tin.isHidden()
            assert not dialog.tax_id_input.isHidden()
            assert not dialog._lbl_vat.isHidden()
            assert not dialog.vat_input.isHidden()

    def test_checking_is_company_when_vat_inactive_hides_vat_but_shows_tin(self, db_session):
        dialog = CustomerEditor()

        with patch.object(TaxService, "is_vat_active", return_value=False):
            dialog.is_company_chk.setChecked(True)

            contacts_idx = dialog.tabs.indexOf(dialog.tab_contacts)
            assert dialog.tabs.isTabVisible(contacts_idx)

            assert not dialog._lbl_tin.isHidden()
            assert not dialog.tax_id_input.isHidden()
            assert dialog._lbl_vat.isHidden()
            assert dialog.vat_input.isHidden()

    def test_loading_individual_customer_without_contacts_hides_contacts_tab(self, db_session):
        customer = Customer(name="Individual John", is_company=False)
        db_session.add(customer)
        db_session.flush()

        dialog = CustomerEditor(customer=customer)

        contacts_idx = dialog.tabs.indexOf(dialog.tab_contacts)
        assert not dialog.tabs.isTabVisible(contacts_idx)
        assert dialog._lbl_tin.isHidden()
        assert dialog.tax_id_input.isHidden()
        assert dialog._lbl_vat.isHidden()
        assert dialog.vat_input.isHidden()

    def test_loading_individual_customer_with_existing_contacts_keeps_contacts_tab_visible(self, db_session):
        customer = Customer(name="Legacy Individual", is_company=False)
        db_session.add(customer)
        db_session.flush()

        contact = CustomerContact(customer_id=customer.id, name="Emergency Contact", phone="0771234567")
        db_session.add(contact)
        db_session.flush()

        dialog = CustomerEditor(customer=customer)

        contacts_idx = dialog.tabs.indexOf(dialog.tab_contacts)
        assert dialog.tabs.isTabVisible(contacts_idx)
        assert dialog.contact_table.rowCount() == 1
        # Tax fields remain hidden because is_company is False
        assert dialog._lbl_tin.isHidden()
        assert dialog.tax_id_input.isHidden()

    def test_removing_last_contact_for_individual_customer_hides_contacts_tab(self, db_session):
        customer = Customer(name="Legacy Individual", is_company=False)
        db_session.add(customer)
        db_session.flush()

        contact = CustomerContact(customer_id=customer.id, name="Single Contact")
        db_session.add(contact)
        db_session.flush()

        dialog = CustomerEditor(customer=customer)
        contacts_idx = dialog.tabs.indexOf(dialog.tab_contacts)
        assert dialog.tabs.isTabVisible(contacts_idx)

        dialog.contact_table.setCurrentCell(0, 0)
        dialog.remove_contact_row()

        assert dialog.contact_table.rowCount() == 0
        assert not dialog.tabs.isTabVisible(contacts_idx)


class TestUntickingBusinessCustomerConfirmation:
    def test_unticking_business_with_contacts_cancelling_preserves_contacts_and_checked(self, db_session):
        dialog = CustomerEditor()
        dialog.is_company_chk.setChecked(True)
        dialog.add_contact_row()
        assert dialog.contact_table.rowCount() == 1

        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No) as mock_question:
            dialog.is_company_chk.setChecked(False)

            mock_question.assert_called_once()
            assert dialog.is_company_chk.isChecked()
            assert dialog.contact_table.rowCount() == 1
            contacts_idx = dialog.tabs.indexOf(dialog.tab_contacts)
            assert dialog.tabs.isTabVisible(contacts_idx)

    def test_unticking_business_with_contacts_confirming_clears_contacts_and_hides_tab(self, db_session):
        dialog = CustomerEditor()
        dialog.is_company_chk.setChecked(True)
        dialog.add_contact_row()
        assert dialog.contact_table.rowCount() == 1

        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes) as mock_question:
            dialog.is_company_chk.setChecked(False)

            mock_question.assert_called_once()
            assert not dialog.is_company_chk.isChecked()
            assert dialog.contact_table.rowCount() == 0
            contacts_idx = dialog.tabs.indexOf(dialog.tab_contacts)
            assert not dialog.tabs.isTabVisible(contacts_idx)

    def test_unticking_business_without_contacts_does_not_prompt_and_hides_tab(self, db_session):
        dialog = CustomerEditor()
        dialog.is_company_chk.setChecked(True)
        assert dialog.contact_table.rowCount() == 0

        with patch.object(QMessageBox, "question") as mock_question:
            dialog.is_company_chk.setChecked(False)

            mock_question.assert_not_called()
            assert not dialog.is_company_chk.isChecked()
            contacts_idx = dialog.tabs.indexOf(dialog.tab_contacts)
            assert not dialog.tabs.isTabVisible(contacts_idx)


class TestSaveCommercialAndContacts:
    def test_save_clears_company_tax_fields_for_individual_customer(self, db_session):
        dialog = CustomerEditor()
        dialog.name_input.setText("Jane Doe")
        dialog.is_company_chk.setChecked(False)
        dialog.company_name_input.setText("Ignored Co")
        dialog.vat_input.setText("VAT123")
        dialog.tax_id_input.setText("TIN456")

        dialog.save()

        saved = db_session.query(Customer).filter_by(name="Jane Doe").one()
        assert not saved.is_company
        assert saved.company_name is None
        assert saved.vat_number is None
        assert saved.tax_id is None
