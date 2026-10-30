"""Data Safety -> Maintenance tab: database info, optimize (VACUUM), integrity check."""

import logging

from PyQt6.QtWidgets import QFrame, QGroupBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from cbpos.core.services.backup_service import BackupService
from cbpos.i18n import _t
from cbpos.ui.resources.icons import Icons
from cbpos.ui.utils.style_helpers import set_status_class
from cbpos.ui.views.data_safety.network_notice import NetworkModeNoticeCard
from cbpos.ui.widgets.loading_overlay import LoadingOverlay

logger = logging.getLogger(__name__)


class MaintenanceTabWidget(QWidget):
    """Database facts and the two maintenance actions, each run off the UI thread."""

    def __init__(self, overlay: LoadingOverlay, parent: QWidget | None = None) -> None:
        """Build the tab.

        Args:
            overlay: The page's loading overlay, shown while a job runs.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._overlay = overlay
        self._build_ui()
        self.retranslate_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 16, 8, 8)
        layout.setSpacing(16)

        # Database info card — Executive 4-card KPI metric grid
        self.grp_info = QGroupBox()
        info_box_layout = QVBoxLayout(self.grp_info)
        info_box_layout.setContentsMargins(14, 18, 14, 14)
        info_box_layout.setSpacing(12)

        cards_row = QHBoxLayout()
        cards_row.setSpacing(12)

        def _make_kpi_card(icon_name: str, title_lbl: QLabel, val_lbl: QLabel, subtitle_text: str) -> QFrame:
            card = QFrame()
            card.setObjectName("StatCard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(14, 12, 14, 12)
            card_layout.setSpacing(6)

            hdr = QHBoxLayout()
            hdr.setSpacing(8)
            icon_lbl = QLabel()
            icon_lbl.setPixmap(Icons.get(icon_name, "#00BCEB").pixmap(20, 20))
            hdr.addWidget(icon_lbl)
            title_lbl.setObjectName("StatLabel")
            title_lbl.setStyleSheet("font-size: 12px; font-weight: bold; color: #94A3B8;")
            hdr.addWidget(title_lbl, 1)
            card_layout.addLayout(hdr)

            val_lbl.setObjectName("StatBigValue")
            val_lbl.setStyleSheet("font-size: 22px; font-weight: bold; color: #00BCEB;")
            card_layout.addWidget(val_lbl)

            sub = QLabel(subtitle_text)
            sub.setProperty("class", "muted")
            sub.setStyleSheet("font-size: 11px;")
            card_layout.addWidget(sub)

            return card

        self.lbl_db_size = QLabel("--")
        self.lbl_db_size_label = QLabel()
        cards_row.addWidget(
            _make_kpi_card("fa5s.database", self.lbl_db_size_label, self.lbl_db_size, "SQLite Storage"), 1
        )

        self.lbl_products_count = QLabel("--")
        self.lbl_products_label = QLabel()
        cards_row.addWidget(
            _make_kpi_card(Icons.INVENTORY, self.lbl_products_label, self.lbl_products_count, "Catalog Items"), 1
        )

        self.lbl_customers_count = QLabel("--")
        self.lbl_customers_label = QLabel()
        cards_row.addWidget(
            _make_kpi_card(Icons.CUSTOMERS, self.lbl_customers_label, self.lbl_customers_count, "Active Accounts"), 1
        )

        self.lbl_sales_count = QLabel("--")
        self.lbl_sales_label = QLabel()
        cards_row.addWidget(
            _make_kpi_card(Icons.SALES, self.lbl_sales_label, self.lbl_sales_count, "Completed Orders"), 1
        )

        info_box_layout.addLayout(cards_row)
        layout.addWidget(self.grp_info)

        # Actions card
        self.grp_actions = QGroupBox()
        actions_layout = QVBoxLayout(self.grp_actions)
        actions_layout.setContentsMargins(14, 18, 14, 14)
        actions_layout.setSpacing(12)

        # Optimize row
        optimize_row = QHBoxLayout()
        optimize_row.setSpacing(14)
        optimize_info = QVBoxLayout()
        optimize_info.setSpacing(2)
        self.lbl_opt_title = QLabel()
        self.lbl_opt_title.setProperty("class", "bold")
        self.lbl_opt_title.setStyleSheet("font-size: 13px; font-weight: bold;")
        optimize_info.addWidget(self.lbl_opt_title)
        self.lbl_opt_desc = QLabel()
        self.lbl_opt_desc.setProperty("class", "muted")
        self.lbl_opt_desc.setWordWrap(True)
        optimize_info.addWidget(self.lbl_opt_desc)
        optimize_row.addLayout(optimize_info, 1)

        self.btn_vacuum = QPushButton()
        self.btn_vacuum.setProperty("class", "secondary")
        self.btn_vacuum.setIcon(Icons.get("fa5s.sync", "white"))
        self.btn_vacuum.setMinimumWidth(150)
        self.btn_vacuum.clicked.connect(self._run_vacuum)
        optimize_row.addWidget(self.btn_vacuum)
        actions_layout.addLayout(optimize_row)

        # Separator — let QSS style QFrame HLine
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        actions_layout.addWidget(sep)

        # Integrity check row
        integrity_row = QHBoxLayout()
        integrity_row.setSpacing(14)
        integrity_info = QVBoxLayout()
        integrity_info.setSpacing(2)
        self.lbl_int_title = QLabel()
        self.lbl_int_title.setProperty("class", "bold")
        self.lbl_int_title.setStyleSheet("font-size: 13px; font-weight: bold;")
        integrity_info.addWidget(self.lbl_int_title)
        self.lbl_int_desc = QLabel()
        self.lbl_int_desc.setProperty("class", "muted")
        self.lbl_int_desc.setWordWrap(True)
        integrity_info.addWidget(self.lbl_int_desc)
        integrity_row.addLayout(integrity_info, 1)

        self.btn_integrity = QPushButton()
        self.btn_integrity.setProperty("class", "secondary")
        self.btn_integrity.setIcon(Icons.get("fa5s.shield-alt", "white"))
        self.btn_integrity.setMinimumWidth(150)
        self.btn_integrity.clicked.connect(self._run_integrity_check)
        integrity_row.addWidget(self.btn_integrity)
        actions_layout.addLayout(integrity_row)

        self.lbl_maintenance_status = QLabel("")
        self.lbl_maintenance_status.setWordWrap(True)
        actions_layout.addWidget(self.lbl_maintenance_status)

        self.notice_card = NetworkModeNoticeCard()
        layout.addWidget(self.notice_card)

        layout.addWidget(self.grp_actions)
        layout.addStretch()
        self._apply_mode()

    def _apply_mode(self) -> None:
        supported = BackupService.is_supported()
        self.grp_info.setVisible(supported)
        self.grp_actions.setVisible(supported)
        self.notice_card.setVisible(not supported)

    def refresh(self) -> None:
        """Reload the database size and record counts."""
        self._apply_mode()
        if not BackupService.is_supported():
            return
        try:
            from cbpos.core.services.maintenance_service import MaintenanceService

            info = MaintenanceService.get_database_info()
            self.lbl_db_size.setText(info.get("size", "--"))
            self.lbl_products_count.setText(str(info.get("products", 0)))
            self.lbl_customers_count.setText(str(info.get("customers", 0)))
            self.lbl_sales_count.setText(str(info.get("sales", 0)))
        except Exception as e:
            logger.warning("Could not load DB info: %s", e)

    def _run_vacuum(self) -> None:
        self.btn_vacuum.setEnabled(False)
        self.lbl_maintenance_status.setText("")
        self._overlay.show_loading(_t("data_safety.maintenance_optimizing"))

        from cbpos.ui.workers import VacuumWorker

        self._vacuum_worker = VacuumWorker()
        self._vacuum_worker.result.connect(self._on_vacuum_finished)
        self._vacuum_worker.error.connect(self._on_vacuum_error)
        self._vacuum_worker.start()

    def _on_vacuum_finished(self, result: dict) -> None:
        self._overlay.hide_loading()
        self.btn_vacuum.setEnabled(True)
        self.btn_vacuum.setText(_t("data_safety.maintenance_btn_optimize"))
        saved = result.get("saved", "0 KB")
        set_status_class(
            self.lbl_maintenance_status,
            "credit",
            _t("data_safety.maintenance_optimize_complete", saved=saved),
        )
        self.refresh()

    def _on_vacuum_error(self, error: str) -> None:
        self._overlay.hide_loading()
        self.btn_vacuum.setEnabled(True)
        self.btn_vacuum.setText(_t("data_safety.maintenance_btn_optimize"))
        set_status_class(
            self.lbl_maintenance_status,
            "debit",
            _t("data_safety.maintenance_optimize_failed", error=error),
        )

    def _run_integrity_check(self) -> None:
        self.btn_integrity.setEnabled(False)
        self.lbl_maintenance_status.setText("")
        self._overlay.show_loading(_t("data_safety.maintenance_checking"))

        from cbpos.ui.workers import IntegrityCheckWorker

        self._integrity_worker = IntegrityCheckWorker()
        self._integrity_worker.result.connect(self._on_integrity_finished)
        self._integrity_worker.start()

    def _on_integrity_finished(self, ok: bool, message: str) -> None:
        self._overlay.hide_loading()
        self.btn_integrity.setEnabled(True)
        self.btn_integrity.setText(_t("data_safety.maintenance_btn_check"))
        if ok:
            set_status_class(
                self.lbl_maintenance_status,
                "credit",
                _t("data_safety.maintenance_integrity_passed"),
            )
        else:
            set_status_class(
                self.lbl_maintenance_status,
                "debit",
                _t("data_safety.maintenance_integrity_failed", message=message),
            )

    def retranslate_ui(self) -> None:
        """Update all translatable strings."""
        self.notice_card.retranslate_ui()
        self.grp_info.setTitle(_t("data_safety.maintenance_group_info"))
        self.lbl_db_size_label.setText(_t("data_safety.maintenance_db_size"))
        self.lbl_products_label.setText(_t("data_safety.maintenance_products"))
        self.lbl_customers_label.setText(_t("data_safety.maintenance_customers"))
        self.lbl_sales_label.setText(_t("data_safety.maintenance_sales"))
        self.grp_actions.setTitle(_t("data_safety.maintenance_group_tools"))
        self.lbl_opt_title.setText(_t("data_safety.maintenance_optimize_title"))
        self.lbl_opt_desc.setText(_t("data_safety.maintenance_optimize_desc"))
        self.btn_vacuum.setText(_t("data_safety.maintenance_btn_optimize"))
        self.lbl_int_title.setText(_t("data_safety.maintenance_integrity_title"))
        self.lbl_int_desc.setText(_t("data_safety.maintenance_integrity_desc"))
        self.btn_integrity.setText(_t("data_safety.maintenance_btn_check"))
