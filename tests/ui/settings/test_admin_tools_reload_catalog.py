"""Tests for the reload catalog button on AdminToolsView (#871)."""

from unittest.mock import patch

from PyQt6.QtWidgets import QMessageBox

from cbpos.ui.views.admin_tools_view import AdminToolsView
from tests.helpers.sync_two_machines import isolated_settings


def test_reload_catalog_button_visibility(qtbot, tmp_path):
    """The reload catalog button is visible on a terminal and hidden on main/standalone."""
    with isolated_settings(str(tmp_path), terminal_mode="main"):
        view = AdminToolsView()
        qtbot.addWidget(view)
        assert view.btn_reload_catalog.isHidden()

    with isolated_settings(str(tmp_path), terminal_mode="terminal"):
        view2 = AdminToolsView()
        qtbot.addWidget(view2)
        assert not view2.btn_reload_catalog.isHidden()


def test_reload_catalog_button_prompts_confirmation(qtbot, tmp_path):
    """Clicking reload catalog asks for confirmation and aborts if No."""
    with isolated_settings(str(tmp_path), terminal_mode="terminal"):
        view = AdminToolsView()
        qtbot.addWidget(view)

        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No) as mock_q:
            view.btn_reload_catalog.click()
            mock_q.assert_called_once()
            assert view.btn_reload_catalog.isEnabled()
