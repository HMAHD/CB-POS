"""Data Safety view: backup, restore, verify, maintenance and settings behaviour.

Characterization tests, driven through the view's buttons. Workers are
never really started: each worker class's ``start`` is replaced so the
test holds the instance and plays its signals back, as the thread would.
"""

from unittest.mock import MagicMock

import pytest
from PyQt6.QtWidgets import QDialog, QFileDialog, QLineEdit, QMessageBox

from cbpos.core.services.config_service import ConfigService
from cbpos.i18n import _t, get_language, set_language
from cbpos.ui import workers
from cbpos.ui.dialogs.backup_password_dialog import BackupPasswordDialog
from cbpos.ui.views.data_safety_view import DataSafetyView
from tests.helpers.backup_helpers import isolate_config_service

pytestmark = pytest.mark.usefixtures("qapp")

WORKER_CLASSES = (
    workers.BackupWorker,
    workers.BackupListWorker,
    workers.RestoreWorker,
    workers.VerifyBackupWorker,
    workers.VacuumWorker,
    workers.IntegrityCheckWorker,
)


@pytest.fixture(autouse=True)
def restore_language():
    previous = get_language()
    yield
    set_language(previous)


@pytest.fixture
def started(monkeypatch):
    """Every data-safety worker the view starts, in order, never really run."""
    seen: list = []
    for cls in WORKER_CLASSES:
        monkeypatch.setattr(cls, "start", lambda self: seen.append(self))
    return seen


def _last(started: list, cls):
    matches = [w for w in started if isinstance(w, cls)]
    assert matches, f"no {cls.__name__} started"
    return matches[-1]


@pytest.fixture
def config(tmp_path, monkeypatch):
    isolate_config_service(monkeypatch, tmp_path)
    values = {"backup_dir": str(tmp_path / "backups"), "backup_retention_count": 3}
    monkeypatch.setattr(ConfigService, "get", staticmethod(lambda key: values.get(key)))
    monkeypatch.setattr(ConfigService, "set", staticmethod(lambda key, value: values.__setitem__(key, value)))
    return values


@pytest.fixture
def boxes(monkeypatch):
    """Record every message box; ``answer`` is what question/warning return."""
    calls: dict[str, list] = {"information": [], "critical": [], "warning": [], "question": []}
    answer = {"value": QMessageBox.StandardButton.Yes}

    def recorder(kind):
        def show(*args, **kwargs):
            calls[kind].append(args)
            return answer["value"]

        return staticmethod(show)

    for kind in calls:
        monkeypatch.setattr(QMessageBox, kind, recorder(kind))
    calls["answer"] = answer
    return calls


@pytest.fixture
def allowed(monkeypatch):
    monkeypatch.setattr("cbpos.core.utils.permission_helper.check_permission_with_override", lambda *a, **k: True)


@pytest.fixture
def view(qapp, db_session, config, started, boxes):
    v = DataSafetyView()
    yield v
    v.deleteLater()


# ── Backup tab ────────────────────────────────────────────────────────────


class TestBackupTab:
    def test_shows_the_configured_backup_folder(self, view, config):
        assert view.backup_tab.lbl_backup_dir.text() == config["backup_dir"]

    def test_change_folder_saves_it_and_rescans(self, view, config, started, monkeypatch, tmp_path):
        chosen = str(tmp_path / "elsewhere")
        monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: chosen))

        view.backup_tab.btn_change_dir.click()

        assert config["backup_dir"] == chosen
        assert view.backup_tab.lbl_backup_dir.text() == chosen
        assert _last(started, workers.BackupListWorker).backup_dir == chosen

    def test_cancelled_folder_choice_changes_nothing(self, view, config, started, monkeypatch):
        before = config["backup_dir"]
        monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: ""))

        view.backup_tab.btn_change_dir.click()

        assert config["backup_dir"] == before
        assert started == []

    def test_refresh_button_rescans_the_folder(self, view, config, started):
        view.backup_tab.btn_backup_refresh.click()

        assert _last(started, workers.BackupListWorker).backup_dir == config["backup_dir"]

    def test_create_backup_runs_and_reports_where_it_went(self, view, allowed, boxes, started, config):
        ConfigService.set_backup_password("shop-pass-1")

        view.backup_tab.btn_create_backup.click()
        worker = _last(started, workers.BackupWorker)
        assert (worker.destination_dir, worker.password) == (config["backup_dir"], "shop-pass-1")
        assert view.backup_tab.btn_create_backup.isEnabled() is False

        worker.result.emit("/b/cbpos_backup_x.zip")

        assert view.backup_tab.btn_create_backup.isEnabled() is True
        assert "/b/cbpos_backup_x.zip" in boxes["information"][-1][2]

    def test_create_backup_failure_says_so(self, view, allowed, boxes, started):
        ConfigService.set_backup_password("shop-pass-1")
        view.backup_tab.btn_create_backup.click()

        _last(started, workers.BackupWorker).error.emit("disk full")

        assert view.backup_tab.btn_create_backup.isEnabled() is True
        assert "disk full" in boxes["critical"][-1][2]

    def test_create_backup_without_permission_does_nothing(self, view, started, monkeypatch):
        monkeypatch.setattr("cbpos.core.utils.permission_helper.check_permission_with_override", lambda *a, **k: False)

        view.backup_tab.btn_create_backup.click()

        assert started == []

    def test_clean_old_keeps_the_retention_count(self, view, boxes, monkeypatch, config):
        cleanup = MagicMock(return_value=2)
        monkeypatch.setattr("cbpos.core.services.backup_service.BackupService.cleanup_old_backups", cleanup)

        view.backup_tab.btn_clean_old.click()

        cleanup.assert_called_once_with(config["backup_dir"], 3)
        assert len(boxes["information"]) == 1

    def test_clean_old_declined_deletes_nothing(self, view, boxes, monkeypatch):
        boxes["answer"]["value"] = QMessageBox.StandardButton.No
        cleanup = MagicMock(return_value=0)
        monkeypatch.setattr("cbpos.core.services.backup_service.BackupService.cleanup_old_backups", cleanup)

        view.backup_tab.btn_clean_old.click()

        cleanup.assert_not_called()

    def test_setting_the_password_shows_on_both_tabs(self, view, allowed, monkeypatch):
        assert view.backup_tab.btn_backup_password.text() == _t("data_safety.btn_set_password")
        monkeypatch.setattr(BackupPasswordDialog, "exec", _accept_setting("shop-pass-1"))

        view.backup_tab.btn_backup_password.click()

        assert view.backup_tab.btn_backup_password.text() == _t("data_safety.btn_change_password")
        assert view.restore_tab.input_restore_password.placeholderText() == _t(
            "data_safety.restore_pwd_placeholder_shop"
        )


def _accept_setting(password: str):
    """A BackupPasswordDialog.exec that stores *password* and accepts."""

    def exec_(dialog) -> QDialog.DialogCode:
        ConfigService.set_backup_password(password)
        return QDialog.DialogCode.Accepted

    return exec_


# ── Restore tab ───────────────────────────────────────────────────────────


class TestRestoreTab:
    def test_browse_fills_the_path_and_clears_the_old_result(self, view, monkeypatch):
        view.restore_tab.lbl_verify_result.setText("old")
        monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: ("/b/cbpos_backup_x.zip", "")))

        view.restore_tab.btn_browse.click()

        assert view.restore_tab.input_restore_path.text() == "/b/cbpos_backup_x.zip"
        assert view.restore_tab.lbl_verify_result.text() == ""

    def test_verify_without_a_file_warns(self, view, boxes, started):
        view.restore_tab.btn_verify.click()

        assert len(boxes["warning"]) == 1
        assert started == []

    def test_verify_falls_back_to_the_shop_password(self, view, started):
        ConfigService.set_backup_password("shop-pass-1")
        view.restore_tab.input_restore_path.setText("/b/x.zip")

        view.restore_tab.btn_verify.click()

        worker = _last(started, workers.VerifyBackupWorker)
        assert (worker.backup_path, worker.password) == ("/b/x.zip", "shop-pass-1")

    def test_verify_valid_result_is_green(self, view, started):
        view.restore_tab.input_restore_path.setText("/b/x.zip")
        view.restore_tab.input_restore_password.setText("typed")
        view.restore_tab.btn_verify.click()

        _last(started, workers.VerifyBackupWorker).result.emit({"valid": True, "files": ["a", "b"], "size": "1 MB"})

        assert view.restore_tab.lbl_verify_result.property("class") == "credit"
        assert "1 MB" in view.restore_tab.lbl_verify_result.text()
        assert view.restore_tab.btn_restore.isEnabled() and view.restore_tab.btn_verify.isEnabled()

    def test_restore_runs_after_confirmation(self, view, allowed, boxes, started, monkeypatch):
        restarted = []
        monkeypatch.setattr("cbpos.ui.app_restart.restart_application", lambda win: restarted.append(win) or True)

        ConfigService.set_backup_password("shop-pass-1")
        view.restore_tab.input_restore_path.setText("/b/x.zip")
        view.restore_tab.input_restore_password.setText("typed")

        view.restore_tab.btn_restore.click()
        worker = _last(started, workers.RestoreWorker)
        assert (worker.backup_path, worker.password) == ("/b/x.zip", "typed")

        worker.result.emit(True)

        assert view.restore_tab.btn_restore.isEnabled() is True
        assert len(boxes["information"]) == 1
        assert len(restarted) == 1

    def test_password_set_while_restoring_shows_on_the_backup_tab(self, view, allowed, boxes, monkeypatch):
        boxes["answer"]["value"] = QMessageBox.StandardButton.No
        monkeypatch.setattr(BackupPasswordDialog, "exec", _accept_setting("shop-pass-1"))
        view.restore_tab.input_restore_path.setText("/b/x.zip")
        view.restore_tab.input_restore_password.setText("typed")

        view.restore_tab.btn_restore.click()

        assert view.backup_tab.btn_backup_password.text() == _t("data_safety.btn_change_password")

    def test_restore_declined_does_nothing(self, view, allowed, boxes, started):
        ConfigService.set_backup_password("shop-pass-1")
        boxes["answer"]["value"] = QMessageBox.StandardButton.No
        view.restore_tab.input_restore_path.setText("/b/x.zip")

        view.restore_tab.btn_restore.click()

        assert started == []

    def test_restore_refused_explains_why(self, view, allowed, boxes, started):
        ConfigService.set_backup_password("shop-pass-1")
        view.restore_tab.input_restore_path.setText("/b/x.zip")
        view.restore_tab.btn_restore.click()

        _last(started, workers.RestoreWorker).refused.emit("corrupt")

        assert _t("data_safety.error_corrupt") in boxes["critical"][-1][2]
        assert view.restore_tab.btn_restore.isEnabled() is True

    def test_restore_without_a_file_warns(self, view, allowed, boxes, started):
        view.restore_tab.btn_restore.click()

        assert len(boxes["warning"]) == 1
        assert started == []

    def test_show_hide_password(self, view):
        view.restore_tab.btn_toggle_restore_pwd.click()
        assert view.restore_tab.input_restore_password.echoMode() == QLineEdit.EchoMode.Normal
        assert view.restore_tab.btn_toggle_restore_pwd.text() == _t("data_safety.btn_hide")

        view.restore_tab.btn_toggle_restore_pwd.click()
        assert view.restore_tab.input_restore_password.echoMode() == QLineEdit.EchoMode.Password


# ── Maintenance tab ───────────────────────────────────────────────────────


class TestMaintenanceTab:
    def test_optimize_reports_space_saved(self, view, started):
        view.maintenance_tab.btn_vacuum.click()
        assert view.maintenance_tab.btn_vacuum.isEnabled() is False

        _last(started, workers.VacuumWorker).result.emit({"saved": "12 KB"})

        assert view.maintenance_tab.btn_vacuum.isEnabled() is True
        assert view.maintenance_tab.lbl_maintenance_status.property("class") == "credit"
        assert "12 KB" in view.maintenance_tab.lbl_maintenance_status.text()

    def test_optimize_failure(self, view, started):
        view.maintenance_tab.btn_vacuum.click()

        _last(started, workers.VacuumWorker).error.emit("locked")

        assert view.maintenance_tab.lbl_maintenance_status.property("class") == "debit"
        assert "locked" in view.maintenance_tab.lbl_maintenance_status.text()

    @pytest.mark.parametrize("ok, css", [(True, "credit"), (False, "debit")])
    def test_integrity_check(self, view, started, ok, css):
        view.maintenance_tab.btn_integrity.click()

        _last(started, workers.IntegrityCheckWorker).result.emit(ok, "page 3 broken")

        assert view.maintenance_tab.btn_integrity.isEnabled() is True
        assert view.maintenance_tab.lbl_maintenance_status.property("class") == css

    def test_database_info_is_shown(self, view, monkeypatch):
        info = {"size": "8 KB", "products": 5, "customers": 2, "sales": 9}
        monkeypatch.setattr(
            "cbpos.core.services.maintenance_service.MaintenanceService.get_database_info", lambda: info
        )

        view.maintenance_tab.refresh()

        assert [view.maintenance_tab.lbl_db_size.text(), view.maintenance_tab.lbl_products_count.text()] == [
            "8 KB",
            "5",
        ]
        assert [view.maintenance_tab.lbl_customers_count.text(), view.maintenance_tab.lbl_sales_count.text()] == [
            "2",
            "9",
        ]


# ── The page as a whole ───────────────────────────────────────────────────


def test_showing_the_page_loads_the_backup_list(view, started, config):
    view.show()
    try:
        assert _last(started, workers.BackupListWorker).backup_dir == config["backup_dir"]
    finally:
        view.hide()


@pytest.mark.parametrize("lang", ["si", "ta"])
def test_switching_language_retranslates_every_tab(view, lang):
    set_language(lang)

    assert view.lbl_title.text() == _t("data_safety.title")
    titles = [view.tabs.tabText(i) for i in range(view.tabs.count())]
    assert titles == [
        _t("data_safety.tab_backup"),
        _t("data_safety.tab_restore"),
        _t("data_safety.tab_maintenance"),
        _t("data_safety.tab_export"),
    ]
    assert view.backup_tab.btn_create_backup.text() == _t("data_safety.btn_create_backup")
    assert view.restore_tab.btn_verify.text() == _t("data_safety.btn_verify")
    assert view.maintenance_tab.btn_vacuum.text() == _t("data_safety.maintenance_btn_optimize")
    assert view.export_tab.btn_do_export.text() == _t("data_safety.export_btn")
