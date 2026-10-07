"""#619: the shop backup password is set once (Data Safety, or on the first
manual backup) and then used for every backup -- the per-backup random
password reveal is gone.
"""

from unittest.mock import MagicMock

import pytest
from PyQt6.QtWidgets import QDialog, QMessageBox

from cbpos.core.services.config_service import ConfigService
from cbpos.ui.dialogs.backup_password_dialog import BackupPasswordDialog
from cbpos.ui.views.data_safety_view import DataSafetyView
from tests.unit.backup_helpers import isolate_config_service

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    isolate_config_service(monkeypatch, tmp_path)


@pytest.fixture
def dialog(qapp):
    d = BackupPasswordDialog()
    yield d
    d.deleteLater()


class TestBackupPasswordDialog:
    def test_mismatch_is_rejected_and_nothing_saved(self, dialog):
        dialog.input_password.setText("secret-one")
        dialog.input_confirm.setText("secret-two")

        dialog._save()

        assert dialog.result() != QDialog.DialogCode.Accepted
        assert dialog.lbl_error.text()
        assert ConfigService.get_backup_password() is None

    def test_too_short_is_rejected(self, dialog):
        dialog.input_password.setText("abc")
        dialog.input_confirm.setText("abc")

        dialog._save()

        assert ConfigService.get_backup_password() is None

    def test_valid_password_is_saved_and_accepted(self, dialog):
        dialog.input_password.setText("secret-one")
        dialog.input_confirm.setText("secret-one")

        dialog._save()

        assert dialog.result() == QDialog.DialogCode.Accepted
        assert ConfigService.get_backup_password() == "secret-one"


@pytest.fixture
def view(qapp, db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "cbpos.core.services.config_service.ConfigService.get",
        lambda key: str(tmp_path / "backups") if key == "backup_dir" else None,
    )
    monkeypatch.setattr("cbpos.core.utils.permission_helper.check_permission_with_override", lambda *a, **k: True)
    v = DataSafetyView()
    yield v
    v.deleteLater()


class TestManualBackupUsesShopPassword:
    def test_no_password_and_user_cancels_means_no_backup(self, view, monkeypatch):
        monkeypatch.setattr(BackupPasswordDialog, "exec", lambda self: QDialog.DialogCode.Rejected)
        worker_cls = MagicMock()
        monkeypatch.setattr("cbpos.ui.views.data_safety_view.BackupWorker", worker_cls)

        view._create_backup()

        worker_cls.assert_not_called()

    def test_backup_runs_with_the_shop_password(self, view, tmp_path, monkeypatch):
        ConfigService.set_backup_password("shop-pass-1")
        worker_cls = MagicMock()
        monkeypatch.setattr("cbpos.ui.views.data_safety_view.BackupWorker", worker_cls)

        view._create_backup()

        worker_cls.assert_called_once_with(str(tmp_path / "backups"), "shop-pass-1")
        worker_cls.return_value.start.assert_called_once()

    def test_finished_message_never_shows_the_password(self, view, monkeypatch):
        ConfigService.set_backup_password("shop-pass-1")
        info = MagicMock()
        monkeypatch.setattr(QMessageBox, "information", staticmethod(info))
        monkeypatch.setattr(view, "_refresh_backup_list", MagicMock())

        view._on_backup_finished("/some/cbpos_backup_20260101_000000.zip")

        text = info.call_args.args[2]
        assert "shop-pass-1" not in text
        assert "/some/cbpos_backup_20260101_000000.zip" in text

    def test_password_status_reflects_whether_one_is_set(self, view):
        view._update_password_status()
        not_set_text = view.lbl_pwd_status.text()
        ConfigService.set_backup_password("shop-pass-1")
        view._update_password_status()

        assert view.lbl_pwd_status.text() != not_set_text
        assert "shop-pass-1" not in view.lbl_pwd_status.text()
