"""
#677: a till row changed after it was pushed must be pushed again.

The sync client pushes rows with ``synced = False`` and marks them synced
on acknowledgement; nothing flipped the flag back, so a sale voided (or a
shift closed, or a draft GRN committed) after its first push stayed
COMPLETED/OPEN/DRAFT on the Main PC for good. These tests run a real till
database against a real Main PC database through the real client and
server code (see sync_two_machines).
"""

from datetime import datetime
from decimal import Decimal

import pytest

from cbpos.core.models import Purchase, PurchaseItem, Sale, SaleItem, SalePayment, Shift, Supplier, VoidReason
from cbpos.core.services.shift_service import ShiftService
from cbpos.core.services.sync_apply_service import SyncApplyService
from cbpos.core.services.transaction_service import TransactionService
from tests.helpers.sync_two_machines import Shop, isolated_settings

TILL = "TERM-02"


@pytest.fixture
def shop(tmp_path):
    with isolated_settings(str(tmp_path), terminal_id=TILL, terminal_mode="terminal"):
        s = Shop(str(tmp_path))
        s.add_till(TILL)
        yield s


@pytest.fixture
def catalog(shop):
    with shop.session("main") as s:
        reason = VoidReason(description="Customer changed mind", code="CCM")
        supplier = Supplier(company_name="Two Machine Supplier")
        s.add_all([reason, supplier])
        s.flush()
        extra = {"void_reason": reason.id, "supplier": supplier.id}
    ids = shop.seed_catalog()
    ids.update(extra)
    return ids


def _sell_on_till(shop, catalog, number: str = "02-INV-1") -> int:
    with shop.session(TILL) as s:
        sale = Sale(
            document_number=number,
            date=datetime.now(),
            user_id=catalog["user"],
            terminal_id=TILL,
            origin_terminal_id=TILL,
            total_amount=Decimal("200"),
            net_revenue=Decimal("200"),
            payment_method="CASH",
        )
        sale.items.append(
            SaleItem(
                product_id=catalog["product"],
                qty=Decimal("2"),
                unit_price=Decimal("100"),
                original_price=Decimal("100"),
                subtotal=Decimal("200"),
            )
        )
        sale.payments.append(SalePayment(payment_method="CASH", amount=Decimal("200")))
        s.add(sale)
        s.flush()
        return sale.id


def _main_sale(shop, number: str) -> Sale:
    with shop.session("main") as s:
        return s.query(Sale).filter_by(document_number=number).one()


class TestChangeTracking:
    def test_editing_a_pushed_row_marks_it_unsynced(self, shop, catalog):
        sale_id = _sell_on_till(shop, catalog)
        assert shop.push(TILL) > 0
        with shop.session(TILL) as s:
            assert s.get(Sale, sale_id).synced is True
            s.get(Sale, sale_id).status = "VOID"
        with shop.session(TILL) as s:
            assert s.get(Sale, sale_id).synced is False

    def test_setting_a_column_to_its_current_value_is_not_a_change(self, shop, catalog):
        sale_id = _sell_on_till(shop, catalog)
        shop.push(TILL)
        with shop.session(TILL) as s:
            s.get(Sale, sale_id).status = "COMPLETED"
        with shop.session(TILL) as s:
            assert s.get(Sale, sale_id).synced is True

    def test_child_change_resends_its_document(self, shop, catalog):
        sale_id = _sell_on_till(shop, catalog)
        shop.push(TILL)
        with shop.session(TILL) as s:
            s.get(Sale, sale_id).items[0].notes = "bag torn"
        with shop.session(TILL) as s:
            assert s.get(Sale, sale_id).synced is False

    def test_main_pc_applying_a_push_does_not_flag_its_copy(self, shop, catalog):
        _sell_on_till(shop, catalog)
        shop.push(TILL)
        with shop.session(TILL) as s:
            sale = s.query(Sale).one()
            sale.status = "VOID"
        shop.push(TILL)
        assert _main_sale(shop, "02-INV-1").synced is True

    def test_apply_service_restores_tracking_afterwards(self, shop, catalog):
        with shop.session("main") as s:
            SyncApplyService(s, TILL).apply_batch({})
            assert "cbpos_sync_skip_change_tracking" not in s.info


class TestVoidAndShiftCloseReachMainPc:
    def test_voided_sale_is_void_on_main_pc(self, shop, catalog):
        sale_id = _sell_on_till(shop, catalog)
        shop.push(TILL)
        assert _main_sale(shop, "02-INV-1").status == "COMPLETED"

        with shop.on(TILL):
            assert TransactionService.void_sale(sale_id, catalog["user"], "test", catalog["void_reason"]) is True
        assert shop.push(TILL) > 0

        main_sale = _main_sale(shop, "02-INV-1")
        assert main_sale.status == "VOID"
        assert main_sale.void_reason_id == catalog["void_reason"]
        with shop.session("main") as s:
            # One sale, its one item -- re-sent in place, not duplicated.
            assert s.query(Sale).count() == 1
            assert s.query(SaleItem).count() == 1
        with shop.session(TILL) as s:
            assert s.get(Sale, sale_id).synced is True

    def test_closed_shift_is_closed_on_main_pc_with_totals(self, shop, catalog):
        with shop.on(TILL):
            shift = ShiftService().start_shift(catalog["user"], Decimal("1000"))
        shop.push(TILL)
        with shop.session("main") as s:
            assert s.query(Shift).one().status == "OPEN"

        with shop.on(TILL):
            ShiftService().close_shift(shift.id, Decimal("990"), notes="short", reason_category="COUNT")
        shop.push(TILL)

        with shop.session("main") as s:
            main_shift = s.query(Shift).one()
            assert main_shift.status == "CLOSED"
            assert main_shift.actual_cash == Decimal("990")
            assert main_shift.expected_cash == Decimal("1000")
            assert main_shift.end_time is not None
            assert main_shift.notes == "short"

    def test_draft_grn_committed_later_is_completed_on_main_pc(self, shop, catalog):
        with shop.session(TILL) as s:
            purchase = Purchase(
                document_number="02-GRN-1",
                type="purchase",
                user_id=catalog["user"],
                status="DRAFT",
                supplier_id=catalog["supplier"],
                total_cost=Decimal("0"),
            )
            s.add(purchase)
            s.flush()
            purchase_id = purchase.id
        shop.push(TILL)

        with shop.session(TILL) as s:
            purchase = s.get(Purchase, purchase_id)
            purchase.items.append(
                PurchaseItem(product_id=catalog["product"], qty_received=Decimal("5"), unit_cost=Decimal("60"))
            )
            purchase.total_cost = Decimal("300")
            purchase.status = "COMPLETED"
        shop.push(TILL)

        with shop.session("main") as s:
            main_purchase = s.query(Purchase).filter_by(document_number="02-GRN-1").one()
            assert main_purchase.status == "COMPLETED"
            assert main_purchase.total_cost == Decimal("300")
            assert len(main_purchase.items) == 1


class TestChangeDuringPush:
    def test_row_edited_while_push_in_flight_stays_unsynced(self, shop, catalog, monkeypatch):
        """The till must not mark a row synced if it changed after it was collected."""
        sale_id = _sell_on_till(shop, catalog)
        client = shop.client(TILL)
        serve = client._request

        def void_mid_push(method, endpoint, data=None, timeout=10):
            result = serve(method, endpoint, data)
            with shop.session(TILL) as s:
                s.get(Sale, sale_id).status = "VOID"
            return result

        monkeypatch.setattr(client, "_request", void_mid_push)
        shop.push(TILL)
        monkeypatch.setattr(client, "_request", serve)

        with shop.session(TILL) as s:
            assert s.get(Sale, sale_id).synced is False
        assert _main_sale(shop, "02-INV-1").status == "COMPLETED"

        shop.push(TILL)
        assert _main_sale(shop, "02-INV-1").status == "VOID"
        with shop.session(TILL) as s:
            assert s.get(Sale, sale_id).synced is True

    def test_lost_response_is_resent_without_duplicates(self, shop, catalog):
        _sell_on_till(shop, catalog)
        shop.drop_responses = True
        assert shop.push(TILL) == -1
        shop.drop_responses = False
        assert shop.push(TILL) > 0
        with shop.session("main") as s:
            assert s.query(Sale).count() == 1
