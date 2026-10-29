"""
#522/#523: Add Supplier crashed the app on blank fields (no UI-level
validation before the crashing service call), and Suppliers only ever
supported Create -- SupplierDialog already accepted an existing supplier
for editing and SupplierService.update_supplier already supported
is_active, but nothing in purchase_view.py ever wired Edit or Deactivate
to the supplier table.
"""

import pytest
from PyQt6.QtCore import QModelIndex

from cbpos.core.models import Supplier
from cbpos.ui.views.purchase_view import PurchaseView, SupplierDialog

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture
def view(qapp, db_session):
    return PurchaseView()


class TestAddSupplierValidation:
    def test_blank_company_name_is_blocked_before_it_reaches_the_service(self, view, monkeypatch):
        dialog = SupplierDialog(view)
        dialog.company_input.setText("   ")

        warned = []
        monkeypatch.setattr(
            "cbpos.ui.views.purchase_view.QMessageBox.warning",
            lambda *a, **k: warned.append(True),
        )

        dialog.save()

        assert warned == [True]
        assert dialog.result() != dialog.DialogCode.Accepted

    def test_valid_name_accepts_the_dialog(self, view):
        dialog = SupplierDialog(view)
        dialog.company_input.setText("New Supplier Co")

        dialog.save()

        assert dialog.result() == dialog.DialogCode.Accepted

    def test_add_supplier_shows_a_warning_instead_of_crashing_on_duplicate(self, view, db_session, monkeypatch):
        from cbpos.core.services.supplier_service import SupplierService

        SupplierService.create_supplier(company_name="Existing Supplier")

        fake_dialog = SupplierDialog(view)
        fake_dialog.company_input.setText("Existing Supplier")
        monkeypatch.setattr(
            "cbpos.ui.views.purchase_view.SupplierDialog",
            lambda *a, **k: fake_dialog,
        )
        fake_dialog.exec = lambda: True

        warned = []
        monkeypatch.setattr(
            "cbpos.ui.views.purchase_view.QMessageBox.warning",
            lambda *a, **k: warned.append(True),
        )

        view.add_supplier()

        assert warned == [True]


class TestEditSupplier:
    def test_double_click_opens_edit_dialog_prefilled(self, view, db_session, monkeypatch):
        from cbpos.core.services.supplier_service import SupplierService

        SupplierService.create_supplier(company_name="Editable Supplier", phone="0711111111")
        view.refresh_suppliers()
        view.supplier_table.selectRow(0)

        captured = {}

        def fake_dialog_cls(parent, supplier=None):
            captured["supplier"] = supplier
            dlg = SupplierDialog(parent, supplier=supplier)
            dlg.exec = lambda: False
            return dlg

        monkeypatch.setattr("cbpos.ui.views.purchase_view.SupplierDialog", fake_dialog_cls)

        view.edit_supplier()

        assert captured["supplier"].company_name == "Editable Supplier"

    def test_edit_persists_changes_via_update_supplier(self, view, db_session, monkeypatch):
        from cbpos.core.services.supplier_service import SupplierService

        supplier = SupplierService.create_supplier(company_name="Old Name")
        view.refresh_suppliers()
        view.supplier_table.selectRow(0)

        fake_dialog = SupplierDialog(view, supplier=supplier)
        fake_dialog.company_input.setText("New Name")
        fake_dialog.exec = lambda: True
        monkeypatch.setattr("cbpos.ui.views.purchase_view.SupplierDialog", lambda *a, **k: fake_dialog)

        view.edit_supplier()

        db_session.expire_all()
        assert db_session.get(Supplier, supplier.id).company_name == "New Name"

    def test_no_selection_is_a_silent_no_op(self, view, db_session):
        view.supplier_table.setCurrentIndex(QModelIndex())
        view.edit_supplier()  # must not raise


class TestDeactivateSupplier:
    def test_confirming_deactivates_the_supplier(self, view, db_session, monkeypatch):
        from PyQt6.QtWidgets import QMessageBox

        from cbpos.core.services.supplier_service import SupplierService

        supplier = SupplierService.create_supplier(company_name="To Be Deactivated")
        view.refresh_suppliers()
        view.supplier_table.selectRow(0)

        monkeypatch.setattr(
            "cbpos.ui.views.purchase_view.QMessageBox.question",
            lambda *a, **k: QMessageBox.StandardButton.Yes,
        )

        view.deactivate_supplier()

        db_session.expire_all()
        assert db_session.get(Supplier, supplier.id).is_active is False

    def test_declining_leaves_the_supplier_active(self, view, db_session, monkeypatch):
        from PyQt6.QtWidgets import QMessageBox

        from cbpos.core.services.supplier_service import SupplierService

        supplier = SupplierService.create_supplier(company_name="Stays Active")
        view.refresh_suppliers()
        view.supplier_table.selectRow(0)

        monkeypatch.setattr(
            "cbpos.ui.views.purchase_view.QMessageBox.question",
            lambda *a, **k: QMessageBox.StandardButton.No,
        )

        view.deactivate_supplier()

        db_session.expire_all()
        assert db_session.get(Supplier, supplier.id).is_active is True

    def test_deactivated_supplier_disappears_from_the_default_list(self, view, db_session, monkeypatch):
        from PyQt6.QtWidgets import QMessageBox

        from cbpos.core.services.supplier_service import SupplierService

        SupplierService.create_supplier(company_name="Also Deactivated")
        view.refresh_suppliers()
        view.supplier_table.selectRow(0)

        monkeypatch.setattr(
            "cbpos.ui.views.purchase_view.QMessageBox.question",
            lambda *a, **k: QMessageBox.StandardButton.Yes,
        )

        view.deactivate_supplier()

        assert "Also Deactivated" not in [s.company_name for s in view.suppliers]
