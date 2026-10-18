# Customer Ledger, Statements, Adjustments & Loyalty UX Improvements Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure absolute data integrity across customer ledger and statements via write-time enforcement and startup backfill; resolve QSS background bleed on metadata containers with scoped selectors; redesign Customer Statement dialog with 5-way mathematical reconciliation; replace chained `QInputDialog`s with foolproof, signed-mode `AdjustBalanceDialog` and `AdjustPointsDialog`; and modernize the Customer Editor Loyalty tab with state-safe controls and empty states.

**Architecture:**
- **Ledger Data Integrity:**
  - Enforce at write time: `CustomerService.create_customer()` writes an `OPENING` ledger entry (`INIT-BAL` / `INIT-PTS`) whenever `initial_debt > 0` or `loyalty_points > 0` inside the same database transaction.
  - Startup / Migration Backfill: `CustomerCreditService.backfill_missing_ledger_entries()` and `LoyaltyService.backfill_missing_loyalty_entries()` run idempotently on startup, creating `OPENING` entries for any existing customer with debt or points but 0 ledger rows.
  - Pure Statement Math: `StatementService._get_balance_before()` relies strictly on real ledger entries with zero ad-hoc fallbacks.
- **QSS Scoping:**
  - Name metadata containers `item_phone`, `item_address`, `item_company` with `setObjectName("MetaContainer")`.
  - In `dark.qss` and `light.qss`, explicitly scope `QFrame#CreditHeaderCard QWidget#MetaContainer, QFrame#CreditHeaderCard QLabel { background-color: transparent; border: none; }` without using wildcard descendant selectors or inline Python `.setStyleSheet()`.
- **Statement Reconciliation:**
  - Reconcile 5 stat cards in `CustomerStatementDialog`: **Opening Balance** + **Credit Sales** - **Payments** ± **Net Adjustments** = **Closing Balance**.
  - Fix `{phone}` placeholder in `en.json`, `si.json`, and `ta.json`.
- **Foolproof Adjustment Modals:**
  - Implement `AdjustBalanceDialog` and `AdjustPointsDialog` with 3-mode segmented toggles (`Add` / `Deduct` / `Set Exact`), positive-only inputs, live formula calculation banners, and required reason chips.
- **Loyalty Tab State Safety:**
  - In `CustomerEditor`, disable `[Adjust Points]` when `customer_id is None` with a helpful tooltip.
  - After adjustment on existing customer, immediately update the tab's overview card and points history table, and notify the parent customer list.

**Tech Stack:** PyQt6, SQLAlchemy, FontAwesome (`qtawesome`), Python 3.12, QSS.

**Spec:** User feedback on customer ledger drilldown, statement screen, balance/points adjusters, and customer editor loyalty tab.

## Global Constraints
- Strictly no unicode emojis; use FontAwesome vector icons via `Icons.get(...)`.
- All buttons with icons must have 8px trailing padding between icon and text via `_set_button_icon`.
- All user-facing strings must resolve via `_t(...)` or `t_or(...)` across `en.json`, `si.json`, and `ta.json`.
- All DB operations must adhere to existing serializable isolation and row-level locking conventions in `CustomerCreditService` and `LoyaltyService`.
- No inline `.setStyleSheet()` on widgets that need to react to Light/Dark theme switching.

## Review Focus
1. Historical statements (e.g. date ranges before the customer had transactions) must accurately show 0.00 opening and closing balance, not present-day debt.
2. The "First Transaction" cliff: A customer with opening debt making a partial payment must show `Opening (2500) - Payment (500) = Closing (2000)`, never negative balance.
3. Light and Dark theme switching on `CreditHeaderCard` must show no dark rectangular artifacts behind metadata.
4. Adjustment dialog mode switches (`Add`, `Deduct`, `Set Exact`) must correctly compute the net delta and prevent negative balances where disallowed.
5. Opening the Loyalty tab on an unsaved new customer must safely disable adjustments without crashes.

---

### Task 1: Write-Time Enforcement & Startup Backfill for Ledger and Loyalty Data
**Files:**
- Modify: `cbpos/core/services/customer_service.py`
- Modify: `cbpos/core/services/customer_credit_service.py`
- Modify: `cbpos/core/services/loyalty_service.py`
- Modify: `cbpos/core/services/statement_service.py`
- Modify: `main.py`
- Modify: `scripts/seed.py`
- Test: `tests/unit/test_customer_ledger_opening_balance.py`

**Interfaces:**
- `CustomerCreditService.backfill_missing_ledger_entries(session: Session | None = None) -> int`
- `LoyaltyService.backfill_missing_loyalty_entries(session: Session | None = None) -> int`
- `CustomerService.create_customer(data: dict[str, Any]) -> Customer`

- [ ] **Step 1: Write failing tests for write-time enforcement, backfill, and historical statement purity**
```python
def test_create_customer_with_debt_writes_opening_ledger_entry(db_session):
    service = CustomerService()
    cust = service.create_customer({"name": "New Debt Cust", "current_debt": Decimal("3000.00")})
    entries = CustomerCreditService.get_ledger(cust.id)
    assert len(entries) == 1
    assert entries[0].entry_type == "OPENING"
    assert entries[0].amount == Decimal("3000.00")
    assert entries[0].reference_doc == "INIT-BAL"


def test_backfill_missing_ledger_entries_is_idempotent(db_session):
    # Customer created directly without ledger
    c = Customer(name="Direct Cust", current_debt=Decimal("1500.00"), credit_limit=Decimal("5000.00"))
    db_session.add(c)
    db_session.flush()

    assert len(CustomerCreditService.get_ledger(c.id)) == 0
    count = CustomerCreditService.backfill_missing_ledger_entries()
    assert count >= 1
    assert len(CustomerCreditService.get_ledger(c.id)) == 1

    # Second run does not duplicate
    count2 = CustomerCreditService.backfill_missing_ledger_entries()
    assert count2 == 0
    assert len(CustomerCreditService.get_ledger(c.id)) == 1


def test_historical_statement_before_opening_balance_is_pure_zero(db_session):
    past_date = datetime.now() - timedelta(days=60)
    c = Customer(name="Old Cust", current_debt=Decimal("2000.00"))
    db_session.add(c)
    db_session.flush()
    CustomerCreditService.backfill_missing_ledger_entries()

    # Statement for 120 days ago to 90 days ago (prior to opening entry)
    stmt = StatementService.generate_statement(
        c.id, datetime.now() - timedelta(days=120), datetime.now() - timedelta(days=90)
    )
    assert stmt["opening_balance"] == Decimal("0.00")
    assert stmt["closing_balance"] == Decimal("0.00")
```

- [ ] **Step 2: Run test to verify it fails**
Run: `uv run pytest tests/unit/test_customer_ledger_opening_balance.py`
Expected: FAIL (methods not implemented / assertions fail)

- [ ] **Step 3: Implement write-time creation and startup backfill**
1. In `cbpos/core/services/customer_service.py`:
   - In `create_customer()`: If `customer.current_debt > 0`, insert `CustomerLedgerEntry(customer_id=customer.id, entry_type="OPENING", amount=customer.current_debt, balance_after=customer.current_debt, reference_doc="INIT-BAL", note="Opening Balance", user_id=1, timestamp=datetime.now())`.
   - If `customer.loyalty_points > 0`, insert `LoyaltyLedgerEntry(customer_id=customer.id, entry_type="OPENING", points=customer.loyalty_points, balance_after=customer.loyalty_points, note="Opening Points", timestamp=datetime.now())`.
2. In `cbpos/core/services/customer_credit_service.py`:
   - Implement `backfill_missing_ledger_entries()`: Query all customers where `current_debt > 0` that have 0 `CustomerLedgerEntry` rows; insert `OPENING` entry for each.
3. In `cbpos/core/services/loyalty_service.py`:
   - Implement `backfill_missing_loyalty_entries()`: Query all customers where `loyalty_points > 0` that have 0 `LoyaltyLedgerEntry` rows; insert `OPENING` entry for each.
4. In `main.py`: Call `CustomerCreditService.backfill_missing_ledger_entries()` and `LoyaltyService.backfill_missing_loyalty_entries()` during bootstrap after DB setup.
5. In `scripts/seed.py`: Generate opening entries, chronological credit sales, and payments for sample customers.
6. Keep `StatementService._get_balance_before()` 100% pure ledger query without special fallback.

- [ ] **Step 4: Run test to verify it passes**
Run: `uv run pytest tests/unit/test_customer_ledger_opening_balance.py`
Expected: PASS

- [ ] **Step 5: Run existing ledger and credit tests**
Run: `uv run pytest tests/unit/test_credit_ledger_all_button.py tests/unit/test_credit_book_context_menu.py`
Expected: PASS

---

### Task 2: Scoped QSS Transparency Fix for Customer Metadata
**Files:**
- Modify: `cbpos/ui/views/credit_book_view.py`
- Modify: `cbpos/ui/styles/dark.qss`
- Modify: `cbpos/ui/styles/light.qss`
- Test: `tests/unit/test_credit_book_ui_improvements.py`

**Interfaces:**
- Scoped QSS selectors for `#CreditHeaderCard QWidget#MetaContainer`.

- [ ] **Step 1: Write test verifying container objectNames and QSS rule presence**
```python
def test_metadata_containers_have_meta_container_object_name(db_session):
    view = CreditBookView()
    try:
        assert view.item_phone.objectName() == "MetaContainer"
        assert view.item_address.objectName() == "MetaContainer"
        assert view.item_company.objectName() == "MetaContainer"
    finally:
        view.deleteLater()


def test_qss_has_scoped_meta_container_rules():
    dark_qss = (STYLE_DIR / "dark.qss").read_text()
    light_qss = (STYLE_DIR / "light.qss").read_text()
    assert "QFrame#CreditHeaderCard QWidget#MetaContainer" in dark_qss
    assert "QFrame#CreditHeaderCard QWidget#MetaContainer" in light_qss
    assert "QFrame#CreditHeaderCard QWidget {" not in dark_qss
    assert "QFrame#CreditHeaderCard QWidget {" not in light_qss
```

- [ ] **Step 2: Run test to verify it fails**
Run: `uv run pytest tests/unit/test_credit_book_ui_improvements.py -k "MetaContainer"`
Expected: FAIL

- [ ] **Step 3: Update `credit_book_view.py`, `dark.qss`, and `light.qss`**
1. In `credit_book_view.py`:
   - Set `self.item_phone.setObjectName("MetaContainer")`
   - Set `self.item_address.setObjectName("MetaContainer")`
   - Set `self.item_company.setObjectName("MetaContainer")`
   - Remove any inline `setStyleSheet` calls on them.
2. In `dark.qss` and `light.qss`:
```css
QFrame#CreditHeaderCard QWidget#MetaContainer,
QFrame#CreditHeaderCard QLabel {
    background-color: transparent;
    border: none;
}
```

- [ ] **Step 4: Run test to verify it passes**
Run: `uv run pytest tests/unit/test_credit_book_ui_improvements.py -k "MetaContainer"`
Expected: PASS

---

### Task 3: Redesign Customer Statement Dialog with 5-Way Reconciliation
**Files:**
- Modify: `cbpos/ui/dialogs/customer_statement_dialog.py`
- Modify: `cbpos/core/services/statement_service.py`
- Modify: `cbpos/i18n/en.json`, `cbpos/i18n/si.json`, `cbpos/i18n/ta.json`
- Test: `tests/unit/test_customer_statement_dialog_spacing.py`
- Test: `tests/unit/test_customer_statement_reconciliation.py`

**Interfaces:**
- `StatementService.generate_statement()` returning `total_sales`, `total_payments`, `net_adjustments`, `opening_balance`, `closing_balance`.
- `CustomerStatementDialog` with 5 reconciled stat cards.

- [ ] **Step 1: Write test for statement reconciliation math**
```python
def test_statement_reconciles_sales_payments_and_adjustments(db_session, customer):
    # Opening 2500, Sale 1000, Payment 500, Adj -200 -> Closing 2800
    CustomerCreditService.record_adjustment(customer.id, Decimal("-200.00"), "Goodwill discount", 1)
    stmt = StatementService.generate_statement(customer.id, datetime.now() - timedelta(days=30), datetime.now())
    assert (
        stmt["opening_balance"] + stmt["total_sales"] - stmt["total_payments"] + stmt["net_adjustments"]
        == stmt["closing_balance"]
    )
```

- [ ] **Step 2: Update `StatementService.generate_statement()` to break out adjustments**
In `cbpos/core/services/statement_service.py`:
- Track `total_sales` (entry_type == "SALE" or "OPENING"), `total_payments` (entry_type == "PAYMENT"), and `net_adjustments` (ADJUSTMENT, VOID, REFUND).
- Return `total_sales`, `total_payments`, `net_adjustments`, `opening_balance`, and `closing_balance`.

- [ ] **Step 3: Fix `{phone}` placeholder in `en.json`, `si.json`, and `ta.json`**
Update:
- `en.json`: `"phone": "Phone: {phone}"`
- `si.json`: `"phone": "දුරකථනය: {phone}"`
- `ta.json`: `"phone": "போன்: {phone}"`
Add translation keys for 5 stat cards: `stat_opening`, `stat_sales`, `stat_payments`, `stat_adjustments`, `stat_closing`.

- [ ] **Step 4: Redesign `CustomerStatementDialog` UI**
- **Customer Hero Strip**: Avatar icon (`fa5s.user-circle`) + Name + ID badge (`#CUST-XXXX`) + Phone with FontAwesome icon.
- **Filter Row**: Styled container with `From` and `To` date pickers, presets (*This Month*, *Last 30 Days*, *All Time*), and `_set_button_icon(btn_refresh, "fa5s.sync-alt", ...)` with 8px padding.
- **5-Way Stat Cards Layout**:
  1. Opening Balance
  2. Credit Sales (+)
  3. Payments (-)
  4. Net Adjustments (±)
  5. Closing Balance
- **Ledger Table**: Right-aligned numeric amounts, color-coded badges, empty state indicator when no transactions exist.
- **Action Buttons**: `_set_button_icon(btn_print, Icons.PRINT, ...)` with 8px gap and clean `Close` button.

- [ ] **Step 5: Run unit tests**
Run: `uv run pytest tests/unit/test_customer_statement_dialog_spacing.py tests/unit/test_customer_statement_reconciliation.py`
Expected: PASS

---

### Task 4: Foolproof Signed-Mode Adjust Balance & Adjust Points Dialogs
**Files:**
- Create: `cbpos/ui/dialogs/adjust_balance_dialog.py`
- Create: `cbpos/ui/dialogs/adjust_points_dialog.py`
- Modify: `cbpos/ui/views/credit_book_view.py`
- Modify: `cbpos/ui/dialogs/customer_editor.py`
- Modify: `cbpos/i18n/en.json`, `cbpos/i18n/si.json`, `cbpos/i18n/ta.json`
- Test: `tests/unit/test_adjustment_dialogs.py`

**Interfaces:**
- `AdjustBalanceDialog(customer, parent=None) -> QDialog`
- `AdjustPointsDialog(customer, parent=None) -> QDialog`

- [ ] **Step 1: Write tests for mode calculation and reason validation**
```python
def test_adjust_balance_dialog_modes(db_session, customer):
    dlg = AdjustBalanceDialog(customer)
    # Mode: Add to Debt (+500 on 2500 -> 3000)
    dlg.set_mode("add")
    dlg.amount_spin.setValue(500)
    assert dlg.calculate_new_balance() == Decimal("3000.00")
    assert dlg.calculate_delta() == Decimal("500.00")

    # Mode: Reduce Debt (-500 on 2500 -> 2000)
    dlg.set_mode("reduce")
    assert dlg.calculate_new_balance() == Decimal("2000.00")
    assert dlg.calculate_delta() == Decimal("-500.00")

    # Mode: Set Exact Debt (set 1000 on 2500 -> 1000)
    dlg.set_mode("set")
    dlg.amount_spin.setValue(1000)
    assert dlg.calculate_new_balance() == Decimal("1000.00")
    assert dlg.calculate_delta() == Decimal("-1500.00")


def test_adjust_balance_dialog_requires_reason(db_session, customer):
    dlg = AdjustBalanceDialog(customer)
    dlg.amount_spin.setValue(500)
    dlg.reason_edit.setText("")
    assert not dlg.validate()
    dlg.reason_edit.setText("Opening Balance Correction")
    assert dlg.validate()
```

- [ ] **Step 2: Implement `AdjustBalanceDialog`**
- Segmented mode toggle: `[ + Add to Debt ]` | `[ - Reduce Debt ]` | `[ = Set Exact Debt ]`.
- Strictly positive spinbox / double-spinbox (`min=0.01`).
- Live calculation card:
  `Current Debt (Rs. 2,500.00) - Adjustment (Rs. 500.00) = New Balance (Rs. 2,000.00)`.
- Quick reason chips: *Opening Balance Correction*, *Goodwill Credit*, *Returned Goods*, *Data Entry Fix*.
- Required reason input validation.
- Execute adjustment through `CustomerCreditService.record_adjustment()`.

- [ ] **Step 3: Implement `AdjustPointsDialog`**
- Segmented mode toggle: `[ + Add Points ]` | `[ - Deduct Points ]` | `[ = Set Exact Points ]`.
- Strictly positive integer spinbox (`min=1`).
- Quick increment chips: `+10`, `+50`, `+100`, `+500`.
- Live calculation card:
  `Current Points (150 pts) + Adjustment (50 pts) = New Balance (200 pts)`.
  Blocks negative resulting balance.
- Quick reason chips: *Bonus Reward*, *Customer Goodwill*, *Redemption Correction*, *Data Entry Fix*.
- Execute adjustment through `LoyaltyService.adjust_points()`.

- [ ] **Step 4: Connect dialogs in `CreditBookView` and `CustomerEditor`**
Replace `QInputDialog` calls in `CreditBookView.adjust_balance()`, `CreditBookView.adjust_loyalty_points()`, and `CustomerEditor.adjust_points()`.

- [ ] **Step 5: Run unit tests**
Run: `uv run pytest tests/unit/test_adjustment_dialogs.py`
Expected: PASS

---

### Task 5: Customer Editor Loyalty Tab Modernization & State Safety
**Files:**
- Modify: `cbpos/ui/dialogs/customer_editor.py`
- Modify: `cbpos/i18n/en.json`, `cbpos/i18n/si.json`, `cbpos/i18n/ta.json`
- Test: `tests/unit/test_loyalty_tab_redesign.py`

**Interfaces:**
- `CustomerEditor.create_loyalty_tab()`
- `CustomerEditor.load_points_history()`
- Signal / callback: `points_adjusted` to update parent views.

- [ ] **Step 1: Write tests for unsaved new customer vs existing customer**
```python
def test_new_customer_loyalty_tab_disables_adjust_points(qapp):
    # Customer without ID (new customer)
    editor = CustomerEditor(None)
    assert not editor.btn_adjust_points.isEnabled()
    assert "Save the customer first" in editor.btn_adjust_points.toolTip()


def test_existing_customer_loyalty_tab_enables_adjust_points(qapp, customer):
    editor = CustomerEditor(customer)
    assert editor.btn_adjust_points.isEnabled()
```

- [ ] **Step 2: Redesign Loyalty tab in `CustomerEditor`**
- **Loyalty Overview Card**:
  - Loyalty Card Code input with FontAwesome card icon `fa5s.id-card`.
  - Current points card with Amber Star icon (`Icons.POINTS`), large bold points figure, and styled `[Adjust Points]` button with icon.
  - Disable button when `customer is None` or `customer.id is None` with tooltip *"Save the customer first to adjust or view loyalty history."*
- **Points History Section**:
  - Color-coded badges for event types (`EARN` green, `REDEEM` blue, `ADJUSTMENT` amber).
  - Empty state overlay: when points history is empty, show clean empty state ("No loyalty points events recorded yet").
- **State Safety**:
  - When `AdjustPointsDialog` finishes successfully, immediately update `self.points_label` and call `self.load_points_history()`.
  - Emit update signal so the main window / customer list reflects the new points even if the editor profile changes are cancelled.

- [ ] **Step 3: Run unit tests**
Run: `uv run pytest tests/unit/test_loyalty_tab_redesign.py`
Expected: PASS

---

### Task 6: Full Integration & Edge-Case Verification
- Run `uv run pytest tests/unit/test_customer_ledger_opening_balance.py tests/unit/test_adjustment_dialogs.py tests/unit/test_customer_statement_dialog_spacing.py tests/unit/test_loyalty_tab_redesign.py tests/unit/test_credit_book_ui_improvements.py`.
- Run `uv run ruff check` on all modified files.
- Test Light and Dark themes for `CreditHeaderCard`, `CustomerStatementDialog`, `AdjustBalanceDialog`, and `CustomerEditor`.
- Verify database backfill by inspecting seeded customer Kasun Perera.
