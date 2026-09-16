"""
#388: LAN Sync's *static* widgets (labels, combo items, tooltips) were
fixed for i18n in #334/#335, but its *runtime* strings -- the server
address display, sync-test status text, and every QMessageBox title/body
in _test_sync_connection()/_forget_trusted_main_pc() -- were still plain
Python string literals, so a shop running in Sinhala or Tamil still saw
these specific messages in English no matter what.

Patching _t to a distinguishable fake and asserting the *rendered* text
matches that fake (rather than just checking it equals the English
string, which would trivially pass even with a hardcoded literal) is
the same technique already proven in test_network_page_lan_sync_i18n.py
for this page's static widgets.
"""

from unittest.mock import patch

import pytest
from PyQt6.QtWidgets import QMessageBox

from cbpos.ui.views import settings_pages
from cbpos.ui.views.settings_pages import NetworkPage

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture
def page(qapp):
    p = NetworkPage()
    yield p
    p.deleteLater()


@pytest.fixture
def fake_translate(monkeypatch):
    def _t(key, **kwargs):
        rendered = f"[[{key}]]"
        if kwargs:
            rendered += f"|{kwargs}"
        return rendered

    monkeypatch.setattr(settings_pages, "_t", _t)
    return _t


class TestServerAddressDisplayIsTranslated:
    def test_main_pc_mode_renders_through_translation(self, page, fake_translate):
        index = page.cmb_terminal_mode.findData("main")
        page.cmb_terminal_mode.setCurrentIndex(index)

        assert page.lbl_server_address.text().startswith("[[settings.network.sync_server_address_display]]")


class TestTestSyncConnectionIsTranslated:
    def test_empty_address_shows_translated_validation_warning(self, page, fake_translate):
        page.input_main_pc_addr.setText("")

        with patch("cbpos.ui.views.settings_pages.QMessageBox.warning") as mock_warning:
            page._test_sync_connection()

        mock_warning.assert_called_once()
        args, _ = mock_warning.call_args
        assert args[1] == "[[settings.network.sync_validation_title]]"
        assert args[2] == "[[settings.network.sync_validation_message]]"

    def test_unreachable_host_shows_translated_failed_status_and_dialog(self, page, fake_translate):
        import urllib.error

        page.input_main_pc_addr.setText("192.168.1.50:5555")

        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("unreachable")):
            with patch("cbpos.ui.views.settings_pages.QMessageBox.critical") as mock_critical:
                page._test_sync_connection()

        assert page.lbl_sync_test_status.text() == "[[settings.network.sync_test_failed]]"
        mock_critical.assert_called_once()
        args, _ = mock_critical.call_args
        assert args[1] == "[[settings.network.sync_failed_title]]"

    def test_generic_exception_shows_translated_status_and_error_dialog(self, page, fake_translate):
        page.input_main_pc_addr.setText("192.168.1.50:5555")

        with patch("urllib.request.urlopen", side_effect=RuntimeError("boom")):
            with patch("cbpos.ui.views.settings_pages.QMessageBox.critical") as mock_critical:
                page._test_sync_connection()

        assert page.lbl_sync_test_status.text() == "[[settings.network.sync_test_error]]"
        mock_critical.assert_called_once()
        args, _ = mock_critical.call_args
        assert args[1] == "[[settings.network.sync_error_title]]"


class TestForgetTrustedMainPcIsTranslated:
    def test_confirmation_and_done_dialogs_render_through_translation(self, page, fake_translate):
        with (
            patch(
                "cbpos.ui.views.settings_pages.QMessageBox.question",
                return_value=QMessageBox.StandardButton.Yes,
            ) as mock_question,
            patch("cbpos.ui.views.settings_pages.QMessageBox.information") as mock_info,
        ):
            page._forget_trusted_main_pc()

        args, _ = mock_question.call_args
        assert args[1] == "[[settings.network.btn_forget_main]]"
        assert args[2] == "[[settings.network.sync_forget_main_confirm_message]]"

        mock_info.assert_called_once()
        info_args, _ = mock_info.call_args
        assert info_args[1] == "[[settings.network.btn_forget_main]]"
        assert info_args[2] == "[[settings.network.sync_forget_main_done_message]]"
