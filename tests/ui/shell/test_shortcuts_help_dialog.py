"""Tests for ShortcutsHelpDialog (#818)."""

from cbpos.i18n import _t
from cbpos.ui.dialogs.shortcuts_help_dialog import ShortcutsHelpDialog


def test_shortcuts_dialog_includes_ctrl_z_and_ctrl_alt_c(qapp):
    """Shortcuts dialog lists Ctrl+Z and Ctrl+Alt+C."""
    dialog = ShortcutsHelpDialog()
    shortcuts = dialog._get_shortcuts()
    keys = [k for k, _ in shortcuts]

    assert "Ctrl+Z" in keys
    assert "Ctrl+Alt+C" in keys
    assert "Ctrl+B" in keys

    # Verify descriptions are localized
    ctrl_z_desc = next(desc for k, desc in shortcuts if k == "Ctrl+Z")
    assert ctrl_z_desc == _t("shortcuts.undo_remove")

    ctrl_alt_c_desc = next(desc for k, desc in shortcuts if k == "Ctrl+Alt+C")
    assert ctrl_alt_c_desc == _t("shortcuts.calculator")

    dialog.deleteLater()
