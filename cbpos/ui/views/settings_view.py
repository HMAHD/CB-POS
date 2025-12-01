from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QListWidget,
    QListWidgetItem,
    QFormLayout,
    QMessageBox,
    QGroupBox,
    QCheckBox,
    QSpinBox,
    QFrame,
    QComboBox,
    QTextEdit,
    QFileDialog,
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtPrintSupport import QPrinterInfo
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.theme_service import ThemeService
from cbpos.core.services.language_service import LanguageService
from cbpos.ui.dialogs.receipt_preview_dialog import ReceiptPreviewDialog
from cbpos.core.services.receipt_builder import ReceiptBuilder
from cbpos.core.models import Sale, SaleItem, Product
import decimal


class SettingsView(QWidget):
    close_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.init_ui()
        self.load_settings()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Header
        header_frame = QFrame()
        header_frame.setStyleSheet(
            "background-color: #001F3F; border-bottom: 2px solid #003366;"
        )
        header_frame.setFixedHeight(60)
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(20, 0, 20, 0)

        lbl_title = QLabel("Settings")
        lbl_title.setStyleSheet("font-size: 24px; font-weight: bold; color: #00BCEB;")
        header_layout.addWidget(lbl_title)

        main_layout.addWidget(header_frame)

        # 2. Body (Sidebar + Content)
        body_layout = QHBoxLayout()
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        # 2.1 Sidebar
        self.sidebar = QListWidget()
        self.sidebar.setFixedWidth(220)
        self.sidebar.setStyleSheet(
            """
            QListWidget {
                background-color: #2D2D30;
                border: none;
                outline: none;
            }
            QListWidget::item {
                color: #FFFFFF;
                padding: 15px;
                border-bottom: 1px solid #3E3E42;
            }
            QListWidget::item:selected {
                background-color: #3E3E42;
                border-left: 4px solid #00BCEB;
                color: #FFFFFF;
            }
            QListWidget::item:hover {
                background-color: #3E3E42;
            }
        """
        )
        self.sidebar.currentRowChanged.connect(self.change_page)

        # Sidebar Items
        import qtawesome as qta

        items = [
            ("General", "fa5s.sliders-h"),
            ("Order & Payment", "fa5s.credit-card"),
            ("Receipt", "fa5s.receipt"),
            ("Hardware", "fa5s.print"),
            ("Users", "fa5s.users"),
            ("Database", "fa5s.database"),
            ("About", "fa5s.info-circle"),
        ]

        for item_text, icon_name in items:
            item = QListWidgetItem(item_text)
            item.setIcon(qta.icon(icon_name, color="white"))
            item.setSizeHint(QSize(0, 50))
            item.setTextAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )
            self.sidebar.addItem(item)

        body_layout.addWidget(self.sidebar)

        # 2.2 Content Area
        self.stack = QStackedWidget()
        self.stack.setStyleSheet(
            "QWidget { background-color: #1E1E1E; color: #FFFFFF; } "
            "QLineEdit, QComboBox, QSpinBox, QTextEdit { "
            "background-color: #333337; color: white; border: 1px solid #555; "
            "padding: 5px; }"
        )

        # Pages
        self.page_general = QWidget()
        self.page_order_payment = QWidget()
        self.page_receipt = QWidget()
        self.page_hardware = QWidget()
        self.page_users = QWidget()
        self.page_database = QWidget()
        self.page_about = QWidget()

        self.stack.addWidget(self.page_general)
        self.stack.addWidget(self.page_order_payment)
        self.stack.addWidget(self.page_receipt)
        self.stack.addWidget(self.page_hardware)
        self.stack.addWidget(self.page_users)
        self.stack.addWidget(self.page_database)
        self.stack.addWidget(self.page_about)

        self.init_general_page()
        self.init_order_payment_page()
        self.init_receipt_page()
        self.init_hardware_page()
        self.init_users_page()
        self.init_database_page()
        self.init_about_page()

        body_layout.addWidget(self.stack)
        main_layout.addLayout(body_layout)

        # 3. Footer
        footer_frame = QFrame()
        footer_frame.setFixedHeight(60)
        footer_frame.setStyleSheet(
            "background-color: #2D2D30; border-top: 1px solid #3E3E42;"
        )
        footer_layout = QHBoxLayout(footer_frame)
        footer_layout.setContentsMargins(20, 10, 20, 10)

        footer_layout.addStretch()

        self.btn_save = QPushButton("Save")
        self.btn_save.setFixedSize(100, 35)
        self.btn_save.setStyleSheet(
            "background-color: #39FF14; color: black; font-weight: bold; border-radius: 4px;"
        )
        self.btn_save.clicked.connect(self.save_all)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setFixedSize(100, 35)
        self.btn_cancel.setStyleSheet(
            "background-color: #FF4136; color: white; font-weight: bold; border-radius: 4px;"
        )
        self.btn_cancel.clicked.connect(self.close_requested.emit)

        footer_layout.addWidget(self.btn_save)
        footer_layout.addWidget(self.btn_cancel)

        main_layout.addWidget(footer_frame)

        # Select first item
        self.sidebar.setCurrentRow(0)

    def change_page(self, index):
        self.stack.setCurrentIndex(index)

    def init_general_page(self):
        layout = QFormLayout(self.page_general)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)

        lbl_header = QLabel("General Settings")
        lbl_header.setStyleSheet(
            "font-size: 18px; font-weight: bold; color: #00BCEB; margin-bottom: 20px;"
        )
        layout.addRow(lbl_header)

        self.input_shop_name = QLineEdit()
        self.input_address = QLineEdit()
        self.input_phone = QLineEdit()
        self.input_vat = QLineEdit()

        layout.addRow("Shop Name:", self.input_shop_name)
        layout.addRow("Address:", self.input_address)
        layout.addRow("Phone:", self.input_phone)
        layout.addRow("VAT Number:", self.input_vat)

        # Theme
        self.combo_theme = QComboBox()
        self.combo_theme.addItems(["Ceylon Night (Dark)", "Ceylon Day (Light)"])
        layout.addRow("Theme:", self.combo_theme)

        # Language
        self.combo_language = QComboBox()
        languages = LanguageService.get_available_languages()
        # Store codes in user data
        for code, name in languages.items():
            self.combo_language.addItem(f"{name} ({code})", code)
        layout.addRow("Language:", self.combo_language)

    def init_order_payment_page(self):
        layout = QVBoxLayout(self.page_order_payment)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)

        lbl_header = QLabel("Order & Payment Configuration")
        lbl_header.setStyleSheet("font-size: 18px; font-weight: bold; color: #00BCEB;")
        layout.addWidget(lbl_header)

        # Documents Section (Migrated)
        grp_docs = QGroupBox("Document Numbering")
        form_docs = QFormLayout(grp_docs)

        self.combo_reset_period = QComboBox()
        self.combo_reset_period.addItems(["YEARLY", "MONTHLY", "NEVER"])
        form_docs.addRow("Reset Period:", self.combo_reset_period)

        self.input_fmt_sale = QLineEdit()
        self.input_fmt_sale.setPlaceholderText("INV-{Y}-{seq:05d}")
        form_docs.addRow("Sale Format:", self.input_fmt_sale)

        self.input_fmt_purchase = QLineEdit()
        self.input_fmt_purchase.setPlaceholderText("GRN-{Y}-{seq:05d}")
        form_docs.addRow("Purchase Format:", self.input_fmt_purchase)

        self.input_fmt_return = QLineEdit()
        self.input_fmt_return.setPlaceholderText("CN-{Y}-{seq:05d}")
        form_docs.addRow("Return Format:", self.input_fmt_return)

        layout.addWidget(grp_docs)

        # Payment Options
        grp_opts = QGroupBox("Payment Options")
        form_opts = QFormLayout(grp_opts)

        self.chk_show_receipt_dialog = QCheckBox(
            "Show Receipt Options Dialog after Sale"
        )
        form_opts.addRow(self.chk_show_receipt_dialog)

        layout.addWidget(grp_opts)
        layout.addStretch()

    def init_receipt_page(self):
        layout = QVBoxLayout(self.page_receipt)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)

        lbl_header = QLabel("Receipt Designer")
        lbl_header.setStyleSheet("font-size: 18px; font-weight: bold; color: #00BCEB;")
        layout.addWidget(lbl_header)

        # Logo
        grp_logo = QGroupBox("Logo")
        logo_layout = QHBoxLayout(grp_logo)
        self.input_logo_path = QLineEdit()
        self.input_logo_path.setReadOnly(True)
        self.btn_browse_logo = QPushButton("Browse...")
        self.btn_browse_logo.clicked.connect(self.browse_logo)
        self.btn_clear_logo = QPushButton("Clear")
        self.btn_clear_logo.clicked.connect(lambda: self.input_logo_path.clear())

        logo_layout.addWidget(self.input_logo_path)
        logo_layout.addWidget(self.btn_browse_logo)
        logo_layout.addWidget(self.btn_clear_logo)
        layout.addWidget(grp_logo)

        # Content
        grp_content = QGroupBox("Content")
        form_content = QFormLayout(grp_content)

        self.txt_header = QTextEdit()
        self.txt_header.setFixedHeight(80)
        form_content.addRow("Header Text:", self.txt_header)

        self.txt_footer = QTextEdit()
        self.txt_footer.setFixedHeight(80)
        form_content.addRow("Footer Text:", self.txt_footer)

        self.chk_show_barcode = QCheckBox("Show Barcode")
        self.chk_merge_items = QCheckBox("Merge Duplicate Items")
        self.chk_show_tax = QCheckBox("Show Tax Breakdown")

        form_content.addRow("", self.chk_show_barcode)
        form_content.addRow("", self.chk_merge_items)
        form_content.addRow("", self.chk_show_tax)

        layout.addWidget(grp_content)

        # Preview Button
        self.btn_preview = QPushButton("Preview Receipt")
        self.btn_preview.setStyleSheet("background-color: #007ACC; color: white;")
        self.btn_preview.clicked.connect(self.preview_receipt)
        layout.addWidget(self.btn_preview)

        layout.addStretch()

    def init_hardware_page(self):
        layout = QVBoxLayout(self.page_hardware)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)

        lbl_header = QLabel("Hardware Configuration")
        lbl_header.setStyleSheet("font-size: 18px; font-weight: bold; color: #00BCEB;")
        layout.addWidget(lbl_header)

        # Printers
        grp_printer = QGroupBox("Printers")
        form_printer = QFormLayout(grp_printer)

        available_printers = QPrinterInfo.availablePrinterNames() or [
            "No printers found"
        ]

        self.combo_receipt_printer = QComboBox()
        self.combo_receipt_printer.addItems(available_printers)
        form_printer.addRow("Receipt Printer:", self.combo_receipt_printer)

        self.combo_a4_printer = QComboBox()
        self.combo_a4_printer.addItems(available_printers)
        form_printer.addRow("A4 Printer:", self.combo_a4_printer)

        self.chk_auto_print = QCheckBox("Auto-Print Receipt")
        form_printer.addRow("", self.chk_auto_print)

        self.spin_copies = QSpinBox()
        self.spin_copies.setRange(1, 5)
        form_printer.addRow("Copies:", self.spin_copies)

        layout.addWidget(grp_printer)

        # Scale
        grp_scale = QGroupBox("Weighing Scale")
        form_scale = QFormLayout(grp_scale)

        self.input_scale_prefix = QLineEdit()
        self.input_scale_prefix.setMaxLength(2)
        form_scale.addRow("Barcode Prefix (2 digits):", self.input_scale_prefix)

        self.spin_decimal_places = QSpinBox()
        self.spin_decimal_places.setRange(0, 4)
        form_scale.addRow("Decimal Places:", self.spin_decimal_places)

        layout.addWidget(grp_scale)
        layout.addStretch()

    def init_users_page(self):
        layout = QVBoxLayout(self.page_users)
        layout.setContentsMargins(40, 40, 40, 40)
        lbl = QLabel("User Management (Placeholder)")
        lbl.setStyleSheet("color: #888;")
        layout.addWidget(lbl)
        layout.addStretch()

    def init_database_page(self):
        layout = QVBoxLayout(self.page_database)
        layout.setContentsMargins(40, 40, 40, 40)
        lbl = QLabel("Database Maintenance (Placeholder)")
        lbl.setStyleSheet("color: #888;")
        layout.addWidget(lbl)
        layout.addStretch()

    def init_about_page(self):
        layout = QVBoxLayout(self.page_about)
        layout.setContentsMargins(40, 40, 40, 40)
        lbl = QLabel("About CB POS\nVersion 0.1.0\n\n(c) 2025 Ceylon Byte")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet("font-size: 16px; color: #CCC;")
        layout.addWidget(lbl)
        layout.addStretch()

    def load_settings(self):
        settings = ConfigService.get_all()

        # General
        self.input_shop_name.setText(settings.get("shop_name", ""))
        self.input_address.setText(settings.get("shop_address", ""))
        self.input_phone.setText(settings.get("shop_phone", ""))
        self.input_vat.setText(settings.get("vat_number", ""))

        # Theme
        current_theme = settings.get("theme", "Dark")
        index = 0 if current_theme == "Dark" else 1
        self.combo_theme.setCurrentIndex(index)

        # Language
        current_lang = settings.get("language", "en")
        index = self.combo_language.findData(current_lang)
        if index >= 0:
            self.combo_language.setCurrentIndex(index)

        # Order & Payment
        self.combo_reset_period.setCurrentText(
            settings.get("doc_reset_period", "YEARLY")
        )
        self.input_fmt_sale.setText(
            settings.get("doc_format_sale", "INV-{Y}-{seq:05d}")
        )
        self.input_fmt_purchase.setText(
            settings.get("doc_format_purchase", "GRN-{Y}-{seq:05d}")
        )
        self.input_fmt_return.setText(
            settings.get("doc_format_return", "CN-{Y}-{seq:05d}")
        )
        self.chk_show_receipt_dialog.setChecked(
            settings.get("show_receipt_dialog", "True") == "True"
        )

        # Receipt
        self.input_logo_path.setText(settings.get("receipt_logo_path", ""))
        self.txt_header.setText(settings.get("receipt_header", ""))
        self.txt_footer.setText(settings.get("receipt_footer", ""))
        self.chk_show_barcode.setChecked(settings.get("show_barcode", True))
        self.chk_merge_items.setChecked(settings.get("merge_items", True))
        self.chk_show_tax.setChecked(settings.get("show_tax_breakdown", True))

        # Hardware
        receipt_printer = settings.get("receipt_printer_name", "")
        if receipt_printer:
            idx = self.combo_receipt_printer.findText(receipt_printer)
            if idx >= 0:
                self.combo_receipt_printer.setCurrentIndex(idx)

        a4_printer = settings.get("a4_printer_name", "")
        if a4_printer:
            idx = self.combo_a4_printer.findText(a4_printer)
            if idx >= 0:
                self.combo_a4_printer.setCurrentIndex(idx)

        self.chk_auto_print.setChecked(settings.get("auto_print_receipt", True))
        self.spin_copies.setValue(settings.get("receipt_copies", 1))

        self.input_scale_prefix.setText(settings.get("scale_barcode_prefix", "20"))
        self.spin_decimal_places.setValue(settings.get("scale_decimal_places", 3))

    def browse_logo(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Logo", "", "Images (*.png *.jpg *.bmp)"
        )
        if path:
            self.input_logo_path.setText(path)

    def preview_receipt(self):
        # Create a dummy sale for preview
        dummy_sale = Sale(
            id=12345,
            total_amount=decimal.Decimal("1500.00"),
            tax_vat=decimal.Decimal("228.81"),
            tax_sscl=decimal.Decimal("37.50"),
            net_revenue=decimal.Decimal("1233.69"),
        )
        # Dummy items
        p1 = Product(name_en="Test Product 1")
        p2 = Product(name_en="Test Product 2")
        dummy_sale.items = [
            SaleItem(
                product=p1,
                qty=decimal.Decimal(1),
                unit_price=decimal.Decimal(500),
                subtotal=decimal.Decimal(500),
            ),
            SaleItem(
                product=p2,
                qty=decimal.Decimal(2),
                unit_price=decimal.Decimal(500),
                subtotal=decimal.Decimal(1000),
            ),
        ]

        # Temporarily save settings to config so builder uses them
        # Or better, pass config to builder? Builder reads from ConfigService.
        # So we should update ConfigService temporarily or just save first?
        # The user might want to preview BEFORE saving.
        # But ConfigService is global.
        # Let's just update the in-memory config without saving to disk if possible,
        # or just save to disk. Saving is safer.
        self.save_all(silent=True)

        commands = ReceiptBuilder.build_receipt(dummy_sale)
        dlg = ReceiptPreviewDialog(commands, self)
        dlg.exec()

    def save_all(self, silent=False):
        # Validation
        scale_prefix = self.input_scale_prefix.text().strip()
        if len(scale_prefix) != 2 or not scale_prefix.isdigit():
            if not silent:
                QMessageBox.warning(self, "Error", "Scale Prefix must be 2 digits.")
            return

        theme_selection = "Dark" if self.combo_theme.currentIndex() == 0 else "Light"
        lang_code = self.combo_language.currentData()

        # Check if language changed
        current_lang = ConfigService.get_all().get("language", "en")
        lang_changed = lang_code != current_lang

        data = {
            "shop_name": self.input_shop_name.text(),
            "shop_address": self.input_address.text(),
            "shop_phone": self.input_phone.text(),
            "vat_number": self.input_vat.text(),
            "theme": theme_selection,
            "language": lang_code,
            "doc_reset_period": self.combo_reset_period.currentText(),
            "doc_format_sale": self.input_fmt_sale.text(),
            "doc_format_purchase": self.input_fmt_purchase.text(),
            "doc_format_return": self.input_fmt_return.text(),
            "show_receipt_dialog": str(self.chk_show_receipt_dialog.isChecked()),
            # Receipt
            "receipt_logo_path": self.input_logo_path.text(),
            "receipt_header": self.txt_header.toPlainText(),
            "receipt_footer": self.txt_footer.toPlainText(),
            "show_barcode": self.chk_show_barcode.isChecked(),
            "merge_items": self.chk_merge_items.isChecked(),
            "show_tax_breakdown": self.chk_show_tax.isChecked(),
            "receipt_printer_name": self.combo_receipt_printer.currentText(),
            "a4_printer_name": self.combo_a4_printer.currentText(),
            "auto_print_receipt": self.chk_auto_print.isChecked(),
            "receipt_copies": self.spin_copies.value(),
            "scale_barcode_prefix": scale_prefix,
            "scale_decimal_places": self.spin_decimal_places.value(),
        }

        ConfigService.update_all(data)

        # Apply Theme Immediately
        ThemeService.apply_theme(theme_selection)

        if not silent:
            if lang_changed:
                QMessageBox.information(
                    self,
                    "Restart Required",
                    "Please restart the application to apply " "language changes.",
                )
            else:
                QMessageBox.information(self, "Saved", "Settings saved successfully.")

            self.close_requested.emit()
