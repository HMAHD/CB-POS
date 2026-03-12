from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTableView,
    QPushButton,
    QMessageBox,
    QFileDialog,
    QSplitter,
    QLabel,
    QStackedWidget,
    QHeaderView,
    QScrollArea,
    QFrame,
    QSizePolicy,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QRectF
from PyQt6.QtGui import QPainter, QPen
import pandas as pd

from cbpos.core.reports.registry import ReportRegistry
from cbpos.core.services.export_service import ExportService
from cbpos.ui.views.reports.filter_widget import FilterWidget
from cbpos.ui.views.reports.pandas_model import PandasModel
from cbpos.ui.workers import ExportWorker
from cbpos.ui.widgets.loading_overlay import LoadingOverlay
from cbpos.ui.widgets.pagination_widget import PaginationWidget
from cbpos.core.services.tax_service import TaxService
from cbpos.i18n import _t, register_language_callback, unregister_language_callback


class ReportWorker(QThread):
    """Background thread for report generation to avoid freezing the UI."""

    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, report, filters):
        super().__init__()
        self.finished.connect(self.deleteLater)
        self.error.connect(self.deleteLater)
        self.report = report
        self.filters = filters

    def run(self):
        try:
            df = self.report.generate(self.filters)
            self.finished.emit(df)
        except Exception as e:
            self.error.emit(str(e))


class _ReportPlaceholderIcon(QWidget):
    """Painted bar-chart icon for the empty state."""

    _SIZE = 64

    def __init__(self) -> None:
        super().__init__()
        self.setFixedSize(self._SIZE, self._SIZE)
        self.setObjectName("ReportEmptyIcon")

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Use palette foreground so the icon adapts to dark/light theme
        theme_color = self.palette().color(self.foregroundRole())
        theme_color.setAlpha(120)
        bar_color = theme_color
        line_color = theme_color

        s = self._SIZE
        margin = 8
        base_y = s - margin
        bar_w = 8
        gap = 6
        bars = [0.35, 0.6, 0.45, 0.85, 0.55]
        max_h = s - margin * 2 - 4

        p.setPen(QPen(line_color, 1.5))
        p.drawLine(margin, base_y, s - margin, base_y)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(bar_color)
        total_w = len(bars) * bar_w + (len(bars) - 1) * gap
        x_start = (s - total_w) / 2
        for i, ratio in enumerate(bars):
            bh = max_h * ratio
            x = x_start + i * (bar_w + gap)
            p.drawRoundedRect(QRectF(x, base_y - bh, bar_w, bh), 2, 2)

        p.end()


class ReportViewer(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("ReportViewer")
        self.registry = ReportRegistry()
        self.export_service = ExportService()
        self.current_report = None
        self._full_df = pd.DataFrame()
        self.init_ui()

        # Register for language changes
        register_language_callback(self.retranslate_ui)
        self.destroyed.connect(lambda: unregister_language_callback(self.retranslate_ui))

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
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
        sidebar_layout.addWidget(scroll)

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

        # Page 0: Empty State
        empty_state = QWidget()
        empty_state.setObjectName("ReportEmptyState")
        empty_layout = QVBoxLayout(empty_state)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon_container = QHBoxLayout()
        icon_container.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_icon = _ReportPlaceholderIcon()
        icon_container.addWidget(empty_icon)
        empty_layout.addLayout(icon_container)

        self.empty_text = QLabel("")
        self.empty_text.setObjectName("ReportEmptyText")
        self.empty_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(self.empty_text)

        self.empty_subtext = QLabel("")
        self.empty_subtext.setObjectName("ReportEmptySubtext")
        self.empty_subtext.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(self.empty_subtext)

        self.content_stack.addWidget(empty_state)

        # Page 1: Data Table
        self.table_view = QTableView()
        self.table_view.setObjectName("ReportDataView")
        self.table_model = PandasModel()
        self.table_view.setModel(self.table_model)
        self.table_view.horizontalHeader().setStretchLastSection(True)
        self.table_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
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
        sidebar.setMinimumWidth(260)

        main_layout.addWidget(splitter)

        # Loading overlay
        self._overlay = LoadingOverlay(self)

        # Apply translations
        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        """Set all translatable text using _t()."""
        self.sidebar_title.setText(_t("report_viewer.sidebar_title"))
        self.btn_run.setText(_t("report_viewer.btn_run"))
        self.empty_text.setText(_t("report_viewer.empty_title"))
        self.empty_subtext.setText(_t("report_viewer.empty_subtitle"))
        self.btn_print.setText(_t("common.print"))
        self.btn_export_excel.setText(_t("report_viewer.btn_excel"))
        self.btn_export_pdf.setText(_t("report_viewer.btn_pdf"))
        self.btn_email.setText(_t("common.email"))

    # ------------------------------------------------------------------
    # Sidebar construction
    # ------------------------------------------------------------------

    def _populate_sidebar(self) -> None:
        """Build category sections with report buttons."""
        categories = self.registry.get_all_categories()

        vat_active = TaxService.is_vat_active()

        for idx, category in enumerate(categories):
            all_reports = self.registry.get_reports_by_category(category)
            # Filter out VAT-only reports when VAT is not active
            reports = [r for r in all_reports if not getattr(r, "requires_vat", False) or vat_active]
            if not reports:
                continue

            # Category header row: label + count badge
            if idx > 0:
                self._nav_layout.addSpacing(8)

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
        if not self.current_report:
            return

        filters = self.filter_widget.get_filter_values()

        self._overlay.show_loading(_t("report_viewer.generating"))
        self.btn_run.setEnabled(False)

        self._report_worker = ReportWorker(self.current_report, filters)
        self._report_worker.finished.connect(self._on_report_finished)
        self._report_worker.error.connect(self._on_report_error)
        self._report_worker.start()

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
            self.pagination.setVisible(True)
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
        self.table_model.set_data(page_df)

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
        from cbpos.core.utils.permission_helper import check_permission_with_override
        from cbpos.core.constants.permissions import Permissions

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
        from cbpos.core.utils.permission_helper import check_permission_with_override
        from cbpos.core.constants.permissions import Permissions

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
        self._export_worker.finished.connect(self._on_export_finished)
        self._export_worker.error.connect(self._on_export_error)
        self._export_worker.start()

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

    def print_report(self):
        from PyQt6.QtPrintSupport import QPrinter, QPrintDialog
        from PyQt6.QtGui import QTextDocument

        df = self._full_df
        if df.empty:
            return

        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dialog = QPrintDialog(printer, self)

        if dialog.exec() == QPrintDialog.DialogCode.Accepted:
            import textwrap

            html_content = textwrap.dedent(
                """
            <html>
            <head>
                <style>
                    body {{ font-family: Helvetica, sans-serif; }}
                    h1 {{ text-align: center; color: #001F3F; }}
                    table {{
                        width: 100%;
                        border-collapse: collapse;
                        margin-top: 20px;
                    }}
                    th {{
                        background-color: #00BCEB;
                        color: white;
                        padding: 8px;
                        text-align: left;
                    }}
                    td {{
                        padding: 8px;
                        border-bottom: 1px solid #ddd;
                    }}
                    tr:nth-child(even) {{
                        background-color: #f2f2f2;
                    }}
                </style>
            </head>
            <body>
                <h1>CB POS - {report_name}</h1>
                <p style="text-align: center;">
                    Generated on: {generated_on}
                </p>
                {table_html}
            </body>
            </html>
            """
            ).format(
                report_name=self.current_report.name,
                generated_on=pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
                table_html=df.to_html(classes="table", index=False, border=0),
            )

            document = QTextDocument()
            document.setHtml(html_content)
            document.print(printer)

    def email_report(self):
        from cbpos.core.services.email_service import EmailService
        from cbpos.core.services.config_service import ConfigService
        import tempfile
        import os
        from PyQt6.QtWidgets import QInputDialog

        df = self._full_df
        if df.empty:
            return

        config = ConfigService.get_all()
        default_email = config.get("admin_email", "")

        email, ok = QInputDialog.getText(
            self,
            _t("report_viewer.email_title"),
            _t("report_viewer.email_prompt"),
            text=default_email,
        )

        if ok and email:
            try:
                temp_dir = tempfile.gettempdir()
                filename = f"{self.current_report.name.replace(' ', '_')}.pdf"
                filepath = os.path.join(temp_dir, filename)

                self.export_service.export_to_pdf(df, filepath, self.current_report.name)

                body = _t("report_viewer.email_body", report_name=self.current_report.name)

                self._email_thread = EmailService.send_email(
                    email,
                    f"{_t('report_viewer.email_subject_prefix')}: {self.current_report.name}",
                    body,
                    filepath,
                    callback=lambda success, msg: (
                        QMessageBox.information(self, _t("common.email"), msg)
                        if success
                        else QMessageBox.warning(self, _t("report_viewer.email_failed"), msg)
                    ),
                )

                QMessageBox.information(
                    self,
                    _t("common.email"),
                    _t("report_viewer.email_sending"),
                )

            except Exception as e:
                QMessageBox.critical(
                    self,
                    _t("common.error"),
                    _t("report_viewer.email_prepare_failed", error=str(e)),
                )
