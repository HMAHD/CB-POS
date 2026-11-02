"""UI tests for LAN Sync TLS certificate pairing and status display (#800)."""

import os
from unittest.mock import MagicMock

from PyQt6.QtWidgets import QApplication

from cbpos.core.models import AuditLog
from cbpos.core.services.config_service import ConfigService
from cbpos.i18n import _t
from cbpos.infrastructure import sync_tls
from cbpos.ui.dialogs.sync_pairing_dialog import SyncPairingDialog
from cbpos.ui.views.settings_pages.network import NetworkPage
from cbpos.ui.widgets.sync_status_widget import SyncStatusWidget


def test_issue_800_sync_status_widget_unpaired_and_mismatch(qapp):
    widget = SyncStatusWidget()
    widget.set_mode("terminal")

    # Test unpaired state
    widget.set_state("unpaired")
    assert widget._dot.property("status") == "unpaired"
    assert widget._label.text() == _t("sync_pairing.not_paired_short")
    details_unpaired = widget._build_details_text()
    assert _t("sync_pairing.not_paired") in details_unpaired

    # Test cert mismatch state
    widget.set_state("error", error_code="cert_mismatch")
    assert widget._dot.property("status") == "error"
    assert widget._label.text() == _t("sync_pairing.changed")
    details_mismatch = widget._build_details_text()
    assert _t("sync_pairing.changed") in details_mismatch


def test_issue_800_network_page_sync_cards(qapp, tmp_path, monkeypatch):
    # Isolated config
    monkeypatch.setattr(ConfigService, "SETTINGS_FILE", os.path.join(tmp_path, "settings.json"))
    monkeypatch.setattr(ConfigService, "_settings", {})
    ConfigService.load()

    cert_path = os.path.join(tmp_path, "test_cert.pem")
    key_path = os.path.join(tmp_path, "test_key.pem")
    monkeypatch.setattr(sync_tls, "CERT_FILE", cert_path)
    monkeypatch.setattr(sync_tls, "KEY_FILE", key_path)
    sync_tls.get_or_create_certificate()

    page = NetworkPage()
    page.show()
    page.tabs.setCurrentIndex(3)

    # 1. Standalone mode: both cards hidden
    page.cmb_terminal_mode.setCurrentIndex(page.cmb_terminal_mode.findData("standalone"))
    assert not page.main_code_card.isVisible()
    assert not page.terminal_pairing_card.isVisible()

    # 2. Main PC mode: main_code_card visible, terminal_pairing_card hidden
    page.cmb_terminal_mode.setCurrentIndex(page.cmb_terminal_mode.findData("main"))
    assert page.main_code_card.isVisible()
    assert not page.terminal_pairing_card.isVisible()
    assert page.lbl_main_code_fp.text() != ""
    assert len(page.lbl_main_code_fp.text().split("\n")) == 4

    # Test copy main code
    page._copy_main_code()
    assert QApplication.clipboard().text() == page._main_canonical_fp

    # 3. Terminal mode: terminal_pairing_card visible, main_code_card hidden
    page.cmb_terminal_mode.setCurrentIndex(page.cmb_terminal_mode.findData("terminal"))
    assert not page.main_code_card.isVisible()
    assert page.terminal_pairing_card.isVisible()

    # 3a. Unpaired state
    assert _t("sync_pairing.not_paired") in page.lbl_tp_status.text()
    assert page.btn_pair_action.text() == _t("sync_pairing.title")

    # 3b. Paired state
    ConfigService.set("sync_pinned_cert_fp", "AA:BB:CC:DD:EE:FF:00:11")
    page._update_terminal_pairing_card()
    assert _t("sync_pairing.paired") in page.lbl_tp_status.text()
    assert page.btn_pair_action.text() == _t("sync_pairing.change")

    # 3c. Mismatch state
    page._cert_mismatch = True
    page._update_terminal_pairing_card()
    assert _t("sync_pairing.changed") in page.lbl_tp_status.text()
    assert page.btn_pair_action.text() == _t("sync_pairing.review")


def test_issue_800_sync_pairing_dialog_pairing(qapp, tmp_path, db_session, monkeypatch):
    monkeypatch.setattr(ConfigService, "SETTINGS_FILE", os.path.join(tmp_path, "settings.json"))
    monkeypatch.setattr(ConfigService, "_settings", {})
    ConfigService.load()

    cert_path = os.path.join(tmp_path, "srv_cert.pem")
    key_path = os.path.join(tmp_path, "srv_key.pem")
    monkeypatch.setattr(sync_tls, "CERT_FILE", cert_path)
    monkeypatch.setattr(sync_tls, "KEY_FILE", key_path)
    sync_tls.get_or_create_certificate()
    with open(cert_path, encoding="ascii") as f:
        pem = f.read()

    canonical_fp = sync_tls.cert_fingerprint(pem)

    monkeypatch.setattr(SyncPairingDialog, "_start_fetch", lambda self: None)
    dlg = SyncPairingDialog(host="127.0.0.1", port=5555, re_pair=False)
    dlg.show()
    # Simulate worker fetch completion
    dlg._on_cert_fetched(True, pem, canonical_fp)

    assert dlg.card_frame.isVisible()
    assert dlg.btn_pair.isEnabled()
    assert dlg.btn_cancel.isDefault()
    assert not dlg.btn_pair.isDefault()

    # Mock QMessageBox.information
    monkeypatch.setattr("cbpos.ui.dialogs.sync_pairing_dialog.QMessageBox.information", lambda *a, **k: None)
    dlg.accept = MagicMock()

    dlg._on_pair_clicked()

    assert ConfigService.get("sync_pinned_cert_pem") == pem
    assert ConfigService.get("sync_pinned_cert_fp") == canonical_fp
    dlg.accept.assert_called_once()

    # Verify AuditLog row was recorded
    logs = db_session.query(AuditLog).filter_by(action="SYNC_PAIRED", event_type="SECURITY").all()
    assert len(logs) == 1
    assert canonical_fp in logs[0].details
