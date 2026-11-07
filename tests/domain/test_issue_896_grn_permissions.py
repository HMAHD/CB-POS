from datetime import datetime
from decimal import Decimal

import pytest

from cbpos.core.constants.permissions import Permissions
from cbpos.core.models import Permission, Product, Role, Supplier, User
from cbpos.core.services.purchase_service import GrnLine, GrnRequest, PurchaseService
from cbpos.core.services.supplier_service import SupplierService

_counter = 0


def _uid():
    global _counter
    _counter += 1
    return str(_counter)


@pytest.fixture
def supplier(db_session):
    s = Supplier(company_name=f"Test Supplier {_uid()}")
    db_session.add(s)
    db_session.commit()
    return s


@pytest.fixture
def product(db_session):
    p = Product(
        name_en=f"Test Product {_uid()}",
        barcode=f"BAR{_uid()}",
        price=Decimal("150.00"),
        cost=Decimal("100.00"),
        stock_qty=Decimal("10"),
    )
    db_session.add(p)
    db_session.commit()
    return p


@pytest.fixture
def unprivileged_user(db_session):
    uid = _uid()
    p = Permission(code=f"dummy_{uid}", description="dummy", group="Sales")
    role = Role(name=f"Role_{uid}", permissions=[p])
    user = User(username=f"user_{uid}", pin_hash="hash", role=role)
    db_session.add_all([p, role, user])
    db_session.commit()
    return user


@pytest.fixture
def privileged_user(db_session):
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

    role = Role(name=f"PrivRole_{uid}", permissions=[p_grn, p_sup])
    user = User(username=f"priv_user_{uid}", pin_hash="hash", role=role)
    db_session.add_all([role, user])
    db_session.commit()
    return user


def test_issue_896_receive_goods_requires_permission(db_session, supplier, product, unprivileged_user, privileged_user):
    """Calling receive_goods with a user lacking purchase.create_grn raises PermissionError."""
    req_denied = GrnRequest(
        supplier_id=supplier.id,
        date_received=datetime.now(),
        supplier_invoice_no=f"INV-{_uid()}",
        input_vat=Decimal("0.00"),
        lines=[GrnLine(product_id=product.id, qty=Decimal("5"), unit_cost=Decimal("100.00"))],
        user_id=unprivileged_user.id,
    )

    with pytest.raises(PermissionError) as exc_info:
        PurchaseService.receive_goods(req_denied)
    assert "purchase.create_grn" in str(exc_info.value)

    # With privileged user, receive_goods succeeds
    req_allowed = GrnRequest(
        supplier_id=supplier.id,
        date_received=datetime.now(),
        supplier_invoice_no=f"INV-{_uid()}",
        input_vat=Decimal("0.00"),
        lines=[GrnLine(product_id=product.id, qty=Decimal("5"), unit_cost=Decimal("100.00"))],
        user_id=privileged_user.id,
    )
    purchase = PurchaseService.receive_goods(req_allowed)
    assert purchase is not None
    assert purchase.document_number is not None

    # With unprivileged user but supervisor override (approved_by=privileged_user.id), it succeeds
    req_override = GrnRequest(
        supplier_id=supplier.id,
        date_received=datetime.now(),
        supplier_invoice_no=f"INV-{_uid()}",
        input_vat=Decimal("0.00"),
        lines=[GrnLine(product_id=product.id, qty=Decimal("5"), unit_cost=Decimal("100.00"))],
        user_id=unprivileged_user.id,
        approved_by=privileged_user.id,
    )
    purchase_ovr = PurchaseService.receive_goods(req_override)
    assert purchase_ovr is not None


def test_issue_896_supplier_crud_requires_suppliers_manage(db_session, unprivileged_user, privileged_user):
    """SupplierService mutators require suppliers.manage when an acting user is provided."""
    # 1. create_supplier without permission fails
    with pytest.raises(PermissionError) as exc_info:
        SupplierService.create_supplier(
            company_name=f"Denied Supplier {_uid()}",
            acting_user_id=unprivileged_user.id,
        )
    assert "suppliers.manage" in str(exc_info.value)

    # 2. create_supplier with permission succeeds
    sup = SupplierService.create_supplier(
        company_name=f"Allowed Supplier {_uid()}",
        acting_user_id=privileged_user.id,
    )
    assert sup.id is not None

    # 3. update_supplier without permission fails
    with pytest.raises(PermissionError) as exc_info:
        SupplierService.update_supplier(
            supplier_id=sup.id,
            company_name=f"Updated Denied {_uid()}",
            acting_user_id=unprivileged_user.id,
        )
    assert "suppliers.manage" in str(exc_info.value)

    # 4. update_supplier with permission succeeds
    updated = SupplierService.update_supplier(
        supplier_id=sup.id,
        company_name=f"Updated Allowed {_uid()}",
        acting_user_id=privileged_user.id,
    )
    assert updated.company_name.startswith("Updated Allowed")

    # 5. deactivate without permission fails
    with pytest.raises(PermissionError) as exc_info:
        SupplierService.update_supplier(
            supplier_id=sup.id,
            is_active=False,
            acting_user_id=unprivileged_user.id,
        )
    assert "suppliers.manage" in str(exc_info.value)
