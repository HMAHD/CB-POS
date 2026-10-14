"""
#637: Settings -> Documents offered Sale and Return number formats, but real
sales got random ``REC-3F9A1C2B`` numbers and refunds ``REF-...``, so a
missing or deleted receipt was undetectable. Sales and refunds now take the
next number from DocumentService (``INV-{Y}-{seq:05d}`` / ``CN-{Y}-{seq:05d}``
by default) inside the sale's own transaction. Old REC-/REF- numbers stay.
"""

import logging
from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

import pytest

from cbpos.core.database import Database
from cbpos.core.models import Document, Product, Sale, SaleItem, User
from cbpos.core.services import document_service
from cbpos.core.services.cart_service import CartService
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.document_browser_service import DocumentBrowserService
from cbpos.core.services.document_service import DocumentService
from cbpos.core.services.sale_query_service import SaleQueryService
from cbpos.core.services.transaction_service import TransactionService

YEAR = datetime.now().strftime("%Y")


@pytest.fixture
def user(db_session):
    u = User(username="seqrcpt_user", pin_hash="x", role_id=None, is_active=True)
    db_session.add(u)
    db_session.flush()
    return u


@pytest.fixture
def product(db_session):
    p = Product(name_en="SeqRcpt Item", price=Decimal("100"), stock_qty=Decimal("50"), barcode="SEQRCPT01")
    db_session.add(p)
    db_session.flush()
    return p


@pytest.fixture
def settings(monkeypatch):
    data = {"doc_reset_period": "YEARLY", "terminal_id": "TERM-01", "terminal_mode": "standalone", "language": "en"}
    monkeypatch.setattr(ConfigService, "get_all", lambda: dict(data))
    monkeypatch.setattr(ConfigService, "get", lambda key, default=None: data.get(key, default))
    return data


@pytest.fixture
def no_print():
    with (
        patch("cbpos.core.services.transaction_service.PrintWorker"),
        patch("cbpos.core.services.transaction_service.PrinterService"),
    ):
        yield


def _sell(user, product) -> Sale:
    with patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=user):
        cart = CartService()
        cart.add_item(product, qty=Decimal("1"))
        sale = TransactionService.process_sale(cart, [{"method": "CASH", "amount": Decimal("100")}])
    assert sale is not None
    return sale


@pytest.mark.usefixtures("settings", "no_print")
class TestSaleNumbers:
    def test_sales_follow_the_default_format_and_increment(self, db_session, user, product):
        first = _sell(user, product)
        second = _sell(user, product)

        assert first.document_number == f"INV-{YEAR}-00001"
        assert second.document_number == f"INV-{YEAR}-00002"

    def test_old_random_receipts_do_not_affect_the_sequence(self, db_session, user, product):
        db_session.add(
            Sale(document_number="REC-3F9A1C2B", user_id=user.id, total_amount=Decimal("10"), payment_method="CASH")
        )
        db_session.flush()

        assert _sell(user, product).document_number == f"INV-{YEAR}-00001"

    def test_custom_format_is_honoured(self, db_session, user, product, settings):
        settings["doc_format_sale"] = "S{T}-{Y}{M}-{seq:04d}"

        sale = _sell(user, product)

        assert sale.document_number == f"S01-{YEAR}{datetime.now():%m}-0001"

    def test_invalid_stored_format_falls_back_to_default(self, db_session, user, product, settings, caplog):
        settings["doc_format_sale"] = "INV-{seq}-{Y}"

        with caplog.at_level(logging.WARNING):
            sale = _sell(user, product)

        assert sale.document_number == f"INV-{YEAR}-00001"
        assert any("doc_format_sale" in r.getMessage() for r in caplog.records)

    def test_number_taken_by_another_till_is_skipped_not_fatal(self, db_session, user, product, monkeypatch):
        """Network mode: another till committed INV-...-00001 after this sale
        read the sequence. The unique index rejects it, the sale retries with
        the next number inside the same transaction and still completes once."""
        monkeypatch.setattr(Database(), "_db_mode", "network")
        db_session.add(Document(document_number=f"INV-{YEAR}-00001", type="document", user_id=user.id))
        db_session.flush()
        real_next_seq = document_service._next_seq
        calls = []

        def stale_then_real(session, prefix):
            calls.append(prefix)
            return 1 if len(calls) == 1 else real_next_seq(session, prefix)

        monkeypatch.setattr(document_service, "_next_seq", stale_then_real)
        stock_before = product.stock_qty

        sale = _sell(user, product)

        assert sale.document_number == f"INV-{YEAR}-00002"
        assert db_session.query(Sale).filter(Sale.document_number.like(f"INV-{YEAR}-%")).count() == 1
        assert db_session.query(SaleItem).filter_by(sale_id=sale.id).count() == 1
        db_session.refresh(product)
        assert product.stock_qty == stock_before - 1

    def test_standalone_never_uses_a_savepoint(self, db_session, user, product, monkeypatch):
        """pysqlite opens its transaction lazily, so a SAVEPOINT taken before
        the sale's first INSERT is the outermost transaction and releasing it
        commits the sale header -- a later failure could not roll it back."""

        def no_savepoint(*args, **kwargs):
            raise AssertionError("SAVEPOINT used in standalone (SQLite) mode")

        monkeypatch.setattr(db_session, "begin_nested", no_savepoint)

        assert _sell(user, product).document_number == f"INV-{YEAR}-00001"

    def test_sync_terminal_puts_its_id_in_front(self, db_session, user, product, settings):
        """Synced tills number offline in their own database, so a shared
        sequence would collide on the Main PC: the terminal goes in front."""
        settings.update(terminal_mode="terminal", terminal_id="TERM-02")

        assert _sell(user, product).document_number == f"02-INV-{YEAR}-00001"

    def test_format_that_already_has_the_terminal_is_left_alone(self, db_session, user, product, settings):
        settings.update(terminal_mode="main", terminal_id="TERM-01", doc_format_sale="INV-{T}-{Y}-{seq:05d}")

        assert _sell(user, product).document_number == f"INV-01-{YEAR}-00001"


@pytest.mark.usefixtures("settings", "no_print")
class TestRefundNumbers:
    def test_refund_gets_a_credit_note_number(self, db_session, user, product):
        sale = _sell(user, product)

        assert TransactionService.process_refund(sale.id, "Damaged", user.id) is True

        refund = db_session.query(Sale).filter(Sale.refund_of_sale_id == sale.id).one()
        assert refund.document_number == f"CN-{YEAR}-00001"


@pytest.mark.usefixtures("settings", "no_print")
def test_search_finds_old_and_new_numbers(db_session, user, product):
    db_session.add(
        Sale(document_number="REC-3F9A1C2B", user_id=user.id, total_amount=Decimal("10"), payment_method="CASH")
    )
    db_session.flush()
    new = _sell(user, product)
    day_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = datetime.now().replace(hour=23, minute=59, second=59)

    for term, expected in (("REC-3F9A", "REC-3F9A1C2B"), (new.document_number, new.document_number)):
        history = SaleQueryService.get_sales_history(day_start, day_end, term)
        assert [s.document_number for s in history] == [expected]
        browser = DocumentBrowserService.search_documents(search_term=term)
        assert [d["document_number"] for d in browser["documents"]] == [expected]


def test_preview_includes_terminal_for_sync_tills(db_session, monkeypatch):
    monkeypatch.setattr(ConfigService, "get", lambda key, default=None: {"terminal_mode": "terminal"}.get(key, default))

    assert DocumentService.preview_number("INV-{Y}-{seq:05d}", "YEARLY", "TERM-02", "SALE") == f"02-INV-{YEAR}-00001"
    assert (
        DocumentService.preview_number("GRN-{Y}-{seq:05d}", "YEARLY", "TERM-02", "PURCHASE") == f"02-GRN-{YEAR}-00001"
    )
    assert (
        DocumentService.preview_number("PO-{Y}-{seq:05d}", "YEARLY", "TERM-02", "PURCHASE_ORDER") == f"PO-{YEAR}-00001"
    )


class TestPurchaseNumbers:
    """#679: GRNs are pushed to the Main PC like receipts, where
    ``document_number`` is unique, so a synced till's GRNs carry its terminal."""

    def _grn(self, db_session, user) -> str:
        from cbpos.core.models import Supplier
        from cbpos.core.services.purchase_service import PurchaseService

        supplier = db_session.query(Supplier).filter_by(company_name="SeqRcpt Supplier").one_or_none()
        if supplier is None:
            supplier = Supplier(company_name="SeqRcpt Supplier")
            db_session.add(supplier)
            db_session.flush()
        return PurchaseService.create_purchase(supplier.id, "INV-X", user.id).document_number

    def test_standalone_grn_keeps_the_shared_series(self, db_session, user, settings):
        assert self._grn(db_session, user) == f"GRN-{YEAR}-00001"

    def test_two_tills_number_grns_in_their_own_series(self, db_session, user, settings):
        settings.update(terminal_mode="terminal", terminal_id="TERM-02")
        first = self._grn(db_session, user)
        settings.update(terminal_id="TERM-03")
        other_till = self._grn(db_session, user)

        assert first == f"02-GRN-{YEAR}-00001"
        assert other_till == f"03-GRN-{YEAR}-00001"
