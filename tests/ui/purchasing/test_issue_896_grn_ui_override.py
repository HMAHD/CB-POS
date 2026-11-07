from decimal import Decimal
from unittest.mock import patch

import pytest

from cbpos.core.constants.permissions import Permissions
from cbpos.core.models import Permission, Product, Purchase, Role, Supplier, User
from cbpos.ui.views.purchase_view import PurchaseView

pytestmark = pytest.mark.usefixtures("qapp")

_counter = 0


def _uid():
    global _counter
    _counter += 1
    return str(_counter)


@pytest.fixture
def supplier(db_session):
    s = Supplier(company_name=f"UI Supplier {_uid()}")
    db_session.add(s)
    db_session.flush()
    return s


@pytest.fixture
def product(db_session):
    p = Product(
        name_en=f"UI Product {_uid()}",
        barcode=f"BARUI{_uid()}",
        price=Decimal("200.00"),
        cost=Decimal("100.00"),
        stock_qty=Decimal("10"),
    )
    db_session.add(p)
    db_session.flush()
    return p


@pytest.fixture
def unprivileged_user(db_session):
    uid = _uid()
    p = Permission(code=f"dummy_{uid}", description="dummy", group="Sales")
    role = Role(name=f"Role_{uid}", permissions=[p])
    user = User(username=f"user_{uid}", pin_hash="hash", role=role)
    db_session.add_all([p, role, user])
    db_session.flush()
    return user


@pytest.fixture
def supervisor_user(db_session):
    uid = _uid()
    p_grn = db_session.query(Permission).filter_by(code=Permissions.PURCHASE_CREATE_GRN).first()
    if not p_grn:
        p_grn = Permission(
            code=Permissions.PURCHASE_CREATE_GRN,
            description="Create GRN",
            group="Purchase",
        )
        db_session.add(p_grn)

    p_sup = db_session.query(Permission).filter_by(code="suppliers.manage").first()
    if not p_sup:
        p_sup = Permission(
            code="suppliers.manage",
            description="Manage Suppliers",
            group="Purchase",
        )
        db_session.add(p_sup)

    role = Role(name=f"SuperRole_{uid}", permissions=[p_grn, p_sup])
    user = User(username=f"supervisor_{uid}", pin_hash="hash", role=role)
    db_session.add_all([role, user])
    db_session.flush()
    return user


def test_issue_896_commit_without_permission_prompts_override(
    db_session, supplier, product, unprivileged_user, supervisor_user, monkeypatch
):
    """A user without purchase.create_grn is prompted for override when committing GRN."""
    view = PurchaseView()
    view.set_user(unprivileged_user)
    view.supplier_combo.addItem(supplier.company_name, supplier.id)
    view.supplier_combo.setCurrentIndex(view.supplier_combo.findData(supplier.id))
    view.invoice_input.setText("INV-896-TEST")
    view._add_grn_row(product, Decimal("2"), Decimal("100.00"))

    # 1. Override cancelled (returns None) -> no purchase created
    with patch(
        "cbpos.ui.views.purchase_view.check_permission_with_override",
        return_value=None,
    ) as mock_override:
        view.commit_grn()
        mock_override.assert_called_once_with(Permissions.PURCHASE_CREATE_GRN, view)

    db_session.expire_all()
    assert db_session.query(Purchase).filter_by(reference_external="INV-896-TEST").first() is None
    # Form still has items
    assert view.grn_model.rowCount() == 1

    # 2. Override approved (returns supervisor_user) -> purchase created
    monkeypatch.setattr("cbpos.ui.views.purchase_view.QMessageBox.information", lambda *a, **k: None)
    with patch(
        "cbpos.ui.views.purchase_view.check_permission_with_override",
        return_value=supervisor_user,
    ) as mock_override:
        view.commit_grn()
        mock_override.assert_called_once_with(Permissions.PURCHASE_CREATE_GRN, view)

    db_session.expire_all()
    purchase = db_session.query(Purchase).filter_by(reference_external="INV-896-TEST").first()
    assert purchase is not None
    # Form was reset
    assert view.grn_model.rowCount() == 0


def test_issue_896_supplier_crud_prompts_override(db_session, supplier, unprivileged_user, supervisor_user):
    """Supplier add, edit, and deactivate buttons require suppliers.manage."""
    view = PurchaseView()
    view.set_user(unprivileged_user)

    # 1. Add supplier - cancelled
    with (
        patch(
            "cbpos.ui.views.purchase_view.check_permission_with_override",
            return_value=None,
        ) as mock_override,
        patch("cbpos.ui.views.purchase_view.SupplierDialog") as mock_dlg,
    ):
        view.add_supplier()
        mock_override.assert_called_once_with(Permissions.SUPPLIERS_MANAGE, view)
        mock_dlg.assert_not_called()

    # 2. Edit supplier - cancelled
    with patch.object(view, "_selected_supplier", return_value=supplier):
        with (
            patch(
                "cbpos.ui.views.purchase_view.check_permission_with_override",
                return_value=None,
            ) as mock_override,
            patch("cbpos.ui.views.purchase_view.SupplierDialog") as mock_dlg,
        ):
            view.edit_supplier()
            mock_override.assert_called_once_with(Permissions.SUPPLIERS_MANAGE, view)
            mock_dlg.assert_not_called()

    # 3. Deactivate supplier - cancelled
    with patch.object(view, "_selected_supplier", return_value=supplier):
        with (
            patch(
                "cbpos.ui.views.purchase_view.check_permission_with_override",
                return_value=None,
            ) as mock_override,
            patch("cbpos.ui.views.purchase_view.QMessageBox.question") as mock_q,
        ):
            view.deactivate_supplier()
            mock_override.assert_called_once_with(Permissions.SUPPLIERS_MANAGE, view)
            mock_q.assert_not_called()
