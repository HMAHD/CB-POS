"""
#680: customers created on a till reach the Main PC with the right id.

Customers are pulled from the Main PC by id, so a customer created on a
till used to stay there: the till's sale pointed at a ``customer_id`` the
Main PC didn't have -- or that was a different customer on the Main PC --
and the next catalog pull could overwrite the till's customer with the
Main PC's customer of the same id. A till now pushes the customers it
creates (ahead of the sales that use them); the Main PC gives each its own
id and the till renumbers its copy to match.
"""

import sqlite3
from datetime import datetime
from decimal import Decimal

import pytest
from alembic.config import Config as AlembicConfig
from sqlalchemy import create_engine, inspect

from alembic import command
from cbpos.config import Config
from cbpos.core.models import Base, Customer, CustomerLedgerEntry, Sale
from cbpos.core.services.customer_credit_service import CustomerCreditService
from cbpos.core.services.customer_service import CustomerService
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
        s.add(Customer(name="Pulled Customer", phone="0710000001", credit_limit=Decimal("5000")))
    return shop.seed_catalog()


def _main_only_customer(shop, name: str, phone: str | None = None) -> int:
    """A customer added on the Main PC after the tills last pulled."""
    with shop.session("main") as s:
        c = Customer(name=name, phone=phone, credit_limit=Decimal("5000"))
        s.add(c)
        s.flush()
        return c.id


def _new_customer(shop, till: str, name: str, phone: str | None = None) -> int:
    with shop.on(till):
        return CustomerService().create_customer({"name": name, "phone": phone, "credit_limit": Decimal("5000")}).id


def _sale(shop, till: str, catalog, customer_id: int, number: str, credit: str | None = None) -> int:
    amount = Decimal(credit or "100")
    with shop.session(till) as s:
        sale = Sale(
            document_number=number,
            date=datetime.now(),
            user_id=catalog["user"],
            terminal_id=till,
            origin_terminal_id=till,
            customer_id=customer_id,
            total_amount=amount,
            net_revenue=amount,
            payment_method="CREDIT" if credit else "CASH",
        )
        s.add(sale)
        s.flush()
        sale_id = sale.id
    if credit:
        with shop.on(till):
            CustomerCreditService.record_credit_sale(customer_id, sale_id, amount, number, catalog["user"])
    return sale_id


def _customer_of(shop, machine: str, number: str) -> Customer:
    with shop.session(machine) as s:
        sale = s.query(Sale).filter_by(document_number=number).one()
        return s.get(Customer, sale.customer_id)


def _names(shop, machine: str) -> dict[int, str]:
    with shop.session(machine) as s:
        return {c.id: c.name for c in s.query(Customer)}


class TestTillCreatedCustomer:
    def test_only_tills_mark_new_customers_for_pushing(self, shop, catalog, tmp_path):
        local_id = _new_customer(shop, TILL_A, "Till Customer")
        with shop.session(TILL_A) as s:
            assert s.get(Customer, local_id).synced is False
        with isolated_settings(str(tmp_path), terminal_mode="standalone"), shop.on(TILL_A):
            other = CustomerService().create_customer({"name": "Standalone Customer"})
        assert other.synced is True

    def test_sale_to_new_customer_shows_that_customer_on_main_pc(self, shop, catalog):
        main_own = _main_only_customer(shop, "Main Customer")  # takes the id the till will use
        local_id = _new_customer(shop, TILL_A, "Till Customer", "0770000002")
        assert local_id == main_own  # the clash this issue is about

        _sale(shop, TILL_A, catalog, local_id, "02-INV-1", credit="250.00")
        shop.cycle(TILL_A)

        main_customer = _customer_of(shop, "main", "02-INV-1")
        assert main_customer.name == "Till Customer"
        assert main_customer.id != main_own
        assert main_customer.current_debt == Decimal("250.00")
        with shop.session("main") as s:
            assert s.query(CustomerLedgerEntry).one().customer_id == main_customer.id

        # The till renumbered its customer to the Main PC id; its own sale and
        # ledger follow, and the Main PC's customer arrived at its own id.
        till_customer = _customer_of(shop, TILL_A, "02-INV-1")
        assert till_customer.id == main_customer.id
        assert till_customer.synced is True
        assert till_customer.current_debt == Decimal("250.00")
        assert _names(shop, TILL_A) == _names(shop, "main")

    def test_two_tills_new_customers_with_the_same_local_id_stay_apart(self, shop, catalog):
        a = _new_customer(shop, TILL_A, "Customer of A")
        b = _new_customer(shop, TILL_B, "Customer of B")
        assert a == b
        _sale(shop, TILL_A, catalog, a, "02-INV-1")
        _sale(shop, TILL_B, catalog, b, "03-INV-1")

        for till in (TILL_A, TILL_B, TILL_A):
            shop.cycle(till)

        assert _customer_of(shop, "main", "02-INV-1").name == "Customer of A"
        assert _customer_of(shop, "main", "03-INV-1").name == "Customer of B"
        assert _customer_of(shop, TILL_A, "02-INV-1").name == "Customer of A"
        assert _customer_of(shop, TILL_B, "03-INV-1").name == "Customer of B"
        assert _names(shop, TILL_A) == _names(shop, "main")

    def test_customer_the_main_pc_already_has_by_phone_is_not_duplicated(self, shop, catalog):
        existing = _main_only_customer(shop, "Nimal Perera", "0771234567")
        local_id = _new_customer(shop, TILL_A, "Nimal", "0771234567")
        _sale(shop, TILL_A, catalog, local_id, "02-INV-1")

        shop.cycle(TILL_A)

        assert _customer_of(shop, "main", "02-INV-1").id == existing
        assert _customer_of(shop, "main", "02-INV-1").name == "Nimal Perera"
        assert _customer_of(shop, TILL_A, "02-INV-1").id == existing
        with shop.session("main") as s:
            assert s.query(Customer).filter_by(phone="0771234567").count() == 1

    @pytest.mark.parametrize("phone", ["0770000002", None], ids=["held-back-by-phone", "merged-duplicate"])
    def test_lost_acknowledgement_does_not_duplicate_or_misplace_the_customer(self, shop, catalog, phone):
        """Without a phone the pull brings the Main PC's copy in as a second
        row; renumbering then merges the till's row into it."""
        _main_only_customer(shop, "Main Customer")
        local_id = _new_customer(shop, TILL_A, "Till Customer", phone)
        _sale(shop, TILL_A, catalog, local_id, "02-INV-1")

        shop.drop_responses = True
        shop.push(TILL_A)
        shop.drop_responses = False
        assert shop.pull(TILL_A) >= 0  # the Main PC copy must not clobber the till's customer
        with shop.session(TILL_A) as s:
            assert s.get(Customer, local_id).name == "Till Customer"

        shop.cycle(TILL_A)
        shop.cycle(TILL_A)

        with shop.session("main") as s:
            assert s.query(Customer).filter_by(name="Till Customer").count() == 1
        assert _customer_of(shop, "main", "02-INV-1").name == "Till Customer"
        assert _customer_of(shop, TILL_A, "02-INV-1").name == "Till Customer"
        assert _names(shop, TILL_A) == _names(shop, "main")

    def test_several_new_customers_renumbered_in_a_chain(self, shop, catalog):
        _main_only_customer(shop, "Main Customer")
        first = _new_customer(shop, TILL_A, "First")
        second = _new_customer(shop, TILL_A, "Second")
        _sale(shop, TILL_A, catalog, first, "02-INV-1")
        _sale(shop, TILL_A, catalog, second, "02-INV-2")

        shop.cycle(TILL_A)

        for number, name in (("02-INV-1", "First"), ("02-INV-2", "Second")):
            assert _customer_of(shop, "main", number).name == name
            assert _customer_of(shop, TILL_A, number).name == name
        assert _names(shop, TILL_A) == _names(shop, "main")

    def test_customer_created_during_the_push_is_moved_out_of_the_way(self, shop, catalog, monkeypatch):
        _main_only_customer(shop, "Main Customer")
        early = _new_customer(shop, TILL_A, "Early")
        _sale(shop, TILL_A, catalog, early, "02-INV-1")
        client = shop.client(TILL_A)
        serve = client._request
        created = {}

        def create_mid_push(method, endpoint, data=None, timeout=10):
            result = serve(method, endpoint, data)
            if "late" not in created:
                created["late"] = _new_customer(shop, TILL_A, "Late")
                _sale(shop, TILL_A, catalog, created["late"], "02-INV-2")
            return result

        monkeypatch.setattr(client, "_request", create_mid_push)
        shop.push(TILL_A)
        monkeypatch.setattr(client, "_request", serve)
        shop.cycle(TILL_A)
        shop.cycle(TILL_A)

        assert _customer_of(shop, TILL_A, "02-INV-1").name == "Early"
        assert _customer_of(shop, TILL_A, "02-INV-2").name == "Late"
        assert _customer_of(shop, "main", "02-INV-1").name == "Early"
        assert _customer_of(shop, "main", "02-INV-2").name == "Late"
        assert _names(shop, TILL_A) == _names(shop, "main")


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------
@pytest.fixture
def alembic_cfg(tmp_path, monkeypatch):
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
    command.stamp(cfg, "head")
    return cfg, db_path, uri


def test_migration_marks_existing_customers_synced(alembic_cfg):
    cfg, db_path, uri = alembic_cfg

    command.downgrade(cfg, "e177823b8aa9")
    engine = create_engine(uri)
    assert "synced" not in {c["name"] for c in inspect(engine).get_columns("customers")}
    engine.dispose()
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO customers (name, is_company, credit_limit, current_debt, payment_terms, loyalty_points,"
            " is_active, last_modified) VALUES ('Old', 0, 0, 0, 0, 0, 1, '2026-10-01')"
        )

    command.upgrade(cfg, "head")

    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT synced FROM customers WHERE name = 'Old'").fetchone()[0] == 1
