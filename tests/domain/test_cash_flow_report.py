"""
Regression tests for Issue #844:
Cash Flow report adds refunds back (net too high by 2x refunds).
Payments by PaymentMethod.kind, drawer CashMovement, and pure Decimal.
"""

import uuid
from datetime import datetime
from decimal import Decimal

import pytest

from cbpos.core.constants.status import DocumentStatus, PaymentMethodKind
from cbpos.core.models import CashMovement, Permission, Product, Role, Sale, SaleItem, SalePayment, User
from cbpos.core.reports.definitions.cash_flow_report import CashFlowReport


def _row_map(df):
    assert not df["Category"].duplicated().any(), (
        f"Duplicate categories found: {df['Category'][df['Category'].duplicated()].tolist()}"
    )
    return dict(zip(df["Category"], df["Amount"], strict=False))


@pytest.fixture
def cf_user(db_session):
    suffix = uuid.uuid4().hex[:8]
    perm = Permission(code=f"cf_perm_{suffix}")
    role = Role(name=f"CFRole_{suffix}", permissions=[perm])
    user = User(username=f"cashier_{suffix}", pin_hash="hash", role=role)
    db_session.add_all([perm, role, user])
    db_session.flush()
    return user


@pytest.fixture
def cf_product(db_session):
    suffix = uuid.uuid4().hex[:8]
    product = Product(
        name_en=f"CFProduct_{suffix}",
        barcode=f"CFP{suffix}",
        price=Decimal("100.00"),
        cost=Decimal("50.00"),
        stock_qty=Decimal("100"),
    )
    db_session.add(product)
    db_session.flush()
    return product


class TestCashFlowReportIssue844:
    """Issue #844: Cash Flow reconciles payments by method_kind, drawer movements and Decimal math."""

    def test_issue_844_sale_plus_full_refund_nets_zero(self, db_session, cf_user, cf_product):
        """A completed sale plus its full refund gives net 0, without double-subtracting or adding back."""
        # Sale of 100 in Cash
        sale = Sale(
            document_number="REC-844-001",
            date=datetime(2026, 4, 10, 10, 0, 0),
            total_amount=Decimal("100.00"),
            user_id=cf_user.id,
            payment_method="CASH",
            status=DocumentStatus.COMPLETED,
        )
        db_session.add(sale)
        db_session.flush()

        item = SaleItem(
            sale_id=sale.id,
            product_id=cf_product.id,
            qty=Decimal("1.000"),
            unit_price=Decimal("100.00"),
            original_price=Decimal("100.00"),
            subtotal=Decimal("100.00"),
            unit_cost=Decimal("50.00"),
        )
        pay_sale = SalePayment(
            sale_id=sale.id,
            payment_method="CASH",
            method_kind=PaymentMethodKind.CASH,
            amount=Decimal("100.00"),
        )
        db_session.add_all([item, pay_sale])

        # Refund of 100 in Cash
        refund_sale = Sale(
            document_number="REF-844-001",
            date=datetime(2026, 4, 10, 11, 0, 0),
            total_amount=Decimal("-100.00"),
            user_id=cf_user.id,
            payment_method="REFUND",
            status=DocumentStatus.COMPLETED,
            refund_of_sale_id=sale.id,
        )
        db_session.add(refund_sale)
        db_session.flush()

        item.refunded_qty = Decimal("1.000")
        refund_item = SaleItem(
            sale_id=refund_sale.id,
            product_id=cf_product.id,
            qty=Decimal("-1.000"),
            unit_price=Decimal("100.00"),
            original_price=Decimal("100.00"),
            subtotal=Decimal("-100.00"),
            unit_cost=Decimal("50.00"),
            refund_of_item_id=item.id,
        )
        pay_refund = SalePayment(
            sale_id=refund_sale.id,
            payment_method="CASH",
            method_kind=PaymentMethodKind.CASH,
            amount=Decimal("-100.00"),
        )
        db_session.add_all([refund_item, pay_refund])
        db_session.commit()

        report = CashFlowReport()
        df = report.generate({"date_range": {"start": "2026-04-10", "end": "2026-04-10"}})

        # Lookup by Category
        row_map = _row_map(df)
        assert row_map.get("Cash Sales") == Decimal("100.00")
        assert row_map.get("Cash Refunds") == Decimal("100.00")
        assert row_map.get("Net Cash") == Decimal("0.00")
        assert row_map.get("Net Cash Flow") == Decimal("0.00")

    def test_issue_844_partial_refund_nets_correctly(self, db_session, cf_user, cf_product):
        """Partial refund accurately reduces cash net."""
        sale = Sale(
            document_number="REC-844-002",
            date=datetime(2026, 4, 11, 10, 0, 0),
            total_amount=Decimal("200.00"),
            user_id=cf_user.id,
            payment_method="CASH",
            status=DocumentStatus.COMPLETED,
        )
        db_session.add(sale)
        db_session.flush()

        pay_sale = SalePayment(
            sale_id=sale.id,
            payment_method="CASH",
            method_kind=PaymentMethodKind.CASH,
            amount=Decimal("200.00"),
        )
        db_session.add(pay_sale)

        refund_sale = Sale(
            document_number="REF-844-PART",
            date=datetime(2026, 4, 11, 12, 0, 0),
            total_amount=Decimal("-50.00"),
            user_id=cf_user.id,
            payment_method="REFUND",
            status=DocumentStatus.COMPLETED,
            refund_of_sale_id=sale.id,
        )
        db_session.add(refund_sale)
        db_session.flush()

        pay_refund = SalePayment(
            sale_id=refund_sale.id,
            payment_method="CASH",
            method_kind=PaymentMethodKind.CASH,
            amount=Decimal("-50.00"),
        )
        db_session.add(pay_refund)
        db_session.commit()

        report = CashFlowReport()
        df = report.generate({"date_range": {"start": "2026-04-11", "end": "2026-04-11"}})

        row_map = _row_map(df)
        assert row_map.get("Cash Sales") == Decimal("200.00")
        assert row_map.get("Cash Refunds") == Decimal("50.00")
        assert row_map.get("Net Cash") == Decimal("150.00")
        assert row_map.get("Net Cash Flow") == Decimal("150.00")

    def test_issue_844_multi_tender_sale_and_proportional_refund(self, db_session, cf_user):
        """Multi-tender sales and refunds net each payment method kind separately."""
        sale = Sale(
            document_number="REC-844-MULTI",
            date=datetime(2026, 4, 12, 10, 0, 0),
            total_amount=Decimal("150.00"),
            user_id=cf_user.id,
            payment_method="SPLIT",
            status=DocumentStatus.COMPLETED,
        )
        db_session.add(sale)
        db_session.flush()

        pay_cash = SalePayment(
            sale_id=sale.id,
            payment_method="CASH",
            method_kind=PaymentMethodKind.CASH,
            amount=Decimal("100.00"),
        )
        pay_card = SalePayment(
            sale_id=sale.id,
            payment_method="VISA",
            method_kind=PaymentMethodKind.CARD,
            amount=Decimal("50.00"),
        )
        db_session.add_all([pay_cash, pay_card])

        # Refund 30 CASH + 15 CARD
        refund = Sale(
            document_number="REF-844-MULTI",
            date=datetime(2026, 4, 12, 14, 0, 0),
            total_amount=Decimal("-45.00"),
            user_id=cf_user.id,
            payment_method="REFUND",
            status=DocumentStatus.COMPLETED,
            refund_of_sale_id=sale.id,
        )
        db_session.add(refund)
        db_session.flush()

        ref_cash = SalePayment(
            sale_id=refund.id,
            payment_method="CASH",
            method_kind=PaymentMethodKind.CASH,
            amount=Decimal("-30.00"),
        )
        ref_card = SalePayment(
            sale_id=refund.id,
            payment_method="VISA",
            method_kind=PaymentMethodKind.CARD,
            amount=Decimal("-15.00"),
        )
        db_session.add_all([ref_cash, ref_card])
        db_session.commit()

        report = CashFlowReport()
        df = report.generate({"date_range": {"start": "2026-04-12", "end": "2026-04-12"}})

        row_map = _row_map(df)
        assert row_map.get("Cash Sales") == Decimal("100.00")
        assert row_map.get("Cash Refunds") == Decimal("30.00")
        assert row_map.get("Net Cash") == Decimal("70.00")

        assert row_map.get("Card Sales") == Decimal("50.00")
        assert row_map.get("Card Refunds") == Decimal("15.00")
        assert row_map.get("Net Card") == Decimal("35.00")

        assert row_map.get("Net Cash Flow") == Decimal("105.00")

    def test_issue_844_voided_sale_contributes_no_payment_flow(self, db_session, cf_user):
        """Voided transactions contribute zero payment inflow or outflow."""
        void_sale = Sale(
            document_number="REC-844-VOID",
            date=datetime(2026, 4, 13, 10, 0, 0),
            total_amount=Decimal("500.00"),
            user_id=cf_user.id,
            payment_method="CASH",
            status=DocumentStatus.VOID,
        )
        db_session.add(void_sale)
        db_session.flush()

        void_pay = SalePayment(
            sale_id=void_sale.id,
            payment_method="CASH",
            method_kind=PaymentMethodKind.CASH,
            amount=Decimal("500.00"),
        )
        db_session.add(void_pay)
        db_session.commit()

        report = CashFlowReport()
        df = report.generate({"date_range": {"start": "2026-04-13", "end": "2026-04-13"}})

        row_map = _row_map(df)
        assert row_map.get("Cash Sales") == Decimal("0.00")
        assert row_map.get("Net Cash") == Decimal("0.00")
        assert row_map.get("Net Cash Flow") == Decimal("0.00")

    def test_issue_844_cash_refund_override_appears_under_cash(self, db_session, cf_user):
        """Manager override changing card refund tender to cash is reported under CASH."""
        # Original Card sale
        sale = Sale(
            document_number="REC-844-CARD",
            date=datetime(2026, 4, 14, 10, 0, 0),
            total_amount=Decimal("100.00"),
            user_id=cf_user.id,
            payment_method="CARD",
            status=DocumentStatus.COMPLETED,
        )
        db_session.add(sale)
        db_session.flush()

        db_session.add(
            SalePayment(
                sale_id=sale.id,
                payment_method="CARD",
                method_kind=PaymentMethodKind.CARD,
                amount=Decimal("100.00"),
            )
        )

        # Refund overridden to CASH
        refund = Sale(
            document_number="REF-844-OVERRIDE",
            date=datetime(2026, 4, 14, 11, 0, 0),
            total_amount=Decimal("-100.00"),
            user_id=cf_user.id,
            payment_method="CASH",
            status=DocumentStatus.COMPLETED,
            refund_of_sale_id=sale.id,
        )
        db_session.add(refund)
        db_session.flush()

        db_session.add(
            SalePayment(
                sale_id=refund.id,
                payment_method="CASH",
                method_kind=PaymentMethodKind.CASH,
                amount=Decimal("-100.00"),
            )
        )
        db_session.commit()

        report = CashFlowReport()
        df = report.generate({"date_range": {"start": "2026-04-14", "end": "2026-04-14"}})

        row_map = _row_map(df)
        assert row_map.get("Card Sales") == Decimal("100.00")
        assert row_map.get("Card Refunds", Decimal("0.00")) == Decimal("0.00")
        assert row_map.get("Net Card") == Decimal("100.00")

        assert row_map.get("Cash Sales") == Decimal("0.00")
        assert row_map.get("Cash Refunds") == Decimal("100.00")
        assert row_map.get("Net Cash") == Decimal("-100.00")

        assert row_map.get("Net Cash Flow") == Decimal("0.00")

    def test_issue_844_drawer_cash_in_out_reconcile(self, db_session, cf_user):
        """Cash drawer in/out movements correctly add and subtract from physical cash."""
        mov_in = CashMovement(
            user_id=cf_user.id,
            type="IN",
            amount=Decimal("150.00"),
            reason="Opening float top-up",
            timestamp=datetime(2026, 4, 15, 9, 0, 0),
        )
        mov_out = CashMovement(
            user_id=cf_user.id,
            type="PAYOUT",
            amount=Decimal("40.00"),
            reason="Office tea/sugar expense",
            timestamp=datetime(2026, 4, 15, 15, 0, 0),
        )
        db_session.add_all([mov_in, mov_out])
        db_session.commit()

        report = CashFlowReport()
        df = report.generate({"date_range": {"start": "2026-04-15", "end": "2026-04-15"}})

        row_map = _row_map(df)
        assert row_map.get("Cash In (Drawer)") == Decimal("150.00")
        assert row_map.get("Cash Out (Drawer)") == Decimal("40.00")
        assert row_map.get("Net Cash") == Decimal("110.00")
        assert row_map.get("Net Cash Flow") == Decimal("110.00")

    def test_issue_844_legacy_refund_cash_back_counted_once(self, db_session, cf_user):
        """Legacy refund without payment row uses refund_cash_back and is not counted twice."""
        orig_sale = Sale(
            document_number="REC-844-LEGACY",
            date=datetime(2026, 4, 16, 10, 0, 0),
            total_amount=Decimal("180.00"),
            user_id=cf_user.id,
            payment_method="CASH",
            status=DocumentStatus.COMPLETED,
        )
        db_session.add(orig_sale)
        db_session.flush()

        db_session.add(
            SalePayment(
                sale_id=orig_sale.id,
                payment_method="CASH",
                method_kind=PaymentMethodKind.CASH,
                amount=Decimal("180.00"),
            )
        )

        # 1. Genuine legacy refund without ANY SalePayment row (exercises refund_cash_back fallback)
        refund_nopay = Sale(
            document_number="REF-844-NOPAY",
            date=datetime(2026, 4, 16, 11, 0, 0),
            total_amount=Decimal("-50.00"),
            user_id=cf_user.id,
            payment_method="REFUND",
            status=DocumentStatus.COMPLETED,
            refund_of_sale_id=orig_sale.id,
        )
        db_session.add(refund_nopay)

        # 2. Legacy refund with REFUND_LEGACY payment row
        refund_legacy = Sale(
            document_number="REF-844-LEGACY",
            date=datetime(2026, 4, 16, 11, 30, 0),
            total_amount=Decimal("-30.00"),
            user_id=cf_user.id,
            payment_method="REFUND",
            status=DocumentStatus.COMPLETED,
            refund_of_sale_id=orig_sale.id,
        )
        db_session.add(refund_legacy)
        db_session.flush()

        db_session.add(
            SalePayment(
                sale_id=refund_legacy.id,
                payment_method="REFUND",
                method_kind=PaymentMethodKind.REFUND_LEGACY,
                amount=Decimal("-30.00"),
            )
        )
        db_session.commit()

        report = CashFlowReport()
        df = report.generate({"date_range": {"start": "2026-04-16", "end": "2026-04-16"}})

        row_map = _row_map(df)
        assert row_map.get("Cash Sales") == Decimal("180.00")
        # 50.00 from refund_nopay via refund_cash_back + 30.00 from refund_legacy
        assert row_map.get("Cash Refunds") == Decimal("80.00")
        assert row_map.get("Net Cash") == Decimal("100.00")
        assert row_map.get("Net Cash Flow") == Decimal("100.00")

    def test_issue_844_no_float_money_math(self, db_session, cf_user):
        """All Amount values in CashFlowReport DataFrame are Decimal instances on populated data."""
        # Seed populated transactions: sale, refund, drawer movements
        sale = Sale(
            document_number="REC-844-FLOAT-CHECK",
            date=datetime(2026, 4, 10, 10, 0, 0),
            total_amount=Decimal("150.00"),
            user_id=cf_user.id,
            payment_method="CASH",
            status=DocumentStatus.COMPLETED,
        )
        db_session.add(sale)
        db_session.flush()
        db_session.add(
            SalePayment(
                sale_id=sale.id,
                payment_method="CASH",
                method_kind=PaymentMethodKind.CASH,
                amount=Decimal("150.00"),
            )
        )
        ref = Sale(
            document_number="REF-844-FLOAT-CHECK",
            date=datetime(2026, 4, 10, 11, 0, 0),
            total_amount=Decimal("-50.00"),
            user_id=cf_user.id,
            payment_method="CASH",
            status=DocumentStatus.COMPLETED,
            refund_of_sale_id=sale.id,
        )
        db_session.add(ref)
        db_session.flush()
        db_session.add(
            SalePayment(
                sale_id=ref.id,
                payment_method="CASH",
                method_kind=PaymentMethodKind.CASH,
                amount=Decimal("-50.00"),
            )
        )
        mv = CashMovement(
            user_id=cf_user.id,
            type="IN",
            amount=Decimal("25.00"),
            reason="Cash float deposit",
            timestamp=datetime(2026, 4, 10, 12, 0, 0),
        )
        db_session.add(mv)
        db_session.commit()

        report = CashFlowReport()
        df = report.generate({"date_range": {"start": "2026-04-10", "end": "2026-04-10"}})

        assert len(df) > 0, "Expected non-empty report rows"
        for amt in df["Amount"]:
            assert isinstance(amt, Decimal), f"Expected Decimal, got {type(amt)}: {amt}"
        row_map = _row_map(df)
        assert row_map["Cash Sales"] == Decimal("150.00")
        assert row_map["Cash Refunds"] == Decimal("50.00")
        assert row_map["Cash In (Drawer)"] == Decimal("25.00")
