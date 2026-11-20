"""UI tests for AutosaveRecoveryDialog (Phase 10B.1 / #932)."""

from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMessageBox

from cbpos.core.services.cart_autosave_service import CartAutosaveService
from cbpos.i18n import set_language
from cbpos.ui.dialogs.autosave_recovery_dialog import AutosaveAction, AutosaveRecoveryDialog


@pytest.fixture
def sample_summary():
    return {
        "id": 1,
        "terminal_id": "TERM-UI-01",
        "item_count": 3,
        "total_qty": Decimal("5.000"),
        "total": Decimal("1250.00"),
        "timestamp": datetime(2026, 11, 20, 10, 30, 0),
    }


@pytest.mark.ui
def test_issue_932_recovery_dialog_ui_elements(qtbot, sample_summary):
    """AutosaveRecoveryDialog initializes with proper header, body, formatted currency, and buttons."""
    set_language("en")
    dlg = AutosaveRecoveryDialog(sample_summary)
    qtbot.addWidget(dlg)

    assert "Unfinished Bill Found" in dlg.windowTitle()
    body_text = dlg.findChild(object, "AutosaveBody").text()
    assert "3 items" in body_text
    assert "1,250.00" in body_text

    time_text = dlg.findChild(object, "AutosaveTimestamp").text()
    assert "Saved at:" in time_text

    assert dlg.btn_continue is not None
    assert dlg.btn_discard is not None
    assert dlg.btn_continue.isDefault() is True


@pytest.mark.ui
def test_issue_932_recovery_dialog_continue_action(qtbot, sample_summary):
    """Clicking Continue sets action to CONTINUE and accepts dialog."""
    dlg = AutosaveRecoveryDialog(sample_summary)
    qtbot.addWidget(dlg)

    with qtbot.waitSignal(dlg.accepted):
        dlg.btn_continue.click()

    assert dlg.action == AutosaveAction.CONTINUE


@pytest.mark.ui
def test_issue_932_recovery_dialog_discard_confirmed(qtbot, sample_summary):
    """Clicking Discard shows confirmation box; confirming purges autosave."""
    terminal_id = sample_summary["terminal_id"]

    with patch.object(CartAutosaveService, "discard_autosave") as mock_discard:
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            dlg = AutosaveRecoveryDialog(sample_summary)
            qtbot.addWidget(dlg)

            with qtbot.waitSignal(dlg.accepted):
                dlg.btn_discard.click()

            assert dlg.action == AutosaveAction.DISCARD
            mock_discard.assert_called_once_with(terminal_id)


@pytest.mark.ui
def test_issue_932_recovery_dialog_discard_cancelled(qtbot, sample_summary):
    """Cancelling discard confirmation leaves dialog open and does not discard."""
    with patch.object(CartAutosaveService, "discard_autosave") as mock_discard:
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No):
            dlg = AutosaveRecoveryDialog(sample_summary)
            qtbot.addWidget(dlg)
            dlg.show()

            dlg.btn_discard.click()

            assert dlg.action == AutosaveAction.IGNORE
            mock_discard.assert_not_called()
            assert dlg.isVisible() is True


@pytest.mark.ui
def test_issue_932_recovery_dialog_escape_ignores(qtbot, sample_summary):
    """Pressing Escape rejects dialog with IGNORE action without deleting row."""
    with patch.object(CartAutosaveService, "discard_autosave") as mock_discard:
        dlg = AutosaveRecoveryDialog(sample_summary)
        qtbot.addWidget(dlg)

        with qtbot.waitSignal(dlg.rejected):
            qtbot.keyClick(dlg, Qt.Key.Key_Escape)

        assert dlg.action == AutosaveAction.IGNORE
        mock_discard.assert_not_called()


@pytest.mark.ui
def test_issue_932_recovery_dialog_trilingual(qtbot, sample_summary):
    """AutosaveRecoveryDialog renders properly in Sinhala and Tamil without placeholder issues."""
    for lang in ("si", "ta", "en"):
        set_language(lang)
        dlg = AutosaveRecoveryDialog(sample_summary)
        qtbot.addWidget(dlg)

        body = dlg.findChild(object, "AutosaveBody").text()
        assert "{count}" not in body
        assert "{total}" not in body
        assert "3" in body
        assert "1,250.00" in body
    set_language("en")


@pytest.mark.ui
def test_defect_9_discard_dialog_failure_keeps_dialog_open_and_shows_error(qtbot, sample_summary):
    """Defect 9: When discard_autosave fails (returns False), dialog must NOT accept,
    must show an error message, and action must remain IGNORE.
    """
    terminal_id = sample_summary["terminal_id"]

    with patch.object(CartAutosaveService, "discard_autosave", return_value=False) as mock_discard:
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            with patch.object(QMessageBox, "critical") as mock_critical:
                dlg = AutosaveRecoveryDialog(sample_summary)
                qtbot.addWidget(dlg)
                dlg.show()

                dlg.btn_discard.click()

                # Discard was called
                mock_discard.assert_called_once_with(terminal_id)

                # Error message was shown
                mock_critical.assert_called_once()

                # Dialog must NOT have accepted; remains open with IGNORE action
                assert dlg.action == AutosaveAction.IGNORE
                assert dlg.isVisible() is True
