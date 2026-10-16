# Reports KPI Summary Cards Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add KPI summary card row above report tables in ReportViewer computed from the full DataFrame ([REC-08], Fixes #543).

**Architecture:** Extend `BaseReport` with optional `get_summary(df: pd.DataFrame) -> list[dict[str, Any]]` returning card metadata. Consolidate dead `InfoCard` classes into a clean, flat, shadow-free widget in `cbpos/ui/widgets/info_card.py`. Render dynamic summary cards above the content stack in `ReportViewer` computed from `self._full_df` to ensure all rows across all pages are included in metrics.

**Tech Stack:** PyQt6, Pandas, Python 3.12, QSS, pytest-qt.

**Spec:** GitHub Issue #543 ([REC-08] Reports: KPI summary cards above report tables).

## Global Constraints

- Flat cards without drop shadows (`QGraphicsDropShadowEffect`) to avoid side-menu paint lag (#524).
- Summary cards must be computed strictly from `self._full_df` (all rows), never the paginated slice.
- Delete dead `InfoCard` class in `custom_widgets.py`, consolidate to `cbpos/ui/widgets/info_card.py`.
- Trilingual localization (`en`, `si`, `ta`) for all card labels.
- Theme support in both `dark.qss` and `light.qss`.

## Review Focus

1. Empty DataFrame (zero rows): `get_summary(df)` handles gracefully without ZeroDivisionError or crash.
2. NaNs or None in numeric columns: handled with standard fillna/coalesce so cards display valid numbers.
3. Pagination isolation: switching pages does not recompute or reset the summary cards.
4. Report switching: selecting a report without summary hides the summary card row immediately.
5. Dynamic language switch: translations update labels while keeping computed metric values intact.

---

### Task 1: Consolidate Flat `InfoCard` Widget and Clean Up Dead Classes

**Files:**
- Modify: `cbpos/ui/widgets/info_card.py`
- Modify: `cbpos/ui/widgets/custom_widgets.py:8-60`
- Modify: `cbpos/ui/styles/dark.qss`
- Modify: `cbpos/ui/styles/light.qss`
- Test: `tests/unit/test_info_card.py`

**Interfaces:**
- Produces: `cbpos.ui.widgets.info_card.InfoCard(title: str, value: str, icon_name: str, color: str = ..., parent=None)`
  - Methods: `set_value(value: str)`, `set_title(title: str)`

- [ ] **Step 1: Write failing unit test for flat `InfoCard` in `tests/unit/test_info_card.py`**

```python
def test_info_card_flat_without_graphics_effect(qapp):
    from cbpos.ui.widgets.info_card import InfoCard

    card = InfoCard(title="Total Sales", value="Rs. 1,000.00", icon_name="fa5s.chart-line")
    assert card.graphicsEffect() is None
    assert card.objectName() == "InfoCard"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_info_card.py -v`
Expected: FAIL (currently has QGraphicsDropShadowEffect)

- [ ] **Step 3: Update `cbpos/ui/widgets/info_card.py` and remove duplicate in `cbpos/ui/widgets/custom_widgets.py`**

Refactor `InfoCard` in `cbpos/ui/widgets/info_card.py` into a lightweight, flat card frame with icon, title, and big value. Delete unused `InfoCard` from `cbpos/ui/widgets/custom_widgets.py`. Ensure dark and light QSS styles support flat `#InfoCard`, `#InfoCardTitle`, `#InfoCardValue`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/unit/test_info_card.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add cbpos/ui/widgets/info_card.py cbpos/ui/widgets/custom_widgets.py cbpos/ui/styles/ tests/unit/test_info_card.py
git commit -m "refactor(ui): consolidate flat InfoCard widget without drop shadows (#543)"
```

---

### Task 2: BaseReport Summary Contract and Concrete Reports Implementation

**Files:**
- Modify: `cbpos/core/reports/base_report.py`
- Modify: `cbpos/core/reports/definitions/daily_sales.py`
- Modify: `cbpos/core/reports/definitions/inventory_valuation.py`
- Modify: `cbpos/i18n/en.json`
- Modify: `cbpos/i18n/si.json`
- Modify: `cbpos/i18n/ta.json`
- Test: `tests/unit/test_report_kpi_summary_cards.py`

**Interfaces:**
- Produces: `BaseReport.get_summary(self, df: pd.DataFrame) -> list[dict[str, Any]]`
  - Each item: `{"title": str, "value": str, "icon": str, "color": str | None}`

- [ ] **Step 1: Write failing tests for `get_summary(df)`**

```python
def test_base_report_default_summary_is_empty():
    class DummyReport(BaseReport): ...

    assert DummyReport().get_summary(pd.DataFrame()) == []


def test_daily_sales_summary_computation():
    report = DailySalesReport()
    df = pd.DataFrame({"Date": ["2026-10-01", "2026-10-02"], "Total Sales": [1000.0, 3000.0]})
    summary = report.get_summary(df)
    assert len(summary) >= 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_report_kpi_summary_cards.py -v`
Expected: FAIL (`get_summary` not implemented)

- [ ] **Step 3: Implement `get_summary` in `BaseReport`, `DailySalesReport`, `InventoryValuationReport` and i18n keys**

Add `get_summary` default in `BaseReport`. Add translations for summary titles in `en.json`, `si.json`, `ta.json`. Implement calculation logic in `DailySalesReport` (Total Sales, Invoices, Avg Ticket) and `InventoryValuationReport` (Total Items, Total Cost Value, Total Retail Value).

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/unit/test_report_kpi_summary_cards.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add cbpos/core/reports/base_report.py cbpos/core/reports/definitions/ cbpos/i18n/ tests/unit/test_report_kpi_summary_cards.py
git commit -m "feat(reports): implement get_summary contract for BaseReport and core reports (#543)"
```

---

### Task 3: Render Summary Cards in ReportViewer

**Files:**
- Modify: `cbpos/ui/views/reports/report_viewer.py`
- Modify: `cbpos/ui/styles/dark.qss`
- Modify: `cbpos/ui/styles/light.qss`
- Test: `tests/unit/test_report_kpi_summary_cards.py`

**Interfaces:**
- Consumes: `report.get_summary(full_df) -> list[dict[str, Any]]`
- Consumes: `InfoCard(title, value, icon, color)`

- [ ] **Step 1: Write failing tests in `test_report_kpi_summary_cards.py` for `ReportViewer` summary row**

```python
def test_report_viewer_displays_summary_cards_from_full_df(qapp, db_session):
    viewer = ReportViewer()
    # verify summary_container exists and displays cards from self._full_df
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_report_kpi_summary_cards.py -k test_report_viewer_displays_summary_cards_from_full_df -v`
Expected: FAIL

- [ ] **Step 3: Add `summary_container` to `ReportViewer` and populate on report finish**

In `ReportViewer._init_ui()`, insert `self.summary_container` with a horizontal flow or layout above `self.content_stack`. In `_on_report_finished()`, call `self.current_report.get_summary(self._full_df)`, populate cards, and show container if cards exist. Hide container when switching reports, clearing, or when no cards returned. In language change callback, refresh summary cards if displayed.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/unit/test_report_kpi_summary_cards.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add cbpos/ui/views/reports/report_viewer.py cbpos/ui/styles/ tests/unit/test_report_kpi_summary_cards.py
git commit -m "feat(reports): render KPI summary cards row in ReportViewer (#543)"
```

---

### Task 4: Full Test Suite, Visual Verification, and Polish

**Files:**
- Modify: `tests/unit/test_report_kpi_summary_cards.py`
- Test: All unit test suites

- [ ] **Step 1: Add edge cases and review focus tests**

Test empty DataFrame, zero rows, pagination isolation, report switching, and language changes.

- [ ] **Step 2: Run full report test suite and linters**

Run: `.venv/bin/pytest tests/unit/test_report_*.py && .venv/bin/ruff check cbpos/ tests/unit/test_report_*.py`
Expected: All tests pass, no lint errors.

- [ ] **Step 3: Generate and verify Dark/Light visual screenshots**

Generate visual preview script and capture screenshots of ReportViewer with summary cards in Dark and Light themes.

- [ ] **Step 4: Commit**

```bash
git add tests/ cbpos/
git commit -m "test(reports): add complete verification tests for report KPI summary cards (#543)"
```
