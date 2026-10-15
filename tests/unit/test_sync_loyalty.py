"""
#716: loyalty points across LAN Sync.

``Customer.loyalty_points`` is a catalog column: tills pull it from the
Main PC. Points a till awarded were never sent anywhere, so the next
catalog pull copied the Main PC's figure over them and they were gone.
Points now move by event, like credit book debts (#678): each award is a
loyalty ledger row the till pushes, the Main PC adds it once, and a till's
figure is the Main PC's plus the rows it has not pushed yet.
"""

from decimal import Decimal

import pytest

from cbpos.core.models import Customer
from cbpos.core.services import sync_apply_service
from cbpos.core.services.customer_service import CustomerService
from tests.unit.sync_two_machines import Shop, isolated_settings

TILL_A = "TERM-02"
TILL_B = "TERM-03"


@pytest.fixture
def shop(tmp_path):
    with isolated_settings(
        str(tmp_path), terminal_id=TILL_A, terminal_mode="terminal", enable_loyalty=True, loyalty_points_ratio=100
    ):
        s = Shop(str(tmp_path))
        s.add_till(TILL_A)
        s.add_till(TILL_B)
        yield s


@pytest.fixture
def catalog(shop):
    with shop.session("main") as s:
        customer = Customer(name="Loyal Customer", phone="0711111111", loyalty_points=10)
        s.add(customer)
        s.flush()
        extra = {"customer": customer.id}
    ids = shop.seed_catalog()
    ids.update(extra)
    return ids


def _earn(shop, till: str, customer_id: int, spent: str) -> int:
    with shop.on(till):
        return CustomerService().add_loyalty_points(customer_id, Decimal(spent))


def _points(shop, machine: str, customer_id: int) -> int:
    with shop.session(machine) as s:
        return s.get(Customer, customer_id).loyalty_points


class TestLoyaltyPoints:
    def test_points_earned_on_till_reach_main_pc_and_other_tills(self, shop, catalog):
        assert _earn(shop, TILL_A, catalog["customer"], "500") == 5
        assert _points(shop, TILL_A, catalog["customer"]) == 15

        shop.cycle(TILL_A)
        shop.cycle(TILL_B)

        assert _points(shop, "main", catalog["customer"]) == 15
        assert _points(shop, TILL_A, catalog["customer"]) == 15
        assert _points(shop, TILL_B, catalog["customer"]) == 15

    def test_pull_before_push_keeps_the_tills_points(self, shop, catalog):
        _earn(shop, TILL_A, catalog["customer"], "500")

        shop.pull(TILL_A, full=True)

        assert _points(shop, TILL_A, catalog["customer"]) == 15
        assert _points(shop, "main", catalog["customer"]) == 10

    def test_points_pulled_after_a_push_add_the_tills_unpushed_points(self, shop, catalog):
        _earn(shop, TILL_A, catalog["customer"], "500")
        shop.push(TILL_A)
        _earn(shop, TILL_A, catalog["customer"], "300")

        shop.pull(TILL_A, full=True)

        assert _points(shop, TILL_A, catalog["customer"]) == 18
        assert _points(shop, "main", catalog["customer"]) == 15

    def test_resent_points_are_counted_once_and_lost_reply_self_corrects(self, shop, catalog):
        _earn(shop, TILL_A, catalog["customer"], "500")
        shop.drop_responses = True
        shop.push(TILL_A)
        shop.drop_responses = False
        shop.pull(TILL_A)  # the Main PC already counts them; the till hasn't heard back

        shop.cycle(TILL_A)

        assert _points(shop, "main", catalog["customer"]) == 15
        assert _points(shop, TILL_A, catalog["customer"]) == 15

    def test_two_tills_points_add_up_everywhere(self, shop, catalog):
        _earn(shop, TILL_A, catalog["customer"], "500")
        _earn(shop, TILL_B, catalog["customer"], "200")

        shop.cycle(TILL_A)
        shop.cycle(TILL_B)
        shop.cycle(TILL_A)

        assert _points(shop, "main", catalog["customer"]) == 17
        assert _points(shop, TILL_A, catalog["customer"]) == 17
        assert _points(shop, TILL_B, catalog["customer"]) == 17

    def test_points_of_a_till_created_customer_are_not_doubled(self, shop, catalog):
        with shop.on(TILL_A):
            local_id = CustomerService().create_customer({"name": "New On Till", "phone": "0722222222"}).id
        _earn(shop, TILL_A, local_id, "700")

        shop.cycle(TILL_A)

        with shop.session("main") as s:
            main_customer = s.query(Customer).filter_by(phone="0722222222").one()
            main_id, main_points = main_customer.id, main_customer.loyalty_points
        assert main_points == 7
        assert _points(shop, TILL_A, main_id) == 7


class TestOlderMainPc:
    """A till upgraded before the Main PC: the Main PC turns loyalty rows away."""

    @pytest.fixture
    def old_main(self, monkeypatch):
        monkeypatch.setattr(
            sync_apply_service,
            "TRANSACTION_TABLES",
            [t for t in sync_apply_service.TRANSACTION_TABLES if t != "loyalty_ledger"],
        )
        monkeypatch.setattr(
            sync_apply_service, "APPLY_ORDER", tuple(t for t in sync_apply_service.APPLY_ORDER if t != "loyalty_ledger")
        )

    def test_rejected_points_stay_on_the_till_and_go_out_once_the_main_pc_is_upgraded(
        self, shop, catalog, old_main, monkeypatch
    ):
        _earn(shop, TILL_A, catalog["customer"], "500")

        shop.cycle(TILL_A)

        assert _points(shop, TILL_A, catalog["customer"]) == 15
        assert _points(shop, "main", catalog["customer"]) == 10

        monkeypatch.undo()  # the Main PC is upgraded
        shop.cycle(TILL_A)

        assert _points(shop, "main", catalog["customer"]) == 15
        assert _points(shop, TILL_A, catalog["customer"]) == 15
