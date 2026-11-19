"""Domain tests for ReceiptFontService (Phase 10A #925).

Tests:
1. Default preset is 'clear'.
2. Setting valid presets ('clear', 'compact') updates ConfigService and current().
3. Invalid or unknown presets fail safe and return 'clear'.
4. get_font_families() returns correct fallback chains for thermal raster.
5. get_pdf_font_name() maps ReportLab font names correctly for en/si/ta and bold weights.
6. is_nirmala_available() returns True only on Windows when Nirmala UI exists.
7. get_available_presets() lists supported choices with translated metadata.
"""

from unittest.mock import patch

import pytest

from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.receipt_font_service import ReceiptFontService


@pytest.fixture(autouse=True)
def reset_font_preset():
    """Ensure clean config state for each test."""
    original = ConfigService.get("receipt_font_preset")
    yield
    if original is not None:
        ConfigService.set("receipt_font_preset", original)
    else:
        ConfigService.set("receipt_font_preset", "clear")


def test_default_preset():
    """Default receipt font preset must be 'clear'."""
    ConfigService.set("receipt_font_preset", None)
    assert ReceiptFontService.current() == ReceiptFontService.PRESET_CLEAR


def test_set_and_get_preset():
    """Valid preset transitions persist and reflect in current()."""
    ReceiptFontService.set_preset(ReceiptFontService.PRESET_COMPACT)
    assert ReceiptFontService.current() == ReceiptFontService.PRESET_COMPACT
    assert ConfigService.get("receipt_font_preset") == "compact"

    ReceiptFontService.set_preset(ReceiptFontService.PRESET_CLEAR)
    assert ReceiptFontService.current() == ReceiptFontService.PRESET_CLEAR
    assert ConfigService.get("receipt_font_preset") == "clear"


def test_invalid_preset_fallback():
    """Unrecognized or arbitrary preset strings safely fall back to 'clear'."""
    ConfigService.set("receipt_font_preset", "arbitrary_comic_sans")
    assert ReceiptFontService.current() == ReceiptFontService.PRESET_CLEAR

    with pytest.raises(ValueError, match="Invalid receipt font preset"):
        ReceiptFontService.set_preset("invalid_preset")


def test_get_font_families():
    """Thermal raster font family chains match specifications."""
    # Clear: Noto Sinhala -> Noto Tamil -> Noto Latin
    clear_fams = ReceiptFontService.get_font_families(ReceiptFontService.PRESET_CLEAR)
    assert clear_fams == ["Noto Sans Sinhala", "Noto Sans Tamil", "Noto Sans"]

    # Compact: Yaldevi (Sinhala/Latin) -> Noto Tamil -> Noto Latin
    compact_fams = ReceiptFontService.get_font_families(ReceiptFontService.PRESET_COMPACT)
    assert compact_fams == ["Yaldevi", "Noto Sans Tamil", "Noto Sans"]

    # Active preset inference
    ReceiptFontService.set_preset(ReceiptFontService.PRESET_COMPACT)
    assert ReceiptFontService.get_font_families() == ["Yaldevi", "Noto Sans Tamil", "Noto Sans"]


def test_pdf_font_names():
    """ReportLab font name resolution for A4 vector PDF invoices."""
    # Clear preset
    assert ReceiptFontService.get_pdf_font_name("si", bold=False, preset="clear") == "NotoSansSinhala"
    assert ReceiptFontService.get_pdf_font_name("si", bold=True, preset="clear") == "NotoSansSinhala-Bold"
    assert ReceiptFontService.get_pdf_font_name("ta", bold=False, preset="clear") == "NotoSansTamil"
    assert ReceiptFontService.get_pdf_font_name("ta", bold=True, preset="clear") == "NotoSansTamil-Bold"
    assert ReceiptFontService.get_pdf_font_name("en", bold=False, preset="clear") == "NotoSans"
    assert ReceiptFontService.get_pdf_font_name("en", bold=True, preset="clear") == "NotoSans-Bold"

    # Compact preset: Sinhala resolves to Yaldevi; Tamil stays NotoSansTamil
    assert ReceiptFontService.get_pdf_font_name("si", bold=False, preset="compact") == "Yaldevi"
    assert ReceiptFontService.get_pdf_font_name("si", bold=True, preset="compact") == "Yaldevi-Bold"
    assert ReceiptFontService.get_pdf_font_name("ta", bold=False, preset="compact") == "NotoSansTamil"
    assert ReceiptFontService.get_pdf_font_name("ta", bold=True, preset="compact") == "NotoSansTamil-Bold"
    assert ReceiptFontService.get_pdf_font_name("en", bold=False, preset="compact") == "NotoSans"
    assert ReceiptFontService.get_pdf_font_name("en", bold=True, preset="compact") == "NotoSans-Bold"


def test_nirmala_availability():
    """Nirmala UI is only available on Windows if installed in QFontDatabase."""
    with patch("sys.platform", "darwin"):
        assert not ReceiptFontService.is_nirmala_available()

    with patch("sys.platform", "linux"):
        assert not ReceiptFontService.is_nirmala_available()

    with patch("sys.platform", "win32"):
        with patch("PyQt6.QtGui.QFontDatabase.families", return_value=["Arial", "Segoe UI"]):
            assert not ReceiptFontService.is_nirmala_available()

        with patch("PyQt6.QtGui.QFontDatabase.families", return_value=["Arial", "Nirmala UI", "Segoe UI"]):
            assert ReceiptFontService.is_nirmala_available()


def test_available_presets_list():
    """Presets list returns metadata and conditionally includes Nirmala on Windows."""
    with patch.object(ReceiptFontService, "is_nirmala_available", return_value=False):
        presets = ReceiptFontService.get_available_presets()
        preset_ids = [p["id"] for p in presets]
        assert preset_ids == ["clear", "compact"]
        assert all("name" in p and "desc" in p for p in presets)

    with patch.object(ReceiptFontService, "is_nirmala_available", return_value=True):
        presets = ReceiptFontService.get_available_presets()
        preset_ids = [p["id"] for p in presets]
        assert preset_ids == ["clear", "compact", "nirmala"]
