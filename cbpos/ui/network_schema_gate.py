"""PostgreSQL network mode schema gate (#799).

Ensures all terminals connecting to a shared PostgreSQL database run
against an identical schema version. Only the designated schema owner PC
may run Alembic migrations (under a PostgreSQL advisory lock).
Other terminals refuse to start against mismatched schemas with clear guidance.
"""

import logging
from enum import Enum

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QLabel,
    QMessageBox,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from cbpos.core.services.auth_service import AuthService
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.schema_migration_service import SchemaMigrationService
from cbpos.i18n import _t
from cbpos.ui.dialogs.admin_pin_dialog import AdminPinDialog

logger = logging.getLogger(__name__)


class GateAction(Enum):
    """Actions decided by the pure gate decision function."""

    CONTINUE = "continue"
    BLOCK_APP_TOO_OLD = "block_app_too_old"
    BLOCK_NEEDS_OWNER_UPDATE = "block_needs_owner_update"
    PROMPT_OWNER_UPDATE = "prompt_owner_update"


def decide(
    rev: str | None,
    head: str | None,
    known: set[str],
    is_owner: bool,
) -> GateAction:
    """Pure decision function for network mode startup schema check.

    Args:
        rev: Current stamped database revision (or None if empty/unstamped).
        head: Target head revision in Alembic scripts.
        known: Set of all revision identifiers known to this app version.
        is_owner: True if this PC is designated as the network schema owner.

    Returns:
        GateAction indicating what the UI should do.
    """
    if rev == head or rev is None:
        return GateAction.CONTINUE
    if rev not in known:
        return GateAction.BLOCK_APP_TOO_OLD
    if not is_owner:
        return GateAction.BLOCK_NEEDS_OWNER_UPDATE
    return GateAction.PROMPT_OWNER_UPDATE


class UpgradeWorker(QThread):
    """Worker thread to execute schema migration off the Qt UI thread."""

    success = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, db_uri: str, user_id: int | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.db_uri = db_uri
        self.user_id = user_id

    def run(self):
        """Execute migration with advisory lock in worker thread."""
        try:
            SchemaMigrationService.upgrade_with_lock(self.db_uri, user_id=self.user_id)
            self.success.emit()
        except Exception as e:
            logger.exception("Network schema upgrade failed: %s", e)
            self.error.emit(str(e))


class NetworkSchemaGate:
    """Coordinates network startup checks and migration dialogs."""

    @classmethod
    def check_and_gate(cls, parent: QWidget | None = None) -> bool:
        """Run network schema gate check.

        Returns True if application startup should proceed; False if it was cancelled or blocked.
        """
        db_mode = ConfigService.get("db_mode") or "standalone"
        if db_mode != "network":
            return True

        try:
            pg_uri = ConfigService.get_postgres_uri()
        except Exception as e:
            logger.error("Could not obtain PostgreSQL URI: %s", e)
            return True

        is_owner = bool(ConfigService.get("network_schema_owner"))

        while True:
            try:
                rev = SchemaMigrationService.current_revision(pg_uri)
                head = SchemaMigrationService.head_revision(pg_uri)
                known = SchemaMigrationService.known_revisions(pg_uri)
            except Exception as e:
                logger.error("Error inspecting PostgreSQL schema revision: %s", e)
                # Fail closed on database inspection failure in network mode
                QMessageBox.critical(
                    parent,
                    _t("common.error"),
                    _t("network_gate.update_failed", error=str(e)),
                )
                return False

            action = decide(rev, head, known, is_owner)

            if action == GateAction.CONTINUE:
                return True

            if action == GateAction.BLOCK_APP_TOO_OLD:
                QMessageBox.critical(
                    parent,
                    _t("common.error"),
                    _t("network_gate.newer_body"),
                )
                return False

            if action == GateAction.BLOCK_NEEDS_OWNER_UPDATE:
                owner_host = SchemaMigrationService.get_schema_owner_host(pg_uri) or "Main PC"
                msg_box = QMessageBox(
                    QMessageBox.Icon.Warning,
                    _t("network_gate.behind_title"),
                    _t("network_gate.behind_body", host=owner_host),
                    QMessageBox.StandardButton.Retry | QMessageBox.StandardButton.Close,
                    parent,
                )
                res = msg_box.exec()
                if res == QMessageBox.StandardButton.Retry:
                    continue
                return False

            if action == GateAction.PROMPT_OWNER_UPDATE:
                return cls._run_owner_upgrade(pg_uri, parent=parent)

        return True

    @classmethod
    def _run_owner_upgrade(cls, pg_uri: str, parent: QWidget | None = None) -> bool:
        """Prompt admin PIN and perform off-thread database upgrade."""
        msg = QMessageBox(
            QMessageBox.Icon.Question,
            _t("network_gate.update_title"),
            _t("network_gate.update_body"),
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            parent,
        )
        if msg.exec() != QMessageBox.StandardButton.Ok:
            return False

        # Authenticate Admin PIN
        pin_dialog = AdminPinDialog(parent=parent)
        pin_dialog.setWindowTitle(_t("network_gate.update_title"))
        if not pin_dialog.exec():
            return False

        entered_pin = pin_dialog.pin()
        user, role = AuthService.authenticate_pin(entered_pin)
        if not user or not role or (role.access_level < 9 and role.name != "Admin"):
            QMessageBox.warning(
                parent,
                _t("common.error"),
                _t("permission.admin_override_failed"),
            )
            return False

        # Show progress dialog with indeterminate bar
        progress = QDialog(parent)
        progress.setWindowTitle(_t("network_gate.update_title"))
        progress.setModal(True)
        progress.setFixedWidth(400)
        # Disable Esc key
        progress.reject = lambda: None

        vbox = QVBoxLayout(progress)
        lbl = QLabel(_t("network_gate.updating"))
        bar = QProgressBar()
        bar.setRange(0, 0)  # Indeterminate
        vbox.addWidget(lbl)
        vbox.addWidget(bar)

        worker = UpgradeWorker(pg_uri, user_id=user.id, parent=progress)
        upgrade_result = {"success": False, "error": ""}

        def on_success():
            upgrade_result["success"] = True
            progress.accept()

        def on_error(err_str: str):
            upgrade_result["error"] = err_str
            progress.reject()

        worker.success.connect(on_success)
        worker.error.connect(on_error)
        worker.start()

        progress.exec()
        worker.wait()

        if upgrade_result["success"]:
            # Record owner hostname in shop_meta
            import socket

            try:
                SchemaMigrationService.set_schema_owner_host(pg_uri, socket.gethostname())
            except Exception as e:
                logger.warning("Could not set schema_owner_host after upgrade: %s", e)
            return True

        QMessageBox.critical(
            parent,
            _t("common.error"),
            _t("network_gate.update_failed", error=upgrade_result["error"]),
        )
        return False
