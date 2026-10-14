"""
#715: voiding or refunding a credit sale must give the credit back.

Neither path wrote a CustomerLedgerEntry, so ``Customer.current_debt`` kept
the voided/refunded amount -- and since LAN Sync (#678) moves balances only
through ledger rows, the Main PC and other tills kept it too.
"""

from decimal import Decimal
from unittest.mock import patch

import pytest

from cbpos.core.models import AuditLog, Customer, CustomerLedgerEntry, Permission, Product, Role, Sale, User
from cbpos.core.services.cart_service import CartService
from cbpos.core.services.customer_credit_service import CustomerCreditService
from cbpos.core.services.transaction_service import TransactionService

_counter = 0


@pytest.fixture
def user(db_session):
    global _counter
    _counter += 1
    permission = Permission(code=f"credit715_{_counter}")
    role = Role(name=f"Credit715Role_{_counter}", permissions=[permission])
    u = User(username=f"credit715_{_counter}", pin_hash="hash", role=role)
    db_session.add_all([permission, role, u])
    db_session.flush()
    return u


@pytest.fixture
def product(db_session):
    global _counter
    _counter += 1
    p = Product(
        name_en=f"Credit715_{_counter}", price=Decimal("100.00"), stock_qty=Decimal("50"), barcode=f"715-{_counter}"
    )
    db_session.add(p)
    db_session.flush()
    return p


@pytest.fixture
def customer(db_session):
    c = Customer(name="Credit 715", credit_limit=Decimal("10000.00"), current_debt=Decimal("50.00"))
    db_session.add(c)
    db_session.flush()
    return c


def _sell(db_session, user, product, customer, payments: list[tuple[str, str]], qty: str = "2") -> Sale:
    """Ring up ``qty`` x 100.00 through TransactionService with the given (method, amount) payments."""
    db_session.commit()
    with (
        patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=user),
        patch("cbpos.core.services.transaction_service.PrintWorker"),
    ):
        cart = CartService()
        cart.add_item(product, qty=Decimal(qty))
        sale = TransactionService.process_sale(
            cart, [{"method": m, "amount": Decimal(a)} for m, a in payments], customer_id=customer.id
        )
    assert sale is not None
    return sale


def _debt(db_session, customer) -> Decimal:
    db_session.expire_all()
    return db_session.get(Customer, customer.id).current_debt


def _reversals(db_session, customer) -> list[CustomerLedgerEntry]:
    db_session.expire_all()
    return (
        db_session.query(CustomerLedgerEntry)
        .filter(
            CustomerLedgerEntry.customer_id == customer.id,
            CustomerLedgerEntry.entry_type.in_(("VOID", "REFUND")),
        )
        .order_by(CustomerLedgerEntry.id)
        .all()
    )


class TestVoidCreditSale:
    def test_void_returns_debt_to_previous_value(self, db_session, user, product, customer):
        sale = _sell(db_session, user, product, customer, [("Credit", "200.00")])
        assert _debt(db_session, customer) == Decimal("250.00")

        assert TransactionService.void_sale(sale.id, user.id, "Wrong customer") is True

        assert _debt(db_session, customer) == Decimal("50.00")
        [entry] = _reversals(db_session, customer)
        assert entry.entry_type == "VOID"
        assert entry.amount == Decimal("-200.00")
        assert entry.balance_after == Decimal("50.00")
        assert entry.reference_id == sale.id
        assert entry.reference_doc == sale.document_number
        assert entry.synced is False  # queued for LAN Sync like any other ledger row

    def test_void_of_mixed_payment_reverses_only_the_credit_part(self, db_session, user, product, customer):
        sale = _sell(db_session, user, product, customer, [("Cash", "120.00"), ("Credit", "80.00")])
        assert _debt(db_session, customer) == Decimal("130.00")

        TransactionService.void_sale(sale.id, user.id, "Mistake")

        assert _debt(db_session, customer) == Decimal("50.00")
        [entry] = _reversals(db_session, customer)
        assert entry.amount == Decimal("-80.00")

    def test_void_of_cash_sale_writes_no_ledger_row(self, db_session, user, product, customer):
        sale = _sell(db_session, user, product, customer, [("Cash", "200.00")])

        TransactionService.void_sale(sale.id, user.id, "Mistake")

        assert _reversals(db_session, customer) == []
        assert _debt(db_session, customer) == Decimal("50.00")

    def test_void_is_audited(self, db_session, user, product, customer):
        sale = _sell(db_session, user, product, customer, [("Credit", "200.00")])

        TransactionService.void_sale(sale.id, user.id, "Mistake")

        db_session.expire_all()
        log = db_session.query(AuditLog).filter(AuditLog.action == "CREDIT_REVERSAL").one()
        assert sale.document_number in log.details
        assert "200.00" in log.details


class TestRefundCreditSale:
    def test_refund_returns_debt_to_previous_value(self, db_session, user, product, customer):
        sale = _sell(db_session, user, product, customer, [("Credit", "200.00")])

        assert TransactionService.process_refund(sale.id, "Returned", user.id) is True

        assert _debt(db_session, customer) == Decimal("50.00")
        [entry] = _reversals(db_session, customer)
        refund = db_session.query(Sale).filter(Sale.refund_of_sale_id == sale.id).one()
        assert entry.entry_type == "REFUND"
        assert entry.amount == Decimal("-200.00")
        assert entry.balance_after == Decimal("50.00")
        assert entry.reference_id == sale.id
        assert entry.reference_doc == refund.document_number

    def test_refund_of_mixed_payment_reverses_only_the_credit_part(self, db_session, user, product, customer):
        sale = _sell(db_session, user, product, customer, [("Cash", "150.00"), ("Credit", "50.00")])

        TransactionService.process_refund(sale.id, "Returned", user.id)

        assert _debt(db_session, customer) == Decimal("50.00")
        assert [e.amount for e in _reversals(db_session, customer)] == [Decimal("-50.00")]

    def test_voiding_a_refunded_sale_does_not_reverse_the_credit_twice(self, db_session, user, product, customer):
        sale = _sell(db_session, user, product, customer, [("Credit", "200.00")])
        TransactionService.process_refund(sale.id, "Returned", user.id)

        TransactionService.void_sale(sale.id, user.id, "Oops")

        assert _debt(db_session, customer) == Decimal("50.00")
        assert len(_reversals(db_session, customer)) == 1


class TestPartialRefundRule:
    """No partial-refund screen exists yet; the rule lives in the service."""

    def test_partial_refund_reverses_its_credit_share(self, db_session, user, product, customer):
        # 200.00 sale: 120 cash + 80 credit. Refunding 100.00 (half) gives back 40.00 of credit.
        sale = _sell(db_session, user, product, customer, [("Cash", "120.00"), ("Credit", "80.00")])
        sale_row = db_session.get(Sale, sale.id)
        entry = CustomerCreditService.reverse_credit_sale_in_session(
            db_session, sale_row, "REFUND", user.id, "RET-PART-1", refund_amount=Decimal("100.00")
        )
        db_session.flush()

        assert entry.amount == Decimal("-40.00")
        assert _debt(db_session, customer) == Decimal("90.00")

    def test_repeated_partial_refunds_never_exceed_the_credit(self, db_session, user, product, customer):
        sale = _sell(db_session, user, product, customer, [("Cash", "120.00"), ("Credit", "80.00")])
        sale_row = db_session.get(Sale, sale.id)
        for doc in ("RET-1", "RET-2", "RET-3"):
            CustomerCreditService.reverse_credit_sale_in_session(
                db_session, sale_row, "REFUND", user.id, doc, refund_amount=Decimal("150.00")
            )
        db_session.flush()

        assert sum(e.amount for e in _reversals(db_session, customer)) == Decimal("-80.00")
        assert _debt(db_session, customer) == Decimal("50.00")


class TestRefundBreakdown:
    """The refund screens' split: what is handed back vs. taken off credit."""

    def test_cash_only_sale_hands_everything_back(self, db_session, user, product, customer):
        sale = _sell(db_session, user, product, customer, [("Cash", "200.00")])

        b = TransactionService.refund_breakdown(sale.id)

        assert (b["cash_back"], b["credit_reversed"], b["refundable"]) == (Decimal("200.00"), Decimal("0.00"), True)

    def test_credit_only_sale_hands_nothing_back(self, db_session, user, product, customer):
        sale = _sell(db_session, user, product, customer, [("Credit", "200.00")])

        b = TransactionService.refund_breakdown(sale.id)

        assert (b["cash_back"], b["credit_reversed"]) == (Decimal("0.00"), Decimal("200.00"))
        assert b["customer_name"] == "Credit 715"

    def test_mixed_sale_splits(self, db_session, user, product, customer):
        sale = _sell(db_session, user, product, customer, [("Cash", "120.00"), ("Credit", "80.00")])

        b = TransactionService.refund_breakdown(sale.id)

        assert (b["total"], b["cash_back"], b["credit_reversed"]) == (
            Decimal("200.00"),
            Decimal("120.00"),
            Decimal("80.00"),
        )

    def test_breakdown_matches_what_the_refund_reverses(self, db_session, user, product, customer):
        sale = _sell(db_session, user, product, customer, [("Cash", "120.00"), ("Credit", "80.00")])
        b = TransactionService.refund_breakdown(sale.id)

        TransactionService.process_refund(sale.id, "Returned", user.id)

        assert [-e.amount for e in _reversals(db_session, customer)] == [b["credit_reversed"]]

    def test_already_refunded_sale_has_nothing_left(self, db_session, user, product, customer):
        sale = _sell(db_session, user, product, customer, [("Cash", "120.00"), ("Credit", "80.00")])
        TransactionService.process_refund(sale.id, "Returned", user.id)

        b = TransactionService.refund_breakdown(sale.id)

        assert (b["cash_back"], b["credit_reversed"], b["refundable"]) == (Decimal("0.00"), Decimal("0.00"), False)

    def test_voided_sale_has_nothing_left(self, db_session, user, product, customer):
        sale = _sell(db_session, user, product, customer, [("Credit", "200.00")])
        TransactionService.void_sale(sale.id, user.id, "Mistake")

        b = TransactionService.refund_breakdown(sale.id)

        assert (b["cash_back"], b["credit_reversed"], b["refundable"]) == (Decimal("0.00"), Decimal("0.00"), False)

    def test_missing_sale(self, db_session):
        assert TransactionService.refund_breakdown(99999999) is None


@pytest.mark.usefixtures("qapp")
class TestRefundDialogStatesTheSplit:
    """The refund dialog no longer tells the cashier to hand back the full total."""

    def _run(self, db_session, user, sale):
        from PyQt6.QtWidgets import QMessageBox

        from cbpos.ui.dialogs.refund_dialog import RefundDialog

        dialog = RefundDialog()
        dialog.found_sale = sale
        dialog.txt_reason.setPlainText("Returned")
        with (
            patch("cbpos.ui.dialogs.refund_dialog.check_permission_with_override", return_value=user),
            patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes) as question,
            patch.object(QMessageBox, "information") as information,
        ):
            dialog.process_refund()
        dialog.deleteLater()
        return question.call_args.args[2], information.call_args.args[2]

    def test_mixed_sale_confirm_and_done_show_both_parts(self, db_session, user, product, customer):
        from cbpos.core.utils.formatters import format_currency
        from cbpos.i18n import _t

        sale = _sell(db_session, user, product, customer, [("Cash", "120.00"), ("Credit", "80.00")])

        confirm, done = self._run(db_session, user, sale)

        cash = _t("refund_split.cash_back", amount=format_currency(Decimal("120.00")))
        assert cash in confirm
        assert (
            _t("refund_split.credit_will_reverse", amount=format_currency(Decimal("80.00")), customer="Credit 715")
            in confirm
        )
        assert "Returned" in confirm
        assert cash in done
        assert (
            _t("refund_split.credit_reversed", amount=format_currency(Decimal("80.00")), customer="Credit 715") in done
        )
        assert format_currency(Decimal("200.00")) not in done

    def test_credit_only_sale_says_nothing_to_hand_back(self, db_session, user, product, customer):
        from cbpos.core.utils.formatters import format_currency
        from cbpos.i18n import _t

        sale = _sell(db_session, user, product, customer, [("Credit", "200.00")])

        confirm, done = self._run(db_session, user, sale)

        for text in (confirm, done):
            assert _t("refund_split.nothing_to_hand_back") in text
            assert _t("refund_split.cash_back", amount=format_currency(Decimal("200.00"))) not in text

    def test_cash_only_sale_mentions_no_credit(self, db_session, user, product, customer):
        from cbpos.core.utils.formatters import format_currency
        from cbpos.i18n import _t

        sale = _sell(db_session, user, product, customer, [("Cash", "200.00")])

        confirm, done = self._run(db_session, user, sale)

        assert _t("refund_split.cash_back", amount=format_currency(Decimal("200.00"))) in confirm
        assert "Credit 715" not in confirm
        assert "Credit 715" not in done


class TestRefundVoucherSplit:
    def test_voucher_shows_given_back_and_off_credit(self):
        from cbpos.core.services.refund_receipt_builder import RefundReceiptBuilder
        from cbpos.core.utils.formatters import format_currency

        sale = Sale(document_number="REC-V-1", date=None, total_amount=Decimal("200.00"))
        sale.items = []
        with patch.object(RefundReceiptBuilder, "_append_header_block", return_value=32):
            commands = RefundReceiptBuilder.build_refund_receipt(sale, credit_reversed=Decimal("80.00"))
        text = "\n".join(str(c.get("val", "")) for c in commands)

        assert RefundReceiptBuilder._rt("refund_given_back", amount=format_currency(Decimal("120.00"))) in text
        assert RefundReceiptBuilder._rt("refund_off_credit", amount=format_currency(Decimal("80.00"))) in text

    def test_all_credit_voucher_gives_nothing_back(self):
        from cbpos.core.services.refund_receipt_builder import RefundReceiptBuilder
        from cbpos.core.utils.formatters import format_currency

        sale = Sale(document_number="REC-V-2", date=None, total_amount=Decimal("200.00"))
        sale.items = []
        with patch.object(RefundReceiptBuilder, "_append_header_block", return_value=32):
            commands = RefundReceiptBuilder.build_refund_receipt(sale, credit_reversed=Decimal("200.00"))
        text = "\n".join(str(c.get("val", "")) for c in commands)

        assert RefundReceiptBuilder._rt("refund_given_back", amount=format_currency(Decimal("0.00"))) in text


@pytest.mark.usefixtures("qapp")
class TestEveryRefundEntryPointStatesTheSplit:
    """History, Documents and Sale History confirm with the same split as the Refund dialog (#730)."""

    @staticmethod
    def _confirm_text(module: str, view, start) -> str:
        from PyQt6.QtWidgets import QMessageBox

        with patch(f"{module}.QMessageBox") as box:
            box.StandardButton = QMessageBox.StandardButton
            box.question.return_value = QMessageBox.StandardButton.No
            start()
        view.deleteLater()
        return box.question.call_args.args[2]

    @staticmethod
    def _expected_html(sale: Sale) -> str:
        from cbpos.core.utils.formatters import format_currency

        return (
            "<b>Refund Transaction?</b><br><br>"
            f"Receipt: {sale.document_number}<br>"
            f"Amount: {format_currency(Decimal('200.00'))}<br><br>"
            f"Give back {format_currency(Decimal('120.00'))} to the customer.<br>"
            f"{format_currency(Decimal('80.00'))} will be taken off Credit 715&#x27;s credit.<br><br>"
            "<b style='color: #FF4136'>Warning:</b> "
            "Stock will be restored. This action cannot be undone."
        )

    def test_history_view_confirm(self, db_session, user, product, customer):
        from cbpos.ui.views.history_view import HistoryView

        sale = _sell(db_session, user, product, customer, [("Cash", "120.00"), ("Credit", "80.00")])
        view = HistoryView()
        view.current_sale = sale

        text = self._confirm_text("cbpos.ui.views.history_view", view, view.process_refund)

        assert text == self._expected_html(sale)

    def test_document_view_confirm(self, db_session, user, product, customer):
        from cbpos.ui.views.document_view import DocumentBrowserView

        sale = _sell(db_session, user, product, customer, [("Cash", "120.00"), ("Credit", "80.00")])
        view = DocumentBrowserView()
        view.current_doc = {
            "id": sale.id,
            "type": "sale",
            "document_number": sale.document_number,
            "total_amount": sale.total_amount,
        }

        text = self._confirm_text("cbpos.ui.views.document_view", view, view.process_refund)

        assert text == self._expected_html(sale)

    def test_sale_history_dialog_confirm(self, db_session, user, product, customer):
        from cbpos.core.utils.formatters import format_currency
        from cbpos.ui.dialogs.sale_history_dialog import SaleHistoryDialog

        sale = _sell(db_session, user, product, customer, [("Cash", "120.00"), ("Credit", "80.00")])
        dialog = SaleHistoryDialog()
        dialog._selected_sale = sale
        dialog.txt_refund_reason.setPlainText("Returned")

        with patch("cbpos.core.utils.permission_helper.check_permission_with_override", return_value=user):
            text = self._confirm_text("cbpos.ui.dialogs.sale_history_dialog", dialog, dialog._confirm_refund)

        assert text == (
            f"Refund {sale.document_number}? Total {format_currency(Decimal('200.00'))}.\n\n"
            f"Give back {format_currency(Decimal('120.00'))} to the customer.\n"
            f"{format_currency(Decimal('80.00'))} will be taken off Credit 715's credit.\n\n"
            "Reason: Returned"
        )
