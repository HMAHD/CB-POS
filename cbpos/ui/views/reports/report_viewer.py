from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTreeWidget,
    QTreeWidgetItem,
    QTableView,
    QPushButton,
    QMessageBox,
    QFileDialog,
    QSplitter,
)
from PyQt6.QtCore import Qt
import pandas as pd

from cbpos.core.reports.registry import ReportRegistry
from cbpos.core.services.export_service import ExportService
from cbpos.ui.views.reports.filter_widget import FilterWidget
from cbpos.ui.views.reports.pandas_model import PandasModel

# Import and register reports (Ideally this happens at app startup)
from cbpos.core.reports.definitions.sales_report import DailySalesSummaryReport


class ReportViewer(QWidget):
    def __init__(self):
        super().__init__()
        self.registry = ReportRegistry()
        self.export_service = ExportService()
        self.current_report = None
        # Register reports (Temporary location, should be in main app init)
        self.registry.register(DailySalesSummaryReport)

        self.setup_ui()

    def setup_ui(self):
        main_layout = QHBoxLayout(self)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # --- Left Sidebar (Report List) ---
        self.tree_widget = QTreeWidget()
        self.tree_widget.setHeaderLabel("Reports")
        self.tree_widget.itemClicked.connect(self.on_report_selected)
        self.populate_report_tree()
        splitter.addWidget(self.tree_widget)

        # --- Right Side (Content) ---
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)

        # Initialize Buttons FIRST
        self.btn_run = QPushButton("Run Report")
        self.btn_print = QPushButton("Print")
        self.btn_export_excel = QPushButton("Export Excel")
        self.btn_export_pdf = QPushButton("Export PDF")

        # Configure Buttons
        self.btn_run.clicked.connect(self.run_report)
        self.btn_run.setEnabled(False)
        self.btn_run.setStyleSheet("background-color: #00BCEB; color: white; " "font-weight: bold; padding: 5px 15px;")

        self.btn_print.setIcon(self.style().standardIcon(self.style().StandardPixmap.SP_FileIcon))
        self.btn_print.clicked.connect(self.print_report)
        self.btn_print.setEnabled(False)

        self.btn_export_excel.clicked.connect(self.export_excel)
        self.btn_export_excel.setEnabled(False)

        self.btn_export_pdf.clicked.connect(self.export_pdf)
        self.btn_export_pdf.setEnabled(False)

        self.btn_email = QPushButton("Email")
        self.btn_email.clicked.connect(self.email_report)
        self.btn_email.setEnabled(False)

        # Top Bar: Filters & Actions
        top_bar = QHBoxLayout()
        self.filter_widget = FilterWidget()

        top_bar.addWidget(self.filter_widget)
        top_bar.addWidget(self.btn_run)
        right_layout.addLayout(top_bar)

        # Center: Table View
        self.table_view = QTableView()
        self.table_model = PandasModel()
        self.table_view.setModel(self.table_model)
        self.table_view.horizontalHeader().setStretchLastSection(True)
        self.table_view.setAlternatingRowColors(True)
        right_layout.addWidget(self.table_view)

        # Bottom Bar: Exports
        bottom_bar = QHBoxLayout()
        bottom_bar.addStretch()
        bottom_bar.addWidget(self.btn_print)
        bottom_bar.addWidget(self.btn_export_excel)
        bottom_bar.addWidget(self.btn_export_pdf)
        bottom_bar.addWidget(self.btn_email)
        right_layout.addLayout(bottom_bar)

        splitter.addWidget(right_widget)
        splitter.setSizes([200, 800])  # Initial sizes

        main_layout.addWidget(splitter)

    def populate_report_tree(self):
        self.tree_widget.clear()
        categories = self.registry.get_all_categories()

        for category in categories:
            cat_item = QTreeWidgetItem(self.tree_widget)
            cat_item.setText(0, category)
            cat_item.setExpanded(True)

            reports = self.registry.get_reports_by_category(category)
            for report in reports:
                rep_item = QTreeWidgetItem(cat_item)
                rep_item.setText(0, report.name)
                rep_item.setData(0, Qt.ItemDataRole.UserRole, report.id)

    def on_report_selected(self, item, column):
        report_id = item.data(0, Qt.ItemDataRole.UserRole)
        if not report_id:
            self.current_report = None
            self.filter_widget.clear_filters()
            self.btn_run.setEnabled(False)
            return

        self.current_report = self.registry.get_report_by_id(report_id)
        if self.current_report:
            self.filter_widget.build_filters(self.current_report.get_filter_definitions())
            self.btn_run.setEnabled(True)
            # Clear previous results
            self.table_model.set_data(pd.DataFrame())
            self.btn_export_excel.setEnabled(False)
            self.btn_export_pdf.setEnabled(False)
            self.btn_print.setEnabled(False)
            self.btn_email.setEnabled(False)

    def run_report(self):
        if not self.current_report:
            return

        filters = self.filter_widget.get_filter_values()
        try:
            # TODO: Run in QThread to avoid freezing UI
            df = self.current_report.generate(filters)
            self.table_model.set_data(df)

            if not df.empty:
                self.btn_export_excel.setEnabled(True)
                self.btn_export_pdf.setEnabled(True)
                self.btn_print.setEnabled(True)
                self.btn_email.setEnabled(True)
            else:
                QMessageBox.information(self, "Report", "No data found for the selected filters.")
                self.btn_export_excel.setEnabled(False)
                self.btn_export_pdf.setEnabled(False)
                self.btn_print.setEnabled(False)
                self.btn_email.setEnabled(False)

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to generate report: {str(e)}")

    def export_excel(self):
        df = self.table_model.get_dataframe()
        if df.empty:
            return

        filename, _ = QFileDialog.getSaveFileName(self, "Save Excel", "", "Excel Files (*.xlsx)")
        if filename:
            try:
                self.export_service.export_to_excel(df, filename, self.current_report.name)
                QMessageBox.information(self, "Success", "Export successful!")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Export failed: {str(e)}")

    def export_pdf(self):
        df = self.table_model.get_dataframe()
        if df.empty:
            return

        filename, _ = QFileDialog.getSaveFileName(self, "Save PDF", "", "PDF Files (*.pdf)")
        if filename:
            try:
                self.export_service.export_to_pdf(df, filename, self.current_report.name)
                QMessageBox.information(self, "Success", "Export successful!")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Export failed: {str(e)}")

    def print_report(self):
        from PyQt6.QtPrintSupport import QPrinter, QPrintDialog
        from PyQt6.QtGui import QTextDocument

        df = self.table_model.get_dataframe()
        if df.empty:
            return

        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dialog = QPrintDialog(printer, self)

        if dialog.exec() == QPrintDialog.DialogCode.Accepted:
            # Create HTML content for printing
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
                <p style="text-align: center;">Generated on: {generated_on}</p>
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

        df = self.table_model.get_dataframe()
        if df.empty:
            return

        # Get Recipient
        config = ConfigService.get_all()
        default_email = config.get("admin_email", "")

        email, ok = QInputDialog.getText(self, "Email Report", "Recipient Email:", text=default_email)

        if ok and email:
            try:
                # Generate PDF to temp file
                temp_dir = tempfile.gettempdir()
                filename = f"{self.current_report.name.replace(' ', '_')}.pdf"
                filepath = os.path.join(temp_dir, filename)

                self.export_service.export_to_pdf(df, filepath, self.current_report.name)

                # Send Email
                body = f"Please find attached the {self.current_report.name}."

                # Create worker and thread (fire and forget for now, but ideally track
                # it)
                # Note: In a real app, we should keep a reference to the worker/thread
                # to prevent premature garbage collection if the local variable goes
                # out of scope.
                # The EmailService.send_email returns the thread, so we can store it.
                self._email_thread = EmailService.send_email(
                    email,
                    f"Report: {self.current_report.name}",
                    body,
                    filepath,
                    callback=lambda success, msg: (
                        QMessageBox.information(self, "Email", msg)
                        if success
                        else QMessageBox.warning(self, "Email Failed", msg)
                    ),
                )

                QMessageBox.information(self, "Email", "Email sending started in background...")

            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to prepare email: {str(e)}")
