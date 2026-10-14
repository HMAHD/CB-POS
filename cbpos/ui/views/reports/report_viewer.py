"""Report viewer view for browsing, running, and exporting reports."""

import pandas as pd
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from cbpos.core.reports.registry import ReportRegistry
from cbpos.core.services.export_service import ExportService
from cbpos.core.services.tax_service import TaxService
from cbpos.i18n import _t, register_language_callback
from cbpos.ui.resources.icons import Icons
from cbpos.ui.views.reports.filter_widget import FilterWidget
from cbpos.ui.views.reports.pandas_model import PandasModel
from cbpos.ui.widgets.empty_state_widget import EmptyStateWidget
from cbpos.ui.widgets.loading_overlay import LoadingOverlay
from cbpos.ui.widgets.pagination_widget import PaginationWidget
from cbpos.ui.workers import ExportWorker, ReportEmailWorker, ReportPrintWorker, start_background_job


class ReportWorker(QThread):
    """Background thread for report generation to avoid freezing the UI."""

    result = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, report, filters):
        """Initialize the worker with a report instance and its filter values."""
        super().__init__()
        self.finished.connect(self.deleteLater)
        self.report = report
        self.filters = filters

    def run(self):
        """Generate the report's DataFrame and emit the result, or emit an error message on failure."""
        try:
            df = self.report.generate(self.filters)
            self.result.emit(df)
        except Exception as e:
            self.error.emit(str(e))


class ReportViewer(QWidget):
    """Report viewer view listing available reports, running them, and displaying results."""

    def __init__(self):
        """Initialize the view, register language callbacks, and build the UI."""
        super().__init__()
        self.setObjectName("ReportViewer")
        self.registry = ReportRegistry()
        self.export_service = ExportService()
        self.current_report = None
        self._full_df = pd.DataFrame()
        self.init_ui()

        # Register for language changes
        register_language_callback(self.retranslate_ui, owner=self)

    def init_ui(self):
        """Build the sidebar, filter bar, data table, and action bar layout."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        from cbpos.ui.widgets.page_header import PageHeader

        self._page_header = PageHeader(icon_name=Icons.REPORTS)
        header_row = QHBoxLayout()
        header_row.setContentsMargins(16, 12, 16, 0)
        header_row.addWidget(self._page_header)
        main_layout.addLayout(header_row)

        self.splitter = splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("ReportSplitter")

        # ── LEFT: Sidebar Panel ──
        sidebar = QWidget()
        sidebar.setObjectName("ReportSidebarPanel")
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)

        self.sidebar_title = QLabel("")
        self.sidebar_title.setObjectName("ReportSidebarTitle")
        sidebar_layout.addWidget(self.sidebar_title)

        # Scrollable report navigation
        scroll = QScrollArea()
        scroll.setObjectName("ReportSidebarScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        nav_container = QWidget()
        nav_container.setObjectName("ReportNavContainer")
        self._nav_layout = QVBoxLayout(nav_container)
        self._nav_layout.setContentsMargins(12, 8, 12, 12)
        self._nav_layout.setSpacing(4)

        self._populate_sidebar()
        self._nav_layout.addStretch()

        scroll.setWidget(nav_container)
        scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sidebar_layout.addWidget(scroll, 1)

        splitter.addWidget(sidebar)

        # ── RIGHT: Content Panel ──
        content = QWidget()
        content.setObjectName("ReportContentPanel")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # Report Header (hidden until report selected)
        self.report_header = QWidget()
        self.report_header.setObjectName("ReportHeader")
        header_layout = QVBoxLayout(self.report_header)
        header_layout.setContentsMargins(24, 16, 24, 16)
        header_layout.setSpacing(2)

        self.report_title = QLabel()
        self.report_title.setObjectName("ReportTitle")
        header_layout.addWidget(self.report_title)

        self.report_description = QLabel()
        self.report_description.setObjectName("ReportDescription")
        header_layout.addWidget(self.report_description)

        self.report_header.setVisible(False)
        content_layout.addWidget(self.report_header)

        # Filter Bar (hidden until report selected)
        self.filter_bar = QWidget()
        self.filter_bar.setObjectName("ReportFilterBar")
        filter_layout = QHBoxLayout(self.filter_bar)
        filter_layout.setContentsMargins(24, 10, 24, 10)

        self.filter_widget = FilterWidget()
        filter_layout.addWidget(self.filter_widget)

        self.btn_run = QPushButton("")
        self.btn_run.setObjectName("RunReportBtn")
        self.btn_run.clicked.connect(self.run_report)
        self.btn_run.setEnabled(False)
        self.btn_run.setCursor(Qt.CursorShape.PointingHandCursor)
        filter_layout.addWidget(self.btn_run)

        self.filter_bar.setVisible(False)
        content_layout.addWidget(self.filter_bar)

        # Content Stack (empty state / data table)
        self.content_stack = QStackedWidget()
        self.content_stack.setObjectName("ReportContentStack")

        # Page 0: Empty State -- the shared EmptyStateWidget (#254) instead
        # of this screen's own custom-painted icon + label pair.
        self.empty_state_widget = EmptyStateWidget(Icons.REPORTS)
        self.content_stack.addWidget(self.empty_state_widget)

        # Page 1: Data Table
        self.table_view = QTableView()
        self.table_view.setObjectName("ReportDataView")
        self.table_model = PandasModel()
        self.table_view.setModel(self.table_model)
        # Report columns vary per report type (different reports have
        # different columns entirely), so there's no fixed per-column map to
        # apply -- but the previous combination of Interactive (fixed once,
        # from often-empty initial content) + stretchLastSection (forcing
        # whichever column is last to bloat regardless of its content) meant
        # every report's "detail" column looked bare while a short column
        # like TYPE or STATUS absorbed all the extra width. ResizeToContents
        # sizes every column to its real, current content instead.
        self.table_view.horizontalHeader().setStretchLastSection(False)
        self.table_view.horizontalHeader().setMinimumSectionSize(80)
        self.table_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table_view.setAlternatingRowColors(True)
        self.table_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table_view.verticalHeader().setVisible(False)
        self.content_stack.addWidget(self.table_view)

        self.content_stack.setCurrentIndex(0)
        content_layout.addWidget(self.content_stack, 1)

        # Pagination
        self.pagination = PaginationWidget()
        self.pagination.page_changed.connect(self._on_page_changed)
        self.pagination.setVisible(False)
        content_layout.addWidget(self.pagination)

        # Action Bar (hidden until data exists)
        self.action_bar = QWidget()
        self.action_bar.setObjectName("ReportActionBar")
        action_layout = QHBoxLayout(self.action_bar)
        action_layout.setContentsMargins(24, 10, 24, 10)

        self.row_count_label = QLabel()
        self.row_count_label.setObjectName("ReportRowCount")
        action_layout.addWidget(self.row_count_label)

        action_layout.addStretch()

        self.btn_print = QPushButton("")
        self.btn_print.setObjectName("ReportPrintBtn")
        self.btn_print.clicked.connect(self.print_report)
        self.btn_print.setCursor(Qt.CursorShape.PointingHandCursor)
        action_layout.addWidget(self.btn_print)

        self.btn_export_excel = QPushButton("")
        self.btn_export_excel.setObjectName("ReportExportExcelBtn")
        self.btn_export_excel.clicked.connect(self.export_excel)
        self.btn_export_excel.setCursor(Qt.CursorShape.PointingHandCursor)
        action_layout.addWidget(self.btn_export_excel)

        self.btn_export_pdf = QPushButton("")
        self.btn_export_pdf.setObjectName("ReportExportPdfBtn")
        self.btn_export_pdf.clicked.connect(self.export_pdf)
        self.btn_export_pdf.setCursor(Qt.CursorShape.PointingHandCursor)
        action_layout.addWidget(self.btn_export_pdf)

        self.btn_email = QPushButton("")
        self.btn_email.setObjectName("ReportEmailBtn")
        self.btn_email.clicked.connect(self.email_report)
        self.btn_email.setCursor(Qt.CursorShape.PointingHandCursor)
        action_layout.addWidget(self.btn_email)

        self.action_bar.setVisible(False)
        content_layout.addWidget(self.action_bar)

        splitter.addWidget(content)
        splitter.setSizes([280, 720])
        splitter.setHandleWidth(1)
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)
        sidebar.setMinimumWidth(260)
        # Without explicit stretch factors, a plain QSplitter keeps its
        # panels' proportional ratio as the window resizes -- on a large
        # monitor that stretched a panel whose content is short labels
        # into far more width than it needs, starving the report content
        # pane (the one that actually needs the room) of extra space (#286).
        sidebar.setMaximumWidth(340)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        main_layout.addWidget(splitter, 1)

        # Loading overlay
        self._overlay = LoadingOverlay(self)

        # Apply translations
        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        """Set all translatable text using _t()."""
        self._page_header.set_title(_t("management.sidebar_reports"))
        self.sidebar_title.setText(_t("report_viewer.sidebar_title"))
        self.btn_run.setText(_t("report_viewer.btn_run"))
        self.empty_state_widget.set_title(_t("report_viewer.empty_title"))
        self.empty_state_widget.set_subtitle(_t("report_viewer.empty_subtitle"))
        self.btn_print.setText(_t("common.print"))
        self.btn_export_excel.setText(_t("report_viewer.btn_excel"))
        self.btn_export_pdf.setText(_t("report_viewer.btn_pdf"))
        self.btn_email.setText(_t("common.email"))

    def showEvent(self, event) -> None:
        """Ensure splitter sizes and layouts are properly computed on display."""
        super().showEvent(event)
        sizes = self.splitter.sizes()
        if sizes and sizes[0] < 260:
            remaining = sum(sizes) - 280
            self.splitter.setSizes([280, max(remaining, 100)])
        if self.layout() is not None:
            self.layout().activate()

    # ------------------------------------------------------------------
    # Sidebar construction
    # ------------------------------------------------------------------

    def _populate_sidebar(self) -> None:
        """Build category sections with report buttons."""
        categories = self.registry.get_all_categories()

        vat_active = TaxService.is_vat_active()
        rendered_any = False

        for _idx, category in enumerate(categories):
            all_reports = self.registry.get_reports_by_category(category)
            # Filter out VAT-only reports when VAT is not active
            reports = [r for r in all_reports if not getattr(r, "requires_vat", False) or vat_active]
            if not reports:
                continue

            # Category header row: label + count badge
            if rendered_any:
                self._nav_layout.addSpacing(8)
            rendered_any = True

            cat_row = QHBoxLayout()
            cat_row.setContentsMargins(6, 8, 6, 4)

            cat_label = QLabel(category.upper())
            cat_label.setObjectName("ReportCategoryLabel")
            cat_row.addWidget(cat_label)

            cat_row.addStretch()

            count_badge = QLabel(str(len(reports)))
            count_badge.setObjectName("ReportCategoryCount")
            count_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            count_badge.setFixedWidth(24)
            cat_row.addWidget(count_badge)

            self._nav_layout.addLayout(cat_row)

            # Report item buttons
            for report in reports:
                btn = QPushButton(report.name)
                btn.setObjectName("ReportNavItem")
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.setSizePolicy(
                    QSizePolicy.Policy.Expanding,
                    QSizePolicy.Policy.Fixed,
                )
                btn.setProperty("report_id", report.id)
                btn.setCheckable(True)
                btn.setAutoExclusive(True)
                btn.clicked.connect(lambda checked, r=report.id: self._on_nav_clicked(r))
                self._nav_layout.addWidget(btn)

    def _on_nav_clicked(self, report_id: str) -> None:
        """Handle sidebar report button click."""
        self.current_report = self.registry.get_report_by_id(report_id)
        if not self.current_report:
            return

        # Show header
        self.report_title.setText(self.current_report.name)
        self.report_description.setText(self.current_report.category)
        self.report_header.setVisible(True)

        # Show filter bar
        self.filter_widget.build_filters(self.current_report.get_filter_definitions())
        self.btn_run.setEnabled(True)
        self.filter_bar.setVisible(True)

        # Reset content to empty state
        self._full_df = pd.DataFrame()
        self.table_model.set_data(pd.DataFrame())
        self.content_stack.setCurrentIndex(0)
        self.action_bar.setVisible(False)
        self.pagination.setVisible(False)

    # ------------------------------------------------------------------
    # Report execution
    # ------------------------------------------------------------------

    def run_report(self):
        """Run the currently selected report in a background thread using the active filter values."""
        if not self.current_report:
            return

        filters = self.filter_widget.get_filter_values()

        self._overlay.show_loading(_t("report_viewer.generating"))
        self.btn_run.setEnabled(False)

        self._report_worker = ReportWorker(self.current_report, filters)
        self._report_worker.result.connect(self._on_report_finished)
        self._report_worker.error.connect(self._on_report_error)
        start_background_job(self._report_worker)

    def _on_report_finished(self, df: pd.DataFrame):
        self._overlay.hide_loading()
        self.btn_run.setEnabled(True)
        self._full_df = df
        has_data = not df.empty

        if has_data:
            self.pagination.set_total(len(df))
            self._show_current_page()
            self.content_stack.setCurrentIndex(1)
            row_count = len(df)
            self.row_count_label.setText(_t("common.row_count", count=row_count))
            self.action_bar.setVisible(True)
        else:
            self.table_model.set_data(df)
            self.content_stack.setCurrentIndex(0)
            self.action_bar.setVisible(False)
            self.pagination.setVisible(False)
            QMessageBox.information(
                self,
                _t("report_viewer.report_title"),
                _t("report_viewer.no_data"),
            )

    def _show_current_page(self) -> None:
        """Display the current page slice of the full DataFrame."""
        start = self.pagination.start_index
        end = self.pagination.end_index
        page_df = self._full_df.iloc[start:end].reset_index(drop=True)
        render_hints = self.current_report.get_render_hints() if self.current_report else {}
        self.table_model.set_data(page_df, render_hints=render_hints)

    def _on_page_changed(self, _page: int) -> None:
        self._show_current_page()

    def _on_report_error(self, error_msg: str):
        self._overlay.hide_loading()
        self.btn_run.setEnabled(True)
        QMessageBox.critical(self, _t("common.error"), _t("report_viewer.generation_failed", error=error_msg))

    # ------------------------------------------------------------------
    # Export / Print / Email
    # ------------------------------------------------------------------

    def export_excel(self) -> None:
        """Prompt for a save path and export the full report DataFrame to Excel."""
        from cbpos.core.constants.permissions import Permissions
        from cbpos.core.utils.permission_helper import check_permission_with_override

        if not check_permission_with_override(Permissions.REPORTS_EXPORT, self):
            return

        if self._full_df.empty:
            return

        filename, _ = QFileDialog.getSaveFileName(
            self, _t("report_viewer.save_excel_title"), "", _t("report_viewer.excel_filter")
        )
        if filename:
            self._start_export(self._full_df, filename, "excel")

    def export_pdf(self) -> None:
        """Prompt for a save path and export the full report DataFrame to PDF."""
        from cbpos.core.constants.permissions import Permissions
        from cbpos.core.utils.permission_helper import check_permission_with_override

        if not check_permission_with_override(Permissions.REPORTS_EXPORT, self):
            return

        if self._full_df.empty:
            return

        filename, _ = QFileDialog.getSaveFileName(
            self, _t("report_viewer.save_pdf_title"), "", _t("report_viewer.pdf_filter")
        )
        if filename:
            self._start_export(self._full_df, filename, "pdf")

    def _start_export(self, df: pd.DataFrame, filepath: str, fmt: str) -> None:
        """Run export in background thread."""
        self._set_export_buttons_enabled(False)
        self._overlay.show_loading(_t("report_viewer.exporting"))

        self._export_worker = ExportWorker(
            self.export_service,
            df,
            filepath,
            self.current_report.name,
            fmt,
        )
        self._export_worker.result.connect(self._on_export_finished)
        self._export_worker.error.connect(self._on_export_error)
        start_background_job(self._export_worker)

    def _on_export_finished(self, message: str) -> None:
        self._overlay.hide_loading()
        self._set_export_buttons_enabled(True)
        QMessageBox.information(self, _t("common.success"), message)

    def _on_export_error(self, error_msg: str) -> None:
        self._overlay.hide_loading()
        self._set_export_buttons_enabled(True)
        QMessageBox.critical(self, _t("common.error"), _t("report_viewer.export_failed", error=error_msg))

    def _set_export_buttons_enabled(self, enabled: bool) -> None:
        self.btn_export_excel.setEnabled(enabled)
        self.btn_export_pdf.setEnabled(enabled)
        self.btn_print.setEnabled(enabled)
        self.btn_email.setEnabled(enabled)

    def print_report(self) -> None:
        """Ask for a printer, then lay out and print the full report off the UI thread (#643)."""
        from PyQt6.QtPrintSupport import QPrintDialog, QPrinter

        df = self._full_df
        if df.empty or self.current_report is None:
            return

        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dialog = QPrintDialog(printer, self)
        if dialog.exec() != QPrintDialog.DialogCode.Accepted:
            return

        self._set_export_buttons_enabled(False)
        self._overlay.show_loading(_t("report_viewer.printing"))

        self._print_report_name = self.current_report.name
        self._print_worker = ReportPrintWorker(
            printer,
            df,
            _t("report_viewer.print_title", name=self.current_report.name),
            _t("report_viewer.generated_on"),
        )
        self._print_worker.result.connect(self._on_print_finished)
        self._print_worker.error.connect(self._on_print_error)
        start_background_job(self._print_worker)

    def _on_print_finished(self) -> None:
        self._overlay.hide_loading()
        self._set_export_buttons_enabled(True)
        QMessageBox.information(self, _t("common.print"), _t("report_viewer.print_sent", name=self._print_report_name))

    def _on_print_error(self, error_msg: str) -> None:
        self._overlay.hide_loading()
        self._set_export_buttons_enabled(True)
        QMessageBox.critical(self, _t("common.error"), _t("report_viewer.print_failed", error=error_msg))

    def email_report(self) -> None:
        """Ask for a recipient, then export the report to PDF and email it off the UI thread (#643)."""
        from PyQt6.QtWidgets import QInputDialog

        from cbpos.core.services.config_service import ConfigService

        df = self._full_df
        if df.empty or self.current_report is None:
            return

        default_email = ConfigService.get_all().get("admin_email", "")
        email, ok = QInputDialog.getText(
            self,
            _t("report_viewer.email_title"),
            _t("report_viewer.email_prompt"),
            text=default_email,
        )
        email = email.strip()
        if not ok or not email:
            return

        report_name = self.current_report.name
        self._set_export_buttons_enabled(False)
        self._overlay.show_loading(_t("report_viewer.email_sending"))

        self._email_worker = ReportEmailWorker(
            self.export_service,
            df,
            report_name,
            email,
            f"{_t('report_viewer.email_subject_prefix')}: {report_name}",
            _t("report_viewer.email_body", report_name=report_name),
        )
        self._email_worker.result.connect(self._on_email_sent)
        self._email_worker.error.connect(self._on_email_error)
        start_background_job(self._email_worker)

    def _on_email_sent(self, recipient: str) -> None:
        self._overlay.hide_loading()
        self._set_export_buttons_enabled(True)
        QMessageBox.information(self, _t("common.email"), _t("report_viewer.email_sent", email=recipient))

    def _on_email_error(self, stage: str, detail: str) -> None:
        self._overlay.hide_loading()
        self._set_export_buttons_enabled(True)
        if stage == ReportEmailWorker.STAGE_NOT_CONFIGURED:
            message = _t("report_viewer.email_not_configured")
        elif stage == ReportEmailWorker.STAGE_EXPORT:
            message = _t("report_viewer.email_prepare_failed", error=detail)
        else:
            message = _t("report_viewer.email_send_failed", error=detail)
        QMessageBox.warning(self, _t("report_viewer.email_failed"), message)
