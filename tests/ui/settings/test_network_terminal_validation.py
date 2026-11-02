"""Tests for terminal ID validation and registered terminals UI (#867, #866)."""

from datetime import datetime

import pytest

from cbpos.core.services.sync_terminal_service import SyncTerminalService
from cbpos.i18n import _t
from cbpos.ui.views.settings_pages.network import NetworkPage


@pytest.fixture
def network_page(qapp, tmp_path, monkeypatch):
    from cbpos.infrastructure import sync_tls

    monkeypatch.setattr(sync_tls, "CERT_FILE", str(tmp_path / "sync_tls_cert.pem"))
    monkeypatch.setattr(sync_tls, "KEY_FILE", str(tmp_path / "sync_tls_key.pem"))
    page = NetworkPage()
    return page


def test_issue_867_network_page_refuses_blank_terminal_id(network_page):
    """NetworkPage.validate() rejects blank terminal ID in main and terminal modes."""
    # Terminal mode
    idx = network_page.cmb_terminal_mode.findData("terminal")
    network_page.cmb_terminal_mode.setCurrentIndex(idx)
    network_page.input_terminal_id.setText("   ")

    with pytest.raises(ValueError) as excinfo:
        network_page.validate()
    assert _t("settings.network.terminal_id_required") in str(excinfo.value)

    # Main mode
    idx = network_page.cmb_terminal_mode.findData("main")
    network_page.cmb_terminal_mode.setCurrentIndex(idx)
    network_page.input_terminal_id.setText("")

    with pytest.raises(ValueError) as excinfo:
        network_page.validate()
    assert _t("settings.network.terminal_id_required") in str(excinfo.value)

    # Standalone mode ignores blank terminal ID
    idx = network_page.cmb_terminal_mode.findData("standalone")
    network_page.cmb_terminal_mode.setCurrentIndex(idx)
    network_page.input_terminal_id.setText("")
    # Should not raise
    network_page.validate()


def test_issue_867_network_page_refuses_invalid_terminal_id(network_page):
    """NetworkPage.validate() rejects invalid characters and lengths in terminal ID."""
    idx = network_page.cmb_terminal_mode.findData("terminal")
    network_page.cmb_terminal_mode.setCurrentIndex(idx)

    invalid_ids = ["-TILL1", "TILL#1", "A" * 17, "T", "TILL 1"]
    for bad_id in invalid_ids:
        network_page.input_terminal_id.setText(bad_id)
        with pytest.raises(ValueError) as excinfo:
            network_page.validate()
        assert _t("settings.network.terminal_id_invalid") in str(excinfo.value)


def test_issue_867_network_page_accepts_valid_terminal_id(network_page):
    """NetworkPage.validate() accepts valid terminal IDs (2-16 alphanumeric + hyphen)."""
    idx = network_page.cmb_terminal_mode.findData("terminal")
    network_page.cmb_terminal_mode.setCurrentIndex(idx)

    valid_ids = ["TILL-01", "TERM-1", "POS1", "MAIN-COUNTER-1", "01-A"]
    for good_id in valid_ids:
        network_page.input_terminal_id.setText(good_id)
        network_page.validate()


def test_issue_867_network_page_normalizes_to_uppercase(network_page):
    """NetworkPage.save() converts terminal_id to uppercase."""
    network_page.input_terminal_id.setText("till-counter-01")
    settings = network_page.save()
    assert settings["terminal_id"] == "TILL-COUNTER-01"


def test_issue_866_registered_terminals_card_visibility(network_page):
    """Registered terminals card is visible only in Main PC mode."""
    # Main mode -> visible
    idx = network_page.cmb_terminal_mode.findData("main")
    network_page.cmb_terminal_mode.setCurrentIndex(idx)
    assert not network_page.registered_terminals_card.isHidden()

    # Terminal mode -> hidden
    idx = network_page.cmb_terminal_mode.findData("terminal")
    network_page.cmb_terminal_mode.setCurrentIndex(idx)
    assert network_page.registered_terminals_card.isHidden()

    # Standalone mode -> hidden
    idx = network_page.cmb_terminal_mode.findData("standalone")
    network_page.cmb_terminal_mode.setCurrentIndex(idx)
    assert network_page.registered_terminals_card.isHidden()


def test_issue_866_registered_terminals_table_displays_info(network_page, monkeypatch):
    """Registered terminals table populates all columns correctly."""
    mock_terminals = [
        {
            "terminal_id": "TILL-01",
            "db_instance_id": "12345678-1234-5678-1234-567812345678",
            "first_seen": datetime(2026, 11, 1, 10, 0, 0),
            "last_seen": datetime(2026, 11, 2, 12, 30, 0),
            "last_ip": "192.168.1.101",
            "released": False,
        },
        {
            "terminal_id": "TILL-02",
            "db_instance_id": "87654321-4321-8765-4321-876543210987",
            "first_seen": datetime(2026, 11, 1, 11, 0, 0),
            "last_seen": datetime(2026, 11, 2, 11, 15, 0),
            "last_ip": "192.168.1.102",
            "released": True,
        },
    ]
    monkeypatch.setattr(SyncTerminalService, "list_terminals", staticmethod(lambda: mock_terminals))

    network_page._refresh_registered_terminals()

    table = network_page.tbl_registered_terminals
    assert table.rowCount() == 2

    # Row 0: TILL-01
    assert table.item(0, 0).text() == "TILL-01"
    assert table.item(0, 1).text() == "12345678…"
    assert table.item(0, 1).toolTip() == "12345678-1234-5678-1234-567812345678"
    assert table.item(0, 2).text() == "2026-11-02 12:30:00"
    assert table.item(0, 3).text() == "192.168.1.101"
    assert table.item(0, 4).text() == _t("settings.network.status_active")
    assert table.cellWidget(0, 5) is not None  # Release button present

    # Row 1: TILL-02 (released)
    assert table.item(1, 0).text() == "TILL-02"
    assert table.item(1, 4).text() == _t("settings.network.status_released")
    assert table.cellWidget(1, 5) is None  # No release button for already released
