# Technical Design: Per-Unit Warranty Registration & Lifecycle Coupling (#822)

**Phase:** 9 · **Batch:** 9.2  
**Issue:** #822 (Warranty W2) · **Epic:** #820  
**Owner:** CB POS Remediation Team  
**Date:** 2026-11-12  
**Status:** APPROVED (Post-EGM Revisions Applied)  

---

## 1. Context & Objectives

In Batch 9.1 (#821, W1), CB POS established the data foundation for warranties: reusable `WarrantyPolicy` models, product and category inheritance rules, calendar-aware duration calculations, and feature gating.

**Batch 9.2 (#822, W2)** introduces the core transactional lifecycle for warranties:
1. **Per-Unit Warranty Registration**: When a covered product is sold at checkout, one `Warranty` row is created per integer unit sold, populated with immutable snapshots of terms, coverage dates, remedy, provider, and customer contact details.
2. **Sequential Code Allocation**: Unique human-readable warranty identifiers `<doc-number>-01..NN` generated from the full document number (including terminal prefix).
3. **Void Lifecycle Coupling**: When a sale is voided in `TransactionService.void_sale()`, all its `ACTIVE` warranties transition atomically to `VOID` with audit logging (suppressed when zero warranties exist).
4. **Partial/Full Refund Lifecycle Coupling**: When a sale is refunded in `RefundService.refund()`, warranties are cancelled per refunded unit (highest unit index first) with row locking, setting status to `CANCELLED` and linking `cancelled_by_sale_id`. Refusal guards fail closed if active units are insufficient on warranty lines, while non-warranty lines are skipped cleanly without false errors.
5. **Batched Resolution & Query Budget**: A sale without warranty items adds at most 1 query (batched policy resolution in the same session as `_fetch_composite_map`), with 0 N+1 queries.
6. **Whole-Unit Guard**: Products with warranty coverage sold with fractional quantities (`qty % 1 != 0`) are rejected at checkout before stock or payment mutations with translated error `errors.warranty_whole_units`.
7. **Eager Loading & Detached Safety**: `SaleItem.warranties` is declared with `lazy="selectin"`, initialized in-memory during checkout, and eager-loaded in `_load_receipt_relations` and `SaleQueryService` to guarantee detached printing and reprinting never trigger `DetachedInstanceError`.
8. **Multi-Terminal LAN Sync**: Bump protocol to `1.4`. `warranties` table is added to `TRANSACTION_TABLES`, `APPLY_ORDER`, `_TABLE_MODEL_MAP`, `_FLAT_PUSH_TABLES` (in `sync_client.py`), and remapped via `sync_id_map` with `origin_db_instance_id`.

---

## 2. Data Model & Schema Specifications

### 2.1 The `Warranty` Model (`warranties` table)

The `Warranty` model represents the legal warranty commitment made to a customer for a single physical unit of a covered product.

```python
class Warranty(Base):
    """A per-unit warranty issued upon sale of a covered product."""

    __tablename__ = "warranties"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(60), unique=True, index=True, nullable=False)
    unit_index: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # Foreign Keys (Restricted deletion to preserve transaction history)
    sale_id: Mapped[int] = mapped_column(ForeignKey("sales.id", ondelete="RESTRICT"), index=True, nullable=False)
    sale_item_id: Mapped[int] = mapped_column(
        ForeignKey("sale_items.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"), index=True, nullable=False)
    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("customers.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    policy_id: Mapped[int | None] = mapped_column(
        ForeignKey("warranty_policies.id", ondelete="RESTRICT"), nullable=True, index=True
    )

    # Customer Snapshots (walk-in customers may provide contact details without a Customer record)
    customer_name_snapshot: Mapped[str | None] = mapped_column(String(100), nullable=True)
    customer_phone_snapshot: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Serial Number (Reserved for W3 #823; nullable in W2)
    serial_number: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    # Policy Snapshots (Immutable capture of policy terms at the exact time of sale, CAA s.31(g))
    warranty_type: Mapped[str] = mapped_column(String(20), nullable=False)  # SHOP, MANUFACTURER, EXTENDED
    duration: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_unit: Mapped[str] = mapped_column(String(10), nullable=False)  # DAYS, MONTHS, YEARS
    remedy: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # REPAIR_OR_REPLACE, REPAIR_ONLY, REPLACE_ONLY, REFUND
    provider_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    terms_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    exclusions_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    lang: Mapped[str] = mapped_column(String(5), nullable=False, default="en")

    # Coverage Dates (Inclusive end date: valid until end_date 23:59:59)
    start_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    end_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    # Lifecycle Status: ACTIVE, VOID, CANCELLED, REPLACED, CLOSED
    # Note: EXPIRED is a derived property based on end_date < today
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE", index=True)

    # Lifecycle Links
    cancelled_by_sale_id: Mapped[int | None] = mapped_column(
        ForeignKey("sales.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    covers_warranty_id: Mapped[int | None] = mapped_column(
        ForeignKey("warranties.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    replaces_warranty_id: Mapped[int | None] = mapped_column(
        ForeignKey("warranties.id", ondelete="RESTRICT"), nullable=True, index=True
    )

    # Multi-terminal & Auditing
    terminal_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    synced: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, server_default=func.now(), nullable=False
    )
    last_modified: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, server_default=func.now(), onupdate=datetime.now, nullable=False, index=True
    )

    # Relationships
    sale: Mapped["Sale"] = relationship("Sale", foreign_keys=[sale_id], back_populates="warranties")
    sale_item: Mapped["SaleItem"] = relationship("SaleItem", foreign_keys=[sale_item_id], back_populates="warranties")
    product: Mapped["Product"] = relationship("Product", foreign_keys=[product_id])
    customer: Mapped[Optional["Customer"]] = relationship("Customer", foreign_keys=[customer_id])
    policy: Mapped[Optional["WarrantyPolicy"]] = relationship("WarrantyPolicy", foreign_keys=[policy_id])
    cancelled_by_sale: Mapped[Optional["Sale"]] = relationship("Sale", foreign_keys=[cancelled_by_sale_id])
    covered_warranty: Mapped[Optional["Warranty"]] = relationship(
        "Warranty", foreign_keys=[covers_warranty_id], remote_side=[id]
    )
    replaced_warranty: Mapped[Optional["Warranty"]] = relationship(
        "Warranty", foreign_keys=[replaces_warranty_id], remote_side=[id]
    )

    @property
    def is_expired(self) -> bool:
        """Derived property: return True if end_date has passed."""
        return date.today() > self.end_date
```

### 2.2 Table Constraints & Composite Indexes

```python
__table_args__ = (
    CheckConstraint("duration > 0", name="ck_warranties_duration"),
    CheckConstraint("duration_unit IN ('DAYS', 'MONTHS', 'YEARS')", name="ck_warranties_duration_unit"),
    CheckConstraint("warranty_type IN ('SHOP', 'MANUFACTURER', 'EXTENDED')", name="ck_warranties_warranty_type"),
    CheckConstraint(
        "remedy IN ('REPAIR_OR_REPLACE', 'REPAIR_ONLY', 'REPLACE_ONLY', 'REFUND')",
        name="ck_warranties_remedy",
    ),
    CheckConstraint(
        "status IN ('ACTIVE', 'VOID', 'CANCELLED', 'REPLACED', 'CLOSED')",
        name="ck_warranties_status",
    ),
    CheckConstraint("end_date >= start_date", name="ck_warranties_dates"),
    CheckConstraint("unit_index > 0", name="ck_warranties_unit_index"),
    Index("ix_warranties_sale_item_status_unit", "sale_item_id", "status", "unit_index"),
)
```

### 2.3 Relationships on Existing Models
- `SaleItem.warranties`: `Mapped[list["Warranty"]] = relationship("Warranty", back_populates="sale_item", lazy="selectin")`
- `Sale.warranties`: `Mapped[list["Warranty"]] = relationship("Warranty", foreign_keys="[Warranty.sale_id]", back_populates="sale", lazy="selectin")`

---

## 3. Centralized Domain Interface (`WarrantyService`)

`WarrantyService` is extended with four transactional methods:

```python
class WarrantyService:
    @classmethod
    def resolve_policies_for_products(
        cls,
        session: Session,
        product_ids: list[int],
    ) -> dict[int, WarrantyPolicy | None]:
        """Batched policy resolution for a list of product IDs.
        
        Performs 1 single query for Products, Categories, and WarrantyPolicies.
        Respects precedence: Product POLICY > Category default > Parent default.
        Respects Decision D30:
          - If prod.warranty_override == 'POLICY': check policy.is_active. If False, return None (no fallthrough).
          - If prod.warranty_override == 'INHERIT': inspect cat.default_warranty_policy_id.
            If present: check policy.is_active. If False, return None immediately (do NOT traverse to cat.parent_id).
            Only traverse up to cat.parent_id if default_warranty_policy_id is None.
        Weighted products (is_weighted == True) return None.
        Returns: {product_id: WarrantyPolicy | None}
        """

    @classmethod
    def register_for_sale_in_session(
        cls,
        session: Session,
        sale: Sale,
        sale_items_with_policies: list[tuple[SaleItem, WarrantyPolicy]],
        receipt_lang: str | None = None,
    ) -> list[Warranty]:
        """Create per-unit Warranty rows for sold lines in the current session.
        
        - Validates that qty is an exact integer.
        - Generates codes: <sale.document_number>-01..NN across all warranty units of the sale.
        - Sets unit_index per line (1..int(qty)).
        - Computes start_date = sale.date.date(), end_date = compute_end_date(...).
        - Snapshots terms/exclusions in the receipt language (falling back to English).
        - Snapshots customer name and phone.
        - Attaches created Warranty objects to sale_item.warranties in-memory.
        - Emits an atomic WARRANTY audit log entry if any warranties were created.
        """

    @classmethod
    def void_sale_warranties_in_session(
        cls,
        session: Session,
        sale_id: int,
        actor_id: int,
    ) -> int:
        """Atomically transition all ACTIVE warranties for sale_id to VOID.
        
        - Runs under the caller's sale row lock.
        - Updates status to 'VOID' and updates last_modified.
        - Emits an atomic WARRANTY audit log entry ONLY when count > 0 (suppresses noise for non-warranty sales).
        - Returns the number of warranties voided.
        """

    @classmethod
    def cancel_units_for_refund_in_session(
        cls,
        session: Session,
        refund_sale: Sale,
        refund_lines: list[tuple[int, Decimal]],  # (sale_item_id, qty)
        actor_id: int,
    ) -> list[Warranty]:
        """Cancel ACTIVE warranties per refunded line item (highest unit_index first).
        
        - For each refunded line item (sale_item_id, qty):
          1. Query count of total warranties issued for sale_item_id:
             total_warranties = session.scalar(select(func.count(Warranty.id)).where(Warranty.sale_item_id == sale_item_id))
          2. If total_warranties == 0: cleanly skip (non-warranty line item).
          3. If total_warranties > 0:
             - Validate integer quantity (qty % 1 == 0).
             - Query active warranties with row locking (with_for_update, order_by(unit_index.desc())).
             - If len(active_warranties) < int(qty): FAIL CLOSED with ValueError("insufficient_active_warranties").
             - Cancel the first int(qty) units (highest unit_index): status = 'CANCELLED', cancelled_by_sale_id = refund_sale.id.
        - Emits an atomic WARRANTY audit log entry if any warranties were cancelled.
        - Returns list of cancelled Warranty records.
        """
```

---

## 4. Transaction Boundaries & Integration Seams

```
  +-------------------------------------------------------------------------------+
  |                        complete_sale() / _execute_sale()                      |
  | 1. Batched policy resolution (1 query via resolve_policies_for_products)      |
  | 2. Whole-unit validation: if policy exists and qty % 1 != 0 -> raise error   |
  | 3. Create Sale, SalePayment records                                           |
  | 4. _write_sale_lines() -> creates SaleItem rows, returns list[SaleItem]       |
  | 5. session.flush() -> populates db-assigned sale_item.id                      |
  | 6. WarrantyService.register_for_sale_in_session() -> create Warranty rows     |
  |    (also appends to sale_item.warranties in memory)                           |
  | 7. _load_receipt_relations() -> touch item.warranties for detached printing    |
  | 8. Commit transaction atomically                                              |
  +-------------------------------------------------------------------------------+

  +-------------------------------------------------------------------------------+
  |                              void_sale()                                      |
  | 1. Lock Sale row (with_for_update=True)                                       |
  | 2. Reverse stock, reverse customer credit, reverse loyalty                    |
  | 3. WarrantyService.void_sale_warranties_in_session()                          |
  |    -> UPDATE warranties SET status='VOID' WHERE sale_id=X AND status='ACTIVE' |
  |    -> Emits audit log only if count > 0                                       |
  | 4. Commit transaction atomically                                              |
  +-------------------------------------------------------------------------------+

  +-------------------------------------------------------------------------------+
  |                          RefundService.refund()                               |
  | 1. Lock original Sale row (with_for_update=True)                              |
  | 2. Create refund Sale (RETURN), refund SaleItem rows                          |
  | 3. Reverse stock, reverse credit, adjust loyalty                              |
  | 4. WarrantyService.cancel_units_for_refund_in_session()                       |
  |    -> Skips non-warranty items (total_warranties == 0)                        |
  |    -> Lock active warranties for each covered line                            |
  |    -> Pick highest unit_index units                                           |
  |    -> Fail closed if active count < refund qty                                |
  |    -> UPDATE warranties SET status='CANCELLED', cancelled_by_sale_id=Y        |
  | 5. Commit transaction atomically                                              |
  +-------------------------------------------------------------------------------+
```

### 4.1 Whole-Unit Guard (`errors.warranty_whole_units`)
In `TransactionService._execute_sale`:
Before stock reservation or payment processing:
```python
if WarrantyService.is_enabled(session=session):
    product_ids = [item["product"].id for item in cart_items]
    policy_map = WarrantyService.resolve_policies_for_products(session, product_ids)
    for item in cart_items:
        p_id = item["product"].id
        if policy_map.get(p_id) is not None:
            qty = item["qty"]
            if qty <= Decimal("0") or qty % Decimal("1") != Decimal("0"):
                from cbpos.i18n import _t

                raise ValueError(
                    _t("errors.warranty_whole_units", default="Warranty items must be sold in whole units")
                )
```
Translations added to `en.json`, `si.json`, `ta.json`:
- `en`: "Warranty items must be sold in whole units"
- `si`: "වගකීම් සහිත භාණ්ඩ සම්පූර්ණ ඒකක වලින් පමණක් විකිණිය යුතුය"
- `ta`: "உத்தரவாதப் பொருட்கள் முழு அலகுகளாக மட்டுமே වிற்கப்பட வேண்டும்"

### 4.2 Code Generation Algorithm: `global_seq` vs `unit_index`
- `global_seq`: Monotonically increasing counter (1..N) across all warranty units of the entire sale document, used to format code `<sale.document_number>-<global_seq:02d>`.
- `unit_index`: 1-based index (1..int(qty)) per `SaleItem`, used to order units within a line item for partial refunds.

Example for a sale `INV-2026-00412` containing Line 1 (2 Laptops) and Line 2 (1 Phone):
- Line 1:
  - Unit 1: code `INV-2026-00412-01`, `unit_index = 1`
  - Unit 2: code `INV-2026-00412-02`, `unit_index = 2`
- Line 2:
  - Unit 1: code `INV-2026-00412-03`, `unit_index = 1`

### 4.3 Concurrent Partial Refunds & Row Locking
To prevent race conditions during concurrent partial refunds of the same sale:
1. `RefundService.refund()` locks the original `Sale` record via `session.get(Sale, sale_id, with_for_update=True)`.
2. `cancel_units_for_refund_in_session()` issues `SELECT ... FROM warranties WHERE sale_item_id = :id AND status = 'ACTIVE' ORDER BY unit_index DESC WITH FOR UPDATE`.
3. If two concurrent transactions attempt to refund 2 units of a 3-unit sale, the second transaction waits for the first to commit, then observes only 1 active unit remaining, and fails closed with `ValueError` rather than over-cancelling.

### 4.4 Receipt Reprints & Detached Safety (`SaleQueryService`)
In `SaleQueryService.get_last_sale()` and `get_sale_details()`:
Add `selectinload(Sale.items).selectinload(SaleItem.warranties)` to the query options and touch `_ = it.warranties` before `session.expunge_all()`. This guarantees that historical receipt reprinting from the sale history dialog never encounters `DetachedInstanceError`.

---

## 5. Decision D30 Adherence (Inactive Policy Resolution)

Under Decision D30:
1. When resolving coverage for checkout:
   - If a product has explicit `override == "POLICY"` pointing to an inactive policy, it produces **no coverage** (`None`).
   - It **never falls through** to a category default policy or parent category policy.
   - If a product has `override == "INHERIT"`, inspect `cat.default_warranty_policy_id`. If set, inspect that policy. If it is inactive, return **no coverage** (`None`) immediately; it does **not fall through** to any parent or grandparent category.
2. The inactive assignment remains intact on the `Product` or `Category` record.
3. No cashier warning or manager override prompt is displayed (W2 keeps POS workflow uninterrupted).

---

## 6. LAN Sync Protocol 1.4

1. Bump `SYNC_PROTOCOL_VERSION = "1.4"` in `cbpos/core/services/sync_protocol.py`.
2. Add `"warranties"` to `TRANSACTION_TABLES` (placed after `"sale_payments"`).
3. Add `"warranties": Warranty` to `_TABLE_MODEL_MAP` in `get_table_model_map()`.
4. In `cbpos/infrastructure/sync_client.py`:
   - Add `("warranties", Warranty)` to `_FLAT_PUSH_TABLES`.
   - Till push loop automatically queries unsynced warranties, serializes them via `model_to_dict`, tracks fingerprints, and marks them `synced = True` on server acknowledgement.
5. In `cbpos/core/services/sync_apply_service.py`:
   - Add `"warranties"` to `APPLY_ORDER` (after `"sale_items"` and `"sale_payments"`).
   - Add foreign key remapping to `TERMINAL_REFS`:
     ```python
     "warranties": {
         "sale_id": DOCUMENT_ID_SPACE,
         "sale_item_id": "sale_items",
         "cancelled_by_sale_id": DOCUMENT_ID_SPACE,
         "covers_warranty_id": "warranties",
         "replaces_warranty_id": "warranties",
     }
     ```
   - Add `"warranties"` to `_CUSTOMER_REF_TABLES` so `customer_id` is remapped if the customer was created on the till in the same push batch.

---

## 7. Alembic Migration (`alembic/versions/<hash>_add_warranties_table.py`)

- `down_revision = "e1f2a3b4c5d6"`
- Safe execution in SQLite batch mode:
  - Uses `op.create_table("warranties", ...)` with check constraints and foreign keys.
  - Creates indexes on `code` (unique), `sale_id`, `sale_item_id`, `product_id`, `customer_id`, `status`, `start_date`, `end_date`, `last_modified`, and composite `ix_warranties_sale_item_status_unit`.
- Clean downgrade dropping table and indexes.

---

## 8. Test Matrix (TDD Before Implementation)

| # | Test Scenario | File | Expected Behavior |
|---|---|---|---|
| 1 | 3 covered units sold | `tests/domain/test_warranty_service.py` | 3 `ACTIVE` rows created with `-01..-03`, unit_index 1..3, start/end dates |
| 2 | Immutability snapshot | `tests/domain/test_warranty_service.py` | Subsequent edits to `WarrantyPolicy` or `Customer` do not alter warranty rows |
| 3 | Non-warranty product sale | `tests/domain/test_warranty_service.py` | 0 warranty rows created; max 1 query added to sale |
| 4 | Inactive policy assignment (D30) | `tests/domain/test_warranty_service.py` | 0 warranty rows created; no category fallthrough |
| 5 | Feature flag disabled | `tests/domain/test_warranty_service.py` | `warranty_enabled=False` produces 0 rows and 0 side effects |
| 6 | Fractional quantity rejection | `tests/domain/test_warranty_service.py` | Covered item sold with 1.5 raises `errors.warranty_whole_units`; rollback |
| 7 | Composite item coverage | `tests/domain/test_warranty_service.py` | Follows parent policy only; component items produce no warranties |
| 8 | Injected sale failure rollback | `tests/domain/test_warranty_service.py` | Payment failure rolls back all warranty rows atomically |
| 9 | Sale void transition | `tests/domain/test_warranty_service.py` | `void_sale()` transitions ACTIVE warranties to VOID with audit log |
| 10 | Injected void failure | `tests/domain/test_warranty_service.py` | Failure during void rolls back; warranties remain ACTIVE |
| 11 | Single-unit partial refund | `tests/domain/test_warranty_service.py` | 1 of 3 units refunded cancels unit 3 (highest index); 1 & 2 stay ACTIVE |
| 12 | Second partial refund | `tests/domain/test_warranty_service.py` | Subsequent refund cancels unit 2; unit 1 stays ACTIVE |
| 13 | Full refund cancellation | `tests/domain/test_warranty_service.py` | Full refund sets all units to CANCELLED with `cancelled_by_sale_id` |
| 14 | Injected refund failure | `tests/domain/test_warranty_service.py` | Refund failure rolls back; all warranties remain ACTIVE |
| 15 | Over-refund / insufficient active | `tests/domain/test_warranty_service.py` | Attempting to refund more units than active fails closed |
| 16 | Non-warranty refund cleanly skips | `tests/domain/test_warranty_service.py` | Refunding items without warranties succeeds without error |
| 17 | Receipt eager-loading & detached safety | `tests/guardrails/test_warranty_guardrails.py` | Detached `sale.items[0].warranties` access does not raise DetachedInstanceError |
| 18 | Two-machine LAN sync | `tests/integration/test_sync_warranty.py` | Till sale with warranties syncs to Main PC with remapped IDs without collision |
