"""
Dashboard view — real-time business insights with animated charts.

Layout:
  Row 1: Monthly Sales bar chart + Yearly Summary panel
  Row 2: Periodic Reports header with date range selector
  Row 3: Top Products table + Hourly Sales chart + Quick Stats
  Row 4: Top Categories donut + Top Customers horizontal bars
"""

import logging
from datetime import date

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QFrame,
    QTableWidget,
    QHeaderView,
    QTableWidgetItem,
    QToolButton,
    QDateEdit,
    QScrollArea,
)
from PyQt6.QtCore import Qt, QDate, QThread, pyqtSignal

from cbpos.ui.widgets.charts import (
    VerticalBarChart,
    DonutChart,
    HorizontalBarChart,
    MONTH_COLORS,
    HOURLY_COLORS,
)
from cbpos.core.utils.formatters import format_currency
from cbpos.core.services.tax_service import TaxService
from cbpos.i18n import _t, register_language_callback, unregister_language_callback

logger = logging.getLogger(__name__)


class _YearlyWorker(QThread):
    """Fetches yearly dashboard data (monthly chart + summary) off the UI thread."""

    finished = pyqtSignal(list, dict)  # monthly, summary
    error_occurred = pyqtSignal(str)

    def __init__(self, year: int) -> None:
        super().__init__()
        self._year = year

    def run(self) -> None:
        from cbpos.core.services.dashboard_service import DashboardService

        try:
            monthly = DashboardService.get_monthly_sales(self._year)
            summary = DashboardService.get_yearly_summary(self._year)
            self.finished.emit(monthly, summary)
        except Exception as e:
            logger.exception("Failed to load yearly dashboard data")
            self.error_occurred.emit(str(e))


class _PeriodicWorker(QThread):
    """Fetches period-scoped data (products, hourly, stats, categories, customers, tax)."""

    finished = pyqtSignal(list, list, dict, list, list, dict)
    error_occurred = pyqtSignal(str)

    def __init__(self, start_date: date, end_date: date) -> None:
        super().__init__()
        self._start = start_date
        self._end = end_date

    def run(self) -> None:
        from cbpos.core.services.dashboard_service import DashboardService

        try:
            products = DashboardService.get_period_top_products(self._start, self._end)
            hourly = DashboardService.get_hourly_sales(self._start, self._end)
            stats = DashboardService.get_period_stats(self._start, self._end)
            categories = DashboardService.get_top_categories(self._start, self._end)
            customers = DashboardService.get_top_customers(self._start, self._end)
            tax_summary = DashboardService.get_today_tax_summary()
            self.finished.emit(products, hourly, stats, categories, customers, tax_summary)
        except Exception as e:
            logger.exception("Failed to load periodic dashboard data")
            self.error_occurred.emit(str(e))


class DashboardView(QWidget):
    def __init__(self):
        super().__init__()
        self._current_year = date.today().year
        self.init_ui()

        from cbpos.ui.widgets.loading_overlay import LoadingOverlay

        self._monthly_overlay = LoadingOverlay(self.monthly_panel)

        self.retranslate_ui()
        register_language_callback(self.retranslate_ui)
        self.destroyed.connect(lambda: unregister_language_callback(self.retranslate_ui))

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def init_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Scroll area for the dashboard content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("DashboardScroll")
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # === ROW 1: Monthly Chart + Yearly Summary ===
        row1 = QHBoxLayout()
        row1.setSpacing(16)
        self._build_monthly_panel(row1)
        self._build_yearly_summary(row1)
        layout.addLayout(row1, 3)

        # === ROW 2: Periodic Reports Header ===
        self._build_period_header(layout)

        # === ROW 3: Top Products + Hourly Sales + Quick Stats + Tax Today ===
        row3 = QHBoxLayout()
        row3.setSpacing(16)
        self._build_top_products_panel(row3)
        self._build_hourly_panel(row3)
        self._build_quick_stats_panel(row3)
        self._build_tax_today_panel(row3)
        layout.addLayout(row3, 3)

        # === ROW 4: Categories Donut + Top Customers ===
        row4 = QHBoxLayout()
        row4.setSpacing(16)
        self._build_categories_panel(row4)
        self._build_customers_panel(row4)
        layout.addLayout(row4, 3)

        scroll.setWidget(container)
        outer.addWidget(scroll)

    # --- Row 1: Monthly Chart ---
    def _build_monthly_panel(self, parent_layout: QHBoxLayout) -> None:
        panel = QFrame()
        self.monthly_panel = panel
        panel.setObjectName("MonthlyChartPanel")
        vbox = QVBoxLayout(panel)
        vbox.setContentsMargins(16, 12, 16, 12)
        vbox.setSpacing(8)

        # Header: title + year nav
        header = QHBoxLayout()
        self.lbl_monthly_title = QLabel()
        self.lbl_monthly_title.setObjectName("PanelTitle")
        header.addWidget(self.lbl_monthly_title)
        header.addStretch()

        self.btn_prev_year = QToolButton()
        self.btn_prev_year.setText("\u25c0")
        self.btn_prev_year.setObjectName("YearNavButton")
        self.btn_prev_year.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_prev_year.clicked.connect(lambda: self._change_year(-1))
        header.addWidget(self.btn_prev_year)

        self.btn_next_year = QToolButton()
        self.btn_next_year.setText("\u25b6")
        self.btn_next_year.setObjectName("YearNavButton")
        self.btn_next_year.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_next_year.clicked.connect(lambda: self._change_year(1))
        header.addWidget(self.btn_next_year)

        vbox.addLayout(header)

        self.monthly_chart = VerticalBarChart()
        vbox.addWidget(self.monthly_chart, 1)

        panel.setMinimumWidth(220)  # keep charts legible when the row wraps (#203)
        parent_layout.addWidget(panel, 4)

    # --- Row 1: Yearly Summary ---
    def _build_yearly_summary(self, parent_layout: QHBoxLayout) -> None:
        panel = QFrame()
        panel.setObjectName("YearlySummaryPanel")
        vbox = QVBoxLayout(panel)
        vbox.setContentsMargins(20, 20, 20, 20)
        vbox.setSpacing(6)

        self.lbl_total_sales_title = QLabel()
        self.lbl_total_sales_title.setObjectName("SummaryLabel")
        vbox.addWidget(self.lbl_total_sales_title)

        self.lbl_yearly_total = QLabel("Rs. 0")
        self.lbl_yearly_total.setObjectName("SummaryBigValue")
        # 32px bold with zero safety net (no wrap/elide/max-width) clipped on
        # at least one real device for a value that rendered fine in every
        # offscreen test here (#269) -- word-wrap can't clip, it can only
        # ever fall back to a second line, which this panel has room for.
        self.lbl_yearly_total.setWordWrap(True)
        vbox.addWidget(self.lbl_yearly_total)

        vbox.addSpacing(16)

        self.lbl_top_month_title = QLabel()
        self.lbl_top_month_title.setObjectName("SummaryLabel")
        vbox.addWidget(self.lbl_top_month_title)

        self.lbl_top_month = QLabel("-")
        self.lbl_top_month.setObjectName("SummaryHighlight")
        vbox.addWidget(self.lbl_top_month)

        self.lbl_top_month_total = QLabel("Rs. 0")
        self.lbl_top_month_total.setObjectName("SummarySubValue")
        vbox.addWidget(self.lbl_top_month_total)

        vbox.addStretch()
        # Wider than the shared 220px floor (#203) -- gives the 32px bold
        # yearly total headroom for a typical 6-7 digit value before ever
        # needing the word-wrap fallback above to kick in (#269).
        panel.setMinimumWidth(260)
        parent_layout.addWidget(panel, 1)

    # --- Row 2: Period Header ---
    def _build_period_header(self, parent_layout: QVBoxLayout) -> None:
        header = QFrame()
        header.setObjectName("PeriodHeader")
        header.setMinimumHeight(50)
        hbox = QHBoxLayout(header)
        hbox.setContentsMargins(16, 8, 16, 8)
        hbox.setSpacing(12)

        self.lbl_period = QLabel()
        self.lbl_period.setObjectName("PanelTitle")
        hbox.addWidget(self.lbl_period)

        hbox.addStretch()

        self.date_from = QDateEdit()
        self.date_from.setObjectName("PeriodDateEdit")
        self.date_from.setCalendarPopup(True)
        self.date_from.setDisplayFormat("dd.MM.yyyy")
        self.date_from.setDate(QDate(date.today().year, 1, 1))
        hbox.addWidget(self.date_from)

        dash = QLabel("\u2014")
        dash.setObjectName("PeriodDash")
        hbox.addWidget(dash)

        self.date_to = QDateEdit()
        self.date_to.setObjectName("PeriodDateEdit")
        self.date_to.setCalendarPopup(True)
        self.date_to.setDisplayFormat("dd.MM.yyyy")
        self.date_to.setDate(QDate.currentDate())
        hbox.addWidget(self.date_to)

        self.btn_refresh = QToolButton()
        self.btn_refresh.setText("\u21bb")
        self.btn_refresh.setObjectName("PeriodRefreshBtn")
        self.btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh.clicked.connect(self.refresh_periodic)
        hbox.addWidget(self.btn_refresh)

        parent_layout.addWidget(header)

    # --- Row 3: Top Products Table ---
    def _build_top_products_panel(self, parent_layout: QHBoxLayout) -> None:
        panel = QFrame()
        panel.setObjectName("TopProductsPanel")
        vbox = QVBoxLayout(panel)
        vbox.setContentsMargins(16, 12, 16, 12)
        vbox.setSpacing(8)

        header = QHBoxLayout()
        self.lbl_top_products = QLabel()
        self.lbl_top_products.setObjectName("PanelTitle")
        header.addWidget(self.lbl_top_products)
        header.addStretch()

        self.lbl_top_products_sub = QLabel()
        self.lbl_top_products_sub.setObjectName("PanelSubtitle")
        header.addWidget(self.lbl_top_products_sub)
        vbox.addLayout(header)

        self.products_table = QTableWidget()
        self.products_table.setObjectName("DashboardTable")
        self.products_table.setColumnCount(2)
        self.products_table.setHorizontalHeaderLabels(["", ""])
        self.products_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.products_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.products_table.setColumnWidth(1, 110)
        self.products_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.products_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.products_table.verticalHeader().setVisible(False)
        self.products_table.setShowGrid(False)
        vbox.addWidget(self.products_table, 1)

        panel.setMinimumWidth(220)  # keep charts legible when the row wraps (#203)
        parent_layout.addWidget(panel, 2)

    # --- Row 3: Hourly Sales Chart ---
    def _build_hourly_panel(self, parent_layout: QHBoxLayout) -> None:
        panel = QFrame()
        panel.setObjectName("HourlySalesPanel")
        vbox = QVBoxLayout(panel)
        vbox.setContentsMargins(16, 12, 16, 12)
        vbox.setSpacing(8)

        self.lbl_hourly_sales = QLabel()
        self.lbl_hourly_sales.setObjectName("PanelTitle")
        vbox.addWidget(self.lbl_hourly_sales)

        self.hourly_chart = VerticalBarChart()
        vbox.addWidget(self.hourly_chart, 1)

        panel.setMinimumWidth(220)  # keep charts legible when the row wraps (#203)
        parent_layout.addWidget(panel, 2)

    # --- Row 3: Quick Stats ---
    def _build_quick_stats_panel(self, parent_layout: QHBoxLayout) -> None:
        panel = QFrame()
        panel.setObjectName("QuickStatsPanel")
        vbox = QVBoxLayout(panel)
        vbox.setContentsMargins(20, 16, 20, 16)
        vbox.setSpacing(4)

        # Avg Order
        self.lbl_avg_order_title = QLabel()
        self.lbl_avg_order_title.setObjectName("StatLabel")
        vbox.addWidget(self.lbl_avg_order_title)

        self.lbl_avg_order = QLabel("Rs. 0")
        self.lbl_avg_order.setObjectName("StatBigValue")
        vbox.addWidget(self.lbl_avg_order)

        vbox.addSpacing(14)

        # Items Sold
        self.lbl_items_sold_title = QLabel()
        self.lbl_items_sold_title.setObjectName("StatLabel")
        vbox.addWidget(self.lbl_items_sold_title)

        self.lbl_items_sold = QLabel("0")
        self.lbl_items_sold.setObjectName("StatValue")
        vbox.addWidget(self.lbl_items_sold)

        vbox.addSpacing(14)

        # Unique Customers
        self.lbl_unique_customers_title = QLabel()
        self.lbl_unique_customers_title.setObjectName("StatLabel")
        vbox.addWidget(self.lbl_unique_customers_title)

        self.lbl_unique_customers = QLabel("0")
        self.lbl_unique_customers.setObjectName("StatValue")
        vbox.addWidget(self.lbl_unique_customers)

        vbox.addSpacing(14)

        # Transactions
        self.lbl_txn_title = QLabel()
        self.lbl_txn_title.setObjectName("StatLabel")
        vbox.addWidget(self.lbl_txn_title)

        self.lbl_txn_count = QLabel("0")
        self.lbl_txn_count.setObjectName("StatValue")
        vbox.addWidget(self.lbl_txn_count)

        vbox.addStretch()
        panel.setMinimumWidth(220)  # keep charts legible when the row wraps (#203)
        parent_layout.addWidget(panel, 1)

    # --- Row 3: Tax Today ---
    def _build_tax_today_panel(self, parent_layout: QHBoxLayout) -> None:
        panel = QFrame()
        panel.setObjectName("TaxTodayPanel")
        vbox = QVBoxLayout(panel)
        vbox.setContentsMargins(20, 16, 20, 16)
        vbox.setSpacing(4)

        # VAT
        self.lbl_vat_title = QLabel()
        self.lbl_vat_title.setObjectName("StatLabel")
        vbox.addWidget(self.lbl_vat_title)

        self.lbl_tax_vat = QLabel("Rs. 0")
        self.lbl_tax_vat.setObjectName("StatBigValue")
        vbox.addWidget(self.lbl_tax_vat)

        vbox.addSpacing(14)

        # SSCL
        self.lbl_sscl_title = QLabel()
        self.lbl_sscl_title.setObjectName("StatLabel")
        vbox.addWidget(self.lbl_sscl_title)

        self.lbl_tax_sscl = QLabel("Rs. 0")
        self.lbl_tax_sscl.setObjectName("StatValue")
        vbox.addWidget(self.lbl_tax_sscl)

        vbox.addSpacing(14)

        # Net Revenue
        self.lbl_net_revenue_title = QLabel()
        self.lbl_net_revenue_title.setObjectName("StatLabel")
        vbox.addWidget(self.lbl_net_revenue_title)

        self.lbl_net_revenue = QLabel("Rs. 0")
        self.lbl_net_revenue.setObjectName("StatValue")
        vbox.addWidget(self.lbl_net_revenue)

        vbox.addStretch()
        self.tax_today_panel = panel
        panel.setMinimumWidth(220)  # keep charts legible when the row wraps (#203)
        parent_layout.addWidget(panel, 1)

    # --- Row 4: Categories Donut ---
    def _build_categories_panel(self, parent_layout: QHBoxLayout) -> None:
        panel = QFrame()
        panel.setObjectName("TopCategoriesPanel")
        vbox = QVBoxLayout(panel)
        vbox.setContentsMargins(16, 12, 16, 12)
        vbox.setSpacing(8)

        header = QHBoxLayout()
        self.lbl_top_groups = QLabel()
        self.lbl_top_groups.setObjectName("PanelTitle")
        header.addWidget(self.lbl_top_groups)
        header.addStretch()
        self.lbl_top_groups_sub = QLabel()
        self.lbl_top_groups_sub.setObjectName("PanelSubtitle")
        header.addWidget(self.lbl_top_groups_sub)
        vbox.addLayout(header)

        self.category_chart = DonutChart()
        vbox.addWidget(self.category_chart, 1)

        panel.setMinimumWidth(220)  # keep charts legible when the row wraps (#203)
        parent_layout.addWidget(panel, 1)

    # --- Row 4: Top Customers ---
    def _build_customers_panel(self, parent_layout: QHBoxLayout) -> None:
        panel = QFrame()
        panel.setObjectName("TopCustomersPanel")
        vbox = QVBoxLayout(panel)
        vbox.setContentsMargins(16, 12, 16, 12)
        vbox.setSpacing(8)

        header = QHBoxLayout()
        self.lbl_top_customers = QLabel()
        self.lbl_top_customers.setObjectName("PanelTitle")
        header.addWidget(self.lbl_top_customers)
        header.addStretch()
        self.lbl_top_customers_sub = QLabel()
        self.lbl_top_customers_sub.setObjectName("PanelSubtitle")
        header.addWidget(self.lbl_top_customers_sub)
        vbox.addLayout(header)

        self.customer_chart = HorizontalBarChart()
        vbox.addWidget(self.customer_chart, 1)

        panel.setMinimumWidth(220)  # keep charts legible when the row wraps (#203)
        parent_layout.addWidget(panel, 1)

    # ------------------------------------------------------------------
    # Translation
    # ------------------------------------------------------------------

    def retranslate_ui(self) -> None:
        """Update all widget text from the translation system."""
        self.lbl_monthly_title.setText(_t("dashboard.monthly_sales", year=self._current_year))
        self.lbl_total_sales_title.setText(_t("dashboard.total_sales"))
        self.lbl_top_month_title.setText(_t("dashboard.top_performing_month"))
        self.lbl_period.setText(_t("dashboard.periodic_reports"))
        self.lbl_top_products.setText(_t("dashboard.top_products"))
        self.lbl_top_products_sub.setText(_t("dashboard.by_revenue"))
        self.products_table.setHorizontalHeaderLabels([_t("dashboard.header_product"), _t("dashboard.header_total")])
        self.lbl_hourly_sales.setText(_t("dashboard.hourly_sales"))
        self.lbl_avg_order_title.setText(_t("dashboard.avg_order_value"))
        self.lbl_items_sold_title.setText(_t("dashboard.items_sold"))
        self.lbl_unique_customers_title.setText(_t("dashboard.unique_customers"))
        self.lbl_txn_title.setText(_t("dashboard.transactions"))
        self.lbl_vat_title.setText(_t("dashboard.vat_collected"))
        self.lbl_sscl_title.setText(_t("dashboard.sscl_liability"))
        self.lbl_net_revenue_title.setText(_t("dashboard.net_revenue"))
        self.lbl_top_groups.setText(_t("dashboard.top_selling_groups"))
        self.lbl_top_groups_sub.setText(_t("dashboard.categories_in_period"))
        self.lbl_top_customers.setText(_t("dashboard.top_customers"))
        self.lbl_top_customers_sub.setText(_t("dashboard.by_spend"))

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def showEvent(self, event) -> None:  # noqa: N802
        """Auto-refresh when dashboard becomes visible."""
        super().showEvent(event)
        self.refresh_all()

    def refresh_all(self) -> None:
        """Refresh both yearly and periodic data."""
        self.tax_today_panel.setVisible(TaxService.is_vat_active())
        self._refresh_yearly()
        self.refresh_periodic()

    def _refresh_yearly(self) -> None:
        """Refresh yearly data (Row 1: monthly chart + summary)."""
        self.lbl_monthly_title.setText(_t("dashboard.monthly_sales", year=self._current_year))
        self.btn_prev_year.setEnabled(False)
        self.btn_next_year.setEnabled(False)
        self.lbl_yearly_total.setText(_t("dashboard.loading"))
        self._monthly_overlay.show_loading(_t("dashboard.loading"))

        self._yearly_worker = _YearlyWorker(self._current_year)
        self._yearly_worker.finished.connect(self._on_yearly_ready)
        self._yearly_worker.error_occurred.connect(self._on_yearly_error)
        self._yearly_worker.start()

    def refresh_periodic(self) -> None:
        """Refresh period-scoped data (Rows 3-4) based on the date range."""
        sd = self.date_from.date().toPyDate()
        ed = self.date_to.date().toPyDate()

        self.lbl_period.setText(
            _t(
                "dashboard.periodic_reports_range",
                start=sd.strftime("%d.%m.%Y"),
                end=ed.strftime("%d.%m.%Y"),
            )
        )
        self.btn_refresh.setEnabled(False)
        self.btn_refresh.setText("\u231b")  # hourglass while loading
        # Prevent changing the range mid-refresh (#214) -- a rapid second
        # change would otherwise start a second _PeriodicWorker while the
        # first is still in flight.
        self.date_from.setEnabled(False)
        self.date_to.setEnabled(False)
        self.lbl_avg_order.setText(_t("dashboard.loading"))

        self._periodic_worker = _PeriodicWorker(sd, ed)
        self._periodic_worker.finished.connect(self._on_periodic_ready)
        self._periodic_worker.error_occurred.connect(self._on_periodic_error)
        self._periodic_worker.start()

    def _change_year(self, delta: int) -> None:
        self._current_year += delta
        self._refresh_yearly()

    def _on_yearly_ready(self, monthly: list, summary: dict) -> None:
        """Handle yearly data from worker thread."""
        self.btn_prev_year.setEnabled(True)
        self.btn_next_year.setEnabled(True)
        self._monthly_overlay.hide_loading()
        chart_data = [
            {
                "label": m["label"],
                "value": m["total"],
                "color": MONTH_COLORS[m["month"] - 1],
            }
            for m in monthly
        ]
        self.monthly_chart.set_data(chart_data)

        self.lbl_yearly_total.setText(format_currency(summary["total"]))
        self.lbl_top_month.setText(summary["top_month_name"].upper())
        self.lbl_top_month_total.setText(format_currency(summary["top_month_total"]))

    def _on_yearly_error(self, message: str) -> None:
        """Re-enable controls left disabled mid-load when the worker fails (#270)."""
        self.btn_prev_year.setEnabled(True)
        self.btn_next_year.setEnabled(True)
        self._monthly_overlay.hide_loading()
        self.lbl_yearly_total.setText(_t("dashboard.load_error"))

    def _on_periodic_ready(
        self, products: list, hourly: list, stats: dict, categories: list, customers: list, tax_summary: dict
    ) -> None:
        """Handle periodic data from worker thread."""
        self.btn_refresh.setEnabled(True)
        self.btn_refresh.setText("\u21bb")
        self.date_from.setEnabled(True)
        self.date_to.setEnabled(True)
        # Top Products table
        self.products_table.setRowCount(len(products))
        for row, p in enumerate(products):
            self.products_table.setItem(row, 0, QTableWidgetItem(p["name"]))
            item = QTableWidgetItem(format_currency(p["total"]))
            item.setTextAlignment(int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))
            self.products_table.setItem(row, 1, item)

        # Hourly Sales chart
        hourly_with_data = [h for h in hourly if h["total"] > 0]
        if not hourly_with_data:
            hourly_with_data = hourly
        hourly_chart_data = [
            {
                "label": h["label"],
                "value": h["total"],
                "color": HOURLY_COLORS[i % len(HOURLY_COLORS)],
            }
            for i, h in enumerate(hourly_with_data)
        ]
        self.hourly_chart.set_data(hourly_chart_data)

        # Quick Stats — items_sold is now Decimal, format with commas
        self.lbl_avg_order.setText(format_currency(stats["avg_order"]))
        items = stats["items_sold"]
        items_text = format(items, ",.3f") if items % 1 else format(int(items), ",")
        self.lbl_items_sold.setText(items_text)
        self.lbl_unique_customers.setText(str(stats["unique_customers"]))
        self.lbl_txn_count.setText(f'{stats["txn_count"]:,}')  # noqa: E231

        # Categories donut
        self.category_chart.set_data([{"label": c["name"], "value": c["total"]} for c in categories])

        # Top Customers
        self.customer_chart.set_data([{"label": c["name"], "value": c["total"]} for c in customers])

        # Tax Today
        self.lbl_tax_vat.setText(format_currency(tax_summary["vat"]))
        self.lbl_tax_sscl.setText(format_currency(tax_summary["sscl"]))
        self.lbl_net_revenue.setText(format_currency(tax_summary["net_revenue"]))

    def _on_periodic_error(self, message: str) -> None:
        """Re-enable controls left disabled mid-load when the worker fails (#270)."""
        self.btn_refresh.setEnabled(True)
        self.btn_refresh.setText("↻")
        self.date_from.setEnabled(True)
        self.date_to.setEnabled(True)
        self.lbl_avg_order.setText(_t("dashboard.load_error"))
