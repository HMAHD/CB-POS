"""#620: each backup row has Restore (pre-fills the Restore tab) and
Delete (with confirmation), and a Type column telling manual, automatic
and safety-snapshot backups apart.
"""

from unittest.mock import MagicMock

import pytest
from PyQt6.QtWidgets import QMessageBox, QPushButton

from cbpos.i18n import _t
from cbpos.ui.views.data_safety_view import DataSafetyView

pytestmark = pytest.mark.usefixtures("qapp")

BACKUPS = [
    {
        "path": "/b/cbpos_auto_20260103_000000.zip",
        "filename": "cbpos_auto_20260103_000000.zip",
        "date": "2026-01-03 00:00:00",
        "size": "44 KB",
        "type": "auto",
    },
    {
        "path": "/b/cbpos_backup_20260102_000000.pre_restore.zip",
        "filename": "cbpos_backup_20260102_000000.pre_restore.zip",
        "date": "2026-01-02 00:00:00",
        "size": "44 KB",
        "type": "snapshot",
    },
    {
        "path": "/b/cbpos_backup_20260101_000000.zip",
        "filename": "cbpos_backup_20260101_000000.zip",
        "date": "2026-01-01 00:00:00",
        "size": "44 KB",
        "type": "manual",
    },
]


@pytest.fixture
def view(qapp, db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "cbpos.core.services.config_service.ConfigService.get",
        lambda key: str(tmp_path) if key == "backup_dir" else None,
    )
    v = DataSafetyView()
    v._on_backup_list_loaded(BACKUPS)
    yield v
    v.deleteLater()


def _row_button(view, row: int, name: str) -> QPushButton:
    cell = view.backup_table.cellWidget(row, view.COL_ACTIONS)
    return cell.findChild(QPushButton, name)


def test_type_column_labels_each_kind(view):
    labels = [view.backup_table.item(r, view.COL_TYPE).text() for r in range(3)]
    assert labels == [
        _t("data_safety.backup_type_auto"),
        _t("data_safety.backup_type_snapshot"),
        _t("data_safety.backup_type_manual"),
    ]
    assert len(set(labels)) == 3


def test_row_restore_prefills_the_restore_tab(view):
    view.input_restore_password.setText("left over")
    view.lbl_verify_result.setText("old result")

    _row_button(view, 1, "BackupRowRestore").click()

    assert view.tabs.currentIndex() == 1
    assert view.input_restore_path.text() == BACKUPS[1]["path"]
    assert view.input_restore_password.text() == ""
    assert view.lbl_verify_result.text() == ""


def test_row_delete_asks_first(view, monkeypatch):
    warning = MagicMock(return_value=QMessageBox.StandardButton.No)
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(warning))
    delete = MagicMock()
    monkeypatch.setattr("cbpos.ui.views.data_safety_view.BackupService.delete_backup", delete)

    _row_button(view, 2, "BackupRowDelete").click()

    warning.assert_called_once()
    delete.assert_not_called()


def test_row_delete_confirmed_deletes_that_file(view, monkeypatch):
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    delete = MagicMock(return_value=True)
    monkeypatch.setattr("cbpos.ui.views.data_safety_view.BackupService.delete_backup", delete)
    monkeypatch.setattr(view, "_refresh_backup_list", MagicMock())

    _row_button(view, 2, "BackupRowDelete").click()

    delete.assert_called_once_with(BACKUPS[2]["path"])
