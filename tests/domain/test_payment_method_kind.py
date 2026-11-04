"""Foundation tests for PaymentMethodKind, classification, and schema migration."""

import sqlite3
from decimal import Decimal
from unittest.mock import patch

import pytest
from alembic.config import Config as AlembicConfig
from sqlalchemy import create_engine, text

from alembic import command
from cbpos.config import Config
from cbpos.core.constants.status import PaymentMethodKind
from cbpos.core.models import Base, PaymentMethod, Product, Role, User
from cbpos.core.services.cart_service import CartService
from cbpos.core.services.payment_service import classify_method_name
from cbpos.core.services.transaction_service import TransactionService

_counter = 0


def _next() -> int:
    global _counter
    _counter += 1
    return _counter


@pytest.fixture
def test_cashier(db_session):
    suffix = _next()
    role = Role(name=f"CashierRole_{suffix}")
    user = User(username=f"cashier_{suffix}", pin_hash="hash", role=role)
    db_session.add_all([role, user])
    db_session.commit()
    return user


@pytest.mark.domain
def test_classify_method_name_mapping():
    """Table-driven test verifying classify_method_name maps standard names to kinds."""
    test_cases = [
        ("Cash", PaymentMethodKind.CASH),
        ("CASH", PaymentMethodKind.CASH),
        ("cash", PaymentMethodKind.CASH),
        ("  cash  ", PaymentMethodKind.CASH),
        ("Card", PaymentMethodKind.CARD),
        ("CARD", PaymentMethodKind.CARD),
        ("Credit", PaymentMethodKind.CREDIT),
        ("CREDIT", PaymentMethodKind.CREDIT),
        ("QR/Mobile", PaymentMethodKind.QR),
        ("qr/mobile", PaymentMethodKind.QR),
        ("QR", PaymentMethodKind.QR),
        ("qr", PaymentMethodKind.QR),
        ("mobile", PaymentMethodKind.QR),
        ("Mobile", PaymentMethodKind.QR),
        ("Cheque", PaymentMethodKind.CHEQUE),
        ("CHEQUE", PaymentMethodKind.CHEQUE),
        ("check", PaymentMethodKind.CHEQUE),
        ("Check", PaymentMethodKind.CHEQUE),
        ("Bank Transfer", PaymentMethodKind.TRANSFER),
        ("bank transfer", PaymentMethodKind.TRANSFER),
        ("Transfer", PaymentMethodKind.TRANSFER),
        ("TRANSFER", PaymentMethodKind.TRANSFER),
        ("REFUND", PaymentMethodKind.REFUND_LEGACY),
        ("refund", PaymentMethodKind.REFUND_LEGACY),
        ("Bitcoin", PaymentMethodKind.OTHER),
        ("Loyalty", PaymentMethodKind.OTHER),
        ("", PaymentMethodKind.OTHER),
        (None, PaymentMethodKind.OTHER),
    ]

    for raw_name, expected_kind in test_cases:
        assert classify_method_name(raw_name) == expected_kind, (
            f"Expected '{raw_name}' to classify as {expected_kind}, got {classify_method_name(raw_name)}"
        )


@pytest.mark.domain
def test_sale_payment_snapshots_kind(db_session, test_cashier):
    """A sale paid with method 'Bank Transfer' records method_kind == 'TRANSFER'."""
    suffix = _next()
    product = Product(
        name_en=f"Test Prod {suffix}",
        barcode=f"BC_{suffix}",
        price=Decimal("500.00"),
        stock_qty=Decimal("10.000"),
    )
    db_session.add(product)

    # Ensure "Bank Transfer" exists with kind TRANSFER
    method = db_session.query(PaymentMethod).filter(PaymentMethod.name == "Bank Transfer").first()
    if not method:
        method = PaymentMethod(name="Bank Transfer", kind=PaymentMethodKind.TRANSFER, is_active=True)
        db_session.add(method)
    else:
        method.kind = PaymentMethodKind.TRANSFER
    db_session.commit()

    cart = CartService()
    cart.add_item(product, qty=Decimal("1.000"))

    with patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=test_cashier):
        sale = TransactionService.process_sale(
            cart,
            [{"method": "Bank Transfer", "amount": Decimal("500.00")}],
            customer_id=None,
        )

    assert sale is not None
    assert len(sale.payments) == 1
    payment = sale.payments[0]
    assert payment.payment_method == "Bank Transfer"
    assert payment.method_kind == PaymentMethodKind.TRANSFER
    assert payment.amount == Decimal("500.00")


@pytest.mark.domain
def test_unknown_method_name_rejected(db_session, test_cashier):
    """process_sale with an unknown method raises ValueError('unknown_payment_method')."""
    suffix = _next()
    product = Product(
        name_en=f"Test Prod {suffix}",
        barcode=f"BC_{suffix}",
        price=Decimal("500.00"),
        stock_qty=Decimal("10.000"),
    )
    db_session.add(product)
    db_session.commit()

    cart = CartService()
    cart.add_item(product, qty=Decimal("1.000"))

    with patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=test_cashier):
        with pytest.raises(ValueError, match="unknown_payment_method"):
            TransactionService.process_sale(
                cart,
                [{"method": "Bitcoin", "amount": Decimal("500.00")}],
                customer_id=None,
            )


@pytest.mark.domain
def test_migration_backfills_kind(tmp_path, monkeypatch):
    """An Alembic upgrade backfills kind on payment_methods and sale_payments."""
    db_path = tmp_path / "cbpos.db"
    uri = f"sqlite:///{db_path}"
    engine = create_engine(uri)
    Base.metadata.create_all(engine)
    engine.dispose()
    monkeypatch.setattr(Config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(Config, "DB_URI", uri)

    cfg = AlembicConfig(str(Config.BASE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(Config.BASE_DIR / "alembic"))
    cfg.attributes["configure_logger"] = False

    # 1. Stamp head and downgrade to previous revision: 3c4d5e6f7a8b
    command.stamp(cfg, "head")
    command.downgrade(cfg, "3c4d5e6f7a8b")

    # 2. Insert older rows before the migration
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = OFF")
        # Payment methods without 'kind' column
        conn.execute(
            "INSERT INTO payment_methods (name, is_cash, open_drawer, is_active, last_modified) "
            "VALUES ('Cash', 1, 1, 1, '2026-01-01 00:00:00')"
        )
        conn.execute(
            "INSERT INTO payment_methods (name, is_cash, open_drawer, is_active, last_modified) "
            "VALUES ('Bank Transfer', 0, 0, 1, '2026-01-01 00:00:00')"
        )
        conn.execute(
            "INSERT INTO payment_methods (name, is_cash, open_drawer, is_active, last_modified) "
            "VALUES ('Custom Wallet', 0, 0, 1, '2026-01-01 00:00:00')"
        )

        # Sales and Sale payments without 'method_kind' or 'tendered_amount'
        conn.execute(
            "INSERT INTO documents (id, document_number, type, date, user_id, status, synced) "
            "VALUES (101, 'REC-001', 'SALE', '2026-01-01 10:00:00', 1, 'COMPLETED', 0)"
        )
        conn.execute(
            "INSERT INTO sales (id, total_amount, tax_vat, tax_sscl, net_revenue, "
            "additional_discount_type, additional_discount_value, loyalty_points_redeemed, loyalty_points_value, loyalty_points_earned, payment_method) "
            "VALUES (101, 100.0, 0.0, 0.0, 100.0, 'NONE', 0.0, 0, 0.0, 0, 'Cash')"
        )
        conn.execute("INSERT INTO sale_payments (id, sale_id, payment_method, amount) VALUES (1, 101, 'Cash', 100.0)")

        conn.execute(
            "INSERT INTO documents (id, document_number, type, date, user_id, status, synced) "
            "VALUES (102, 'REC-002', 'SALE', '2026-01-01 11:00:00', 1, 'COMPLETED', 0)"
        )
        conn.execute(
            "INSERT INTO sales (id, total_amount, tax_vat, tax_sscl, net_revenue, "
            "additional_discount_type, additional_discount_value, loyalty_points_redeemed, loyalty_points_value, loyalty_points_earned, payment_method) "
            "VALUES (102, 200.0, 0.0, 0.0, 200.0, 'NONE', 0.0, 0, 0.0, 0, 'Bank Transfer')"
        )
        conn.execute(
            "INSERT INTO sale_payments (id, sale_id, payment_method, amount) VALUES (2, 102, 'Bank Transfer', 200.0)"
        )

        # F12 legacy row with payment_method="CASH" (#854)
        conn.execute(
            "INSERT INTO documents (id, document_number, type, date, user_id, status, synced) "
            "VALUES (103, 'REC-003', 'SALE', '2026-01-01 12:00:00', 1, 'COMPLETED', 0)"
        )
        conn.execute(
            "INSERT INTO sales (id, total_amount, tax_vat, tax_sscl, net_revenue, "
            "additional_discount_type, additional_discount_value, loyalty_points_redeemed, loyalty_points_value, loyalty_points_earned, payment_method) "
            "VALUES (103, 300.0, 0.0, 0.0, 300.0, 'NONE', 0.0, 0, 0.0, 0, 'CASH')"
        )
        conn.execute("INSERT INTO sale_payments (id, sale_id, payment_method, amount) VALUES (3, 103, 'CASH', 300.0)")

        # Legacy refund row with payment_method="REFUND"
        conn.execute(
            "INSERT INTO documents (id, document_number, type, date, user_id, status, synced) "
            "VALUES (104, 'REC-004', 'SALE', '2026-01-01 13:00:00', 1, 'COMPLETED', 0)"
        )
        conn.execute(
            "INSERT INTO sales (id, total_amount, tax_vat, tax_sscl, net_revenue, "
            "additional_discount_type, additional_discount_value, loyalty_points_redeemed, loyalty_points_value, loyalty_points_earned, payment_method) "
            "VALUES (104, -50.0, 0.0, 0.0, -50.0, 'NONE', 0.0, 0, 0.0, 0, 'REFUND')"
        )
        conn.execute("INSERT INTO sale_payments (id, sale_id, payment_method, amount) VALUES (4, 104, 'REFUND', -50.0)")

        conn.commit()

    # 3. Upgrade to head
    command.upgrade(cfg, "head")

    # 4. Verify columns exist and data was backfilled
    engine = create_engine(uri)
    with engine.connect() as conn:
        pm_rows = {r[0]: r[1] for r in conn.execute(text("SELECT name, kind FROM payment_methods")).fetchall()}
        assert pm_rows["Cash"] == "CASH"
        assert pm_rows["Bank Transfer"] == "TRANSFER"
        assert pm_rows["Custom Wallet"] == "OTHER"

        sp_rows = {r[0]: r[1] for r in conn.execute(text("SELECT id, method_kind FROM sale_payments")).fetchall()}
        assert sp_rows[1] == "CASH"  # Cash
        assert sp_rows[2] == "TRANSFER"  # Bank Transfer
        assert sp_rows[3] == "CASH"  # CASH (legacy F12 row)
        assert sp_rows[4] == "REFUND_LEGACY"  # REFUND

    engine.dispose()
