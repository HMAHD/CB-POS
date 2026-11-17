# Technical Design: Warranty Lookup & Claims Workflow (#825, #826)

**Phase:** 9 · **Batch:** 9.4  
**Issues:** #825 (Warranty W5: Lookup & Correction), #826 (Warranty W6: Claims Intake & Lifecycle) · **Epic:** #820  
**Owner:** CB POS Remediation Team  
**Date:** 2026-11-17  
**Status:** APPROVED (Post-EGM Revisions Applied)  

---

## 1. Context & Objectives

In Phase 9 Batches 9.1–9.3 (#821, #822, #823, #824), CB POS established:
1. Reusable `WarrantyPolicy` models, product/category assignment precedence, calendar-aware duration arithmetic, and feature gating.
2. Per-unit `Warranty` registration at checkout (`<doc_number>-01..NN`), whole-unit validation, void/refund cascades with per-unit cancellation, and LAN sync protocol 1.4.
3. Checkout serial/IMEI capture, cart serial bookkeeping, held bill persistence, and customer-facing delivery (thermal receipt warranty blocks, A4 invoice lines, and standalone thermal/PDF warranty cards).

**Batch 9.4 (#825, #826)** implements the core post-sale operational workflows:
- **Issue #825 (W5)**: High-speed counter warranty lookup by barcode scan (receipt or warranty card), serial/IMEI, customer phone, or customer name, with live coverage status calculations and permission-controlled admin corrections with audit logs.
- **Issue #826 (W6)**: Complete warranty claims lifecycle: intake ticket creation with terminal-scoped document numbering (`WC-{Y}-{seq:05d}`), coverage auto-detection, strict state-machine transitions, thermal intake/collection slip printing, claims board master-detail UI, and refund/void blocking on open claims.

---

## 2. Issue #825: Warranty Lookup & Correction

### 2.1 Search Architecture & Precedence

When a customer brings a faulty device to the counter, cashiers need immediate resolution. `WarrantyService.search(query, limit=200, today=None) -> list[WarrantyDTO]` executes a unified search algorithm matching criteria in strict priority order:

1. **Warranty Code Match (Priority 1)**:
   - Scanned from standalone warranty card barcode (`<doc_number>-01..NN`).
   - Exact case-insensitive match on `Warranty.code`.
2. **Receipt Document Number (Priority 2)**:
   - Scanned from thermal receipt barcode or tax invoice.
   - Matches `Sale.document_number == query.strip()`. Returns all warranties tied to the sale, ordered by `unit_index`.
3. **Serial / IMEI Match (Priority 3)**:
   - Scanned from device or box.
   - Exact match on `Warranty.serial_number == query.strip().upper()`.
   - Suffix match: If query length >= 6 characters, matches `Warranty.serial_number.endswith(query.strip().upper())`.
4. **Customer Phone Match (Priority 4)**:
   - Normalizes input phone to standard Sri Lankan variants (removing spaces, dashes, leading zeroes, country code `+94`).
   - Matches against `Customer.phone` and `Warranty.customer_phone_snapshot`.
5. **Customer Name Match (Priority 5)**:
   - Substring match on `Customer.name.ilike(f"%{query.strip()}%")` and `Warranty.customer_name_snapshot.ilike(...)`.

**Performance Guarantee:**
- Queries use existing composite indexes (`ix_warranties_serial_status`, `ix_warranties_sale_id`, `ix_warranties_code`). Suffix matches on serials apply only when `len(query) >= 6`.
- Search execution time is bounded under 25ms and results are capped at 200 items.

### 2.2 Effective Status Derivation

The database status (`Warranty.status`) records lifecycle state (`ACTIVE`, `VOID`, `CANCELLED`, `REPLACED`, `EXPIRED`). At lookup time, `effective_status` is dynamically calculated against `today` (defaulting to current local date):
- If `status != "ACTIVE"`: returns stored status (`VOID`, `CANCELLED`, `REPLACED`, `EXPIRED`).
- If `status == "ACTIVE"`:
  - If `today > end_date`: returns `EXPIRED`.
  - If `0 <= (end_date - today).days <= 30`: returns `EXPIRING` (with `days_remaining = (end_date - today).days`).
  - Otherwise: returns `ACTIVE` (with `days_remaining = (end_date - today).days`).

### 2.3 Data Transfer Objects (`WarrantyDTO`)

To prevent `DetachedInstanceError` and enforce Rule 1 ("UI never touches DB"), all service methods return immutable dataclasses (`cbpos/core/services/warranty_dto.py`):

```python
@dataclass(frozen=True)
class WarrantyDTO:
    id: int
    code: str
    serial_number: str | None
    product_id: int
    product_name: str
    customer_id: int | None
    customer_name: str | None
    customer_phone: str | None
    sale_id: int
    sale_document_number: str
    sold_date: datetime
    start_date: date
    end_date: date
    duration: int
    duration_unit: str
    warranty_type: str
    remedy: str
    terms_snapshot: str | None
    exclusions_snapshot: str | None
    status: str
    effective_status: str
    days_remaining: int
    has_active_claim: bool
    active_claim_id: int | None
```

### 2.4 Admin Correction & Audit Trail

Staff with `Permissions.WARRANTY_EDIT` may correct administrative data on an existing warranty:
- Service method: `WarrantyService.update_warranty_admin(warranty_id: int, user_id: int, reason: str, serial_number: str | None = None, start_date: date | None = None, end_date: date | None = None, session: Session | None = None) -> WarrantyDTO`
- Guardrails:
  - Caller must have `Permissions.WARRANTY_EDIT`; otherwise raises `PermissionError("permission_denied")`.
  - Mandatory reason parameter: non-empty string required, otherwise raises `ValueError("reason_required")`.
  - Cannot correct `VOID` or `CANCELLED` warranties.
  - Re-validates that `start_date <= end_date`.
  - Logs an `AuditLog` row:
    - `action = "WARRANTY_CORRECTION"`
    - `event_type = WARRANTY_EVENT`
    - `details` contains JSON payload of before/after field values and the cashier's mandatory reason.

### 2.5 Lookup UI (`WarrantyLookupDialog`)

- **Class**: `cbpos/ui/dialogs/warranty_lookup_dialog.py::WarrantyLookupDialog`
- **Object Name**: `#WarrantyLookupDialog`
- **Features**:
  - Sets `self.accepts_scans = True` and implements `process_barcode_external(barcode)` so hardware scanners route directly into the search input.
  - Search input debounced at 300ms for manual typing; Enter/scanner immediately initiates lookup.
  - Left pane: Search bar, quick filter chips (All, Active, Expiring, Expired, Void/Cancelled), results table with columns: Product, Serial/IMEI, Customer, Sold Date, Valid Until, Status Chip.
  - Right detail pane:
    - Placeholder empty state displayed when no row is selected.
    - When selected:
      - Header: Product name, warranty code, status chip (Theme-aware: `success` for Active, `warning` for Expiring, `danger` for Void/Cancelled, `muted` for Expired).
      - Metadata grid: Sold Date, Coverage Period, End Date, Customer snapshot, Store receipt link.
      - Policy Terms & Conditions snapshot card.
      - Linked Claims History table (from #826).
      - Admin Correction button (opens `WarrantyCorrectionDialog` if authorized).
      - Footer Actions:
        - "Start Claim" (`btn_start_claim`): opens `WarrantyClaimDialog(warranty_id=w.id)` (Issue #826).
        - "Reprint Warranty Card" (`btn_reprint`): dispatches `WarrantyReprintWorker`.
        - "View Sale" (`btn_view_sale`): opens `SaleHistoryDialog` focused on the underlying transaction.
        - "Close" (`btn_close`).

---

## 3. Issue #826: Warranty Claims Workflow

### 3.1 Data Architecture

Claims are first-class business documents inheriting from `Document` via Joined-Table Inheritance (JTI). `synced` is inherited directly from `Document` (no child duplicate column):

```python
class WarrantyClaim(Document):
    __tablename__ = "warranty_claims"

    id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True)
    warranty_id: Mapped[int | None] = mapped_column(
        ForeignKey("warranties.id", ondelete="SET NULL"), nullable=True, index=True
    )
    claim_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="RECEIVED", index=True
    )  # RECEIVED, INSPECTING, AT_SUPPLIER, READY, COLLECTED, REJECTED, VOID, CANCELLED
    coverage_type: Mapped[str] = mapped_column(String(30), nullable=False)  # IN_WARRANTY, OUT_OF_WARRANTY
    fault_description: Mapped[str] = mapped_column(Text, nullable=False)
    accessories_received: Mapped[str | None] = mapped_column(Text, nullable=True)
    item_condition: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_ready_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    resolution: Mapped[str | None] = mapped_column(
        String(30), nullable=True
    )  # REPAIRED, REPLACED, REFUNDED, REJECTED, CANCELLED
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    charge_to_customer: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    cost_to_shop: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    repair_sale_id: Mapped[int | None] = mapped_column(ForeignKey("sales.id", ondelete="SET NULL"), nullable=True)
    collected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    collected_by_name: Mapped[str | None] = mapped_column(String(100), nullable=True)

    warranty: Mapped["Warranty | None"] = relationship("Warranty", backref="claims")
    events: Mapped[list["WarrantyClaimEvent"]] = relationship(
        "WarrantyClaimEvent",
        backref="claim",
        cascade="all, delete-orphan",
        order_by="WarrantyClaimEvent.created_at.asc()",
    )

    __mapper_args__ = {"polymorphic_identity": "warranty_claim"}
```

Timeline tracking:
```python
class WarrantyClaimEvent(Base):
    __tablename__ = "warranty_claim_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    claim_id: Mapped[int] = mapped_column(
        ForeignKey("warranty_claims.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # CREATED, STATUS_CHANGE, RESOLVED, COLLECTED, VOIDED
    from_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    to_status: Mapped[str] = mapped_column(String(30), nullable=False)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    synced: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)

    user: Mapped["User | None"] = relationship("User")
```

### 3.2 Document Numbering & Scoping

- Document type key: `DocumentType.WARRANTY_CLAIM = "warranty_claim"`.
- In `cbpos/core/services/document_service.py`:
  - `PREFIXES["WARRANTY_CLAIM"] = "WC"`
  - `DEFAULT_PATTERNS["WARRANTY_CLAIM"] = "WC-{Y}-{seq:05d}"`
  - `_TERMINAL_SCOPED_TYPES.add("WARRANTY_CLAIM")`
- Generation: `DocumentService.generate_number(session, "WARRANTY_CLAIM", terminal_id)` creates numbers terminal-scoped (e.g. `TERM01-WC-2026-00001`).

### 3.3 State Machine & Transitions

The allowed transition graph is strictly enforced by `WarrantyClaimService`:

```
                 ┌──────────────┐
                 │   RECEIVED   │
                 └──────┬───────┘
                        │
                        ▼
                 ┌──────────────┐
     ┌──────────►│  INSPECTING  │──────────────┐
     │           └──────┬───────┘              │
     │                  │                      │
┌────┴─────────┐        │        ┌─────────────▼──────┐
│ AT_SUPPLIER  │◄───────┘        │      REJECTED      │
└──────────────┘                 │ (requires reason)  │
        │                        └────────────────────┘
        ▼                                  ▲
 ┌─────────────┐                           │
 │    READY    │───────────────────────────┘
 └──────┬──────┘
        │
        ▼
 ┌─────────────┐
 │  COLLECTED  │
 └─────────────┘
```

- Allowed forward paths:
  - `RECEIVED -> INSPECTING`
  - `INSPECTING -> READY`
  - `INSPECTING -> AT_SUPPLIER`
  - `AT_SUPPLIER -> INSPECTING` or `READY`
  - `READY -> COLLECTED`
- Rejection path:
  - Any non-final state (`RECEIVED`, `INSPECTING`, `AT_SUPPLIER`, `READY`) can transition to `REJECTED`.
  - Transition to `REJECTED` strictly requires a non-empty `rejection_reason`.
- Voiding:
  - A claim can be `VOID`ed by authorized staff with `Permissions.WARRANTY_CLAIM_RESOLVE` and a mandatory reason. Both `Document.status` and `WarrantyClaim.claim_status` are set to `"VOID"`.

### 3.4 Invariants & Guards

1. **One Open Claim Rule**:
   - A warranty unit can have at most **one** active claim (`claim_status NOT IN ('COLLECTED', 'REJECTED', 'VOID', 'CANCELLED')`).
   - SQLite: Enforced by `WarrantyClaimService.create_claim()` in a serialized transaction check.
   - PostgreSQL: Enforced by partial unique index directly on `warranty_claims` columns:
     ```sql
     CREATE UNIQUE INDEX uq_warranty_active_claim 
     ON warranty_claims (warranty_id) 
     WHERE claim_status NOT IN ('COLLECTED', 'REJECTED', 'VOID', 'CANCELLED') AND warranty_id IS NOT NULL;
     ```
2. **Refund & Void Guards**:
   - In `RefundService.refund()`: before refunding any sale item or specific warranty unit, check `WarrantyClaimService.get_active_claim_for_warranty(w.id)`. If an active claim exists on any refunded unit:
     - If the refund is a normal customer return: fail closed with `ValueError("cannot_refund_unit_with_open_claim")`.
     - Exception for claim refund resolution: If caller passes `claim_id: int` matching the active claim with `resolution == "REFUNDED"`, the refund proceeds and atomically sets the claim to `COLLECTED` with `resolution_notes = "Refund issued in credit note <doc_number>"`.
   - In `WarrantyService.void_sale_warranties_in_session()`: query `get_active_claim_for_warranty()`. If any warranty on the voided sale has an active claim, fail closed with `ValueError("cannot_void_sale_with_open_claim")`.
3. **Coverage Auto-Detection**:
   - At claim creation, if linked to a `Warranty`, check `WarrantyService.get_effective_status(w, intake_date)`.
   - If `ACTIVE` or `EXPIRING`: `coverage_type = "IN_WARRANTY"`.
   - If `EXPIRED`: `coverage_type = "OUT_OF_WARRANTY"`.
   - Cashiers can manually toggle out-of-warranty, but setting in-warranty on an expired item requires `Permissions.WARRANTY_CLAIM_RESOLVE`.

### 3.5 Financial Workflow & Replacement Stock

- In Phase 9.4 (#826), `charge_to_customer` and `cost_to_shop` are tracked on the claim for repair/service fees.
- When `charge_to_customer > 0`, the fee is collected at POS checkout by selling a "Repair service" item, which records `repair_sale_id` on the claim. If marked `COLLECTED` without a `repair_sale_id`, a warning prompt is presented to confirm collection without linked sale payment.
- Stock movements for replacement units are formally governed in Phase 9.5 (W7 #827); Phase 9.4 allows recording `resolution = "REPLACED"` and logging it for technician tracking.

### 3.6 Data Transfer Objects & Service API

```python
@dataclass(frozen=True)
class WarrantyClaimEventDTO:
    id: int
    claim_id: int
    event_type: str
    from_status: str | None
    to_status: str
    user_id: int | None
    username: str
    created_at: datetime
    notes: str | None


@dataclass(frozen=True)
class WarrantyClaimDTO:
    id: int
    document_number: str
    date: datetime
    claim_status: str
    coverage_type: str
    warranty_id: int | None
    warranty_code: str | None
    product_name: str
    serial_number: str | None
    customer_name: str | None
    customer_phone: str | None
    fault_description: str
    accessories_received: str | None
    item_condition: str | None
    expected_ready_date: date | None
    resolution: str | None
    resolution_notes: str | None
    rejection_reason: str | None
    charge_to_customer: Decimal
    cost_to_shop: Decimal
    repair_sale_id: int | None
    collected_at: datetime | None
    collected_by_name: str | None
    events: list[WarrantyClaimEventDTO]
```

**`WarrantyClaimService` Public Interface:**
```python
class WarrantyClaimService:
    @classmethod
    def create_claim(
        cls,
        warranty_id: int | None,
        fault_description: str,
        user_id: int,
        accessories: str | None = None,
        condition: str | None = None,
        expected_ready_date: date | None = None,
        coverage_type: str | None = None,
        manual_product_name: str | None = None,
        manual_serial: str | None = None,
        manual_customer_name: str | None = None,
        manual_customer_phone: str | None = None,
        terminal_id: str | None = None,
        session: Session | None = None,
    ) -> WarrantyClaimDTO: ...

    @classmethod
    def transition_status(
        cls,
        claim_id: int,
        to_status: str,
        user_id: int,
        notes: str | None = None,
        session: Session | None = None,
    ) -> WarrantyClaimDTO: ...

    @classmethod
    def resolve_claim(
        cls,
        claim_id: int,
        resolution: str,
        user_id: int,
        notes: str | None = None,
        charge_to_customer: Decimal = Decimal("0.00"),
        cost_to_shop: Decimal = Decimal("0.00"),
        session: Session | None = None,
    ) -> WarrantyClaimDTO: ...

    @classmethod
    def reject_claim(
        cls,
        claim_id: int,
        reason: str,
        user_id: int,
        session: Session | None = None,
    ) -> WarrantyClaimDTO: ...

    @classmethod
    def mark_collected(
        cls,
        claim_id: int,
        collected_by_name: str,
        user_id: int,
        notes: str | None = None,
        session: Session | None = None,
    ) -> WarrantyClaimDTO: ...

    @classmethod
    def void_claim(
        cls,
        claim_id: int,
        reason: str,
        user_id: int,
        session: Session | None = None,
    ) -> WarrantyClaimDTO: ...

    @classmethod
    def get_active_claim_for_warranty(
        cls,
        warranty_id: int,
        session: Session | None = None,
    ) -> WarrantyClaim | None: ...

    @classmethod
    def list_claims(
        cls,
        status: str | None = None,
        search: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int = 200,
    ) -> list[WarrantyClaimDTO]: ...

    @classmethod
    def get_claim(cls, claim_id: int) -> WarrantyClaimDTO | None: ...
```

### 3.7 Thermal Slips & Asynchronous Printing (Rule 6)

- **Claim Intake Slip**:
  - `WarrantyClaimReceiptBuilder.build_intake_slip(claim: WarrantyClaimDTO, config_override=None) -> list[dict[str, Any]]`.
  - Dispatched via background thread or `PrintWorker.instance().add_job("print_commands", commands)`.
  - Contents: CB POS branding, shop metadata, claim document number (`WC-...`), date/time, customer snapshot, item details, fault description, expected completion date, CODE128 barcode of claim number via `choose_barcode`, configurable retention terms block.
- **Collection Slip**:
  - `WarrantyClaimReceiptBuilder.build_collection_slip(claim: WarrantyClaimDTO, config_override=None) -> list[dict[str, Any]]`.
  - Contents: Claim reference, resolution details, collected timestamp, customer signature line.

### 3.8 Claims Board UI

- **Location**: Management → Warranty & Repairs → "Claims" subtab.
- **Master-Detail Layout**:
  - Filter bar: Status tabs (`All`, `Received`, `Inspecting`, `At Supplier`, `Ready`, `Collected`, `Rejected`), date range filter, search box (claim number, customer, serial, product).
  - Left table: Claim #, Date, Customer, Product, Serial, Coverage Chip, Status Chip.
  - Right detail view:
    - Empty state displayed when no row selected.
    - Header with big document number and status badge.
    - Fault description, accessories, item condition.
    - Expected ready date.
    - Vertical timeline widget (`ClaimTimelineWidget`) displaying all `WarrantyClaimEventDTO` entries.
    - Action buttons based on current state (e.g. "Begin Inspection", "Send to Supplier", "Mark Ready", "Mark Collected", "Reject Claim", "Print Intake Slip").

---

## 4. Permissions & Gating

### 4.1 Permission Definitions
- `Permissions.WARRANTY_VIEW = "warranty.view"`: View warranties, search lookup, view claim history.
- `Permissions.WARRANTY_EDIT = "warranty.edit"`: Edit serial numbers, start/end dates with mandatory reason.
- `Permissions.WARRANTY_CLAIM_CREATE = "warranty.claim_create"`: Open claims, record intake notes, update status to inspecting/ready.
- `Permissions.WARRANTY_CLAIM_RESOLVE = "warranty.claim_resolve"`: Resolve, reject, or void claims, override coverage.

### 4.2 Role Seeds & Guardrails
- **Admin**: All permissions.
- **Manager**: All permissions.
- **Cashier**: `warranty.view` + `warranty.claim_create`.
- Seeded via Alembic data migration and `cbpos/core/database_setup_service.py`.

---

## 5. Sync & Migrations

### 5.1 Alembic Migration
File: `alembic/versions/<revision>_add_warranty_claims.py`:
1. Creates table `warranty_claims`:
   - `id`: Integer, ForeignKey(`documents.id`, ondelete="CASCADE"), primary key.
   - `warranty_id`: Integer, ForeignKey(`warranties.id`, ondelete="SET NULL"), nullable=True, index=True.
   - `claim_status`: String(30), nullable=False, default="RECEIVED", index=True.
   - `coverage_type`: String(30), nullable=False.
   - `fault_description`: Text, nullable=False.
   - `accessories_received`: Text, nullable=True.
   - `item_condition`: Text, nullable=True.
   - `expected_ready_date`: Date, nullable=True.
   - `resolution`: String(30), nullable=True.
   - `resolution_notes`: Text, nullable=True.
   - `rejection_reason`: Text, nullable=True.
   - `charge_to_customer`: Numeric(12, 2), nullable=False, default=0.
   - `cost_to_shop`: Numeric(12, 2), nullable=False, default=0.
   - `repair_sale_id`: Integer, ForeignKey(`sales.id`, ondelete="SET NULL"), nullable=True.
   - `collected_at`: DateTime, nullable=True.
   - `collected_by_name`: String(100), nullable=True.
2. Creates partial unique index:
   ```sql
   CREATE UNIQUE INDEX uq_warranty_active_claim 
   ON warranty_claims (warranty_id) 
   WHERE claim_status NOT IN ('COLLECTED', 'REJECTED', 'VOID', 'CANCELLED') AND warranty_id IS NOT NULL;
   ```
3. Creates table `warranty_claim_events`:
   - `id`: Integer, primary key.
   - `claim_id`: Integer, ForeignKey(`warranty_claims.id`, ondelete="CASCADE"), nullable=False, index=True.
   - `event_type`: String(30), nullable=False.
   - `from_status`: String(30), nullable=True.
   - `to_status`: String(30), nullable=False.
   - `user_id`: Integer, ForeignKey(`users.id`, ondelete="SET NULL"), nullable=True.
   - `created_at`: DateTime, nullable=False.
   - `notes`: Text, nullable=True.
   - `synced`: Boolean, nullable=False, default=False, index=True.
4. Seeds permissions:
   - Inserts `Permissions.WARRANTY_CLAIM_CREATE` and `Permissions.WARRANTY_CLAIM_RESOLVE` into `permissions` table.
   - Binds `WARRANTY_CLAIM_CREATE` and `WARRANTY_CLAIM_RESOLVE` to Admin and Manager roles; binds `WARRANTY_CLAIM_CREATE` to Cashier role.

### 5.2 Multi-Terminal LAN Sync (Protocol 1.5)
- Bump `SYNC_PROTOCOL_VERSION = "1.5"`.
- In `sync_protocol.py` & `sync_apply_service.py`:
  - `TRANSACTION_TABLES`: include `"warranty_claims"` and `"warranty_claim_events"`.
  - `APPLY_ORDER`: add `documents` -> `warranty_claims` -> `warranty_claim_events`.
  - `_DOCUMENT_TABLES`: include `"warranty_claims"` (in `frozenset({"documents", "sales", "purchases", "warranty_claims"})`).
  - `TERMINAL_REFS`:
    - `"warranty_claims"`: map `warranty_id` to `"warranties"`, `repair_sale_id` to `DOCUMENT_ID_SPACE`.
    - `"warranty_claim_events"`: map `claim_id` to `DOCUMENT_ID_SPACE`.
  - In `sync_client.py`:
    - `_collect_unsynced()` splits unsynced `WarrantyClaim` into parent `documents` payload and child `warranty_claims` payload.

---

## 6. Implementation & Commit Sequence

- **Commit 1**: `feat(warranty): add warranty lookup and correction (#825)`
  - `WarrantyDTO` and `WarrantyService.search()` with 5-tier precedence.
  - `WarrantyService.update_warranty_admin()` with `warranty.edit` check and audit log.
  - `WarrantyLookupDialog` and `WarrantyCorrectionDialog`.
  - Integration into POS side menu, Management tab, and Customer editor.
  - Comprehensive unit and UI tests.
- **Commit 2**: `feat(warranty): add warranty claims workflow (#826)`
  - Alembic migration for `WarrantyClaim` and `WarrantyClaimEvent` with permissions seed.
  - `WarrantyClaimService` with strict state machine and 1-open-claim guard.
  - Refund service integration blocking refunds on open claim units (with claim resolution bridge).
  - Thermal intake and collection slip generation in `WarrantyClaimReceiptBuilder`.
  - Management Claims Board UI and `WarrantyClaimDialog`.
  - LAN sync protocol 1.5 bump and test suite.
