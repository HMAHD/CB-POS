"""UI tests for AdminPinDialog (#791)."""

import pytest

from cbpos.i18n import set_language
from cbpos.ui.dialogs.admin_pin_dialog import AdminPinDialog


@pytest.fixture
def pin_dialog(app_fixture):
    """Instantiate an AdminPinDialog under the shared QApplication."""
    dialog = AdminPinDialog()
    return dialog


def test_admin_pin_dialog_initial_focus(pin_dialog):
    """Initial focus starts in the first password field."""
    assert pin_dialog.input_pin.hasFocus() or pin_dialog.focusWidget() == pin_dialog.input_pin


def test_admin_pin_dialog_cancel_rejects(pin_dialog):
    """Clicking cancel or reject leaves pin None."""
    pin_dialog.btn_cancel.click()
    assert pin_dialog.pin() is None


def test_admin_pin_dialog_keyboard_enter_saves_valid_pin(pin_dialog):
    """Pressing default save button validates and stores pin."""
    pin_dialog.input_pin.setText("654321")
    pin_dialog.input_pin_confirm.setText("654321")
    assert pin_dialog.btn_save.isDefault()
    pin_dialog.btn_save.click()
    assert pin_dialog.pin() == "654321"


@pytest.mark.parametrize("lang", ["en", "si", "ta"])
def test_admin_pin_dialog_trilingual(pin_dialog, lang):
    """All labels and titles update cleanly in all three languages."""
    set_language(lang)
    pin_dialog.retranslate_ui()
    assert pin_dialog.windowTitle() != ""
    assert pin_dialog.lbl_body.text() != ""
    assert pin_dialog.btn_save.text() != ""
    assert pin_dialog.btn_cancel.text() != ""
    # Reset language
    set_language("en")
