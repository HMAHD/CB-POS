"""Receipt configuration settings page with live preview split-pane layout."""

import decimal
import logging

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from cbpos.core.models import Product, Sale, SaleItem, SalePayment
from cbpos.core.services.receipt_builder import ReceiptBuilder
from cbpos.core.services.receipt_logo_service import store_receipt_logo
from cbpos.i18n import _t, register_language_callback
from cbpos.ui.dialogs.guide_dialog import GuideDialog
from cbpos.ui.views.settings_pages.base import SettingsPage
from cbpos.ui.widgets.help_icon_button import HelpIconButton
from cbpos.ui.widgets.receipt_preview_widget import ReceiptPreviewWidget

logger = logging.getLogger(__name__)


class ReceiptPage(SettingsPage):
    """Receipt settings with live preview split-pane layout.

    Left panel: settings tabs (Content + Display).
    Right panel: live receipt preview that auto-updates on every change.
    """

    def init_ui(self):
        """Build the split-pane layout: Content/Display settings tabs on the left, live preview on the right."""
        # --- Custom layout: split-pane instead of standard vertical ---
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(8)

        title_row = QHBoxLayout()
        self._page_title = QLabel()
        self._page_title.setProperty("class", "dialog-title")
        title_row.addWidget(self._page_title, 1)
        title_row.addWidget(self._make_reset_defaults_button())
        root.addLayout(title_row)

        self._page_subtitle = QLabel()
        self._page_subtitle.setProperty("class", "muted")
        root.addWidget(self._page_subtitle)

        # Copies/auto-print (Hardware) and document numbering format
        # (Documents) are just as much "receipt customization" as anything
        # on this page, but live on two other, unrelated-sounding sidebar
        # sections with no link back here -- someone tuning header/footer/
        # logo would feel done and never realize the rest is elsewhere (#331).
        self._lbl_receipt_cross_ref = QLabel()
        self._lbl_receipt_cross_ref.setObjectName("ReceiptCrossRefHint")
        self._lbl_receipt_cross_ref.setProperty("class", "muted")
        self._lbl_receipt_cross_ref.setWordWrap(True)
        root.addWidget(self._lbl_receipt_cross_ref)

        # Horizontal split: settings | preview
        split = QHBoxLayout()
        split.setSpacing(16)

        # --- Left: Tab widget with settings ---
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        self.tabs = QTabWidget()
        left_layout.addWidget(self.tabs)
        split.addWidget(left_panel, 55)

        # --- Right: Live preview ---
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        # Preview header row: title on the left, width selector on the right (#573)
        preview_header_row = QHBoxLayout()
        preview_header_row.setContentsMargins(0, 0, 0, 0)
        self._lbl_preview_title = QLabel()
        self._lbl_preview_title.setObjectName("SettingsSectionTitle")
        preview_header_row.addWidget(self._lbl_preview_title)
        preview_header_row.addStretch()

        self._lbl_preview_width = QLabel()
        self._lbl_preview_width.setProperty("class", "muted")
        preview_header_row.addWidget(self._lbl_preview_width)
        self.combo_preview_width = QComboBox()
        self.combo_preview_width.addItem("80mm", "80mm")
        self.combo_preview_width.addItem("58mm", "58mm")
        self.combo_preview_width.currentIndexChanged.connect(self._schedule_refresh)
        preview_header_row.addWidget(self.combo_preview_width)
        right_layout.addLayout(preview_header_row)

        # ReceiptPreviewWidget sizes its browser to the full receipt height
        # rather than scrolling internally -- a receipt with many items
        # easily exceeds the window's visible height, so this scroll area
        # (kept below the width selector, which stays fixed at the top) is
        # what actually lets the rest of a tall receipt be reached.
        preview_scroll = QScrollArea()
        preview_scroll.setWidgetResizable(True)
        preview_scroll.setFrameShape(QFrame.Shape.NoFrame)
        preview_scroll.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self._preview = ReceiptPreviewWidget()
        preview_scroll.setWidget(self._preview)
        right_layout.addWidget(preview_scroll, 1)

        split.addWidget(right_panel, 45)

        root.addLayout(split, 1)

        # Debounce timer for live preview refresh
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(300)
        self._refresh_timer.timeout.connect(self._refresh_preview)

        # ===================== Tab 1: Content =====================
        tab_content, vbox_content = self._build_vbox_tab()

        # Section: Logo
        self._header_logo = self._make_section_header("settings.receipt.section_logo")
        vbox_content.addWidget(self._header_logo)

        logo_form = QFormLayout()
        self.configure_form_layout(logo_form)
        logo_form.setContentsMargins(0, 0, 0, 0)
        logo_form.setVerticalSpacing(10)
        logo_row = QHBoxLayout()
        self.input_logo_path = QLineEdit()
        self.input_logo_path.setReadOnly(True)
        self.btn_browse_logo = QPushButton()
        self.btn_browse_logo.setProperty("class", "secondary")
        self.btn_browse_logo.setFixedHeight(32)
        self.btn_browse_logo.clicked.connect(self.browse_logo)
        self.btn_clear_logo = QPushButton()
        self.btn_clear_logo.setProperty("class", "secondary")
        self.btn_clear_logo.setFixedHeight(32)
        self.btn_clear_logo.clicked.connect(self._clear_logo)
        self.btn_logo_help = HelpIconButton(on_click=self._show_logo_guide)
        logo_row.addWidget(self.input_logo_path, 1)
        logo_row.addWidget(self.btn_browse_logo)
        logo_row.addWidget(self.btn_clear_logo)
        logo_row.addWidget(self.btn_logo_help)
        self._lbl_logo = QLabel()
        logo_form.addRow(self._lbl_logo, logo_row)
        self.lbl_logo_hint = QLabel()
        self.lbl_logo_hint.setProperty("class", "muted")
        self.lbl_logo_hint.setWordWrap(True)
        logo_form.addRow("", self.lbl_logo_hint)
        vbox_content.addLayout(logo_form)

        # Section: Header & Footer
        self._header_hf = self._make_section_header("settings.receipt.section_header_footer")
        vbox_content.addWidget(self._header_hf)

        hf_form = QFormLayout()
        self.configure_form_layout(hf_form)
        hf_form.setContentsMargins(0, 0, 0, 0)
        hf_form.setVerticalSpacing(10)

        header_container = QWidget()
        header_container_layout = QVBoxLayout(header_container)
        header_container_layout.setContentsMargins(0, 0, 0, 0)
        header_container_layout.setSpacing(2)
        self.txt_header = QTextEdit()
        self.txt_header.setFixedHeight(64)
        self.txt_header.textChanged.connect(self._update_header_char_count)
        header_container_layout.addWidget(self.txt_header)
        self._lbl_header_char_count = QLabel()
        self._lbl_header_char_count.setObjectName("CharCountHint")
        header_container_layout.addWidget(self._lbl_header_char_count)
        self._lbl_header_text = QLabel()
        hf_form.addRow(self._lbl_header_text, header_container)

        footer_container = QWidget()
        footer_container_layout = QVBoxLayout(footer_container)
        footer_container_layout.setContentsMargins(0, 0, 0, 0)
        footer_container_layout.setSpacing(2)
        self.txt_footer = QTextEdit()
        self.txt_footer.setFixedHeight(64)
        self.txt_footer.textChanged.connect(self._update_footer_char_count)
        footer_container_layout.addWidget(self.txt_footer)
        self._lbl_footer_char_count = QLabel()
        self._lbl_footer_char_count.setObjectName("CharCountHint")
        footer_container_layout.addWidget(self._lbl_footer_char_count)
        self._lbl_footer_text = QLabel()
        hf_form.addRow(self._lbl_footer_text, footer_container)

        vbox_content.addLayout(hf_form)

        # Section: Receipt Language
        self._header_receipt_lang = self._make_section_header("settings.receipt.section_receipt_language")
        vbox_content.addWidget(self._header_receipt_lang)

        lang_form = QFormLayout()
        self.configure_form_layout(lang_form)
        lang_form.setContentsMargins(0, 0, 0, 0)
        lang_form.setVerticalSpacing(10)

        lang_row = QHBoxLayout()
        self.combo_receipt_lang = QComboBox()
        self.combo_receipt_lang.addItem(_t("settings.receipt.lang_same_as_ui"), "")
        self.combo_receipt_lang.addItem("English", "en")
        self.combo_receipt_lang.addItem("සිංහල (Sinhala)", "si")
        self.combo_receipt_lang.addItem("தமிழ் (Tamil)", "ta")
        lang_row.addWidget(self.combo_receipt_lang)
        self.btn_receipt_lang_help = HelpIconButton()
        lang_row.addWidget(self.btn_receipt_lang_help)
        lang_row.addStretch()
        self._lbl_receipt_lang = QLabel()
        lang_form.addRow(self._lbl_receipt_lang, lang_row)
        vbox_content.addLayout(lang_form)

        # Without this, the scroll area's inner widget stretches to fill
        # the tab's full height (QScrollArea.setWidgetResizable), and with
        # no trailing stretch item to absorb that surplus, Qt hands it to
        # whichever field widgets can grow -- ballooning the header/footer
        # char-count labels dozens of pixels past their own text (visible
        # as odd gaps before Footer Text / Receipt Language) instead of
        # leaving it as plain empty space below the last section.
        vbox_content.addStretch()

        self.tabs.addTab(tab_content, "")

        # ===================== Tab 2: Display =====================
        tab_display, vbox_display = self._build_vbox_tab()

        # Section: Receipt Elements
        self._header_elements = self._make_section_header("settings.receipt.section_receipt_elements")
        vbox_display.addWidget(self._header_elements)

        elem_form = QFormLayout()
        self.configure_form_layout(elem_form)
        elem_form.setContentsMargins(0, 0, 0, 0)
        elem_form.setVerticalSpacing(10)

        self.chk_show_barcode = QCheckBox()
        self.chk_merge_items = QCheckBox()
        self.chk_show_tax = QCheckBox()

        self._lbl_show_barcode = QLabel()
        self._lbl_merge_items = QLabel()
        self._lbl_tax_breakdown = QLabel()

        elem_form.addRow("", self.chk_show_barcode)
        elem_form.addRow("", self.chk_merge_items)
        elem_form.addRow("", self.chk_show_tax)
        vbox_display.addLayout(elem_form)

        # Section: QR Code -- the schema and config keys
        # (show_qr_on_receipt/receipt_qr_content) already existed, just
        # never wired to a toggle, a builder emission, or a printer
        # command (#328).
        self._header_qr = self._make_section_header("settings.receipt.section_qr")
        vbox_display.addWidget(self._header_qr)

        qr_form = QFormLayout()
        self.configure_form_layout(qr_form)
        qr_form.setContentsMargins(0, 0, 0, 0)
        qr_form.setVerticalSpacing(10)

        self.chk_show_qr = QCheckBox()
        qr_form.addRow("", self.chk_show_qr)

        self.txt_qr_content = QLineEdit()
        self._lbl_qr_content = QLabel()
        qr_form.addRow(self._lbl_qr_content, self.txt_qr_content)
        # QR content only matters while the QR is shown (#564).
        self.chk_show_qr.toggled.connect(self._toggle_qr_content)
        vbox_display.addLayout(qr_form)

        # Section: Staff & Terminal
        self._header_staff = self._make_section_header("settings.receipt.section_staff_terminal")
        vbox_display.addWidget(self._header_staff)

        staff_form = QFormLayout()
        self.configure_form_layout(staff_form)
        staff_form.setContentsMargins(0, 0, 0, 0)
        staff_form.setVerticalSpacing(10)

        self.chk_show_cashier = QCheckBox()
        self.chk_show_terminal = QCheckBox()

        staff_form.addRow("", self.chk_show_cashier)
        staff_form.addRow("", self.chk_show_terminal)
        vbox_display.addLayout(staff_form)

        # Section: Warranty (#824)
        self.warranty_container = QWidget()
        w_layout = QVBoxLayout(self.warranty_container)
        w_layout.setContentsMargins(0, 0, 0, 0)
        w_layout.setSpacing(10)

        self._header_warranty = self._make_section_header("settings.receipt.section_warranty")
        w_layout.addWidget(self._header_warranty)

        warranty_form = QFormLayout()
        self.configure_form_layout(warranty_form)
        warranty_form.setContentsMargins(0, 0, 0, 0)
        warranty_form.setVerticalSpacing(10)

        self.chk_show_warranty = QCheckBox()
        warranty_form.addRow("", self.chk_show_warranty)

        self.combo_warranty_card_mode = QComboBox()
        self.combo_warranty_card_mode.addItem(_t("settings.receipt.warranty_card_mode_off", default="Off"), "OFF")
        self.combo_warranty_card_mode.addItem(
            _t("settings.receipt.warranty_card_mode_ask", default="Ask after checkout"), "ASK"
        )
        self.combo_warranty_card_mode.addItem(
            _t("settings.receipt.warranty_card_mode_always", default="Always print"), "ALWAYS"
        )
        self._lbl_warranty_card_mode = QLabel()
        warranty_form.addRow(self._lbl_warranty_card_mode, self.combo_warranty_card_mode)

        w_layout.addLayout(warranty_form)
        vbox_display.addWidget(self.warranty_container)

        vbox_display.addStretch()

        self.tabs.addTab(tab_display, "")

        # --- Connect all inputs to live preview refresh ---
        self._connect_live_signals()

        self.retranslate_ui()
        register_language_callback(self.retranslate_ui, owner=self)

    def _show_logo_guide(self) -> None:
        """Show guide dialog explaining monochrome receipt logo optimization."""
        steps = [
            ("settings.receipt.guide_logo_step1_title", "settings.receipt.guide_logo_step1_detail"),
            ("settings.receipt.guide_logo_step2_title", "settings.receipt.guide_logo_step2_detail"),
            ("settings.receipt.guide_logo_step3_title", "settings.receipt.guide_logo_step3_detail"),
        ]
        dlg = GuideDialog(
            title_key="settings.receipt.guide_logo_title",
            steps=steps,
            note_key="settings.receipt.guide_logo_note",
            parent=self,
        )
        dlg.exec()

    def retranslate_ui(self) -> None:
        """Update all widget text and tab labels from the translation system."""
        self._page_title.setText(_t("settings.receipt.title"))
        self.btn_reset_defaults.setText(_t("settings.btn_reset_defaults"))
        self._page_subtitle.setText(_t("settings.receipt.subtitle"))
        self._retranslate_section_headers()
        self._lbl_receipt_cross_ref.setText(_t("settings.receipt.cross_ref_hint"))

        self.tabs.setTabText(0, _t("settings.receipt.tab_content"))
        self.tabs.setTabText(1, _t("settings.receipt.tab_display"))
        self._lbl_preview_title.setText(_t("settings.receipt.section_live_preview"))
        self._lbl_preview_width.setText(_t("settings.receipt.preview_width_label"))

        # Content tab
        self._lbl_logo.setText(_t("settings.receipt.logo_label"))
        self.input_logo_path.setPlaceholderText(_t("settings.receipt.logo_placeholder"))
        self.btn_browse_logo.setText(_t("settings.receipt.btn_browse_logo"))
        self.btn_clear_logo.setText(_t("settings.receipt.btn_clear_logo"))
        self.btn_logo_help.setToolTip(_t("settings.receipt.tooltip_logo_help"))
        self.lbl_logo_hint.setText(_t("settings.receipt.logo_hint"))
        self._lbl_header_text.setText(_t("settings.receipt.header_text"))
        self.txt_header.setPlaceholderText(_t("settings.receipt.header_placeholder"))
        self._lbl_footer_text.setText(_t("settings.receipt.footer_text"))
        self.txt_footer.setPlaceholderText(_t("settings.receipt.footer_placeholder"))
        # Re-localize the char-count text and tooltip -- otherwise a
        # language switch leaves them in whichever language was active the
        # last time the header/footer text actually changed.
        self._update_header_char_count()
        self._update_footer_char_count()

        # Receipt language
        self._lbl_receipt_lang.setText(_t("settings.receipt.receipt_language"))
        self.btn_receipt_lang_help.setToolTip(_t("settings.receipt.receipt_language_hint"))
        self.combo_receipt_lang.setItemText(0, _t("settings.receipt.lang_same_as_ui"))

        # Display tab
        self.chk_show_barcode.setText(_t("settings.receipt.chk_show_barcode"))
        self.chk_show_barcode.setToolTip(_t("settings.receipt.tooltip_show_barcode"))
        self.chk_merge_items.setText(_t("settings.receipt.chk_merge_items"))
        self.chk_merge_items.setToolTip(_t("settings.receipt.tooltip_merge_items"))
        self.chk_show_tax.setText(_t("settings.receipt.chk_show_tax"))
        self.chk_show_tax.setToolTip(_t("settings.receipt.tooltip_show_tax"))
        self.chk_show_qr.setText(_t("settings.receipt.chk_show_qr"))
        self.chk_show_qr.setToolTip(_t("settings.receipt.tooltip_show_qr"))
        self._lbl_qr_content.setText(_t("settings.receipt.qr_content"))
        self.txt_qr_content.setPlaceholderText(_t("settings.receipt.qr_content_placeholder"))
        self.chk_show_cashier.setText(_t("settings.receipt.chk_show_cashier"))
        self.chk_show_cashier.setToolTip(_t("settings.receipt.tooltip_show_cashier"))
        self.chk_show_terminal.setText(_t("settings.receipt.chk_show_terminal"))
        self.chk_show_terminal.setToolTip(_t("settings.receipt.tooltip_show_terminal"))

        # Warranty section (#824)
        if hasattr(self, "chk_show_warranty"):
            self.chk_show_warranty.setText(
                _t("settings.receipt.show_warranty_on_receipt", default="Show warranty details on receipt")
            )
            self._lbl_warranty_card_mode.setText(
                _t("settings.receipt.warranty_card_mode", default="Print warranty cards")
            )
            self.combo_warranty_card_mode.setItemText(0, _t("settings.receipt.warranty_card_mode_off", default="Off"))
            self.combo_warranty_card_mode.setItemText(
                1, _t("settings.receipt.warranty_card_mode_ask", default="Ask after checkout")
            )
            self.combo_warranty_card_mode.setItemText(
                2, _t("settings.receipt.warranty_card_mode_always", default="Always print")
            )

        self.equalize_form_labels()

    # ------------------------------------------------------------------
    # Signal wiring for live preview
    # ------------------------------------------------------------------

    def _connect_live_signals(self) -> None:
        """Connect every settings widget's change signal to the debounced refresh."""
        trigger = self._schedule_refresh
        # Text inputs
        self.input_logo_path.textChanged.connect(trigger)
        self.txt_header.textChanged.connect(trigger)
        self.txt_footer.textChanged.connect(trigger)
        self.combo_receipt_lang.currentIndexChanged.connect(trigger)
        # Checkboxes
        self.chk_show_barcode.stateChanged.connect(trigger)
        self.chk_merge_items.stateChanged.connect(trigger)
        self.chk_show_tax.stateChanged.connect(trigger)
        self.chk_show_qr.stateChanged.connect(trigger)
        self.txt_qr_content.textChanged.connect(trigger)
        self.chk_show_cashier.stateChanged.connect(trigger)
        self.chk_show_terminal.stateChanged.connect(trigger)
        if hasattr(self, "chk_show_warranty"):
            self.chk_show_warranty.stateChanged.connect(trigger)
            self.combo_warranty_card_mode.currentIndexChanged.connect(trigger)

    def _schedule_refresh(self) -> None:
        """Restart the debounce timer -- preview refreshes after 300 ms of inactivity."""
        self._refresh_timer.start()

    def _refresh_preview(self) -> None:
        """Build receipt commands from current settings and update the preview."""
        # The preview width selector is independent of the real Hardware-tab
        # paper_width -- it lets a shop check the OTHER paper size's layout
        # without touching their actual printer configuration. self.save()
        # never includes paper_width (that field lives on the Hardware tab),
        # so injecting the previewed width into a copy of it here only
        # affects this dummy preview build, never anything persisted (#325).
        preview_width = self.combo_preview_width.currentData() or "80mm"
        self._preview.set_paper_width(preview_width)

        config = self.save()
        config["paper_width"] = preview_width
        commands = ReceiptBuilder.build_receipt(
            self._make_dummy_sale(),
            config_override=config,
        )
        self._preview.set_commands(commands)
        self._update_header_char_count()
        self._update_footer_char_count()

    def _current_line_chars(self) -> int:
        """Characters-per-line budget for the currently *previewed* paper width.

        Mirrors BaseReceiptBuilder._append_header_block's own 58mm=32 /
        80mm=42 mapping, kept in sync with whichever width the live preview
        to the right is currently showing (not necessarily the real
        Hardware-tab setting -- see _refresh_preview).
        """
        paper_width = self.combo_preview_width.currentData()
        return 32 if paper_width == "58mm" else 42

    def _set_char_count_hint(self, label: QLabel, text: str) -> None:
        line_chars = self._current_line_chars()
        longest = max((len(line) for line in text.split("\n")), default=0)
        label.setText(_t("settings.receipt.char_count_hint", longest=longest, limit=line_chars))
        # The wrap explanation only needs saying once, not on every line of
        # every field -- move it off the always-visible label and onto a
        # hover tooltip, same as the Logo/Receipt Language hints.
        label.setToolTip(_t("settings.receipt.char_count_tooltip"))

    def _update_header_char_count(self) -> None:
        self._set_char_count_hint(self._lbl_header_char_count, self.txt_header.toPlainText())

    def _update_footer_char_count(self) -> None:
        self._set_char_count_hint(self._lbl_footer_char_count, self.txt_footer.toPlainText())

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def browse_logo(self) -> None:
        """Prompt for an image and copy it into the data folder as the receipt logo.

        The copy (not the picked file) is what prints, so moving or
        deleting the original -- or restoring a backup on another PC --
        keeps the logo (#626).
        """
        path, _ = QFileDialog.getOpenFileName(
            self,
            _t("settings.receipt.select_logo_title"),
            "",
            _t("settings.receipt.select_logo_filter"),
        )
        if not path:
            return
        try:
            stored = store_receipt_logo(path)
        except (OSError, ValueError) as e:
            logger.error("Could not copy receipt logo %s: %s", path, e)
            QMessageBox.warning(self, _t("common.error"), _t("settings.receipt.logo_copy_failed"))
            return
        self.input_logo_path.setText(stored)

    def _clear_logo(self) -> None:
        self.input_logo_path.clear()

    def load(self, settings: dict) -> None:
        """Populate logo, header/footer, receipt elements and language fields, then refresh the live preview."""
        # Block signals during bulk load to avoid N refreshes
        self._refresh_timer.stop()
        self.input_logo_path.setText(settings.get("receipt_logo_path", ""))
        self.txt_header.setText(settings.get("receipt_header", ""))
        self.txt_footer.setText(settings.get("receipt_footer", ""))
        from cbpos.core.services.config_service import ConfigService

        _d = ConfigService.DEFAULTS
        self.chk_show_barcode.setChecked(settings.get("show_barcode", _d["show_barcode"]))
        self.chk_merge_items.setChecked(settings.get("merge_items", _d["merge_items"]))
        self.chk_show_tax.setChecked(settings.get("show_tax_breakdown", _d["show_tax_breakdown"]))
        self.chk_show_qr.setChecked(settings.get("show_qr_on_receipt", _d["show_qr_on_receipt"]))
        self.txt_qr_content.setText(settings.get("receipt_qr_content", _d["receipt_qr_content"]))
        # setChecked() only emits toggled on a change, so sync explicitly.
        self._toggle_qr_content()
        self.chk_show_cashier.setChecked(settings.get("show_cashier_on_receipt", _d["show_cashier_on_receipt"]))
        self.chk_show_terminal.setChecked(settings.get("show_terminal_on_receipt", _d["show_terminal_on_receipt"]))

        # Warranty section (#824)
        if hasattr(self, "warranty_container"):
            from cbpos.core.services.warranty_service import WarrantyService

            w_enabled = WarrantyService.is_enabled()
            self.warranty_container.setVisible(w_enabled)
            self.chk_show_warranty.setChecked(
                settings.get("show_warranty_on_receipt", _d.get("show_warranty_on_receipt", True))
            )
            w_mode = settings.get("warranty_card_mode", _d.get("warranty_card_mode", "ASK"))
            idx_m = self.combo_warranty_card_mode.findData(w_mode)
            if idx_m >= 0:
                self.combo_warranty_card_mode.setCurrentIndex(idx_m)

        # Receipt language
        receipt_lang = settings.get("receipt_language", "")
        idx = self.combo_receipt_lang.findData(receipt_lang)
        if idx >= 0:
            self.combo_receipt_lang.setCurrentIndex(idx)

        # Preview width defaults to whatever's really configured on the
        # Hardware tab -- from there the shop can switch it to check the
        # other size without touching that real setting.
        real_paper_width = ConfigService.get("paper_width") or "80mm"
        idx = self.combo_preview_width.findData(real_paper_width)
        if idx >= 0:
            self.combo_preview_width.setCurrentIndex(idx)

        # Single refresh after all fields loaded
        self._refresh_preview()

    def save(self) -> dict:
        """Return logo, header/footer, receipt elements and language fields as a settings dict."""
        return {
            "receipt_logo_path": self.input_logo_path.text(),
            "receipt_header": self.txt_header.toPlainText(),
            "receipt_footer": self.txt_footer.toPlainText(),
            "show_barcode": self.chk_show_barcode.isChecked(),
            "merge_items": self.chk_merge_items.isChecked(),
            "show_tax_breakdown": self.chk_show_tax.isChecked(),
            "show_qr_on_receipt": self.chk_show_qr.isChecked(),
            "receipt_qr_content": self.txt_qr_content.text().strip(),
            "show_cashier_on_receipt": self.chk_show_cashier.isChecked(),
            "show_terminal_on_receipt": self.chk_show_terminal.isChecked(),
            "show_warranty_on_receipt": self.chk_show_warranty.isChecked()
            if hasattr(self, "chk_show_warranty")
            else True,
            "warranty_card_mode": self.combo_warranty_card_mode.currentData()
            if hasattr(self, "combo_warranty_card_mode")
            else "ASK",
            "receipt_language": self.combo_receipt_lang.currentData() or "",
        }

    def _toggle_qr_content(self) -> None:
        """Enable the QR content field (and its label) only while Show QR is on."""
        enabled = self.chk_show_qr.isChecked()
        self.txt_qr_content.setEnabled(enabled)
        self._lbl_qr_content.setEnabled(enabled)

    def save_warnings(self) -> list[str]:
        """Warn when the QR is switched on with nothing to encode -- it would silently print no QR."""
        if self.chk_show_qr.isChecked() and not self.txt_qr_content.text().strip():
            return [_t("settings.receipt.qr_content_empty_warning")]
        return []

    @staticmethod
    def _make_dummy_sale() -> Sale:
        """Create a realistic sample sale for the preview."""
        from datetime import datetime

        sale = Sale(
            id=42,
            document_number="INV-2026-00042",
            date=datetime.now(),
            total_amount=decimal.Decimal("1450.00"),
            tax_vat=decimal.Decimal("221.19"),
            tax_sscl=decimal.Decimal("36.25"),
            net_revenue=decimal.Decimal("1192.56"),
        )
        p1 = Product(name_en="Product A")
        p2 = Product(name_en="Product B")
        p3 = Product(name_en="Product C")
        sale.items = [
            SaleItem(
                product=p1,
                qty=decimal.Decimal("2"),
                unit_price=decimal.Decimal("150.00"),
                original_price=decimal.Decimal("150.00"),
                subtotal=decimal.Decimal("300.00"),
            ),
            SaleItem(
                product=p2,
                qty=decimal.Decimal("1"),
                unit_price=decimal.Decimal("400.00"),
                original_price=decimal.Decimal("450.00"),
                subtotal=decimal.Decimal("400.00"),
            ),
            SaleItem(
                product=p3,
                qty=decimal.Decimal("3"),
                unit_price=decimal.Decimal("250.00"),
                original_price=decimal.Decimal("250.00"),
                subtotal=decimal.Decimal("750.00"),
            ),
        ]
        sale.payments = [
            SalePayment(payment_method="Cash", amount=decimal.Decimal("1500.00")),
        ]
        return sale


__all__ = ["ReceiptPage"]
