"""Tests for first-run SetupWizard behavior (#791)."""

from unittest.mock import patch

from cbpos.ui.dialogs.setup_wizard import SetupWizard


def test_issue_791_wizard_without_pin_page_never_sets_pin(qapp):
    """SetupWizard(ask_admin_pin=False) has no security page and leaves admin_pin None."""
    with patch("cbpos.ui.dialogs.setup_wizard.QPrinterInfo.availablePrinterNames", return_value=[]):
        wizard = SetupWizard(ask_admin_pin=False)

    # Security page is not part of the wizard stack
    assert not hasattr(wizard, "page_security") or wizard.stack.indexOf(wizard.page_security) == -1

    wizard.input_shop_name.setText("Shop Without Pin Reset")
    with patch("cbpos.core.services.config_service.ConfigService.update_all"):
        wizard.finish_wizard()

    assert getattr(wizard, "admin_pin", None) is None


def test_issue_791_wizard_with_pin_page_stores_admin_pin(qapp):
    """SetupWizard(ask_admin_pin=True) validates PIN and stores it on self.admin_pin."""
    with patch("cbpos.ui.dialogs.setup_wizard.QPrinterInfo.availablePrinterNames", return_value=[]):
        wizard = SetupWizard(ask_admin_pin=True)

    assert wizard.stack.indexOf(wizard.page_security) != -1
    wizard.input_shop_name.setText("My Shop")
    wizard.go_next()  # To Step 2
    wizard.go_next()  # To Step 3

    wizard.input_pin.setText("5432")
    wizard.input_pin_confirm.setText("5432")
    with patch("cbpos.core.services.config_service.ConfigService.update_all"):
        wizard.go_next()

    assert wizard.admin_pin == "5432"


def test_issue_791_admin_pin_dialog(qapp):
    """AdminPinDialog validates 4-6 digits, confirm match, and exposes pin()."""
    from cbpos.ui.dialogs.admin_pin_dialog import AdminPinDialog

    dialog = AdminPinDialog()
    assert dialog.pin() is None

    # Mismatch warning
    dialog.input_pin.setText("1234")
    dialog.input_pin_confirm.setText("5678")
    with patch("cbpos.ui.dialogs.admin_pin_dialog.QMessageBox.warning") as mock_warn:
        dialog._on_save()
        assert mock_warn.called
        assert dialog.pin() is None

    # Matching PIN accepts
    dialog.input_pin.setText("9876")
    dialog.input_pin_confirm.setText("9876")
    dialog._on_save()
    assert dialog.pin() == "9876"
