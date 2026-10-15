"""
Apply rows pushed by a till to the Main PC database (LAN Sync, #671).

Every till numbers its own rows from 1, so a pushed row's ``id`` means
nothing on its own: till A's sale 5 and till B's sale 5 are different
sales, and the Main PC has a sale 5 of its own too. This module never
writes a pushed row under the till's id. The Main PC inserts it under an
id it assigns itself and records ``(till, id space, local id) -> server
id`` in ``sync_id_map``. A re-sent row (lost response, retry, Main PC
restart) is found again through that map and updated in place, so
re-sends stay idempotent.

Ownership of the tables a push touches:

- Till-originated (pushed, re-keyed through the map): every table in
  ``TRANSACTION_TABLES`` -- documents/sales/purchases (one shared id
  space, ``"documents"``), sale_items, sale_payments, purchase_items,
  stock_movements, shifts, cash_movements, customer_payments,
  customer_ledger, supplier_payments, supplier_ledger, audit_logs,
  suspended_transactions, inventory_logs.
- Main-owned (pulled by tills from the Main PC, so their ids already
  agree): everything in ``CATALOG_TABLES`` -- users, roles, products,
  customers, suppliers, void_reasons, payment methods, ... Columns that
  point at these (user_id, product_id, customer_id, supplier_id,
  void_reason_id) are written as-is.
- The one exception: a customer *created* on a till (#680) is pushed
  (first in the batch) and mapped like a till row. A ``customer_id`` in
  the same batch that names such a customer is translated; the push
  acknowledgement returns the new ids and the till renumbers its copy
  (sync_customer_renumber), after which its ids agree with the Main PC's.
  Its contacts come in the same batch and are stored with it (#717).

Balances (#678): ``Customer.current_debt`` and ``Supplier.current_payable``
are Main-owned columns that till activity moves. Each pushed ledger row
moves the Main PC balance by its amount on first arrival only, and the
push acknowledgement carries the resulting balances back to the till.
``Customer.loyalty_points`` moves the same way, by loyalty ledger rows (#716).
"""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import inspect as sa_inspect

from cbpos.core.models import Customer, CustomerContact, Document, Product, Supplier, SyncIdMap
from cbpos.core.services.sync_change_tracking import SKIP_CHANGE_TRACKING
from cbpos.core.services.sync_protocol import (
    REJECTED_TABLE_ERROR,
    TRANSACTION_TABLES,
    coerce_columns,
    get_model_for_table,
)

logger = logging.getLogger(__name__)

# Sales and purchases are joined-table subclasses of Document: a sale's
# id *is* its documents.id, so the three share one id space in the map.
DOCUMENT_ID_SPACE = "documents"
_DOCUMENT_TABLES = frozenset({"documents", "sales", "purchases"})

# Order rows are applied in -- parents before anything that points at
# them. This is deliberately not the payload's order: the till lists
# "documents" before "sales", but a documents row only carries the base
# columns of a sale/purchase, so the full subclass row has to create the
# server row first and the documents row then just updates it.
APPLY_ORDER: tuple[str, ...] = (
    "customers",
    "customer_contacts",
    "shifts",
    "sales",
    "purchases",
    "documents",
    "sale_items",
    "sale_payments",
    "purchase_items",
    "stock_movements",
    "cash_movements",
    "customer_payments",
    "customer_ledger",
    "loyalty_ledger",
    "supplier_payments",
    "supplier_ledger",
    "audit_logs",
    "suspended_transactions",
    "inventory_logs",
)
assert set(APPLY_ORDER) == set(TRANSACTION_TABLES), "APPLY_ORDER must cover exactly TRANSACTION_TABLES"


# Columns that point at another till-originated row: column -> id space of
# the row it points at. Translated to the Main PC id before the row is
# written. Main-owned references (user_id, product_id, customer_id, ...)
# are not listed and are kept as sent.
TERMINAL_REFS: dict[str, dict[str, str]] = {
    "sales": {"refund_of_sale_id": DOCUMENT_ID_SPACE},
    "sale_items": {"sale_id": DOCUMENT_ID_SPACE},
    "sale_payments": {"sale_id": DOCUMENT_ID_SPACE},
    "purchase_items": {"purchase_id": DOCUMENT_ID_SPACE},
    "stock_movements": {"document_id": DOCUMENT_ID_SPACE},
    "cash_movements": {"shift_id": "shifts"},
}

# Ledger reference_id is a plain integer whose target depends on the entry.
LEDGER_REFS: dict[str, dict[str, str]] = {
    # VOID/REFUND rows point at the credit sale they give back (#715).
    "customer_ledger": {
        "SALE": DOCUMENT_ID_SPACE,
        "VOID": DOCUMENT_ID_SPACE,
        "REFUND": DOCUMENT_ID_SPACE,
        "PAYMENT": "customer_payments",
    },
    "loyalty_ledger": {
        "EARN": DOCUMENT_ID_SPACE,
        "REVERSAL": DOCUMENT_ID_SPACE,
        "REDEEM": DOCUMENT_ID_SPACE,
    },
    "supplier_ledger": {"PURCHASE": DOCUMENT_ID_SPACE, "PAYMENT": "supplier_payments"},
}

# Tables whose customer_id may point at a customer the till created and
# pushed in the same batch (#680). Any other customer_id is a Main PC id.
_CUSTOMER_REF_TABLES = frozenset(
    {"sales", "customer_payments", "customer_ledger", "loyalty_ledger", "suspended_transactions"}
)

# Columns that point at till rows that are never pushed (purchase orders
# stay on the till that raised them). No Main PC row is that till's row,
# so the reference is dropped rather than left pointing at whatever the
# Main PC happens to have under that id.
UNSYNCED_REFS: dict[str, tuple[str, ...]] = {
    "purchases": ("purchase_order_id",),
    "purchase_items": ("purchase_order_item_id",),
}

# For a reference to a row pushed before sync_id_map existed (stored under
# the till's own id, e.g. a sale voided after the upgrade): the column that
# says which till a Main PC row came from, per id space.
_ORIGIN_COLUMNS: dict[str, tuple[str, tuple[str, ...]]] = {
    DOCUMENT_ID_SPACE: ("documents", ("origin_terminal_id", "terminal_id")),
    "shifts": ("shifts", ("terminal_id",)),
}


@dataclass(frozen=True)
class _LedgerBalance:
    """A Main-owned figure that a till's ledger rows move (#678, #716)."""

    reply_key: str  # key of the figure in the push acknowledgement's "balances"
    owner_model: type
    owner_column: str  # ledger column naming the owner row
    balance_column: str  # the figure on the owner row
    amount_column: str  # ledger column it moves by


# Ledger table -> the figure its rows move.
_LEDGER_BALANCES: dict[str, _LedgerBalance] = {
    "customer_ledger": _LedgerBalance("customers", Customer, "customer_id", "current_debt", "amount"),
    "supplier_ledger": _LedgerBalance("suppliers", Supplier, "supplier_id", "current_payable", "amount"),
    "loyalty_ledger": _LedgerBalance("loyalty_points", Customer, "customer_id", "loyalty_points", "points"),
}


class PushApplyError(Exception):
    """A pushed row can't be applied safely; the whole batch must be rejected."""


def id_space(table_name: str) -> str:
    """Return the sync_id_map ``table_name`` (id space) for a pushed table."""
    return DOCUMENT_ID_SPACE if table_name in _DOCUMENT_TABLES else table_name


class SyncApplyService:
    """Applies one till's pushed batch inside the caller's session.

    The caller owns the transaction: on any exception it must roll back
    the whole batch (the till marks every row it sent as synced as soon as
    the push is acknowledged, so a half-applied batch would lose rows).
    """

    def __init__(self, session: Any, terminal_id: str) -> None:
        """Bind to an open session and the pushing till's terminal id.

        Args:
            session: Open SQLAlchemy session (transaction owned by caller).
            terminal_id: The till that sent the batch (envelope terminal_id).
        """
        if not terminal_id:
            raise PushApplyError("terminal_id required")
        self._session = session
        self._terminal_id = terminal_id
        self._id_cache: dict[tuple[str, int], int] = {}
        # Owners (Main PC ids) whose figure this batch's ledger rows touched, per reply key.
        self._touched_balances: dict[str, set[int]] = {b.reply_key: set() for b in _LEDGER_BALANCES.values()}
        # Till ids of the customers this batch creates (#680).
        self._batch_customers: set[int] = set()
        # ...and of those among them the Main PC didn't have yet (stored new).
        self._inserted_customers: set[int] = set()

    # --- Public API ---

    def apply_batch(self, payload: dict[str, Any]) -> tuple[int, list[str]]:
        """Apply every allowed table in ``payload``.

        Args:
            payload: ``{table_name: [row dict, ...]}`` as sent by the till.

        Returns:
            (rows applied, errors for tables that were skipped because they
            may not be pushed). Any row-level problem raises instead.

        Raises:
            PushApplyError: A row can't be applied without risking wrong data.
        """
        with self._applying():
            return self._apply_batch(payload)

    def _apply_batch(self, payload: dict[str, Any]) -> tuple[int, list[str]]:
        errors: list[str] = []
        customers = payload.get("customers")
        if isinstance(customers, list):
            self._batch_customers = {int(c["id"]) for c in customers if isinstance(c, dict) and c.get("id") is not None}
        for table_name, records in payload.items():
            if table_name not in TRANSACTION_TABLES:
                errors.append(f"{REJECTED_TABLE_ERROR}{table_name}")
                logger.warning("Terminal %s attempted to push disallowed table %r", self._terminal_id, table_name)
            elif not isinstance(records, list):
                raise PushApplyError(f"{table_name}: expected a list of rows")

        applied = 0
        for table_name in APPLY_ORDER:
            records = payload.get(table_name)
            if not records:
                continue
            # Ascending local id: a till's ids only grow, so a row that
            # points at another row of the same table (a refund at its
            # original sale) comes after the row it points at.
            for record in sorted(records, key=lambda r: (r.get("id") is None, r.get("id") or 0)):
                self._apply_record(table_name, dict(record))
                applied += 1
        return applied, errors

    def apply_record(self, table_name: str, record: dict[str, Any]) -> None:
        """Insert or update one pushed row under a server-assigned id.

        Args:
            table_name: Pushed table name (one of TRANSACTION_TABLES).
            record: The till's row, including its local ``id``.

        Raises:
            PushApplyError: The row is malformed or can't be placed safely.
        """
        with self._applying():
            self._apply_record(table_name, record)

    @contextmanager
    def _applying(self) -> Iterator[None]:
        """Rows stored here are the Main PC's copies, not rows to push again (#677)."""
        previous = self._session.info.get(SKIP_CHANGE_TRACKING)
        self._session.info[SKIP_CHANGE_TRACKING] = True
        try:
            yield
            self._session.flush()  # while the flag is still set
        finally:
            if previous is None:
                self._session.info.pop(SKIP_CHANGE_TRACKING, None)
            else:
                self._session.info[SKIP_CHANGE_TRACKING] = previous

    def _apply_record(self, table_name: str, record: dict[str, Any]) -> None:
        model_class = get_model_for_table(table_name)
        if model_class is None or table_name not in TRANSACTION_TABLES:
            raise PushApplyError(f"{table_name}: not a pushable table")

        local_id = record.pop("id", None)
        if local_id is None:
            raise PushApplyError(f"{table_name}: row without id")
        local_id = int(local_id)
        if any(isinstance(v, list) for v in record.values()):
            raise PushApplyError(f"{table_name}[{local_id}]: nested rows are not supported")

        values = coerce_columns(model_class, record)
        values.pop("id", None)
        if table_name == "customers":
            self._apply_customer(local_id, values)
            return
        if table_name == "customer_contacts":
            self._apply_customer_contact(local_id, values)
            return
        self._remap_references(table_name, model_class, local_id, values)
        balance = _LEDGER_BALANCES.get(table_name)
        if balance is not None and values.get(balance.owner_column) is not None:
            self._touched_balances[balance.reply_key].add(int(values[balance.owner_column]))
        if hasattr(model_class, "synced"):
            values["synced"] = True
        if table_name in _DOCUMENT_TABLES and not values.get("origin_terminal_id"):
            values["origin_terminal_id"] = self._terminal_id

        space = id_space(table_name)
        server_id = self._lookup(space, local_id)
        if server_id is not None:
            row = self._session.get(model_class, server_id)
            if row is None:
                # Mapped row was since deleted on the Main PC; don't resurrect
                # it (and never re-apply a stock movement).
                logger.warning(
                    "Sync: %s[%s] from %s maps to missing server row %s; skipped",
                    table_name,
                    local_id,
                    self._terminal_id,
                    server_id,
                )
                return
            self._update(row, table_name, values)
            return

        row = self._adopt_legacy_row(table_name, model_class, space, local_id, values)
        if row is not None:
            self._remember(space, local_id, row.id)
            self._update(row, table_name, values)
            return

        if table_name == "documents":
            # Only base columns -- the full row comes as sales/purchases.
            raise PushApplyError(f"documents[{local_id}]: no matching sales/purchases row in this push")

        instance = model_class(**values)
        self._session.add(instance)
        self._session.flush()  # assigns the server id
        self._remember(space, local_id, instance.id)
        self._on_insert(table_name, instance)

    def customer_id_map(self) -> dict[str, int]:
        """Main PC id of each customer this batch created, keyed by the till's id (as a string).

        Sent back with the push acknowledgement so the till can renumber its
        customer to the shop-wide id (#680).
        """
        result: dict[str, int] = {}
        for local_id in sorted(self._batch_customers):
            server_id = self._lookup("customers", local_id)
            if server_id is not None:
                result[str(local_id)] = server_id
        return result

    def balances(self) -> dict[str, dict[str, str]]:
        """Main PC figures of every customer/supplier whose ledger the applied rows touched.

        Sent back to the till with the push acknowledgement (#678, #716), so
        it can set its own figure to the shop-wide one plus whatever it has
        not pushed yet -- even when an earlier acknowledgement was lost.

        Returns:
            ``{"customers": {id: current_debt}, "suppliers": {id: current_payable},
            "loyalty_points": {id: loyalty_points}}`` with ids and figures as
            strings (JSON-safe). Tills older than #716 ignore "loyalty_points".
        """
        self._session.flush()
        result: dict[str, dict[str, str]] = {}
        for balance in _LEDGER_BALANCES.values():
            figures = result.setdefault(balance.reply_key, {})
            for owner_id in sorted(self._touched_balances[balance.reply_key]):
                owner = self._session.get(balance.owner_model, owner_id)
                if owner is not None:
                    figures[str(owner_id)] = str(getattr(owner, balance.balance_column) or 0)
        return result

    # --- Customers created on a till (#680) ---

    def _apply_customer(self, local_id: int, values: dict[str, Any]) -> None:
        """Give a till-created customer a Main PC id (or find the one it already has).

        A customer with the phone number or loyalty card of one the Main PC
        already has *is* that customer (both are unique): the till's row is
        mapped onto it and the Main PC's details are kept. Otherwise it is
        inserted with a zero balance -- its debt arrives through the ledger
        rows pushed with it. Its ``loyalty_points`` are kept as sent: a till
        sends only the points no loyalty ledger row carries (#716). A re-send
        (lost acknowledgement) changes nothing: the Main PC owns customer
        details once it has the customer.
        """
        if self._lookup("customers", local_id) is not None:
            return

        for unique_column in ("phone", "loyalty_card_code"):
            value = values.get(unique_column)
            if not value:
                continue
            existing = self._session.query(Customer).filter(getattr(Customer, unique_column) == value).one_or_none()
            if existing is not None:
                logger.info(
                    "Sync: customer %s from %s has the %s of customer %s; merged into it",
                    local_id,
                    self._terminal_id,
                    unique_column,
                    existing.id,
                )
                self._remember("customers", local_id, existing.id)
                return

        for column in ("synced", "last_modified", "current_debt"):
            values.pop(column, None)
        customer = Customer(**values, current_debt=Decimal("0.00"), synced=True)
        self._session.add(customer)
        self._session.flush()
        self._remember("customers", local_id, customer.id)
        self._inserted_customers.add(local_id)

    def _apply_customer_contact(self, local_id: int, values: dict[str, Any]) -> None:
        """Store a contact of a customer this batch has just stored new (#717).

        Contacts are part of the customer's details, so they follow the same
        rule: they arrive with the customer and are stored when the Main PC
        stores it. A re-sent customer (lost acknowledgement) or one matched to
        a customer the Main PC already had keeps the Main PC's contacts --
        which also keeps a re-send from adding them twice.
        """
        customer_ref = values.get("customer_id")
        if customer_ref is None or int(customer_ref) not in self._inserted_customers:
            logger.debug(
                "Sync: contact %s from %s is for a customer the Main PC already has; kept the Main PC's",
                local_id,
                self._terminal_id,
            )
            return
        values["customer_id"] = self._lookup("customers", int(customer_ref))
        self._session.add(CustomerContact(**values))

    # --- References to other till rows ---

    def _remap_references(self, table_name: str, model_class: type, local_id: int, values: dict[str, Any]) -> None:
        """Translate every till-row reference in ``values`` to its Main PC id, in place."""
        refs = dict(TERMINAL_REFS.get(table_name, {}))
        ledger_targets = LEDGER_REFS.get(table_name)
        if ledger_targets is not None and values.get("reference_id") is not None:
            target = ledger_targets.get(values.get("entry_type") or "")
            if target is None:
                # e.g. ADJUSTMENT: nothing on the Main PC to point at.
                values["reference_id"] = None
            else:
                refs["reference_id"] = target

        customer_ref = values.get("customer_id")
        if (
            table_name in _CUSTOMER_REF_TABLES
            and customer_ref is not None
            and int(customer_ref) in self._batch_customers
        ):
            server_customer = self._lookup("customers", int(customer_ref))
            if server_customer is None:
                raise PushApplyError(f"{table_name}[{local_id}]: customer {customer_ref} was not applied")
            values["customer_id"] = server_customer

        columns = model_class.__table__.c
        for column, space in refs.items():
            ref = values.get(column)
            if ref is None:
                continue
            server_id = self._resolve_reference(space, int(ref))
            if server_id is None:
                if not columns[column].nullable:
                    raise PushApplyError(f"{table_name}[{local_id}]: {column}={ref} is not a row this till has pushed")
                logger.warning(
                    "Sync: %s[%s] from %s: %s=%s is not a row this till has pushed; cleared",
                    table_name,
                    local_id,
                    self._terminal_id,
                    column,
                    ref,
                )
            values[column] = server_id

        for column in UNSYNCED_REFS.get(table_name, ()):
            if values.get(column) is not None:
                logger.info(
                    "Sync: %s[%s] from %s: %s refers to a till-only row; cleared on Main PC",
                    table_name,
                    local_id,
                    self._terminal_id,
                    column,
                )
                values[column] = None

    def _resolve_reference(self, space: str, local_id: int) -> int | None:
        """Return the Main PC id of this till's row ``local_id`` in ``space``, or None.

        Normally the row was pushed earlier (this batch or a previous one)
        and is in the map. A row pushed before the map existed sits on the
        Main PC under the till's own id; it is adopted only if the row there
        says it came from this till and isn't already another row's mapped
        target (which would make it a server-assigned id, not a legacy one).
        """
        server_id = self._lookup(space, local_id)
        if server_id is not None:
            return server_id

        origin = _ORIGIN_COLUMNS.get(space)
        if origin is None:
            return None
        table_name, origin_columns = origin
        row = self._session.get(get_model_for_table(table_name), local_id)
        if row is None:
            return None
        owner = next((getattr(row, c) for c in origin_columns if getattr(row, c)), None)
        if owner != self._terminal_id or self._is_claimed(space, local_id):
            return None
        self._remember(space, local_id, local_id)
        return local_id

    # --- Id map ---

    def _lookup(self, space: str, local_id: int) -> int | None:
        key = (space, local_id)
        if key in self._id_cache:
            return self._id_cache[key]
        server_id = (
            self._session.query(SyncIdMap.server_id)
            .filter_by(origin_terminal_id=self._terminal_id, table_name=space, local_id=local_id)
            .scalar()
        )
        if server_id is not None:
            self._id_cache[key] = server_id
        return server_id

    def _remember(self, space: str, local_id: int, server_id: int) -> None:
        self._session.add(
            SyncIdMap(origin_terminal_id=self._terminal_id, table_name=space, local_id=local_id, server_id=server_id)
        )
        self._session.flush()
        self._id_cache[(space, local_id)] = server_id

    def _is_claimed(self, space: str, server_id: int) -> bool:
        """True if ``server_id`` is already some till's mapped row (so not a pre-#671 row)."""
        return self._session.query(SyncIdMap.id).filter_by(table_name=space, server_id=server_id).first() is not None

    # --- Pre-#671 rows ---

    def _adopt_legacy_row(
        self, table_name: str, model_class: type, space: str, local_id: int, values: dict[str, Any]
    ) -> Any | None:
        """Find this row if it already reached the Main PC before the id map existed.

        Back then a pushed row was stored under the till's own id, with no
        map entry. A lost-response retry of such a push must not insert it
        a second time (a duplicate document number would even block the
        till's sync for good), nor re-apply a stock movement.

        Documents are recognised by their unique document number, and only
        if that number belongs to this same till. Any other row only if the
        Main PC row at the till's id is identical column for column -- a
        different till's row (or the Main PC's own) at that id differs.
        """
        if space == DOCUMENT_ID_SPACE:
            number = values.get("document_number")
            if not number:
                return None
            existing = self._session.query(Document).filter_by(document_number=number).one_or_none()
            if existing is None:
                return None
            owner = existing.origin_terminal_id or existing.terminal_id
            if owner != self._terminal_id or self._is_claimed(space, existing.id):
                raise PushApplyError(
                    f"{table_name}[{local_id}]: document number {number} already belongs to another document"
                )
            if values.get("type") and existing.type != values["type"]:
                raise PushApplyError(f"{table_name}[{local_id}]: document {number} is a {existing.type}")
            return existing

        row = self._session.get(model_class, local_id)
        if row is None or self._is_claimed(space, local_id):
            return None
        for key, value in values.items():
            if key == "synced":
                continue
            if getattr(row, key) != value:
                return None
        return row

    # --- Writes ---

    def _update(self, row: Any, table_name: str, values: dict[str, Any]) -> None:
        """Re-send of a row the Main PC already has: refresh it in place."""
        if table_name == "stock_movements":
            # Stock was moved when this movement was first stored; a movement
            # never changes on the till afterwards, so leave it untouched.
            if values.get("qty_change") is not None and values["qty_change"] != row.qty_change:
                logger.warning(
                    "Sync: re-sent stock movement %s from %s has a different qty (%s vs %s); kept the original",
                    row.id,
                    self._terminal_id,
                    values["qty_change"],
                    row.qty_change,
                )
            row.synced = True
            return

        columns = {c.key for c in sa_inspect(type(row)).columns}
        for key, value in values.items():
            if key == "id" or key not in columns:
                continue
            if key == "type" and getattr(row, "type", value) != value:
                raise PushApplyError(f"{table_name}: row {row.id} type {row.type} cannot become {value}")
            setattr(row, key, value)

    def _on_insert(self, table_name: str, instance: Any) -> None:
        """Side effects that belong to a row's first arrival only."""
        if table_name == "stock_movements":
            # The Main PC's Product.stock_qty is what every till later pulls,
            # so it must move with each till's movement -- once. This only
            # runs when the movement's map entry is created, so a re-send
            # (found through the map) can never apply it twice.
            product = self._session.get(Product, instance.product_id)
            if product is not None:
                # Product.version_id is an optimistic-lock column: a concurrent
                # update raises StaleDataError at flush/commit, which the sync
                # server retries with a fresh session.
                product.stock_qty += instance.qty_change
        elif table_name in _LEDGER_BALANCES:
            # Same for credit book / payables (#678) and loyalty points
            # (#716): the till moved its own figure together with this ledger
            # row, so the Main PC moves its copy by the same amount -- once,
            # on first arrival. An adjustment never takes a figure below zero
            # (as on the till).
            balance = _LEDGER_BALANCES[table_name]
            owner = self._session.get(balance.owner_model, getattr(instance, balance.owner_column))
            if owner is not None:
                figure = (getattr(owner, balance.balance_column) or 0) + getattr(instance, balance.amount_column)
                if instance.entry_type in ("ADJUSTMENT", "REVERSAL") and figure < 0:
                    figure = Decimal("0.00") if isinstance(figure, Decimal) else 0
                setattr(owner, balance.balance_column, figure)
