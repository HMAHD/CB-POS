"""Data Safety -> Maintenance tab: database info, optimize (VACUUM), integrity check."""

import logging

from PyQt6.QtWidgets import QFormLayout, QFrame, QGroupBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from cbpos.i18n import _t
from cbpos.ui.utils.style_helpers import set_status_class
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

        # Database info card
        self.grp_info = QGroupBox()
        info_layout = QFormLayout(self.grp_info)
        info_layout.setVerticalSpacing(10)
        info_layout.setHorizontalSpacing(20)

        self.lbl_db_size = QLabel("--")
        self.lbl_db_size.setProperty("class", "bold")
        self.lbl_db_size_label = QLabel()
        info_layout.addRow(self.lbl_db_size_label, self.lbl_db_size)

        self.lbl_products_count = QLabel("--")
        self.lbl_products_count.setProperty("class", "bold")
        self.lbl_products_label = QLabel()
        info_layout.addRow(self.lbl_products_label, self.lbl_products_count)

        self.lbl_customers_count = QLabel("--")
        self.lbl_customers_count.setProperty("class", "bold")
        self.lbl_customers_label = QLabel()
        info_layout.addRow(self.lbl_customers_label, self.lbl_customers_count)

        self.lbl_sales_count = QLabel("--")
        self.lbl_sales_count.setProperty("class", "bold")
        self.lbl_sales_label = QLabel()
        info_layout.addRow(self.lbl_sales_label, self.lbl_sales_count)

        layout.addWidget(self.grp_info)

        # Actions card
        self.grp_actions = QGroupBox()
        actions_layout = QVBoxLayout(self.grp_actions)
        actions_layout.setSpacing(12)

        # Optimize row
        optimize_row = QHBoxLayout()
        optimize_info = QVBoxLayout()
        self.lbl_opt_title = QLabel()
        self.lbl_opt_title.setProperty("class", "bold")
        optimize_info.addWidget(self.lbl_opt_title)
        self.lbl_opt_desc = QLabel()
        self.lbl_opt_desc.setProperty("class", "muted")
        self.lbl_opt_desc.setWordWrap(True)
        optimize_info.addWidget(self.lbl_opt_desc)
        optimize_row.addLayout(optimize_info, 1)

        self.btn_vacuum = QPushButton()
        # Optimize and Check are equivalent maintenance actions -> same
        # (secondary) emphasis, neither is the screen's primary action.
        self.btn_vacuum.setProperty("class", "secondary")
        self.btn_vacuum.setFixedWidth(140)
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
        integrity_info = QVBoxLayout()
        self.lbl_int_title = QLabel()
        self.lbl_int_title.setProperty("class", "bold")
        integrity_info.addWidget(self.lbl_int_title)
        self.lbl_int_desc = QLabel()
        self.lbl_int_desc.setProperty("class", "muted")
        self.lbl_int_desc.setWordWrap(True)
        integrity_info.addWidget(self.lbl_int_desc)
        integrity_row.addLayout(integrity_info, 1)

        self.btn_integrity = QPushButton()
        self.btn_integrity.setProperty("class", "secondary")
        self.btn_integrity.setFixedWidth(140)
        self.btn_integrity.clicked.connect(self._run_integrity_check)
        integrity_row.addWidget(self.btn_integrity)
        actions_layout.addLayout(integrity_row)

        self.lbl_maintenance_status = QLabel("")
        self.lbl_maintenance_status.setWordWrap(True)
        actions_layout.addWidget(self.lbl_maintenance_status)

        layout.addWidget(self.grp_actions)
        layout.addStretch()

    def refresh(self) -> None:
        """Reload the database size and record counts."""
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
