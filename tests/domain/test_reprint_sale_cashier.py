"""
#681: a reprinted receipt shows the sale's own cashier and quantities.

ReceiptBuilder used to print the currently logged-in user as cashier, so a
reprint by cashier B of a sale made by cashier A said "Cashier: B". And a
sale reloaded from the database carries its quantity as ``2.000`` (the
column's scale), so a reprint showed ``2.000`` where the auto-print right
after the sale showed ``2``. Both are fixed in the builder, so the original
print and every reprint share one path.
"""

from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from cbpos.core.models import Product, Sale, SaleItem, SalePayment, Unit, User
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.receipt_builder import ReceiptBuilder


class _FakeConfigStore:
    def __init__(self, initial: dict):
        self._data = dict(initial)

    def get(self, key):
        return self._data.get(key)

    def get_all(self):
        return dict(self._data)

    def set(self, key, value):
        self._data[key] = value


@pytest.fixture
def config_store(monkeypatch):
    store = _FakeConfigStore(dict(ConfigService.DEFAULTS))
    store.set("receipt_language", "en")
    store.set("show_cashier_on_receipt", True)
    monkeypatch.setattr(ConfigService, "get", store.get)
    monkeypatch.setattr(ConfigService, "get_all", store.get_all)
    return store


@pytest.fixture
def logged_in_as_b():
    with patch(
        "cbpos.core.services.auth_service.AuthService.get_current_user",
        return_value=SimpleNamespace(username="cashier_b"),
    ):
        yield


def _sale(qty: str = "2.000", unit: Unit | None = None, user: User | None = None, user_id: int | None = None) -> Sale:
    sale = Sale(
        id=11,
        document_number="INV-2026-00011",
        date=datetime(2026, 10, 7, 9, 30),
        total_amount=Decimal("236.00"),
        tax_vat=Decimal("0"),
        tax_sscl=Decimal("0"),
        net_revenue=Decimal("236.00"),
        payment_method="CASH",
        status="COMPLETED",
        user_id=user_id,
    )
    if user is not None:
        sale.user = user
    sale.items = [
        SaleItem(
            product=Product(name_en="Soap", unit=unit),
            qty=Decimal(qty),
            unit_price=Decimal("118.00"),
            original_price=Decimal("118.00"),
            subtotal=Decimal("236.00"),
        )
    ]
    sale.payments = [SalePayment(payment_method="CASH", amount=Decimal("300.00"))]
    return sale


def _texts(commands: list[dict]) -> list[str]:
    return [c.get("val", "") for c in commands if c.get("type") == "text"]


class TestCashierIsTheSalesCashier:
    def test_reprint_shows_original_cashier_not_current_user(self, config_store, logged_in_as_b):
        sale = _sale(user=User(username="cashier_a", pin_hash="x"), user_id=5)

        lines = _texts(ReceiptBuilder.build_receipt(sale, is_reprint=True))

        assert any("cashier_a" in line for line in lines)
        assert not any("cashier_b" in line for line in lines)

    def test_unsaved_preview_sale_falls_back_to_current_user(self, config_store, logged_in_as_b):
        lines = _texts(ReceiptBuilder.build_receipt(_sale()))

        assert any("cashier_b" in line for line in lines)

    def test_saved_sale_without_loaded_user_never_prints_someone_else(self, config_store, logged_in_as_b):
        sale = _sale(user_id=5)  # cashier recorded, but the relationship wasn't loaded

        lines = _texts(ReceiptBuilder.build_receipt(sale, is_reprint=True))

        assert not any("cashier_b" in line for line in lines)


class TestQuantityFormat:
    def test_piece_quantity_from_db_prints_without_decimals(self, config_store, logged_in_as_b):
        lines = _texts(ReceiptBuilder.build_receipt(_sale(qty="2.000", unit=Unit(name="pcs", decimal_places=0))))

        assert any(line.startswith("   2 x ") for line in lines)
        assert not any("2.000 x" in line for line in lines)

    def test_weighed_quantity_keeps_its_three_decimals(self, config_store, logged_in_as_b):
        lines = _texts(ReceiptBuilder.build_receipt(_sale(qty="1.250", unit=Unit(name="kg", decimal_places=3))))

        assert any(line.startswith("   1.250 x ") for line in lines)

    def test_no_unit_prints_whole_number_plainly(self, config_store, logged_in_as_b):
        lines = _texts(ReceiptBuilder.build_receipt(_sale(qty="2.000")))

        assert any(line.startswith("   2 x ") for line in lines)

    def test_no_unit_keeps_fractional_quantity(self, config_store, logged_in_as_b):
        lines = _texts(ReceiptBuilder.build_receipt(_sale(qty="0.500")))

        assert any(line.startswith("   0.500 x ") for line in lines)

    def test_original_and_reloaded_quantity_print_the_same(self, config_store, logged_in_as_b):
        unit = Unit(name="pcs", decimal_places=0)
        fresh = _texts(ReceiptBuilder.build_receipt(_sale(qty="2", unit=unit)))
        reloaded = _texts(ReceiptBuilder.build_receipt(_sale(qty="2.000", unit=unit)))

        assert fresh == reloaded


# ── Database round trip: the sale is reloaded as every reprint path does ──


@pytest.fixture
def two_cashiers(db_session):
    from cbpos.core.models import Role

    role = Role(name="ReprintCashierRole")
    cashier_a = User(username="reprint_cashier_a", pin_hash="x", role=role)
    cashier_b = User(username="reprint_cashier_b", pin_hash="x", role=role)
    pcs = Unit(name="reprint_pcs", abbreviation="pcs", decimal_places=0)
    product = Product(name_en="ReprintSoap", price=Decimal("100"), stock_qty=Decimal("10"), barcode="RPC0001", unit=pcs)
    db_session.add_all([role, cashier_a, cashier_b, pcs, product])
    db_session.flush()
    return cashier_a, cashier_b, product


def test_reprint_of_reloaded_sale_shows_cashier_a_and_plain_quantity(config_store, db_session, two_cashiers):
    from cbpos.core.services.cart_service import CartService
    from cbpos.core.services.sale_query_service import SaleQueryService
    from cbpos.core.services.transaction_service import TransactionService

    cashier_a, cashier_b, product = two_cashiers
    config_store.set("show_receipt_dialog", True)  # no auto-print in this test

    cart = CartService()
    cart.add_item(product, qty=Decimal("2"))
    with (
        patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=cashier_a),
    ):
        sale = TransactionService.process_sale(cart, [{"method": "CASH", "amount": Decimal("200")}])
    sale_id = sale.id
    # Fresh identity map, so the reload really eager-loads, as in the app.
    db_session.expunge_all()

    with patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=cashier_b):
        for reloaded in (
            SaleQueryService.get_sale_details(sale_id),
            SaleQueryService.get_last_sale(),
        ):
            lines = _texts(ReceiptBuilder.build_receipt(reloaded, is_reprint=True))
            assert any("reprint_cashier_a" in line for line in lines)
            assert not any("reprint_cashier_b" in line for line in lines)
            assert any(line.startswith("   2 x ") for line in lines)


@pytest.mark.parametrize("build", ["build_void_receipt", "build_refund_receipt"])
def test_void_and_refund_receipts_format_quantity_by_unit(config_store, logged_in_as_b, build):
    sale = _sale(qty="2.000", unit=Unit(name="pcs", decimal_places=0))

    lines = _texts(getattr(ReceiptBuilder, build)(sale))

    assert any(line.startswith("2 x ") for line in lines)
    assert not any("2.000 x" in line for line in lines)


# ==============================================================================
# Issue #911: Reprint authorisation and document truth
# ==============================================================================


@pytest.fixture
def reprint_users(db_session):
    from cbpos.core.constants.permissions import Permissions
    from cbpos.core.models import Permission, Role, User
    from cbpos.core.services.auth_service import AuthService

    perm_reprint = Permission(code=getattr(Permissions, "SALES_REPRINT", "sales.reprint"))
    perm_view = Permission(code="sales.view")
    db_session.add_all([perm_reprint, perm_view])
    db_session.flush()

    role_allowed = Role(name="ReprintAllowedRole_911", permissions=[perm_reprint, perm_view])
    role_denied = Role(name="ReprintDeniedRole_911", permissions=[perm_view])
    role_manager = Role(name="ReprintManagerRole_911", permissions=[perm_reprint, perm_view])
    db_session.add_all([role_allowed, role_denied, role_manager])
    db_session.flush()

    user_allowed = User(
        username="reprint_user_allowed",
        pin_hash=AuthService.hash_pin("1111"),
        role_id=role_allowed.id,
        is_active=True,
    )
    user_denied = User(
        username="reprint_user_denied",
        pin_hash=AuthService.hash_pin("2222"),
        role_id=role_denied.id,
        is_active=True,
    )
    user_manager = User(
        username="reprint_manager",
        pin_hash=AuthService.hash_pin("3333"),
        role_id=role_manager.id,
        is_active=True,
    )
    db_session.add_all([user_allowed, user_denied, user_manager])
    db_session.commit()
    return user_allowed, user_denied, user_manager


def test_issue_911_reprint_void_refused(db_session, reprint_users):
    """Reprinting a VOID sale is refused with ValueError('reprint_void') (#911)."""
    from cbpos.core.models import Sale
    from cbpos.core.services.receipt_reprint_service import ReceiptReprintService

    user_allowed, _, _ = reprint_users
    void_sale = Sale(
        document_number="INV-2026-VOID",
        date=datetime.now(),
        total_amount=Decimal("100.00"),
        status="VOID",
        payment_method="CASH",
        user_id=user_allowed.id,
    )
    db_session.add(void_sale)
    db_session.commit()

    with pytest.raises(ValueError, match="reprint_void"):
        ReceiptReprintService.reprint(void_sale.id, user_id=user_allowed.id)


def test_issue_911_reprint_requires_permission(db_session, reprint_users):
    """Calling reprint without sales.reprint permission raises an authorization error (#911)."""
    from cbpos.core.models import Sale
    from cbpos.core.services.receipt_reprint_service import ReceiptReprintService

    user_allowed, user_denied, _ = reprint_users
    sale = Sale(
        document_number="INV-2026-COMPLETED",
        date=datetime.now(),
        total_amount=Decimal("150.00"),
        status="COMPLETED",
        payment_method="CASH",
        user_id=user_allowed.id,
    )
    db_session.add(sale)
    db_session.commit()

    with pytest.raises(Exception, match="permission_denied"):
        ReceiptReprintService.reprint(sale.id, user_id=user_denied.id)


def test_issue_911_credit_note_reprints_with_refund_title(db_session, reprint_users):
    """A credit note (refund document) reprints with refund title/builder, not 'CASH RECEIPT' (#911)."""
    from cbpos.core.models import Product, Sale, SaleItem
    from cbpos.core.services.receipt_reprint_service import ReceiptReprintService

    user_allowed, _, _ = reprint_users
    orig_sale = Sale(
        document_number="INV-2026-ORIG",
        date=datetime(2026, 11, 1, 10, 0),
        total_amount=Decimal("200.00"),
        status="COMPLETED",
        payment_method="CASH",
        user_id=user_allowed.id,
    )
    db_session.add(orig_sale)
    db_session.flush()

    prod = Product(name_en="RefundedItem", price=Decimal("100.00"), stock_qty=Decimal("5"), barcode="RF001")
    db_session.add(prod)
    db_session.flush()

    refund_doc = Sale(
        document_number="CN-2026-0001",
        date=datetime(2026, 11, 2, 14, 0),
        total_amount=Decimal("-100.00"),
        status="COMPLETED",
        refund_of_sale_id=orig_sale.id,
        payment_method="REFUND",
        user_id=user_allowed.id,
    )
    refund_item = SaleItem(
        product=prod,
        qty=Decimal("1.000"),
        unit_price=Decimal("100.00"),
        original_price=Decimal("100.00"),
        subtotal=Decimal("-100.00"),
    )
    refund_doc.items = [refund_item]
    db_session.add_all([refund_doc, refund_item])
    db_session.commit()

    job = ReceiptReprintService.reprint(refund_doc.id, user_id=user_allowed.id)
    assert job is not None
    assert job.is_refund is True
    lines = _texts(job.commands)

    # Must contain refund label / title
    assert any("REFUND" in line or "ආපසු ගෙවීම" in line or "பணத்திரும்ப" in line for line in lines)
    # Must NOT be an ordinary CASH RECEIPT
    assert not any(line == "CASH RECEIPT" for line in lines)
    # Must have DUPLICATE marking
    assert any("DUPLICATE" in line or "පිටපත" in line or "நகல்" in line for line in lines)
    # Must reference original sale
    assert any("INV-2026-ORIG" in line for line in lines)


def test_issue_911_ordinary_sale_reprint_has_duplicate_marker(db_session, reprint_users):
    """Reprinting an ordinary completed sale carries the DUPLICATE marker (#911)."""
    from cbpos.core.models import Product, Sale, SaleItem
    from cbpos.core.services.receipt_reprint_service import ReceiptReprintService

    user_allowed, _, _ = reprint_users
    prod = Product(name_en="Item_911", price=Decimal("50.00"), stock_qty=Decimal("10"), barcode="IT911")
    db_session.add(prod)
    db_session.flush()

    sale = Sale(
        document_number="INV-2026-DUP",
        date=datetime.now(),
        total_amount=Decimal("50.00"),
        status="COMPLETED",
        payment_method="CASH",
        user_id=user_allowed.id,
    )
    item = SaleItem(
        product=prod,
        qty=Decimal("1.000"),
        unit_price=Decimal("50.00"),
        original_price=Decimal("50.00"),
        subtotal=Decimal("50.00"),
    )
    sale.items = [item]
    db_session.add_all([sale, item])
    db_session.commit()

    job = ReceiptReprintService.reprint(sale.id, user_id=user_allowed.id)
    lines = _texts(job.commands)
    assert any("DUPLICATE" in line or "පිටපත" in line or "நகல்" in line for line in lines)


def test_issue_911_reprint_writes_audit(db_session, reprint_users):
    """Reprint writes an AuditLog entry with action REPRINT_RECEIPT, recording actor and approver (#911)."""
    from cbpos.core.models import AuditLog, Sale
    from cbpos.core.services.receipt_reprint_service import ReceiptReprintService

    user_allowed, _, user_manager = reprint_users
    sale = Sale(
        document_number="INV-2026-AUDIT",
        date=datetime.now(),
        total_amount=Decimal("100.00"),
        status="COMPLETED",
        payment_method="CASH",
        user_id=user_allowed.id,
    )
    db_session.add(sale)
    db_session.commit()

    ReceiptReprintService.reprint(sale.id, user_id=user_allowed.id, approver_id=user_manager.id)

    db_session.expire_all()
    log = db_session.query(AuditLog).filter_by(action="REPRINT_RECEIPT").order_by(AuditLog.id.desc()).first()
    assert log is not None
    assert log.event_type == "TRANSACTION"
    assert "INV-2026-AUDIT" in log.details
    assert str(user_allowed.username) in log.details or str(user_allowed.id) in log.details
    assert str(user_manager.username) in log.details or str(user_manager.id) in log.details


def test_issue_911_partly_refunded_sale_lists_credit_note_numbers(db_session, reprint_users):
    """Partly refunded sale includes 'Part refunded — see {numbers}' on reprint (#911)."""
    from cbpos.core.models import Product, Sale, SaleItem
    from cbpos.core.services.receipt_reprint_service import ReceiptReprintService

    user_allowed, _, _ = reprint_users
    prod1 = Product(name_en="ItemA", price=Decimal("100.00"), stock_qty=Decimal("10"), barcode="IA001")
    prod2 = Product(name_en="ItemB", price=Decimal("100.00"), stock_qty=Decimal("10"), barcode="IB001")
    db_session.add_all([prod1, prod2])
    db_session.flush()

    orig_sale = Sale(
        document_number="INV-2026-PARTIAL",
        date=datetime.now(),
        total_amount=Decimal("200.00"),
        status="COMPLETED",
        payment_method="CASH",
        user_id=user_allowed.id,
    )
    item1 = SaleItem(
        product=prod1,
        qty=Decimal("1.000"),
        unit_price=Decimal("100.00"),
        original_price=Decimal("100.00"),
        subtotal=Decimal("100.00"),
        refunded_qty=Decimal("1.000"),  # Partially refunded
    )
    item2 = SaleItem(
        product=prod2,
        qty=Decimal("1.000"),
        unit_price=Decimal("100.00"),
        original_price=Decimal("100.00"),
        subtotal=Decimal("100.00"),
        refunded_qty=Decimal("0.000"),
    )
    orig_sale.items = [item1, item2]
    db_session.add_all([orig_sale, item1, item2])
    db_session.flush()

    cn_doc = Sale(
        document_number="CN-2026-P001",
        date=datetime.now(),
        total_amount=Decimal("-100.00"),
        status="COMPLETED",
        refund_of_sale_id=orig_sale.id,
        payment_method="REFUND",
        user_id=user_allowed.id,
    )
    db_session.add(cn_doc)
    db_session.commit()

    job = ReceiptReprintService.reprint(orig_sale.id, user_id=user_allowed.id)
    lines = _texts(job.commands)
    assert any("CN-2026-P001" in line for line in lines)
