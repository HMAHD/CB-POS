"""
#625: every receipt print goes through the new ReceiptBuilder.

Auto-print after a sale/refund, Receipt Options -> Print and the History /
Document Browser reprints used the old ReceiptService text/image builder,
which ignored the shop's receipt settings (logo, header, cashier, receipt
language, tax-breakdown toggle, copies, auto-print, cut) and always printed
a VAT block -- even for shops that aren't VAT registered. All of them now
build with ReceiptBuilder (what the Settings preview shows) and queue one
print job on the worker.

No real printer or settings file is touched: ConfigService is backed by a
dict and PrintWorker is a mock.
"""

from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from cbpos.core.models import Customer, Product, Sale, SaleItem, SalePayment
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.printer_service import PrinterService
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
    monkeypatch.setattr(ConfigService, "get", store.get)
    monkeypatch.setattr(ConfigService, "get_all", store.get_all)
    monkeypatch.setattr(ConfigService, "set", store.set)
    return store


@pytest.fixture
def cashier():
    user = SimpleNamespace(username="nimal")
    with patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=user):
        yield user


@pytest.fixture
def worker():
    """The shared PrintWorker, replaced by a mock that records add_job calls."""
    mock_worker = MagicMock()
    with patch("cbpos.core.services.printer_service.PrintWorker") as mock_cls:
        mock_cls.instance.return_value = mock_worker
        yield mock_worker


def make_sale(vat: str = "0", customer: Customer | None = None) -> Sale:
    sale = Sale(
        id=7,
        document_number="INV-2026-00007",
        date=datetime(2026, 10, 7, 9, 30),
        total_amount=Decimal("236.00"),
        tax_vat=Decimal(vat),
        tax_sscl=Decimal("0"),
        net_revenue=Decimal("236.00") - Decimal(vat),
        payment_method="CASH",
        status="COMPLETED",
    )
    sale.items = [
        SaleItem(
            product=Product(name_en="Dhal 1kg"),
            qty=Decimal("2"),
            unit_price=Decimal("118.00"),
            original_price=Decimal("118.00"),
            subtotal=Decimal("236.00"),
        )
    ]
    sale.payments = [SalePayment(payment_method="CASH", amount=Decimal("300.00"))]
    sale.customer = customer
    return sale


def queued_jobs(mock_worker: MagicMock) -> list[tuple]:
    return [c.args for c in mock_worker.add_job.call_args_list]


def texts(commands: list[dict]) -> list[str]:
    return [c.get("val", "") for c in commands if c.get("type") == "text"]


class TestAutoPrint:
    def test_job_commands_equal_receipt_builder_output(self, config_store, cashier, worker):
        sale = make_sale()

        assert PrinterService.print_transaction(sale) is True

        assert queued_jobs(worker) == [("print_receipt", ReceiptBuilder.build_receipt(sale))]

    def test_header_and_cashier_are_printed(self, config_store, cashier, worker):
        config_store.set("receipt_header", "Avurudu Sale - 10% off")
        config_store.set("show_cashier_on_receipt", True)

        PrinterService.print_transaction(make_sale())

        ((_, commands),) = queued_jobs(worker)
        lines = texts(commands)
        assert "Avurudu Sale - 10% off" in lines
        assert any("nimal" in line for line in lines)

    def test_non_vat_shop_prints_no_vat_block(self, config_store, cashier, worker):
        config_store.set("vat_registered", False)
        config_store.set("show_tax_breakdown", True)

        PrinterService.print_transaction(make_sale(vat="0"))

        ((_, commands),) = queued_jobs(worker)
        assert not [line for line in texts(commands) if "VAT" in line.upper()]

    def test_vat_shop_with_breakdown_on_prints_vat(self, config_store, cashier, worker):
        config_store.set("vat_registered", True)
        config_store.set("show_tax_breakdown", True)

        PrinterService.print_transaction(make_sale(vat="36.00"))

        ((_, commands),) = queued_jobs(worker)
        assert [line for line in texts(commands) if "VAT" in line.upper()]

    def test_auto_print_off_queues_nothing(self, config_store, cashier, worker):
        config_store.set("auto_print_receipt", False)

        assert PrinterService.print_transaction(make_sale()) is False

        worker.add_job.assert_not_called()

    def test_two_copies_are_two_receipts_in_one_job(self, config_store, cashier, worker):
        config_store.set("receipt_copies", 2)
        sale = make_sale()
        one = ReceiptBuilder.build_receipt(sale)

        PrinterService.print_transaction(sale)

        ((job_type, commands),) = queued_jobs(worker)
        assert job_type == "print_receipt"
        assert commands == one + one
        assert len([c for c in commands if c["type"] == "cut"]) == 2

    def test_auto_cut_off_prints_no_cut(self, config_store, cashier, worker):
        config_store.set("auto_cut_paper", False)

        PrinterService.print_transaction(make_sale())

        ((_, commands),) = queued_jobs(worker)
        assert not [c for c in commands if c["type"] == "cut"]

    def test_receipt_language_is_used(self, config_store, cashier, worker):
        config_store.set("receipt_language", "si")
        sale = make_sale()

        PrinterService.print_transaction(sale)

        ((_, commands),) = queued_jobs(worker)
        assert commands == ReceiptBuilder.build_receipt(sale, config_override={"receipt_language": "si"})
        en = ReceiptBuilder.build_receipt(sale, config_override={"receipt_language": "en"})
        assert texts(commands) != texts(en)

    def test_b2b_customer_also_gets_a4_invoice(self, config_store, cashier, worker):
        sale = make_sale(customer=Customer(name="Registered Co", vat_number="VAT-1"))

        with patch.object(PrinterService, "_print_a4_invoice") as a4:
            PrinterService.print_transaction(sale)

        a4.assert_called_once_with(sale)
        assert len(queued_jobs(worker)) == 1  # the receipt still prints


class TestExplicitPrint:
    def test_print_ignores_auto_print_and_uses_copies(self, config_store, cashier, worker):
        config_store.set("auto_print_receipt", False)
        config_store.set("receipt_copies", 2)
        sale = make_sale()
        one = ReceiptBuilder.build_receipt(sale)

        PrinterService.print_receipt(sale)

        assert queued_jobs(worker) == [("print_receipt", one + one)]

    def test_reprint_is_one_duplicate_copy(self, config_store, cashier, worker):
        config_store.set("receipt_copies", 3)
        sale = make_sale()

        PrinterService.print_receipt(sale, is_reprint=True)

        assert queued_jobs(worker) == [("print_receipt", ReceiptBuilder.build_receipt(sale, is_reprint=True))]


# ── Sale / refund auto-print (TransactionService) ────────────────────────

_counter = 0


@pytest.fixture
def db_user(db_session):
    from cbpos.core.models import Permission, Role, User

    global _counter
    _counter += 1
    permission = Permission(code=f"rpp_perm_{_counter}")
    role = Role(name=f"RppRole_{_counter}", permissions=[permission])
    user = User(username=f"rpp_user_{_counter}", pin_hash="hash", role=role)
    db_session.add_all([permission, role, user])
    db_session.flush()
    with patch("cbpos.core.services.auth_service.AuthService.get_current_user", return_value=user):
        yield user


@pytest.fixture
def db_product(db_session):
    global _counter
    _counter += 1
    product = Product(
        name_en=f"RppProduct_{_counter}", price=Decimal("100"), stock_qty=Decimal("10"), barcode=f"RPP{_counter:04d}"
    )
    db_session.add(product)
    db_session.flush()
    return product


def _sell(product: Product) -> Sale:
    from cbpos.core.services.cart_service import CartService
    from cbpos.core.services.transaction_service import TransactionService

    cart = CartService()
    cart.add_item(product, qty=Decimal("2"))
    with patch("cbpos.core.services.transaction_service.PrintWorker"):
        return TransactionService.process_sale(cart, [{"method": "CASH", "amount": Decimal("200")}])


class TestTransactionAutoPrint:
    def test_sale_auto_print_job_equals_receipt_builder(self, config_store, db_user, db_product, worker):
        config_store.set("show_cashier_on_receipt", True)

        built: list[tuple[Sale, list]] = []
        real_build = ReceiptBuilder.build_receipt

        def spy(sale, *args, **kwargs):
            commands = real_build(sale, *args, **kwargs)
            built.append((sale, commands))
            return commands

        with patch.object(ReceiptBuilder, "build_receipt", side_effect=spy):
            sale = _sell(db_product)

        ((built_for, commands),) = built
        assert built_for is sale
        assert queued_jobs(worker) == [("print_receipt", commands)]
        assert any(db_user.username in line for line in texts(queued_jobs(worker)[0][1]))

    def test_receipt_dialog_on_leaves_printing_to_the_dialog(self, config_store, db_user, db_product, worker):
        config_store.set("show_receipt_dialog", True)

        _sell(db_product)

        worker.add_job.assert_not_called()

    def test_sale_with_auto_print_off_prints_nothing(self, config_store, db_user, db_product, worker):
        config_store.set("auto_print_receipt", False)

        _sell(db_product)

        worker.add_job.assert_not_called()

    def test_refund_auto_prints_the_refund_receipt(self, config_store, db_user, db_product, worker):
        from cbpos.core.services.transaction_service import TransactionService
        from cbpos.i18n import translate_in

        config_store.set("receipt_copies", 2)
        sale = _sell(db_product)
        worker.add_job.reset_mock()

        assert TransactionService.process_refund(sale.id, "Damaged", db_user.id) is True

        ((job_type, commands),) = queued_jobs(worker)
        assert job_type == "print_receipt"
        lines = texts(commands)
        refund_label = translate_in("en", "receipt_strings.refund_label")
        assert lines.count(refund_label) == 4  # top + bottom banner, two copies
        assert any(sale.document_number in line for line in lines)
        assert any(db_user.username in line for line in lines)
        assert len([c for c in commands if c["type"] == "cut"]) == 2

    def test_refund_with_auto_print_off_prints_nothing(self, config_store, db_user, db_product, worker):
        from cbpos.core.services.transaction_service import TransactionService

        sale = _sell(db_product)
        worker.add_job.reset_mock()
        config_store.set("auto_print_receipt", False)

        assert TransactionService.process_refund(sale.id, "Damaged", db_user.id) is True

        worker.add_job.assert_not_called()
