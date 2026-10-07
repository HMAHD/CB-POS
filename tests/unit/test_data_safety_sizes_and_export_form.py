"""#618: Data Safety shows real sizes ("44 KB (compressed from 540 KB)"),
the database size label uses the same formatter, and Export is one
compact form whose date rows only show for Sales.
"""

from unittest.mock import patch

import pytest

from cbpos.core.services.maintenance_service import MaintenanceService
from cbpos.i18n import _t
from cbpos.ui.views.data_safety_view import DataSafetyView
from tests.unit.backup_helpers import make_pos_db

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture
def view(qapp, db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "cbpos.core.services.config_service.ConfigService.get",
        lambda key: str(tmp_path) if key == "backup_dir" else None,
    )
    v = DataSafetyView()
    yield v
    v.deleteLater()


def test_backup_row_shows_size_and_original_size(view):
    view._on_backup_list_loaded(
        [
            {
                "path": "/b/cbpos_backup_20260101_000000.zip",
                "filename": "cbpos_backup_20260101_000000.zip",
                "date": "2026-01-01 00:00:00",
                "size": "44 KB",
                "original_size": "540 KB",
                "type": "manual",
            }
        ]
    )

    text = view.backup_table.item(0, 2).text()
    assert "44 KB" in text
    assert "540 KB" in text


def test_database_size_label_uses_format_bytes(tmp_path):
    make_pos_db(tmp_path / "cbpos.db")
    with patch("cbpos.core.services.maintenance_service.Config") as mock_config:
        mock_config.DATA_DIR = tmp_path
        info = MaintenanceService.get_database_info()

    assert info["size"].endswith(" KB")
    assert "." not in info["size"]  # "8 KB", never "8.0 KB" or "0.0 MB"


def test_export_date_rows_only_for_sales(view):
    view.cmb_export_data.setCurrentText(_t("data_safety.export_type_products"))
    assert view.export_form.isRowVisible(view.date_export_from) is False

    view.cmb_export_data.setCurrentText(_t("data_safety.export_type_sales"))
    assert view.export_form.isRowVisible(view.date_export_from) is True
    assert view.export_form.isRowVisible(view.date_export_to) is True


def test_restore_warning_wraps(view):
    assert view.lbl_restore_warning.wordWrap() is True
