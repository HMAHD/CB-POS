"""#564: settings fields that depend on an option are visibly disabled with it.

- Tax tab: with VAT off, the rate fields *and their labels* are disabled.
- Receipt tab: the QR content field is enabled only while Show QR is on,
  and saving with Show QR on but no content asks for confirmation.
"""

import pytest
from PyQt6.QtWidgets import QMessageBox

from cbpos.core.services.config_service import ConfigService
from cbpos.ui.views.settings_pages import ReceiptPage, SalesTaxPage

pytestmark = pytest.mark.usefixtures("qapp")


class _FakeConfigStore:
    """In-memory ConfigService stand-in so tests never touch settings.json."""

    def __init__(self, initial: dict):
        self._data = dict(initial)

    def get(self, key):
        return self._data.get(key)

    def get_all(self):
        return dict(self._data)

    def set(self, key, value):
        self._data[key] = value

    def update_all(self, data, **_kwargs):
        self._data.update(data)


@pytest.fixture
def config_store(monkeypatch):
    store = _FakeConfigStore(dict(ConfigService.DEFAULTS))
    monkeypatch.setattr(ConfigService, "get", store.get)
    monkeypatch.setattr(ConfigService, "get_all", store.get_all)
    monkeypatch.setattr(ConfigService, "set", store.set)
    monkeypatch.setattr(ConfigService, "update_all", store.update_all)
    return store


@pytest.fixture
def tax_page(qtbot):
    page = SalesTaxPage()
    qtbot.addWidget(page)
    return page


@pytest.fixture
def receipt_page(qtbot, config_store):
    page = ReceiptPage()
    qtbot.addWidget(page)
    yield page
    page._refresh_timer.stop()


class TestTaxFieldsAndLabelsFollowVatRegistration:
    def test_vat_off_disables_fields_and_labels(self, tax_page):
        tax_page.load({"vat_registered": False})
        for widget in (
            tax_page.spin_vat,
            tax_page._lbl_vat_rate,
            tax_page.spin_sscl,
            tax_page._lbl_sscl_rate,
            tax_page.spin_sscl_turnover,
            tax_page._lbl_sscl_turnover,
        ):
            assert widget.isEnabled() is False

    def test_vat_on_enables_fields_and_labels(self, tax_page):
        tax_page.load({"vat_registered": True})
        assert tax_page.spin_vat.isEnabled() is True
        assert tax_page._lbl_vat_rate.isEnabled() is True
        assert tax_page._lbl_sscl_turnover.isEnabled() is True

    def test_issue_831_sscl_independent_from_vat(self, tax_page):
        """SSCL registered controls can be active while VAT is disabled (#831)."""
        tax_page.load({"vat_registered": False, "sscl_registered": True})
        assert tax_page.spin_vat.isEnabled() is False
        assert tax_page._lbl_vat_rate.isEnabled() is False
        assert tax_page.spin_sscl.isEnabled() is True
        assert tax_page._lbl_sscl_rate.isEnabled() is True
        assert tax_page.combo_sscl_preset.isEnabled() is True
        assert tax_page._lbl_sscl_preset.isEnabled() is True
        assert tax_page._lbl_sscl_turnover.isEnabled() is True

    def test_issue_831_turnover_spin_enabled_only_on_custom_preset(self, tax_page):
        """Turnover % is locked to preset values and editable only under CUSTOM (#831)."""
        tax_page.load({"sscl_registered": True, "sscl_turnover_preset": "RETAIL"})
        assert tax_page.spin_sscl_turnover.isEnabled() is False
        assert tax_page.spin_sscl_turnover.value() == 50.0

        # Change preset to CUSTOM enables editing
        idx_custom = tax_page.combo_sscl_preset.findData("CUSTOM")
        tax_page.combo_sscl_preset.setCurrentIndex(idx_custom)
        assert tax_page.spin_sscl_turnover.isEnabled() is True

        # Change preset to MANUFACTURER locks to 85%
        idx_mfg = tax_page.combo_sscl_preset.findData("MANUFACTURER")
        tax_page.combo_sscl_preset.setCurrentIndex(idx_mfg)
        assert tax_page.spin_sscl_turnover.isEnabled() is False
        assert tax_page.spin_sscl_turnover.value() == 85.0

        # Change preset to DISTRIBUTOR locks to 25%
        idx_dist = tax_page.combo_sscl_preset.findData("DISTRIBUTOR")
        tax_page.combo_sscl_preset.setCurrentIndex(idx_dist)
        assert tax_page.spin_sscl_turnover.isEnabled() is False
        assert tax_page.spin_sscl_turnover.value() == 25.0


class TestQrContentFollowsShowQr:
    def test_load_with_qr_off_disables_content(self, receipt_page):
        receipt_page.load({"show_qr_on_receipt": False, "receipt_qr_content": ""})
        assert receipt_page.txt_qr_content.isEnabled() is False
        assert receipt_page._lbl_qr_content.isEnabled() is False

    def test_load_with_qr_on_enables_content(self, receipt_page):
        receipt_page.load({"show_qr_on_receipt": True, "receipt_qr_content": "https://wa.me/1"})
        assert receipt_page.txt_qr_content.isEnabled() is True

    def test_toggling_show_qr_toggles_content(self, receipt_page):
        receipt_page.load({"show_qr_on_receipt": False})
        receipt_page.chk_show_qr.setChecked(True)
        assert receipt_page.txt_qr_content.isEnabled() is True
        receipt_page.chk_show_qr.setChecked(False)
        assert receipt_page.txt_qr_content.isEnabled() is False

    def test_qr_on_with_empty_content_warns(self, receipt_page):
        receipt_page.chk_show_qr.setChecked(True)
        receipt_page.txt_qr_content.setText("   ")
        assert len(receipt_page.save_warnings()) == 1

    def test_qr_on_with_content_or_off_does_not_warn(self, receipt_page):
        receipt_page.chk_show_qr.setChecked(True)
        receipt_page.txt_qr_content.setText("https://wa.me/1")
        assert receipt_page.save_warnings() == []
        receipt_page.chk_show_qr.setChecked(False)
        receipt_page.txt_qr_content.setText("")
        assert receipt_page.save_warnings() == []


class TestSettingsViewConfirmsSaveWarnings:
    @pytest.fixture
    def view(self, qtbot, db_session, config_store, monkeypatch):
        from cbpos.ui.views.settings_view import SettingsView

        monkeypatch.setattr(
            "cbpos.core.utils.permission_helper.check_permission_with_override",
            lambda perm, parent: True,
        )
        # Real message boxes block under the offscreen platform.
        monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
        v = SettingsView()
        qtbot.addWidget(v)
        yield v
        for page in v.pages:
            if hasattr(page, "_refresh_timer"):
                page._refresh_timer.stop()

    def _qr_page(self, view):
        return next(p for p in view.pages if isinstance(p, ReceiptPage))

    def test_declining_the_warning_does_not_save(self, view, config_store, monkeypatch):
        asked = []
        monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: asked.append(a) or QMessageBox.StandardButton.No)
        page = self._qr_page(view)
        page.chk_show_qr.setChecked(True)
        page.txt_qr_content.setText("")

        view.save_all()

        assert asked, "expected a confirmation warning"
        assert config_store.get("show_qr_on_receipt") is False

    def test_accepting_the_warning_saves(self, view, config_store, monkeypatch):
        monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.StandardButton.Yes)
        page = self._qr_page(view)
        page.chk_show_qr.setChecked(True)
        page.txt_qr_content.setText("")

        view.save_all()

        assert config_store.get("show_qr_on_receipt") is True
