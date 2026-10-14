"""
LAN Sync must never let two tills' records collide on the Main PC (#671).

Every till numbers its own rows from 1, so "sale id 5" from till A and
"sale id 5" from till B are different sales. The Main PC used to
``session.merge()`` pushed rows by that integer id, so the second push
overwrote the first (with its items and payments), and the second till's
stock movement was mistaken for a re-send and never touched stock.

These tests drive the real push handler with payloads shaped exactly like
``SyncClient._push_transactions`` builds them.
"""

import sqlite3
from datetime import datetime
from decimal import Decimal

import pytest
from alembic.config import Config as AlembicConfig
from sqlalchemy import create_engine, inspect

from alembic import command
from cbpos.config import Config
from cbpos.core.models import (
    AuditLog,
    Base,
    CashMovement,
    Customer,
    CustomerLedgerEntry,
    CustomerPayment,
    Document,
    Permission,
    Product,
    Purchase,
    PurchaseItem,
    Role,
    Sale,
    SaleItem,
    SalePayment,
    Shift,
    StockMovement,
    Supplier,
    SupplierLedgerEntry,
    SupplierPayment,
    User,
    VoidReason,
)
from cbpos.core.services.sync_protocol import make_envelope, model_to_dict
from cbpos.infrastructure.sync_server import SyncRequestHandler, _registry

_counter = 0


def _uid() -> int:
    global _counter
    _counter += 1
    return _counter


# ---------------------------------------------------------------------------
# Main PC catalog fixtures (Main-owned rows the tills reference by id)
# ---------------------------------------------------------------------------
@pytest.fixture
def user(db_session):
    n = _uid()
    permission = Permission(code=f"idmap_perm_{n}")
    role = Role(name=f"IdMapRole_{n}", permissions=[permission])
    u = User(username=f"idmap_user_{n}", pin_hash="hash", role=role)
    db_session.add_all([permission, role, u])
    db_session.flush()
    return u


@pytest.fixture
def product(db_session):
    n = _uid()
    p = Product(name_en=f"IdMapProduct_{n}", price=Decimal("100.00"), stock_qty=Decimal("10"), barcode=f"IDM{n:05d}")
    db_session.add(p)
    db_session.flush()
    return p


@pytest.fixture
def customer(db_session):
    c = Customer(name=f"IdMapCustomer_{_uid()}", credit_limit=Decimal("10000"), current_debt=Decimal("0"))
    db_session.add(c)
    db_session.flush()
    return c


@pytest.fixture
def supplier(db_session):
    s = Supplier(company_name=f"IdMapSupplier_{_uid()}")
    db_session.add(s)
    db_session.flush()
    return s


@pytest.fixture
def void_reason(db_session):
    n = _uid()
    r = VoidReason(description=f"IdMap reason {n}", code=f"IDM{n}")
    db_session.add(r)
    db_session.flush()
    return r


# ---------------------------------------------------------------------------
# Push plumbing
# ---------------------------------------------------------------------------
class _FakePushHandler:
    """Stand-in for SyncRequestHandler exposing only what the push path touches."""

    def __init__(self, envelope):
        self._envelope = envelope
        self.response = None
        self.response_status = None

    def _read_json(self):
        return self._envelope

    def _send_json(self, data, status=200):
        self.response = data
        self.response_status = status

    _handle_push_transactions = SyncRequestHandler._handle_push_transactions
    _handle_push_audit = SyncRequestHandler._handle_push_audit
    _log_sync = staticmethod(SyncRequestHandler._log_sync)


class Till:
    """Builds push payloads the way SyncClient does for one terminal."""

    def __init__(self, terminal_id: str):
        self.terminal_id = terminal_id
        self.sequence = 0

    def push(self, payload: dict, sequence: int | None = None):
        if sequence is None:
            self.sequence += 1
            sequence = self.sequence
        handler = _FakePushHandler(make_envelope(self.terminal_id, "PUSH_TRANSACTIONS", payload, sequence=sequence))
        handler._handle_push_transactions()
        return handler.response, handler.response_status

    def push_audit(self, records: list[dict]):
        handler = _FakePushHandler(make_envelope(self.terminal_id, "PUSH_AUDIT", {"audit_logs": records}))
        handler._handle_push_audit()
        return handler.response, handler.response_status

    # --- record builders (all columns filled, like a persisted till row) ---

    def sale(
        self,
        local_id: int,
        doc_number: str,
        user_id: int,
        total: Decimal,
        customer_id: int | None = None,
        refund_of_sale_id: int | None = None,
        void_reason_id: int | None = None,
        payment_method: str = "CASH",
    ) -> Sale:
        return Sale(
            id=local_id,
            document_number=doc_number,
            type="sale",
            date=datetime(2026, 10, 7, 10, 0, local_id % 60),
            user_id=user_id,
            status="COMPLETED",
            reference_external=None,
            void_reason_id=void_reason_id,
            terminal_id=self.terminal_id,
            origin_terminal_id=self.terminal_id,
            synced=False,
            customer_id=customer_id,
            total_amount=total,
            tax_vat=Decimal("0"),
            tax_sscl=Decimal("0"),
            net_revenue=total,
            additional_discount_type="NONE",
            additional_discount_value=Decimal("0"),
            payment_method=payment_method,
            refund_of_sale_id=refund_of_sale_id,
        )

    @staticmethod
    def item(local_id: int, sale_id: int, product_id: int, qty: Decimal, price: Decimal) -> SaleItem:
        return SaleItem(
            id=local_id,
            sale_id=sale_id,
            product_id=product_id,
            qty=qty,
            unit_price=price,
            original_price=price,
            discount_type="NONE",
            discount_value=Decimal("0"),
            is_manual_price=False,
            subtotal=qty * price,
            notes=None,
        )

    @staticmethod
    def payment(local_id: int, sale_id: int, amount: Decimal, method: str = "CASH") -> SalePayment:
        return SalePayment(id=local_id, sale_id=sale_id, payment_method=method, amount=amount)

    def movement(
        self,
        local_id: int,
        product_id: int,
        user_id: int,
        qty_change: Decimal,
        document_id: int | None,
        movement_type: str = "SALE",
    ) -> StockMovement:
        return StockMovement(
            id=local_id,
            product_id=product_id,
            user_id=user_id,
            timestamp=datetime(2026, 10, 7, 10, 0, local_id % 60),
            qty_change=qty_change,
            balance_after=Decimal("0"),
            document_id=document_id,
            type=movement_type,
            terminal_id=self.terminal_id,
            synced=False,
        )

    def sales_payload(self, sales: list[Sale], items=(), payments=(), movements=()) -> dict:
        """Same shape as SyncClient._push_transactions: documents + sales + children."""
        docs = [
            {
                "id": s.id,
                "document_number": s.document_number,
                "date": s.date.isoformat(),
                "type": s.type,
                "status": s.status,
                "user_id": s.user_id,
                "void_reason_id": s.void_reason_id,
                "terminal_id": s.terminal_id,
                "origin_terminal_id": s.origin_terminal_id or self.terminal_id,
                "synced": True,
            }
            for s in sales
        ]
        payload: dict = {}
        if sales:
            payload["documents"] = docs
            payload["sales"] = [model_to_dict(s) for s in sales]
            payload["sale_items"] = [model_to_dict(i) for i in items]
            payload["sale_payments"] = [model_to_dict(p) for p in payments]
        if movements:
            payload["stock_movements"] = [model_to_dict(m) for m in movements]
        return payload

    def simple_sale_payload(
        self,
        local_id: int,
        doc_number: str,
        user_id: int,
        product_id: int,
        qty: Decimal,
        price: Decimal = Decimal("100.00"),
        customer_id: int | None = None,
    ) -> dict:
        """One sale, one item, one payment, one SALE movement — all with local ids == local_id."""
        total = qty * price
        sale = self.sale(local_id, doc_number, user_id, total, customer_id=customer_id)
        return self.sales_payload(
            [sale],
            items=[self.item(local_id, local_id, product_id, qty, price)],
            payments=[self.payment(local_id, local_id, total)],
            movements=[self.movement(local_id, product_id, user_id, -qty, local_id)],
        )


def _doc(session, doc_number: str) -> Sale | None:
    session.expire_all()
    return session.query(Sale).filter_by(document_number=doc_number).one_or_none()


def _counts(session) -> dict[str, int]:
    session.expire_all()
    return {
        "documents": session.query(Document).count(),
        "sale_items": session.query(SaleItem).count(),
        "sale_payments": session.query(SalePayment).count(),
        "stock_movements": session.query(StockMovement).count(),
    }


# ---------------------------------------------------------------------------
# Acceptance: two tills, same local ids
# ---------------------------------------------------------------------------
class TestTwoTillsSameLocalIds:
    def test_both_sales_kept_with_their_own_items_and_payments(self, db_session, user, product):
        till_a, till_b = Till(f"TA-{_uid()}"), Till(f"TB-{_uid()}")
        doc_a, doc_b = f"{till_a.terminal_id}-INV-1", f"{till_b.terminal_id}-INV-1"

        resp_a, status_a = till_a.push(till_a.simple_sale_payload(1, doc_a, user.id, product.id, Decimal("2")))
        resp_b, status_b = till_b.push(till_b.simple_sale_payload(1, doc_b, user.id, product.id, Decimal("3")))
        assert status_a == 200 and resp_a["status"] == "ok", resp_a
        assert status_b == 200 and resp_b["status"] == "ok", resp_b

        sale_a, sale_b = _doc(db_session, doc_a), _doc(db_session, doc_b)
        assert sale_a is not None, "till A's sale was overwritten by till B's sale with the same local id"
        assert sale_b is not None
        assert sale_a.id != sale_b.id

        assert sale_a.origin_terminal_id == till_a.terminal_id
        assert sale_b.origin_terminal_id == till_b.terminal_id
        assert [i.qty for i in sale_a.items] == [Decimal("2")]
        assert [i.qty for i in sale_b.items] == [Decimal("3")]
        assert [p.amount for p in sale_a.payments] == [Decimal("200.00")]
        assert [p.amount for p in sale_b.payments] == [Decimal("300.00")]
        assert sale_a.total_amount == Decimal("200.00")
        assert sale_b.total_amount == Decimal("300.00")

    def test_main_pcs_own_sale_is_not_overwritten(self, db_session, user, product):
        own = Till("MAIN").sale(0, f"MAIN-OWN-{_uid()}", user.id, Decimal("50.00"))
        own.id = None
        db_session.add(own)
        db_session.flush()
        own_id, own_number = own.id, own.document_number

        till = Till(f"TC-{_uid()}")
        doc = f"{till.terminal_id}-INV-1"
        resp, _ = till.push(till.simple_sale_payload(own_id, doc, user.id, product.id, Decimal("1")))
        assert resp["status"] == "ok", resp

        db_session.expire_all()
        main_sale = db_session.get(Sale, own_id)
        assert main_sale.document_number == own_number
        assert main_sale.total_amount == Decimal("50.00")
        assert _doc(db_session, doc).id != own_id

    def test_stock_reflects_both_tills_movements(self, db_session, user, product):
        till_a, till_b = Till(f"TA-{_uid()}"), Till(f"TB-{_uid()}")
        till_a.push(till_a.simple_sale_payload(1, f"{till_a.terminal_id}-INV-1", user.id, product.id, Decimal("2")))
        till_b.push(till_b.simple_sale_payload(1, f"{till_b.terminal_id}-INV-1", user.id, product.id, Decimal("3")))

        db_session.expire_all()
        assert db_session.get(Product, product.id).stock_qty == Decimal("5")
        assert db_session.query(StockMovement).filter_by(product_id=product.id).count() == 2

    def test_audit_logs_from_two_tills_do_not_overwrite_each_other(self, db_session, user):
        own = AuditLog(user_id=user.id, action="MAIN_OWN", event_type="LOGIN", terminal_id="MAIN")
        db_session.add(own)
        db_session.flush()
        local_id = own.id

        till_a, till_b = Till(f"TA-{_uid()}"), Till(f"TB-{_uid()}")
        for till in (till_a, till_b):
            log = AuditLog(
                id=local_id,
                user_id=user.id,
                action=f"FROM_{till.terminal_id}",
                event_type="LOGIN",
                terminal_id=till.terminal_id,
                details=None,
                timestamp=datetime(2026, 10, 7, 9, 0, 0),
                synced=False,
            )
            resp, _ = till.push_audit([model_to_dict(log)])
            assert resp["status"] == "ok"

        db_session.expire_all()
        assert db_session.get(AuditLog, local_id).action == "MAIN_OWN"
        actions = {a.action for a in db_session.query(AuditLog).all()}
        assert {f"FROM_{till_a.terminal_id}", f"FROM_{till_b.terminal_id}"} <= actions


# ---------------------------------------------------------------------------
# Idempotent re-sends
# ---------------------------------------------------------------------------
class TestRepushIsIdempotent:
    def test_repushing_same_batch_changes_nothing(self, db_session, user, product):
        till_a, till_b = Till(f"TA-{_uid()}"), Till(f"TB-{_uid()}")
        payload_a = till_a.simple_sale_payload(1, f"{till_a.terminal_id}-INV-1", user.id, product.id, Decimal("2"))
        payload_b = till_b.simple_sale_payload(1, f"{till_b.terminal_id}-INV-1", user.id, product.id, Decimal("3"))

        till_a.push(payload_a)
        till_b.push(payload_b)
        before = _counts(db_session)
        stock_before = db_session.get(Product, product.id).stock_qty

        # Lost-response retry: same records, new sequence number.
        resp_a, _ = till_a.push(payload_a)
        resp_b, _ = till_b.push(payload_b)
        assert resp_a["status"] == "ok" and resp_b["status"] == "ok"

        assert _counts(db_session) == before
        db_session.expire_all()
        assert db_session.get(Product, product.id).stock_qty == stock_before == Decimal("5")

    def test_repush_after_main_restart_does_not_double_apply_stock(self, db_session, user, product):
        """The in-memory sequence check is gone after a Main PC restart; the id map is not."""
        till = Till(f"TA-{_uid()}")
        payload = till.simple_sale_payload(1, f"{till.terminal_id}-INV-1", user.id, product.id, Decimal("4"))

        till.push(payload, sequence=1)
        _registry.remove(till.terminal_id)
        till.push(payload, sequence=1)

        db_session.expire_all()
        assert db_session.get(Product, product.id).stock_qty == Decimal("6")
        assert db_session.query(Sale).filter_by(origin_terminal_id=till.terminal_id).count() == 1

    def test_push_after_till_restart_is_not_dropped_as_duplicate(self, db_session, user, product):
        """A restarted till starts its sequence at 1 again; its new sales must still land."""
        till = Till(f"TA-{_uid()}")
        _registry.register(till.terminal_id, "127.0.0.1")
        try:
            till.push(
                till.simple_sale_payload(1, f"{till.terminal_id}-INV-1", user.id, product.id, Decimal("1")), sequence=7
            )
            # Till restarts: SyncClient._push_sequence is back to 0.
            resp, _ = till.push(
                till.simple_sale_payload(2, f"{till.terminal_id}-INV-2", user.id, product.id, Decimal("1")), sequence=1
            )
        finally:
            _registry.remove(till.terminal_id)

        assert resp["status"] == "ok", resp
        assert _doc(db_session, f"{till.terminal_id}-INV-2") is not None


# ---------------------------------------------------------------------------
# Child foreign keys are remapped; Main-owned references are not
# ---------------------------------------------------------------------------
class TestForeignKeyRemapping:
    def test_sale_children_point_at_server_ids(self, db_session, user, product, customer, void_reason):
        # Occupy low ids so the till's local ids cannot coincide with server ids.
        filler = Till("MAIN")
        for _ in range(3):
            s = filler.sale(0, f"MAIN-FILL-{_uid()}", user.id, Decimal("1.00"))
            s.id = None
            db_session.add(s)
        db_session.flush()

        till = Till(f"TA-{_uid()}")
        original = till.sale(1, f"{till.terminal_id}-INV-1", user.id, Decimal("200.00"), customer_id=customer.id)
        refund = till.sale(
            2,
            f"{till.terminal_id}-CN-1",
            user.id,
            Decimal("-100.00"),
            customer_id=customer.id,
            refund_of_sale_id=1,
            void_reason_id=void_reason.id,
        )
        payload = till.sales_payload(
            [refund, original],  # refund listed first on purpose
            items=[
                till.item(1, 1, product.id, Decimal("2"), Decimal("100.00")),
                till.item(2, 2, product.id, Decimal("-1"), Decimal("100.00")),
            ],
            payments=[till.payment(1, 1, Decimal("200.00")), till.payment(2, 2, Decimal("-100.00"))],
            movements=[
                till.movement(1, product.id, user.id, Decimal("-2"), 1),
                till.movement(2, product.id, user.id, Decimal("1"), 2, movement_type="RETURN"),
                till.movement(3, product.id, user.id, Decimal("5"), None, movement_type="ADJUSTMENT"),
            ],
        )
        resp, status = till.push(payload)
        assert status == 200 and resp["status"] == "ok", resp

        sale = _doc(db_session, f"{till.terminal_id}-INV-1")
        credit_note = _doc(db_session, f"{till.terminal_id}-CN-1")
        assert sale.id != 1 and credit_note.id != 2

        assert credit_note.refund_of_sale_id == sale.id
        assert [i.sale_id for i in sale.items] == [sale.id]
        assert [p.sale_id for p in credit_note.payments] == [credit_note.id]

        movements = (
            db_session.query(StockMovement)
            .filter_by(terminal_id=till.terminal_id)
            .order_by(StockMovement.qty_change)
            .all()
        )
        assert [(m.qty_change, m.document_id) for m in movements] == [
            (Decimal("-2"), sale.id),
            (Decimal("1"), credit_note.id),
            (Decimal("5"), None),
        ]

        # Main-owned references keep their ids.
        assert sale.user_id == user.id
        assert sale.customer_id == customer.id
        assert credit_note.void_reason_id == void_reason.id
        assert {i.product_id for i in sale.items + credit_note.items} == {product.id}
        assert {m.product_id for m in movements} == {product.id}
        assert {m.user_id for m in movements} == {user.id}
        db_session.expire_all()
        assert db_session.get(Product, product.id).stock_qty == Decimal("14")

    def test_later_batch_references_earlier_batch(self, db_session, user, product):
        till = Till(f"TA-{_uid()}")
        other = Till(f"TB-{_uid()}")
        # Another till takes the server ids first.
        other.push(other.simple_sale_payload(1, f"{other.terminal_id}-INV-1", user.id, product.id, Decimal("1")))

        till.push(till.simple_sale_payload(1, f"{till.terminal_id}-INV-1", user.id, product.id, Decimal("2")))
        # Later the till voids that sale: a VOID movement pointing at local sale 1.
        resp, _ = till.push(
            {"stock_movements": [model_to_dict(till.movement(2, product.id, user.id, Decimal("2"), 1, "VOID"))]}
        )
        assert resp["status"] == "ok", resp

        sale = _doc(db_session, f"{till.terminal_id}-INV-1")
        void = db_session.query(StockMovement).filter_by(terminal_id=till.terminal_id, type="VOID").one()
        assert void.document_id == sale.id

    def test_shift_cash_and_credit_ledger_remapped(self, db_session, user, product, customer):
        other = Till(f"TB-{_uid()}")
        till = Till(f"TA-{_uid()}")
        start = datetime(2026, 10, 7, 8, 0, 0)

        def shift(t: Till) -> Shift:
            return Shift(
                id=1,
                user_id=user.id,
                start_time=start,
                end_time=None,
                starting_cash=Decimal("1000.00"),
                expected_cash=None,
                actual_cash=None,
                status="OPEN",
                terminal_id=t.terminal_id,
                synced=False,
                reason_category=None,
                notes=None,
            )

        def cash(t: Till, amount: str) -> CashMovement:
            return CashMovement(
                id=1,
                shift_id=1,
                user_id=user.id,
                type="IN",
                amount=Decimal(amount),
                reason=f"float {t.terminal_id}",
                timestamp=start,
                synced=False,
            )

        def cpay(amount: str) -> CustomerPayment:
            return CustomerPayment(
                id=1,
                customer_id=customer.id,
                amount=Decimal(amount),
                payment_method="CASH",
                reference=None,
                note=None,
                user_id=user.id,
                timestamp=start,
                synced=False,
            )

        def ledger(local_id: int, entry_type: str, amount: str, ref: int) -> CustomerLedgerEntry:
            return CustomerLedgerEntry(
                id=local_id,
                customer_id=customer.id,
                entry_type=entry_type,
                amount=Decimal(amount),
                balance_after=Decimal("0"),
                reference_id=ref,
                reference_doc=None,
                note=None,
                user_id=user.id,
                timestamp=start,
                synced=False,
            )

        def payload(t: Till, cash_amt: str, pay_amt: str, qty: str) -> dict:
            p = t.simple_sale_payload(
                1, f"{t.terminal_id}-INV-1", user.id, product.id, Decimal(qty), customer_id=customer.id
            )
            p["shifts"] = [model_to_dict(shift(t))]
            p["cash_movements"] = [model_to_dict(cash(t, cash_amt))]
            p["customer_payments"] = [model_to_dict(cpay(pay_amt))]
            p["customer_ledger"] = [
                model_to_dict(ledger(1, "SALE", "100.00", 1)),
                model_to_dict(ledger(2, "PAYMENT", f"-{pay_amt}", 1)),
            ]
            return p

        assert other.push(payload(other, "11.00", "7.00", "1"))[0]["status"] == "ok"
        resp, _ = till.push(payload(till, "22.00", "9.00", "2"))
        assert resp["status"] == "ok", resp

        db_session.expire_all()
        shifts = {s.terminal_id: s for s in db_session.query(Shift).all()}
        assert till.terminal_id in shifts and other.terminal_id in shifts
        till_shift = shifts[till.terminal_id]

        till_cash = db_session.query(CashMovement).filter_by(reason=f"float {till.terminal_id}").one()
        assert till_cash.shift_id == till_shift.id
        assert till_cash.amount == Decimal("22.00")

        till_sale = _doc(db_session, f"{till.terminal_id}-INV-1")
        till_payment = db_session.query(CustomerPayment).filter_by(amount=Decimal("9.00")).one()
        entries = {
            e.entry_type: e
            for e in db_session.query(CustomerLedgerEntry).filter(
                CustomerLedgerEntry.amount.in_([Decimal("100.00"), Decimal("-9.00")]),
                CustomerLedgerEntry.reference_id.in_([till_sale.id, till_payment.id]),
            )
        }
        assert entries["SALE"].reference_id == till_sale.id
        assert entries["PAYMENT"].reference_id == till_payment.id
        assert db_session.query(CustomerPayment).count() == 2
        assert db_session.query(CashMovement).count() == 2

    def test_purchase_children_and_supplier_ledger_remapped(self, db_session, user, product, supplier):
        other = Till(f"TB-{_uid()}")
        till = Till(f"TA-{_uid()}")
        when = datetime(2026, 10, 7, 11, 0, 0)

        def payload(t: Till, qty: str) -> dict:
            purchase = Purchase(
                id=1,
                document_number=f"{t.terminal_id}-GRN-1",
                type="purchase",
                date=when,
                user_id=user.id,
                status="COMPLETED",
                reference_external=None,
                void_reason_id=None,
                terminal_id=t.terminal_id,
                origin_terminal_id=t.terminal_id,
                synced=False,
                supplier_id=supplier.id,
                total_cost=Decimal(qty) * 50,
                input_vat=Decimal("0"),
                purchase_order_id=None,
            )
            item = PurchaseItem(
                id=1,
                purchase_id=1,
                product_id=product.id,
                qty_received=Decimal(qty),
                unit_cost=Decimal("50.00"),
                purchase_order_item_id=None,
            )
            spay = SupplierPayment(
                id=1,
                supplier_id=supplier.id,
                amount=Decimal(qty),
                payment_method="CASH",
                reference=None,
                note=None,
                user_id=user.id,
                timestamp=when,
                synced=False,
            )
            entries = [
                SupplierLedgerEntry(
                    id=i,
                    supplier_id=supplier.id,
                    entry_type=kind,
                    amount=Decimal(qty),
                    balance_after=Decimal("0"),
                    reference_id=1,
                    reference_doc=None,
                    note=None,
                    user_id=user.id,
                    timestamp=when,
                    synced=False,
                )
                for i, kind in ((1, "PURCHASE"), (2, "PAYMENT"))
            ]
            return {
                "documents": [
                    {
                        "id": 1,
                        "document_number": purchase.document_number,
                        "date": when.isoformat(),
                        "type": "purchase",
                        "status": "COMPLETED",
                        "user_id": user.id,
                        "terminal_id": t.terminal_id,
                        "origin_terminal_id": t.terminal_id,
                        "synced": True,
                    }
                ],
                "purchases": [model_to_dict(purchase)],
                "purchase_items": [model_to_dict(item)],
                "stock_movements": [model_to_dict(t.movement(1, product.id, user.id, Decimal(qty), 1, "PURCHASE"))],
                "supplier_payments": [model_to_dict(spay)],
                "supplier_ledger": [model_to_dict(e) for e in entries],
            }

        assert other.push(payload(other, "3"))[0]["status"] == "ok"
        resp, _ = till.push(payload(till, "4"))
        assert resp["status"] == "ok", resp

        db_session.expire_all()
        purchase = db_session.query(Purchase).filter_by(document_number=f"{till.terminal_id}-GRN-1").one()
        assert [(i.purchase_id, i.qty_received) for i in purchase.items] == [(purchase.id, Decimal("4"))]
        assert purchase.supplier_id == supplier.id
        spay = db_session.query(SupplierPayment).filter_by(amount=Decimal("4")).one()
        refs = {
            e.entry_type: e.reference_id
            for e in db_session.query(SupplierLedgerEntry).filter_by(amount=Decimal("4")).all()
        }
        assert refs == {"PURCHASE": purchase.id, "PAYMENT": spay.id}
        assert db_session.get(Product, product.id).stock_qty == Decimal("17")


# ---------------------------------------------------------------------------
# Failure handling and pre-upgrade (legacy) rows
# ---------------------------------------------------------------------------
class TestFailuresAndLegacyRows:
    def test_unresolvable_child_rejects_whole_batch(self, db_session, user, product):
        """A child whose parent can't be found must not half-apply the batch.

        The till marks every pushed row synced on any "ok"/"partial" reply,
        so a partially applied batch would silently lose the failed rows.
        """
        # Commit the fixtures so the push's rollback only undoes the push
        # (the test's outer transaction still discards them at teardown).
        db_session.commit()
        till = Till(f"TA-{_uid()}")
        payload = till.simple_sale_payload(1, f"{till.terminal_id}-INV-1", user.id, product.id, Decimal("1"))
        payload["sale_items"].append(model_to_dict(till.item(9, 999, product.id, Decimal("1"), Decimal("1"))))

        resp, status = till.push(payload)

        assert status == 500, resp
        assert _doc(db_session, f"{till.terminal_id}-INV-1") is None
        assert db_session.get(Product, product.id).stock_qty == Decimal("10")

    def test_legacy_row_from_before_the_id_map_is_adopted_not_duplicated(self, db_session, user, product):
        """A sale pushed before this fix sits on Main at the till's own id, with no id-map row."""
        till = Till(f"TA-{_uid()}")
        legacy_id = 900_000 + _uid()
        doc = f"{till.terminal_id}-INV-OLD"
        legacy = till.sale(legacy_id, doc, user.id, Decimal("100.00"))
        legacy.synced = True
        db_session.add(legacy)
        db_session.add(till.item(legacy_id, legacy_id, product.id, Decimal("1"), Decimal("100.00")))
        db_session.add(till.movement(legacy_id, product.id, user.id, Decimal("-1"), legacy_id))
        db_session.flush()
        before = _counts(db_session)

        # Lost-response retry of that same pre-upgrade push, now reaching the new code.
        payload = till.simple_sale_payload(legacy_id, doc, user.id, product.id, Decimal("1"))
        payload["sale_payments"] = []
        resp, _ = till.push(payload)
        assert resp["status"] == "ok", resp
        assert _counts(db_session) == before
        assert db_session.get(Product, product.id).stock_qty == Decimal("10")

        # A void made after the upgrade still finds the legacy sale.
        till.push(
            {
                "stock_movements": [
                    model_to_dict(till.movement(legacy_id + 1, product.id, user.id, Decimal("1"), legacy_id, "VOID"))
                ]
            }
        )
        void = db_session.query(StockMovement).filter_by(terminal_id=till.terminal_id, type="VOID").one()
        assert void.document_id == legacy_id

    def test_reference_to_unknown_or_foreign_document_is_cleared(self, db_session, user, product):
        """A nullable reference that can't be resolved to this till's own row is dropped, never misattached."""
        other = Till(f"TB-{_uid()}")
        till = Till(f"TA-{_uid()}")
        foreign_id = 800_000 + _uid()
        foreign = other.sale(foreign_id, f"{other.terminal_id}-INV-X", user.id, Decimal("1.00"))
        db_session.add(foreign)
        db_session.flush()

        resp, _ = till.push(
            {
                "stock_movements": [
                    model_to_dict(till.movement(1, product.id, user.id, Decimal("1"), foreign_id, "VOID")),
                    model_to_dict(till.movement(2, product.id, user.id, Decimal("1"), foreign_id + 1, "VOID")),
                ]
            }
        )
        assert resp["status"] == "ok", resp
        moves = db_session.query(StockMovement).filter_by(terminal_id=till.terminal_id).all()
        assert [m.document_id for m in moves] == [None, None]
        assert db_session.get(Product, product.id).stock_qty == Decimal("12")


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


class TestSyncIdMapMigration:
    def test_downgrade_drops_and_upgrade_recreates_table(self, alembic_cfg):
        cfg, db_path, uri = alembic_cfg

        command.downgrade(cfg, "b4d6fbce9cf4")  # the revision before sync_id_map
        engine = create_engine(uri)
        assert "sync_id_map" not in inspect(engine).get_table_names()
        engine.dispose()

        # Existing data in an older DB survives the upgrade.
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "INSERT INTO sync_logs (terminal_id, direction, sync_type, records_count, status, started_at)"
                " VALUES ('T1', 'PUSH', 'TRANSACTIONS', 1, 'SUCCESS', '2026-10-07 10:00:00')"
            )

        command.upgrade(cfg, "head")
        engine = create_engine(uri)
        insp = inspect(engine)
        assert "sync_id_map" in insp.get_table_names()
        uniques = insp.get_unique_constraints("sync_id_map")
        assert any(set(u["column_names"]) == {"origin_terminal_id", "table_name", "local_id"} for u in uniques), uniques
        engine.dispose()

        with sqlite3.connect(db_path) as conn:
            assert conn.execute("SELECT COUNT(*) FROM sync_logs").fetchone()[0] == 1
            conn.execute(
                "INSERT INTO sync_id_map (origin_terminal_id, table_name, local_id, server_id, created_at)"
                " VALUES ('T1', 'documents', 5, 42, '2026-10-07')"
            )
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO sync_id_map (origin_terminal_id, table_name, local_id, server_id, created_at)"
                    " VALUES ('T1', 'documents', 5, 43, '2026-10-07')"
                )
