## 1. Target Module Architecture & File Structure

Instruct your AI agent to refactor the existing single-file or split-pane reports screen into a modular, data-driven package. All 14 reports must share **one UI Viewer**, **one Table Model**, **one PDF/Print Engine**, and **one Excel Exporter**.

```text
cb_pos/
└── modules/
    └── reports/
        ├── __init__.py
        ├── models.py                # Dataclasses: ReportDef, ColumnDef, KpiDef, FilterState, ShopProfile
        ├── registry.py              # Declarative configurations for all 14 reports
        ├── controller.py            # Async QThreadPool execution, caching, & export orchestration
        ├── repository.py            # Parameterized SQL queries for all 14 reports (off-main-thread)
        ├── exporters/
        │   ├── pdf_exporter.py      # ReportLab A4 engine with Shop Header & CeyByte.com watermark
        │   └── excel_exporter.py    # OpenPyXL/XlsxWriter exporter with formatted totals
        └── ui/
            ├── reports_container.py # QStackedWidget (Index 0: HubView, Index 1: ViewerView)
            ├── hub_view.py          # Full-page 14-report card grid, category tabs, global date bar
            ├── viewer_view.py       # Full-width table viewer, 1-row filter bar, 4 KPI cards, pinned totals
            ├── table_model.py       # High-performance QAbstractTableModel + SortFilterProxyModel
            ├── print_preview.py     # Native A4 Print Preview Modal before physical printing
            └── styles.py            # Dark-mode QSS stylesheet matching CB POS theme tokens

```

---

## 2. Core Data Contracts (`models.py`)

Give your AI agent these strict Python dataclasses first so it builds a type-safe engine rather than hardcoding 14 separate screens:

```python
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Callable


class ReportCategory(str, Enum):
    SALES = "Sales"
    INVENTORY = "Inventory"
    FINANCIAL = "Financial"
    AUDIT = "Audit"


class ColumnFormat(str, Enum):
    TEXT = "text"  # Left-aligned string
    CENTER_TEXT = "center"  # Center-aligned (Phone, Status, Dates, Invoice #)
    INTEGER = "integer"  # Right-aligned: 1,250
    CURRENCY = "currency"  # Right-aligned: 150,000.00
    PERCENT = "percent"  # Right-aligned: 11.11%
    BADGE = "badge"  # Center-aligned pill badge (Risk/Severity/Type)


class AggType(str, Enum):
    NONE = "none"
    SUM = "sum"
    AVG = "avg"
    COUNT = "count"
    MARGIN_PCT = "margin_pct"  # (Sum(Profit) / Sum(Revenue)) * 100
    UTIL_PCT = "util_pct"  # (Sum(Outstanding) / Sum(CreditLimit)) * 100


@dataclass(frozen=True)
class ColumnDef:
    key: str
    header: str
    fmt: ColumnFormat
    width_weight: float = 1.0  # Relative stretch factor in UI & PDF
    agg: AggType = AggType.NONE
    highlight_negative: bool = False  # Red text if < 0 (e.g., Variance, Profit)
    badge_rules: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class KpiDef:
    key: str
    label: str
    fmt: ColumnFormat
    accent_color: str = "#00B8D4"  # Cyan, Emerald, Amber, or Red


@dataclass(frozen=True)
class FilterConfig:
    use_date_range: bool = True
    use_search: bool = True
    search_placeholder: str = "Search records..."
    dropdown_key: str | None = None  # e.g., "cashier", "category", "payment_method", "status"
    dropdown_label: str | None = None


@dataclass(frozen=True)
class ReportDefinition:
    report_id: str
    title: str
    category: ReportCategory
    description: str
    filters: FilterConfig
    kpis: tuple[KpiDef, KpiDef, KpiDef, KpiDef]
    columns: tuple[ColumnDef, ...]
    landscape_pdf: bool = False  # Auto-true if > 6 columns


@dataclass
class ShopProfile:
    shop_name: str
    address_line: str
    phone_number: str
    tax_reg_no: str | None = None
    currency_symbol: str = "Rs."


@dataclass
class FilterState:
    date_preset: str = "This Month"
    start_date: date = field(default_factory=date.today)
    end_date: date = field(default_factory=date.today)
    search_query: str = ""
    dropdown_value: str = "ALL"


@dataclass
class ReportPayload:
    definition: ReportDefinition
    filters_applied: FilterState
    generated_at: datetime
    rows: list[dict[str, Any]]
    kpi_values: dict[str, Any]
    totals_row: dict[str, Any]
```

---

## 3. Complete 14-Report Registry Specification (`registry.py`)

Your AI agent must configure all 14 reports inside `REPORT_REGISTRY: dict[str, ReportDefinition]` using the exact rules below:

| Report ID           | Title & Category                          | Active Toolbar Filters                                                    | 4 KPI Summary Keys                                                              | Column Keys (`[Align | Format | Total Agg]`)                 |
| :------------------ | :---------------------------------------- | :------------------------------------------------------------------------ | :------------------------------------------------------------------------------ | :------------------- | ------ | ---------------------------- | ---- | ------------------------------- | ----- | --------------------------- | ----- | ------------------------- | ----- | ---------------------------- | ----- | -------------------------- | ----- | ------ |
| `daily_sales`       | **Daily Sales Summary** (`Sales`)         | Date Range, Search, Cashier Dropdown                                      | `gross_sales`, `total_discount`, `net_revenue`, `invoice_count`                 | `date` `[C           | TEXT   | COUNT]`, `invoice_count` `[R | INT  | SUM]`, `gross_sales` `[R        | CURR  | SUM]`, `discount` `[R       | CURR  | SUM]`, `tax` `[R          | CURR  | SUM]`, `net_sales` `[R       | CURR  | SUM]`                      |
| `sales_by_category` | **Sales by Category** (`Sales`)           | Date Range, Search, Category Dropdown                                     | `top_category`, `units_sold`, `net_sales`, `avg_margin_pct`                     | `category_name` `[L  | TEXT   | COUNT]`, `items_sold` `[R    | INT  | SUM]`, `gross_sales` `[R        | CURR  | SUM]`, `discount` `[R       | CURR  | SUM]`, `net_sales` `[R    | CURR  | SUM]`, `share_pct` `[R       | PCT   | SUM]`                      |
| `cashier_perf`      | **Cashier Performance** (`Sales`)         | Date Range, Search, Cashier Dropdown                                      | `active_cashiers`, `total_bills`, `net_sales`, `avg_bill_value`                 | `cashier_name` `[L   | TEXT   | COUNT]`, `shifts` `[R        | INT  | SUM]`, `bills_count` `[R        | INT   | SUM]`, `returns_amt` `[R    | CURR  | SUM]`, `net_sales` `[R    | CURR  | SUM]`, `avg_bill` `[R        | CURR  | AVG]`                      |
| `payment_methods`   | **Payment Method Summary** (`Sales`)      | Date Range, Payment Type (`Cash`/`Card`/`QR`/`Credit`)                    | `cash_total`, `card_total`, `credit_total`, `grand_total`                       | `payment_method` `[L | TEXT   | COUNT]`, `tx_count` `[R      | INT  | SUM]`, `total_amount` `[R       | CURR  | SUM]`, `share_pct` `[R      | PCT   | SUM]`                     |
| `inventory_val`     | **Inventory Valuation** (`Inventory`)     | Search SKU/Name, Category Dropdown _(No Date Filter)_                     | `total_skus`, `total_cost_val`, `total_retail_val`, `est_profit_val`            | `sku` `[C            | TEXT   | COUNT]`, `item_name` `[L     | TEXT | NONE]`, `category` `[L          | TEXT  | NONE]`, `qty_on_hand` `[R   | INT   | SUM]`, `unit_cost` `[R    | CURR  | NONE]`, `total_cost` `[R     | CURR  | SUM]`, `retail_val` `[R    | CURR  | SUM]`  |
| `low_stock`         | **Low Stock Alert** (`Inventory`)         | Search SKU/Name, Severity (`All`/`Out of Stock`/`Low`)                    | `out_of_stock_count`, `low_stock_count`, `est_restock_cost`, `suppliers_count`  | `sku` `[C            | TEXT   | COUNT]`, `item_name` `[L     | TEXT | NONE]`, `current_qty` `[R       | INT   | SUM]`, `reorder_level` `[R  | INT   | SUM]`, `shortage_qty` `[R | INT   | SUM]`, `supplier` `[L        | TEXT  | NONE]`, `status` `[C       | BADGE | NONE]` |
| `profit_loss`       | **Profit & Loss Statement** (`Financial`) | Date Range, Search Invoice #                                              | `total_revenue`, `total_cogs`, `gross_profit`, `gross_margin_pct`               | `date` `[C           | TEXT   | COUNT]`, `invoice_no` `[C    | TEXT | NONE]`, `revenue` `[R           | CURR  | SUM]`, `cogs` `[R           | CURR  | SUM]`, `gross_profit` `[R | CURR  | SUM]`, `margin_pct` `[R      | PCT   | MARGIN_PCT]`               |
| `cash_flow`         | **Cash Flow Report** (`Financial`)        | Date Range, Flow Type (`All`/`Inflow`/`Outflow`)                          | `opening_cash`, `total_cash_in`, `total_cash_out`, `closing_cash`               | `datetime` `[C       | TEXT   | COUNT]`, `ref_no` `[C        | TEXT | NONE]`, `description` `[L       | TEXT  | NONE]`, `flow_type` `[C     | BADGE | NONE]`, `cash_in` `[R     | CURR  | SUM]`, `cash_out` `[R        | CURR  | SUM]`, `running_bal` `[R   | CURR  | NONE]` |
| `customer_credit`   | **Customer Credit Report** (`Financial`)  | Search Customer/Phone, Risk Filter (`All`/`Near Limit >85%`/`Over Limit`) | `active_accounts`, `total_credit_limit`, `total_outstanding`, `total_available` | `customer_name` `[L  | TEXT   | COUNT]`, `phone` `[C         | TEXT | NONE]`, `credit_limit` `[R      | CURR  | SUM]`, `outstanding` `[R    | CURR  | SUM]`, `available` `[R    | CURR  | SUM]`, `utilization_pct` `[C | BADGE | UTIL_PCT]`                 |
| `overdue_customers` | **Overdue Customers** (`Financial`)       | Search Customer/Phone, Aging Bucket (`>30d`/`>60d`/`>90d`)                | `overdue_accounts`, `total_overdue_amt`, `critical_90d_amt`, `oldest_days`      | `customer_name` `[L  | TEXT   | COUNT]`, `phone` `[C         | TEXT | NONE]`, `last_payment_date` `[C | TEXT  | NONE]`, `days_overdue` `[R  | INT   | AVG]`, `total_credit` `[R | CURR  | SUM]`, `overdue_balance` `[R | CURR  | SUM]`                      |
| `stock_movement`    | **Stock Movement Audit** (`Audit`)        | Date Range, Search Item, Movement Type (`Sale`/`GRN`/`Return`/`Adj`)      | `total_events`, `total_qty_in`, `total_qty_out`, `net_qty_change`               | `datetime` `[C       | TEXT   | COUNT]`, `item_name` `[L     | TEXT | NONE]`, `move_type` `[C         | BADGE | NONE]`, `ref_no` `[C        | TEXT  | NONE]`, `user` `[L        | TEXT  | NONE]`, `qty_in` `[R         | INT   | SUM]`, `qty_out` `[R       | INT   | SUM]`  |
| `cash_movement`     | **Cash Movement Audit** (`Audit`)         | Date Range, Cashier Dropdown, Type (`Float`/`Safe Drop`/`Petty Out`)      | `opening_floats`, `petty_cash_out`, `safe_drops`, `net_movement`                | `datetime` `[C       | TEXT   | COUNT]`, `shift_id` `[C      | TEXT | NONE]`, `user` `[L              | TEXT  | NONE]`, `move_type` `[C     | BADGE | NONE]`, `reason` `[L      | TEXT  | NONE]`, `amount_in` `[R      | CURR  | SUM]`, `amount_out` `[R    | CURR  | SUM]`  |
| `shift_variance`    | **Shift Variance Report** (`Audit`)       | Date Range, Cashier Dropdown, Status (`All`/`Shortage`/`Overage`)         | `closed_shifts`, `balanced_count`, `total_shortage`, `total_overage`            | `shift_id` `[C       | TEXT   | COUNT]`, `cashier_name` `[L  | TEXT | NONE]`, `closed_at` `[C         | TEXT  | NONE]`, `expected_cash` `[R | CURR  | SUM]`, `counted_cash` `[R | CURR  | SUM]`, `variance` `[R        | CURR  | SUM]`                      |
| `void_refund`       | **Void & Refund Report** (`Audit`)        | Date Range, Cashier Dropdown, Type (`All`/`Void`/`Refund`)                | `void_count`, `refund_count`, `total_reversed_amt`, `top_reason`                | `datetime` `[C       | TEXT   | COUNT]`, `invoice_no` `[C    | TEXT | NONE]`, `cashier` `[L           | TEXT  | NONE]`, `approved_by` `[L   | TEXT  | NONE]`, `action_type` `[C | BADGE | NONE]`, `reason` `[L         | TEXT  | NONE]`, `reversed_amt` `[R | CURR  | SUM]`  |

---

## 4. PyQt6 UI/UX Engineering Specifications

### A. Exact Color & Typography Tokens (`styles.py`)

Keep visual consistency with your current dark shell while upgrading contrast, spacing, and alignment:

- **App Background (`BgMain`):** `#16191D`
- **Panel / Card Surface (`BgPanel`):** `#1E2228`
- **Elevated Surface / Alternating Table Row (`BgElevated`):** `#252A32`
- **Hover Surface (`BgHover`):** `#2C323C`
- **Border / Hairline Divider (`BorderSubtle`):** `#2E3440`
- **Primary Brand Accent (`AccentCyan`):** `#00B8D4` (Hover: `#00E5FF`, Subtle Fill: `rgba(0, 184, 212, 0.12)`)
- **Semantic Colors:** Emerald `#10B981` (Positive / Excel), Amber `#F59E0B` (Warning / 70–85% Credit), Crimson `#EF4444` (Danger / Overdue / PDF / >85% Credit)
- **Numeric Font Enforcement:** Every currency, integer, and percentage cell in both UI and PDF **must** use tabular numbers (`font-variant-numeric: tabular-nums` or monospace/tabular font fallback) so decimals align vertically to the pixel.

### B. View 1: `ReportsHubView` (Index `0` of `QStackedWidget`)

1. **Eliminate the Secondary Sidebar:** Completely remove the 260px `REPORTS` vertical list so the workspace occupies the full remaining width to the right of the main left navigation bar.

2. **Top Control Bar:**

- **Category Filter Pills:** `All (14)`, `★ Favorites`, `Sales (4)`, `Inventory (2)`, `Financial (4)`, `Audit (4)`.

- **Global Date Preset Bar:** `Today`, `Yesterday`, `This Week`, `This Month`, `Custom Range (QDateEdit From -> To)`. Changing this preset updates the shared `FilterState` passed when opening or quick-printing any report.
- **Instant Search Input (`Ctrl+F`):** Filters the 14 report cards in real time by title, category, or description.

3. **Responsive Card Grid:**

- Use a responsive 3-column grid (reflowing to 2 columns on smaller 1366×768 POS monitors).
- Each Card contains:
- **Top Row:** Category Pill Badge (`SALES`, `FINANCIAL`, etc.) + Interactive Star Toggle Button (`★`/`☆`) persisted in `QSettings("CeylonByte", "CBPOS")`.
- **Body:** Report Title (`15px Bold #F3F4F6`) + 2-line description (`12px #9CA3AF`).
- **Footer Action Bar:** Primary `[ Open Report → ]` button + 3 Quick Action icon buttons with tooltips: `[🖨️ Quick Print]`, `[📄 Save PDF]`, `[📊 Export Excel]`. Clicking a quick icon generates and exports the report directly in the background using the current Global Date Preset without switching views.

### C. View 2: `ReportViewerView` (Index `1` of `QStackedWidget`)

1. **Header Bar:**

- `[ ← Back to Reports ]` button (`Esc` shortcut returns to Hub).
- Report Title + Category Badge + Favorite Star toggle (`★`).

- Right-aligned Action Toolbar: `[🖨️ Print Preview (Ctrl+P)]`, `[📄 Export PDF]`, `[📊 Export Excel]`, `[✉️ Email Report]`.

2. **Contextual Single-Row Filter Bar:**

- Replaces the empty row that previously only had the cyan `Run Report` button.

- Dynamically shows/hides widgets based on `ReportDefinition.filters`:
- Search `QLineEdit` with `300ms` `QTimer` debounce (filters existing table rows instantaneously via `QSortFilterProxyModel`).
- Date Preset selector + `From`/`To` `QDateEdit` pickers (hidden for snapshot reports like `Inventory Valuation` and `Customer Credit Report` unless historical filtering is needed).
- Contextual `QComboBox` (e.g., Cashier, Category, Payment Method, Risk Status).
- `[↻ Refresh]` button (`F5` shortcut) to re-query the database.

3. **4-Card KPI Summary Strip:**

- A horizontal `QHBoxLayout` of 4 equal-width cards above the table displaying the 4 `KpiDef` metrics.
- Automatically recalculates when the user filters rows in the search box so the KPIs always match the visible table rows.

4. **Full-Width `QTableView` + Pinned Grand Total Footer:**

- **Critical Requirement:** Do **not** use `QTableWidget` (which lags on >500 rows). Use `QTableView` backed by a custom `QAbstractTableModel`.
- Set `header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)` with proportional column weights from `ColumnDef.width_weight` so the table always spans **100% of the right pane** with zero dead space.

- **Pinned Bottom Total Bar:** Place a synchronized single-row summary widget (or frozen bottom footer table) directly beneath the main `QTableView` that displays `GRAND TOTAL (N Rows)` on the left and the aggregated `SUM` / `AVG` / `MARGIN_PCT` values aligned directly under their respective columns.

---

## 5. Non-Blocking Concurrency Architecture (`controller.py`)

Since you already optimized CB POS main-thread performance in earlier phases, the Reports module must **never** run SQL queries or PDF builds on the Qt GUI thread:

```python
from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal, pyqtSlot
import traceback


class WorkerSignals(QObject):
    started = pyqtSignal(str)          # request_id
    finished = pyqtSignal(str, object) # request_id, ReportPayload or file_path
    error = pyqtSignal(str, str)       # request_id, error_message


class ReportQueryWorker(QRunnable):
    def __init__(self, request_id: str, fn, *args, **kwargs):
        super().__init__()
        self.request_id = request_id
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    @pyqtSlot()
    def run(self):
        self.signals.started.emit(self.request_id)
        try:
            result = self.fn(*self.args, **self.kwargs)
            self.signals.finished.emit(self.request_id, result)
        except Exception as exc:
             traceback.print_exc()
            self.signals.error.emit(self.request_id, str(exc))

```

- **Request ID Cancellation Pattern:** Increment a `self._active_request_id` counter in `ReportController` every time a user changes filters or switches reports. When `finished` emits, ignore any response whose `request_id != self._active_request_id` to prevent race conditions from slow queries overwriting newer queries.

---

## 6. Universal Enterprise PDF & Print Engine (`exporters/pdf_exporter.py`)

Provide this exact **ReportLab** implementation to your AI agent. It renders all 14 reports with:

1. **Centered Shop Header** (`Shop Name`, `Address`, `Phone Number` pulled dynamically from `ShopProfile`).
2. **Report Metadata & 4-KPI Summary Banner**.
3. **Auto-Repeating Table Header** across multi-page printouts (`repeatRows=1`) + bold **GRAND TOTAL** row.
4. **Two-Pass `NumberedCanvas` Footer** on every single page displaying the timestamp on the left, the rounded watermark badge **`CBPOS  |  Powered by CeyByte.com`** in the center, and **`Page X of Y`** on the right.

```python
from __future__ import annotations
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.pdfgen import canvas
from .models import ReportPayload, ShopProfile, ColumnFormat


class CeyByteWatermarkCanvas(canvas.Canvas):
    """Two-pass canvas that draws 'Page X of Y' and 'CBPOS | Powered by CeyByte.com' on every page."""

    def __init__(self, *args, generated_str: str = "", **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states: list[dict] = []
        self._generated_str = generated_str

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_enterprise_footer(num_pages)
            super().showPage()
        super().save()

    def _draw_enterprise_footer(self, page_count: int):
        self.saveState()
        page_width, _ = self._pagesize
        margin_x = 12 * mm
        footer_y = 10 * mm

        # Top divider line above footer
        self.setStrokeColor(colors.HexColor("#CBD5E1"))
        self.setLineWidth(0.6)
        self.line(margin_x, footer_y + 6 * mm, page_width - margin_x, footer_y + 6 * mm)

        # Left: Generated timestamp
        self.setFont("Helvetica", 7.5)
        self.setFillColor(colors.HexColor("#64748B"))
        self.drawString(margin_x, footer_y + 1.5 * mm, f"Generated on: {self._generated_str}")

        # Center: CBPOS | Powered by CeyByte.com pill badge
        badge_w = 64 * mm
        badge_h = 5.2 * mm
        badge_x = (page_width - badge_w) / 2.0
        badge_y = footer_y + 0.2 * mm

        self.setFillColor(colors.HexColor("#F8FAFC"))
        self.setStrokeColor(colors.HexColor("#CBD5E1"))
        self.setLineWidth(0.5)
        self.roundRect(badge_x, badge_y, badge_w, badge_h, 2.5 * mm, stroke=1, fill=1)

        # Draw centered watermark text inside pill
        center_x = page_width / 2.0
        text_y = badge_y + 1.6 * mm
        self.setFont("Helvetica-Bold", 7.5)
        self.setFillColor(colors.HexColor("#0F172A"))
        self.drawRightString(center_x - 8 * mm, text_y, "CBPOS")

        self.setFont("Helvetica", 7.5)
        self.setFillColor(colors.HexColor("#94A3B8"))
        self.drawCentredString(center_x - 5.5 * mm, text_y, "|")

        self.setFillColor(colors.HexColor("#475569"))
        self.drawString(center_x - 3.5 * mm, text_y, "Powered by ")

        self.setFont("Helvetica-Bold", 7.5)
        self.setFillColor(colors.HexColor("#0284C7"))
        self.drawString(center_x + 12.2 * mm, text_y, "CeyByte.com")

        # Right: Page X of Y
        self.setFont("Helvetica-Bold", 7.5)
        self.setFillColor(colors.HexColor("#475569"))
        self.drawRightString(
            page_width - margin_x,
            footer_y + 1.5 * mm,
            f"Page {self._pageNumber} of {page_count}",
        )
        self.restoreState()


def format_cell_value(val, fmt: ColumnFormat) -> str:
    if val is None or val == "":
        return "-"
    if fmt == ColumnFormat.CURRENCY:
        return f"{float(val):,.2f}"
    if fmt == ColumnFormat.INTEGER:
        return f"{int(val):,}"
    if fmt == ColumnFormat.PERCENT:
        return f"{float(val):.2f}%"
    return str(val)


def generate_report_pdf(output_path: str, shop: ShopProfile, payload: ReportPayload) -> str:
    defn = payload.definition
    pagesize = landscape(A4) if defn.landscape_pdf or len(defn.columns) > 6 else A4
    margin = 12 * mm

    doc = SimpleDocTemplate(
        output_path,
        pagesize=pagesize,
        leftMargin=margin,
        rightMargin=margin,
        topMargin=12 * mm,
        bottomMargin=20 * mm,
        title=f"CB POS - {defn.title}",
    )

    usable_w = pagesize[0] - (2 * margin)
    styles = getSampleStyleSheet()

    shop_title_style = ParagraphStyle(
        "ShopTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=15,
        leading=18,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#0F172A"),
    )
    shop_sub_style = ParagraphStyle(
        "ShopSub",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#334155"),
    )

    story = [
        Paragraph(shop.shop_name.upper(), shop_title_style),
        Spacer(1, 1.5 * mm),
        Paragraph(shop.address_line, shop_sub_style),
        Paragraph(
            f"Tel: {shop.phone_number}" + (f"  |  Reg: {shop.tax_reg_no}" if shop.tax_reg_no else ""),
            shop_sub_style,
        ),
        Spacer(1, 3 * mm),
        HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#0F172A"), spaceAfter=3 * mm),
    ]

    # Metadata & Title Bar
    gen_str = payload.generated_at.strftime("%Y-%m-%d %H:%M")
    period_str = f"{payload.filters_applied.start_date} to {payload.filters_applied.end_date}"
    meta_data = [
        [
            f"REPORT: {defn.title.upper()}",
            f"Category: {defn.category.value}   |   Period: {period_str}   |   Currency: {shop.currency_symbol}",
        ]
    ]
    meta_table = Table(meta_data, colWidths=[usable_w * 0.45, usable_w * 0.55])
    meta_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F1F5F9")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("FONTNAME", (0, 0), (0, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (0, 0), 10),
                ("FONTNAME", (1, 0), (1, 0), "Helvetica"),
                ("FONTSIZE", (1, 0), (1, 0), 8.5),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.extend([meta_table, Spacer(1, 3.5 * mm)])

    # 4-Box KPI Strip
    kpi_headers = [k.label.upper() for k in defn.kpis]
    kpi_vals = [format_cell_value(payload.kpi_values.get(k.key), k.fmt) for k in defn.kpis]
    kpi_table = Table([kpi_headers, kpi_vals], colWidths=[usable_w / 4.0] * 4)
    kpi_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 7),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#64748B")),
                ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 1), (-1, 1), 10.5),
                ("TEXTCOLOR", (0, 1), (-1, 1), colors.HexColor("#0F172A")),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.extend([kpi_table, Spacer(1, 4 * mm)])

    # Main Data Table + Totals Row
    total_weight = sum(c.width_weight for c in defn.columns)
    col_widths = [(c.width_weight / total_weight) * usable_w for c in defn.columns]

    table_rows = [[c.header for c in defn.columns]]
    for row in payload.rows:
        table_rows.append([format_cell_value(row.get(c.key), c.fmt) for c in defn.columns])

    # Append Grand Total Row
    totals_cells = []
    for idx, c in enumerate(defn.columns):
        if idx == 0:
            totals_cells.append(f"GRAND TOTAL ({len(payload.rows)} Rows)")
        elif c.key in payload.totals_row:
            totals_cells.append(format_cell_value(payload.totals_row[c.key], c.fmt))
        else:
            totals_cells.append("")
    table_rows.append(totals_cells)

    data_table = Table(table_rows, colWidths=col_widths, repeatRows=1)
    tbl_style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8.5),
        ("FONTNAME", (0, 1), (-1, -2), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -2), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#F8FAFC")]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
        # Grand Total Row Styling
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#E2E8F0")),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, -1), (-1, -1), 8.5),
        ("LINEABOVE", (0, -1), (-1, -1), 1.2, colors.HexColor("#0F172A")),
        ("TOPPADDING", (0, 0), (-1, -1), 4.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
    ]

    # Per-column horizontal alignment
    for col_idx, c in enumerate(defn.columns):
        if c.fmt in (ColumnFormat.CURRENCY, ColumnFormat.INTEGER, ColumnFormat.PERCENT):
            tbl_style.append(("ALIGN", (col_idx, 0), (col_idx, -1), "RIGHT"))
        elif c.fmt in (ColumnFormat.CENTER_TEXT, ColumnFormat.BADGE):
            tbl_style.append(("ALIGN", (col_idx, 0), (col_idx, -1), "CENTER"))
        else:
            tbl_style.append(("ALIGN", (col_idx, 0), (col_idx, -1), "LEFT"))

    data_table.setStyle(TableStyle(tbl_style))
    story.append(data_table)

    doc.build(
        story,
        canvasmaker=lambda *args, **kwargs: CeyByteWatermarkCanvas(*args, generated_str=gen_str, **kwargs),
    )
    return output_path
```

---

## 7. Step-by-Step Prompts to Feed Your AI Coding Agent

Instead of asking the AI agent to "build everything at once" (which causes context truncation), run these **5 sequential prompts**:

### Prompt 1: Data Models & 14-Report Registry

> _"Create `cb_pos/modules/reports/models.py` and `cb_pos/modules/reports/registry.py` implementing the exact dataclasses (`ReportDefinition`, `ColumnDef`, `KpiDef`, `FilterConfig`, `ShopProfile`, `FilterState`, `ReportPayload`) and all 14 report definitions from `REPORTS_MODULE_SPEC.md`. Ensure every currency, integer, and percentage column has the proper `ColumnFormat` and `AggType`."_

### Prompt 2: Off-Thread Repository & Aggregation Engine

> _"Create `cb_pos/modules/reports/repository.py` and `cb_pos/modules/reports/controller.py`. Map all 14 `report_id` keys to parameterized SQL queries against our existing CB POS database schema. Implement `QThreadPool` + `ReportQueryWorker` so queries never block the main UI thread, and compute `kpi_values` and `totals_row` dynamically based on each column's `AggType`."_

### Prompt 3: 2-View PyQt6 UI (`ReportsHubView` + `ReportViewerView`)

> _"Replace our existing split-sidebar Reports widget with `cb_pos/modules/reports/ui/reports_container.py` using a `QStackedWidget`. Page 0 (`hub_view.py`) must render the full-width 14-report card grid with category tabs, `QSettings` favorites (`★`), global date preset buttons, and quick Print/PDF/Excel icons on each card. Page 1 (`viewer_view.py`) must render the full-width viewer with a `← Back to Reports` header, contextual 1-row filter bar, 4 KPI summary cards, a full-width `QTableView` backed by `QAbstractTableModel` (`table_model.py`), and a pinned Grand Total bottom bar."_

### Prompt 4: Enterprise PDF Engine & Native A4 Print Preview

> _"Implement `cb_pos/modules/reports/exporters/pdf_exporter.py` using `CeyByteWatermarkCanvas` and `generate_report_pdf()` from `REPORTS_MODULE_SPEC.md`. Fetch `ShopProfile` (`shop_name`, `address_line`, `phone_number`) from our CB POS system settings table. Create `print_preview.py` so clicking 'Print' opens an A4 preview dialog with a physical printer selector and 'Print Now' / 'Save PDF' actions."_

### Prompt 5: Automated Verification & Unit Tests (`pytest`)

> _"Write a `tests/test_reports_module.py` suite using `pytest` and `pytest-qt` that: (1) validates all 14 `ReportDefinition` entries in `REPORT_REGISTRY`, (2) verifies `totals_row` and `MARGIN_PCT` / `UTIL_PCT` math on mock rows, and (3) generates a test PDF for each of the 14 reports into `tmp_path` verifying non-zero file size and multi-page rendering without errors."_

---

## 8. Enterprise QA Acceptance Checklist

Before merging the AI agent's changes into your main branch, verify these 6 points:

- [ ] **Zero Main-Thread Freezes:** Generating a report with 10,000+ rows shows a smooth loading state while the window remains draggable and responsive.
- [ ] **100% Width Table Utilization:** Opening _Customer Credit Report_ or _Profit & Loss Statement_ stretches columns cleanly across the full right pane with no empty gray gap on the right.

- [ ] **Dynamic Shop Header:** Updating the Shop Name, Address, or Phone Number in CB POS Settings immediately reflects centered at the top of all 14 printed/exported PDFs.
- [ ] **Right-Aligned Two-Decimal Accounting:** Every money column in both the UI and PDF formats as `150,000.00` (never `135.0` left-aligned).

- [ ] **Live Filter & KPI Sync:** Typing a customer name or invoice number in the Viewer search bar filters the table in `<50ms` and updates the 4 KPI cards and Grand Total row to match the filtered subset.
- [ ] **Footer Watermark on Every Page:** Multi-page PDFs show the `CBPOS | Powered by CeyByte.com` badge and `Page X of Y` cleanly at the bottom of every single page without overlapping table rows.

If you share how your current database queries or shop settings are structured in CB POS (e.g., SQLite/PostgreSQL and whether you use raw SQL or SQLAlchemy), I can tailor the `repository.py` SQL queries for all 14 reports to match your exact table names.
