from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import QDateTime
from PyQt6.QtWidgets import QApplication, QFrame, QLabel, QToolButton

from cbpos.ui.views.settings_view import SettingsView

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture
def settings_view(db_session, monkeypatch):
    view = SettingsView()
    yield view
    view.close()
    view.deleteLater()
    QApplication.processEvents()


class TestSettingsHeader:
    def test_settings_header_structure(self, settings_view):
        assert hasattr(settings_view, "settings_header")
        assert isinstance(settings_view.settings_header, QFrame)
        assert settings_view.settings_header.objectName() == "SettingsHeader"

        assert hasattr(settings_view, "lbl_header_title")
        assert isinstance(settings_view.lbl_header_title, QLabel)
        assert settings_view.lbl_header_title.objectName() == "SettingsHeaderTitle"

        assert hasattr(settings_view, "lbl_header_clock")
        assert isinstance(settings_view.lbl_header_clock, QLabel)
        assert settings_view.lbl_header_clock.objectName() == "SettingsHeaderClock"

        assert hasattr(settings_view, "btn_header_pos")
        assert isinstance(settings_view.btn_header_pos, QToolButton)
        assert settings_view.btn_header_pos.objectName() == "SettingsHeaderPosBtn"

        assert hasattr(settings_view, "btn_header_logout")
        assert isinstance(settings_view.btn_header_logout, QToolButton)
        assert settings_view.btn_header_logout.objectName() == "SettingsHeaderLogoutBtn"

    def test_switch_page_updates_header_title(self, settings_view):
        settings_view.switch_page(0)
        assert (
            "Shop Info" in settings_view.lbl_header_title.text() or "Settings" in settings_view.lbl_header_title.text()
        )

        settings_view.switch_page(1)
        assert "Sales" in settings_view.lbl_header_title.text() and "Tax" in settings_view.lbl_header_title.text()

    def test_pos_and_logout_button_clicks(self, settings_view):
        pos_mock = MagicMock()
        logout_mock = MagicMock()

        settings_view.request_pos_view.connect(pos_mock)
        settings_view.logout_requested.connect(logout_mock)

        settings_view.btn_header_pos.click()
        pos_mock.assert_called_once()

        settings_view.btn_header_logout.click()
        logout_mock.assert_called_once()

    def test_clock_updates_on_settings_header(self, settings_view):
        fixed_dt = QDateTime.fromString("2026-10-18 10:15:30", "yyyy-MM-dd hh:mm:ss")
        with patch("cbpos.ui.views.settings_view.QDateTime") as mock_dt:
            mock_dt.currentDateTime.return_value = fixed_dt
            settings_view._update_clock()
            assert settings_view.lbl_header_clock.text() == fixed_dt.toString("ddd, d MMM yyyy  hh:mm:ss")
