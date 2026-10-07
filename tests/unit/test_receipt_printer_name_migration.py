"""
#622: before this, the Hardware page and Setup Wizard saved only
``receipt_printer_name``, which nothing read, so ``printer_type`` stayed
NONE. An existing install with a real printer name there is migrated to a
WIN32 (Windows printer) setting when settings load.
"""

import json
import os

import pytest

from cbpos.core.constants.hardware import PrinterType
from cbpos.core.services.config_service import ConfigService


@pytest.fixture
def isolated_config(tmp_path):
    """Point ConfigService at a throwaway settings file; restore afterwards."""
    original_file = ConfigService.SETTINGS_FILE
    original_settings = ConfigService._settings
    ConfigService.SETTINGS_FILE = os.path.join(tmp_path, "settings.json")
    ConfigService._settings = {}
    yield ConfigService.SETTINGS_FILE
    ConfigService.SETTINGS_FILE = original_file
    ConfigService._settings = original_settings


def _load_from(path: str, data: dict) -> dict:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    ConfigService._settings = {}
    ConfigService.load()
    return ConfigService.get_all()


class TestLegacyReceiptPrinterNameMigration:
    def test_name_with_no_type_becomes_windows_printer(self, isolated_config):
        settings = _load_from(isolated_config, {"printer_type": "NONE", "receipt_printer_name": "XP-80C"})
        assert settings["printer_type"] == PrinterType.WIN32
        assert settings["printer_path"] == "XP-80C"

    def test_migration_is_written_back_to_disk(self, isolated_config):
        _load_from(isolated_config, {"receipt_printer_name": "XP-80C"})
        with open(isolated_config, encoding="utf-8") as f:
            on_disk = json.load(f)
        assert on_disk["printer_type"] == PrinterType.WIN32
        assert on_disk["printer_path"] == "XP-80C"

    def test_existing_network_printer_is_left_alone(self, isolated_config):
        settings = _load_from(
            isolated_config,
            {"printer_type": "NETWORK", "printer_path": "192.168.1.50", "receipt_printer_name": "XP-80C"},
        )
        assert settings["printer_type"] == PrinterType.NETWORK
        assert settings["printer_path"] == "192.168.1.50"

    @pytest.mark.parametrize("name", ["", "No printers found", "Microsoft Print to PDF", "Fax", "OneNote (Desktop)"])
    def test_placeholder_or_virtual_printer_is_not_migrated(self, isolated_config, name):
        settings = _load_from(isolated_config, {"printer_type": "NONE", "receipt_printer_name": name})
        assert settings["printer_type"] == "NONE"

    def test_terminal_prefixed_name_is_migrated(self, isolated_config):
        settings = _load_from(
            isolated_config,
            {"db_mode": "network", "terminal_id": "TERM-02", "TERM-02.receipt_printer_name": "Counter 2"},
        )
        assert settings["TERM-02.printer_type"] == PrinterType.WIN32
        assert settings["TERM-02.printer_path"] == "Counter 2"
