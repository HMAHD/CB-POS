"""
#678: credit book debts and supplier payables across LAN Sync.

Ledger rows already reached the Main PC, but ``Customer.current_debt`` and
``Supplier.current_payable`` there never moved, and the next catalog pull
then copied the Main PC's stale figure over the till's correct one -- a
credit sale's debt could simply disappear. Each pushed ledger row now moves
the Main PC balance once, and a till's balance is always the Main PC's
figure plus the ledger rows the till has not pushed yet.
"""

from datetime import datetime
from decimal import Decimal

import pytest

from cbpos.core.models import Customer, CustomerLedgerEntry, Sale, Supplier
from cbpos.core.services.customer_credit_service import CustomerCreditService
from cbpos.core.services.supplier_payable_service import SupplierPayableService
from tests.unit.sync_two_machines import Shop, isolated_settings

TILL_A = "TERM-02"
TILL_B = "TERM-03"


@pytest.fixture
def shop(tmp_path):
    with isolated_settings(str(tmp_path), terminal_id=TILL_A, terminal_mode="terminal"):
        s = Shop(str(tmp_path))
        s.add_till(TILL_A)
        s.add_till(TILL_B)
        yield s


@pytest.fixture
def catalog(shop):
    with shop.session("main") as s:
        customer = Customer(name="Credit Customer", credit_limit=Decimal("10000"), current_debt=Decimal("100.00"))
        supplier = Supplier(company_name="Payable Supplier", current_payable=Decimal("1000.00"))
        s.add_all([customer, supplier])
        s.flush()
        extra = {"customer": customer.id, "supplier": supplier.id}
    ids = shop.seed_catalog()
    ids.update(extra)
    return ids


def _credit_sale(shop, till: str, catalog, number: str, amount: str) -> None:
    """A credit sale on a till, booked the way TransactionService books one."""
    with shop.session(till) as s:
        sale = Sale(
            document_number=number,
            date=datetime.now(),
            user_id=catalog["user"],
            terminal_id=till,
            origin_terminal_id=till,
            customer_id=catalog["customer"],
            total_amount=Decimal(amount),
            net_revenue=Decimal(amount),
            payment_method="CREDIT",
        )
        s.add(sale)
        s.flush()
        sale_id = sale.id
    with shop.on(till):
        CustomerCreditService.record_credit_sale(catalog["customer"], sale_id, Decimal(amount), number, catalog["user"])


def _debt(shop, machine: str, catalog) -> Decimal:
    with shop.session(machine) as s:
        return s.get(Customer, catalog["customer"]).current_debt


def _payable(shop, machine: str, catalog) -> Decimal:
    with shop.session(machine) as s:
        return s.get(Supplier, catalog["supplier"]).current_payable


class TestCustomerDebt:
    def test_credit_sale_on_till_raises_debt_on_main_pc(self, shop, catalog):
        _credit_sale(shop, TILL_A, catalog, "02-INV-1", "500.00")
        assert _debt(shop, TILL_A, catalog) == Decimal("600.00")

        shop.push(TILL_A)

        assert _debt(shop, "main", catalog) == Decimal("600.00")

    def test_resent_ledger_row_is_not_counted_twice(self, shop, catalog):
        _credit_sale(shop, TILL_A, catalog, "02-INV-1", "500.00")
        shop.drop_responses = True
        shop.push(TILL_A)
        shop.drop_responses = False
        shop.push(TILL_A)

        assert _debt(shop, "main", catalog) == Decimal("600.00")
        with shop.session("main") as s:
            assert s.query(CustomerLedgerEntry).count() == 1

    def test_catalog_pull_keeps_the_tills_balance(self, shop, catalog):
        _credit_sale(shop, TILL_A, catalog, "02-INV-1", "500.00")
        shop.push(TILL_A)
        shop.pull(TILL_A)
        assert _debt(shop, TILL_A, catalog) == Decimal("600.00")

        # Even a full pull before the next push keeps an unpushed credit sale.
        _credit_sale(shop, TILL_A, catalog, "02-INV-2", "50.00")
        shop.pull(TILL_A, full=True)
        assert _debt(shop, TILL_A, catalog) == Decimal("650.00")
        shop.push(TILL_A)
        assert _debt(shop, "main", catalog) == Decimal("650.00")
        assert _debt(shop, TILL_A, catalog) == Decimal("650.00")

    def test_unpushed_sale_survives_a_pull_while_main_pc_is_unreachable_for_pushes(self, shop, catalog):
        _credit_sale(shop, TILL_A, catalog, "02-INV-1", "500.00")
        shop.pull(TILL_A, full=True)  # no push yet

        assert _debt(shop, TILL_A, catalog) == Decimal("600.00")
        assert _debt(shop, "main", catalog) == Decimal("100.00")

    def test_two_tills_debts_add_up_everywhere(self, shop, catalog):
        _credit_sale(shop, TILL_A, catalog, "02-INV-1", "500.00")
        _credit_sale(shop, TILL_B, catalog, "03-INV-1", "200.00")
        shop.cycle(TILL_A)
        shop.cycle(TILL_B)
        shop.cycle(TILL_A)

        assert _debt(shop, "main", catalog) == Decimal("800.00")
        assert _debt(shop, TILL_A, catalog) == Decimal("800.00")
        assert _debt(shop, TILL_B, catalog) == Decimal("800.00")

    def test_payment_on_till_lowers_debt_on_main_pc(self, shop, catalog):
        with shop.on(TILL_A):
            CustomerCreditService.record_payment(catalog["customer"], Decimal("40.00"), "CASH", catalog["user"])
        shop.cycle(TILL_A)

        assert _debt(shop, "main", catalog) == Decimal("60.00")
        assert _debt(shop, TILL_A, catalog) == Decimal("60.00")

    def test_lost_acknowledgement_self_corrects_on_next_push(self, shop, catalog):
        _credit_sale(shop, TILL_A, catalog, "02-INV-1", "500.00")
        shop.drop_responses = True
        shop.push(TILL_A)
        shop.drop_responses = False
        shop.pull(TILL_A)  # Main PC already counts the sale; the till hasn't heard back

        shop.cycle(TILL_A)

        assert _debt(shop, "main", catalog) == Decimal("600.00")
        assert _debt(shop, TILL_A, catalog) == Decimal("600.00")


class TestSupplierPayable:
    def test_payment_to_supplier_on_till_reaches_main_pc(self, shop, catalog):
        with shop.on(TILL_A):
            SupplierPayableService.record_payment(catalog["supplier"], Decimal("300.00"), "CASH", catalog["user"])
        assert _payable(shop, TILL_A, catalog) == Decimal("700.00")

        shop.cycle(TILL_A)

        assert _payable(shop, "main", catalog) == Decimal("700.00")
        assert _payable(shop, TILL_A, catalog) == Decimal("700.00")

    def test_other_tills_see_the_new_payable_after_a_pull(self, shop, catalog):
        with shop.on(TILL_A):
            SupplierPayableService.record_payment(catalog["supplier"], Decimal("300.00"), "CASH", catalog["user"])
        shop.cycle(TILL_A)
        shop.cycle(TILL_B)

        assert _payable(shop, TILL_B, catalog) == Decimal("700.00")
