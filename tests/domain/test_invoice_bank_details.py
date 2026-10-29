"""Settings -> Shop Info -> Bank Name / Account No. / Branch were saved as
company_bank_name / company_account_number / company_bank_branch, but the
A4 invoice read bank_name / bank_account / bank_branch -- keys nothing ever
wrote -- so the bank block never printed. The invoice now reads what the
page saves.

The old defaults were demo values ("Commercial Bank of Ceylon",
"1234567890", "Colombo Fort") written into every settings.json on first
run; wiring the keys would have printed them on real shops' invoices. The
defaults are now blank and that exact demo trio is cleared on load.
"""

import json

import pytest

from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.invoice_service import InvoiceService

DEMO = {
    "company_bank_name": "Commercial Bank of Ceylon",
    "company_account_number": "1234567890",
    "company_bank_branch": "Colombo Fort",
}


def _config(monkeypatch, values: dict):
    monkeypatch.setattr(ConfigService, "get", staticmethod(lambda key: values.get(key)))


class TestInvoicePrintsSavedBankDetails:
    def test_lines_come_from_the_shop_info_keys(self, monkeypatch):
        _config(
            monkeypatch,
            {
                "company_bank_name": "People's Bank",
                "company_account_number": "0041-55-321",
                "company_bank_branch": "Kandy",
            },
        )

        lines = InvoiceService.bank_detail_lines()

        assert lines == ["Bank: People's Bank", "Account No: 0041-55-321", "Branch: Kandy"]

    def test_nothing_printed_when_no_bank_details_are_set(self, monkeypatch):
        _config(monkeypatch, {})

        assert InvoiceService.bank_detail_lines() == []


class TestDemoBankDetailsAreNotPrinted:
    def test_defaults_are_blank(self):
        for key in DEMO:
            assert ConfigService.DEFAULTS[key] == ""

    @pytest.fixture
    def settings_file(self, tmp_path, monkeypatch):
        path = tmp_path / "settings.json"
        monkeypatch.setattr(ConfigService, "SETTINGS_FILE", str(path))
        monkeypatch.setattr(ConfigService, "_settings", {})
        return path

    def test_stored_demo_trio_is_cleared_on_load(self, settings_file):
        settings_file.write_text(json.dumps({**DEMO, "shop_name": "Kamal Stores"}), encoding="utf-8")

        ConfigService.load()

        for key in DEMO:
            assert ConfigService._settings[key] == ""
        assert ConfigService._settings["shop_name"] == "Kamal Stores"
        assert json.loads(settings_file.read_text(encoding="utf-8"))["company_account_number"] == ""

    def test_real_bank_details_are_kept(self, settings_file):
        real = {**DEMO, "company_account_number": "8001234567"}  # same bank and branch, real account
        settings_file.write_text(json.dumps(real), encoding="utf-8")

        ConfigService.load()

        assert ConfigService._settings["company_account_number"] == "8001234567"
        assert ConfigService._settings["company_bank_name"] == "Commercial Bank of Ceylon"
