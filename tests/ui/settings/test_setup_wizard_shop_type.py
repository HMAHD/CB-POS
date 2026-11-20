"""UI tests for Setup Wizard shop type preset selection step (#942)."""

from unittest.mock import patch

import pytest

from cbpos.core.constants.features import ShopTypes
from cbpos.ui.dialogs.setup_wizard import SetupWizard

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture
def wizard():
    with patch("cbpos.ui.dialogs.setup_wizard.QPrinterInfo.availablePrinterNames", return_value=["XP-80C"]):
        w = SetupWizard(ask_admin_pin=True)
    w.input_shop_name.setText("Test Shop")
    w.input_pin.setText("1234")
    w.input_pin_confirm.setText("1234")
    yield w


def test_wizard_defaults_to_grocery(wizard):
    """SetupWizard defaults to ShopTypes.GROCERY selected."""
    assert wizard.shop_type == ShopTypes.GROCERY
    assert wizard.shop_type_buttons[ShopTypes.GROCERY].isChecked()


def test_wizard_has_all_eight_shop_types(wizard):
    """The wizard contains tiles for all 8 defined shop types."""
    assert set(wizard.shop_type_buttons.keys()) == set(ShopTypes.ALL)
    for st in ShopTypes.ALL:
        btn = wizard.shop_type_buttons[st]
        assert btn.objectName() == "ShopTypeTile"
        assert btn.text() != ""


def test_wizard_select_shop_type_updates_state(wizard):
    """Selecting a different shop type tile updates self.shop_type and check state."""
    wizard.select_shop_type(ShopTypes.PHARMACY)
    assert wizard.shop_type == ShopTypes.PHARMACY
    assert wizard.shop_type_buttons[ShopTypes.PHARMACY].isChecked()
    assert not wizard.shop_type_buttons[ShopTypes.GROCERY].isChecked()

    wizard.select_shop_type(ShopTypes.OTHER)
    assert wizard.shop_type == ShopTypes.OTHER
    assert wizard.shop_type_buttons[ShopTypes.OTHER].isChecked()


def test_wizard_step_flow_with_pin(wizard):
    """Step flow with ask_admin_pin=True progresses through 4 steps."""
    assert wizard.stack.currentIndex() == 0

    # Step 0 -> Step 1 (Shop Type)
    wizard.go_next()
    assert wizard.stack.currentIndex() == 1
    assert wizard.lbl_step.text() != ""

    # Step 1 -> Step 2 (Hardware)
    wizard.go_next()
    assert wizard.stack.currentIndex() == 2

    # Step 2 -> Step 3 (Security/PIN)
    wizard.go_next()
    assert wizard.stack.currentIndex() == 3

    # Back navigation
    wizard.go_back()
    assert wizard.stack.currentIndex() == 2
    wizard.go_back()
    assert wizard.stack.currentIndex() == 1
    wizard.go_back()
    assert wizard.stack.currentIndex() == 0


def test_wizard_shop_type_required_validation(wizard):
    """If no shop type is selected, advancing from Step 1 shows a warning and stays on Step 1."""
    wizard.go_next()  # to Step 1
    assert wizard.stack.currentIndex() == 1

    wizard.selected_shop_type = ""
    with patch("cbpos.ui.dialogs.setup_wizard.QMessageBox.warning") as mock_warn:
        wizard.go_next()
        mock_warn.assert_called_once()
    assert wizard.stack.currentIndex() == 1


def test_wizard_saves_selected_shop_type(wizard):
    """finish_wizard() saves shop_type into ConfigService."""
    wizard.select_shop_type(ShopTypes.HARDWARE)
    with (
        patch("cbpos.core.services.config_service.ConfigService.update_all") as mock_update,
        patch("cbpos.ui.dialogs.setup_wizard.SetupWizard.accept"),
    ):
        wizard.finish_wizard()
        mock_update.assert_called_once()
        saved = mock_update.call_args[0][0]
        assert saved["shop_type"] == ShopTypes.HARDWARE
