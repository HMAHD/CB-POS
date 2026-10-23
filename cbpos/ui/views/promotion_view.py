"""Promotion view for listing, creating, and managing discount promotions."""

import logging
from datetime import datetime

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QMenu,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from cbpos.core.services.category_service import CategoryService
from cbpos.core.services.promotion_service import SUPPORTED_TYPES, PromotionService
from cbpos.core.utils.error_messages import translate_error
from cbpos.core.utils.formatters import format_datetime, format_discount, format_promotion_type
from cbpos.i18n import _t, register_language_callback
from cbpos.ui.dialogs.promotion_dialog import PromotionDialog
from cbpos.ui.resources.icons import Icons
from cbpos.ui.resources.status_colors import DANGER, INFO, NEUTRAL, SUCCESS
from cbpos.ui.widgets.status_pill_delegate import StatusPillDelegate, set_status_pill
from cbpos.ui.widgets.table_helpers import (
    NUMERIC_ALIGNMENT,
    align_numeric_headers,
    attach_table_empty_state,
    batch_table_update,
    configure_table_columns,
)

logger = logging.getLogger(__name__)

__all__ = ["CategoryService", "PromotionDialog", "PromotionView"]

_DAY_KEYS = [
    "promotion.day_mon",
    "promotion.day_tue",
    "promotion.day_wed",
    "promotion.day_thu",
    "promotion.day_fri",
    "promotion.day_sat",
    "promotion.day_sun",
]


class PromotionView(QWidget):
    """Promotion list view with add, edit, activate/deactivate, and delete actions."""

    def __init__(self):
        """Initialize the promotion service, build the UI, and load existing promotions."""
        super().__init__()
        self.promotion_service = PromotionService()
        self._loading_promotions = False
        self.init_ui()
        self.load_promotions()

        self.retranslate_ui()
        register_language_callback(self.retranslate_ui, owner=self)

    def init_ui(self):
        """Build the header and promotions table layout."""
        layout = QVBoxLayout(self)

        # Header
        header = QHBoxLayout()
        header.addStretch(1)

        self.btn_add = QPushButton()
        self.btn_add.setProperty("class", "accent")
        self.btn_add.clicked.connect(self.add_promotion)
        header.addWidget(self.btn_add)

        layout.addLayout(header)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        configure_table_columns(
            self.table.horizontalHeader(),
            {
                0: QHeaderView.ResizeMode.Stretch,  # Name - needs the room
                1: QHeaderView.ResizeMode.ResizeToContents,  # Type
                2: QHeaderView.ResizeMode.ResizeToContents,  # Value
                3: QHeaderView.ResizeMode.ResizeToContents,  # Start
                4: QHeaderView.ResizeMode.ResizeToContents,  # End
                5: QHeaderView.ResizeMode.ResizeToContents,  # Scope
                6: QHeaderView.ResizeMode.ResizeToContents,  # Status
                7: QHeaderView.ResizeMode.ResizeToContents,  # On/Off (#595)
            },
        )
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setItemDelegateForColumn(6, StatusPillDelegate(self.table))  # Status (#560)
        self.empty_promotion_state = attach_table_empty_state(self.table, Icons.PROMOTION, "common.no_items")
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(self.edit_promotion)
        self.table.itemChanged.connect(self._on_table_item_changed)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self.table)

    def retranslate_ui(self):
        """Update all translatable strings."""
        self.btn_add.setText(_t("promotion.create_promotion"))
        self.table.setHorizontalHeaderLabels(
            [
                _t("common.name"),
                _t("promotion.type"),
                _t("promotion.value"),
                _t("promotion.start"),
                _t("promotion.end"),
                _t("promotion.scope"),
                _t("common.status"),
                _t("promotion.col_on_off"),
            ]
        )
        align_numeric_headers(self.table, (2,))  # Value

    @staticmethod
    def _get_promotion_status(promotion) -> tuple[str, str]:
        """Return (label, palette meaning) reflecting whether a promotion is really
        active right now, rather than trusting its stored is_active flag on
        its own -- that flag is only ever set True at creation and otherwise
        only changes when an admin manually toggles it, so a promotion whose
        end_time passed months ago would otherwise show "Active" forever.
        """
        if not promotion.is_active:
            return _t("common.inactive"), NEUTRAL
        # Checkout has no BOGO branch, so such a promotion never applies (#635).
        if promotion.type not in SUPPORTED_TYPES:
            return _t("promotion.status_not_applied"), DANGER

        now = datetime.now()
        if promotion.end_time < now:
            return _t("promotion.status_expired"), NEUTRAL
        if promotion.start_time > now:
            return _t("promotion.status_upcoming"), INFO
        return _t("common.active"), SUCCESS

    def load_promotions(self):
        """Reload promotions from the service and repopulate the table."""
        self._loading_promotions = True
        try:
            self.promotions = self.promotion_service.get_all_promotions()
            with batch_table_update(self.table):
                self.table.setRowCount(0)

                # Hoist LEGB locals
                table = self.table
                insert_row = table.insertRow
                set_item = table.setItem
                TableItem = QTableWidgetItem
                num_align = NUMERIC_ALIGNMENT
                align_center = Qt.AlignmentFlag.AlignCenter
                item_flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable
                checked_state = Qt.CheckState.Checked
                unchecked_state = Qt.CheckState.Unchecked
                fmt_type = format_promotion_type
                fmt_disc = format_discount
                fmt_dt = format_datetime
                all_prod_str = _t("promotion.scope_all_products")
                get_status = self._get_promotion_status
                pill_setter = set_status_pill

                for p in self.promotions:
                    row = table.rowCount()
                    insert_row(row)

                    set_item(row, 0, TableItem(p.name))
                    set_item(row, 1, TableItem(fmt_type(p.type)))
                    value_item = TableItem(fmt_disc(p.type, p.value))
                    value_item.setTextAlignment(num_align)
                    set_item(row, 2, value_item)
                    set_item(row, 3, TableItem(fmt_dt(p.start_time)))
                    set_item(row, 4, TableItem(fmt_dt(p.end_time)))

                    scope_text = p.category.name if p.category_id and p.category else all_prod_str
                    set_item(row, 5, TableItem(scope_text))

                    status_text, meaning = get_status(p)
                    set_item(row, 6, pill_setter(TableItem(), status_text, meaning))

                    on_off_item = TableItem()
                    on_off_item.setFlags(item_flags)
                    on_off_item.setCheckState(checked_state if p.is_active else unchecked_state)
                    on_off_item.setTextAlignment(align_center)
                    set_item(row, 7, on_off_item)
        finally:
            self._loading_promotions = False

    def add_promotion(self):
        """Open the create dialog and persist a new promotion on accept."""
        dialog = PromotionDialog(self)
        if dialog.exec():
            data = dialog.get_data()
            try:
                self.promotion_service.create_promotion(**data)
                self.load_promotions()
            except Exception as e:
                logger.exception("Failed to create promotion: %s", e)
                QMessageBox.critical(self, _t("common.error"), translate_error(str(e)))

    def _show_context_menu(self, position) -> None:
        item = self.table.itemAt(position)
        if not item:
            return
        row = item.row()
        promotion = self.promotions[row]

        menu = QMenu(self)
        action_edit = menu.addAction(_t("promotion.context_edit"))
        toggle_label = _t("promotion.context_deactivate") if promotion.is_active else _t("promotion.context_activate")
        action_toggle = menu.addAction(toggle_label)
        action_delete = menu.addAction(_t("promotion.context_delete"))

        chosen = menu.exec(self.table.viewport().mapToGlobal(position))
        if chosen == action_edit:
            self._edit_promotion_row(row)
        elif chosen == action_toggle:
            self._toggle_promotion_active(row)
        elif chosen == action_delete:
            self._delete_promotion_row(row)

    def edit_promotion(self, index) -> None:
        """Open the edit dialog for the double-clicked table row."""
        if index.column() == 7:
            return
        self._edit_promotion_row(index.row())

    def _on_table_item_changed(self, item: QTableWidgetItem) -> None:
        if getattr(self, "_loading_promotions", False):
            return
        if item.column() == 7:
            row = item.row()
            if 0 <= row < len(self.promotions):
                p = self.promotions[row]
                new_state = item.checkState() == Qt.CheckState.Checked
                if new_state != p.is_active:
                    try:
                        self.promotion_service.update_promotion(p.id, is_active=new_state)
                        self.load_promotions()
                    except Exception as e:
                        logger.exception("Failed to toggle promotion active: %s", e)
                        QMessageBox.critical(self, _t("common.error"), translate_error(str(e)))
                        self.load_promotions()

    def _edit_promotion_row(self, row: int) -> None:
        if row < 0 or row >= len(self.promotions):
            return
        promotion = self.promotions[row]

        dialog = PromotionDialog(self, promotion=promotion)
        if dialog.exec():
            data = dialog.get_data()
            try:
                self.promotion_service.update_promotion(promotion.id, **data)
                self.load_promotions()
            except Exception as e:
                logger.exception("Failed to update promotion: %s", e)
                QMessageBox.critical(self, _t("common.error"), translate_error(str(e)))

    def _toggle_promotion_active(self, row: int) -> None:
        if row < 0 or row >= len(self.promotions):
            return
        promotion = self.promotions[row]

        try:
            self.promotion_service.update_promotion(promotion.id, is_active=not promotion.is_active)
            self.load_promotions()
        except Exception as e:
            logger.exception("Failed to toggle promotion active: %s", e)
            QMessageBox.critical(self, _t("common.error"), translate_error(str(e)))

    def _delete_promotion_row(self, row: int) -> None:
        if row < 0 or row >= len(self.promotions):
            return
        promotion = self.promotions[row]

        reply = QMessageBox.question(
            self,
            _t("promotion.confirm_delete_title"),
            _t("promotion.confirm_delete_msg", name=promotion.name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            self.promotion_service.delete_promotion(promotion.id)
            self.load_promotions()
        except Exception as e:
            logger.exception("Failed to delete promotion: %s", e)
            QMessageBox.critical(self, _t("common.error"), translate_error(str(e)))
