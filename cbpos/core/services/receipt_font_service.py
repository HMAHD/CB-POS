"""Receipt font selection and resolution service (Phase 10A #925).

Provides a single deep seam for querying and updating receipt font presets:
- PRESET_CLEAR ('clear', default/recommended): Noto Sans Sinhala, Noto Sans Tamil, Noto Sans
- PRESET_COMPACT ('compact'): Yaldevi (narrow Sinhala/Latin) + Noto Sans Tamil
- PRESET_NIRMALA ('nirmala'): Windows Nirmala UI (exposed on Windows only)

Governs font family selection for 1-bit thermal rasterization (`text_raster.py`)
and font name resolution for A4 vector PDF invoices (`pdf_fonts.py`).
"""

import logging
import sys

from cbpos.core.services.config_service import ConfigService
from cbpos.i18n import _t

logger = logging.getLogger(__name__)


class ReceiptFontService:
    """Manages receipt font choice presets across thermal and vector printing."""

    PRESET_CLEAR = "clear"
    PRESET_COMPACT = "compact"
    PRESET_NIRMALA = "nirmala"

    _ALL_PRESETS = (PRESET_CLEAR, PRESET_COMPACT, PRESET_NIRMALA)

    @classmethod
    def current(cls) -> str:
        """Return the active receipt font preset, falling back safely to 'clear'."""
        val = ConfigService.get("receipt_font_preset")
        if not val or val not in cls.get_available_preset_ids():
            return cls.PRESET_CLEAR
        return str(val)

    @classmethod
    def set_preset(cls, preset: str) -> None:
        """Set and persist the receipt font preset.

        Raises:
            ValueError: If the preset is not supported or not available.
        """
        valid_ids = cls.get_available_preset_ids()
        if preset not in valid_ids:
            raise ValueError(f"Invalid receipt font preset: {preset!r}. Must be one of {valid_ids}")
        ConfigService.set("receipt_font_preset", preset)

    @classmethod
    def is_nirmala_available(cls) -> bool:
        """Return True strictly on Windows if Nirmala UI is installed."""
        if sys.platform != "win32":
            return False
        try:
            from PyQt6.QtGui import QFontDatabase

            return "Nirmala UI" in QFontDatabase.families()
        except Exception as e:
            logger.debug("Failed to query QFontDatabase for Nirmala UI: %s", e)
            return False

    @classmethod
    def get_available_preset_ids(cls) -> list[str]:
        """Return list of valid preset IDs on the current platform."""
        ids = [cls.PRESET_CLEAR, cls.PRESET_COMPACT]
        if cls.is_nirmala_available():
            ids.append(cls.PRESET_NIRMALA)
        return ids

    @classmethod
    def get_available_presets(cls) -> list[dict[str, str]]:
        """Return user-facing preset choices with translated labels and descriptions."""
        presets = [
            {
                "id": cls.PRESET_CLEAR,
                "name": _t("settings.receipt.font_clear", default="Clear (recommended)"),
                "family_info": "Noto Sans",
                "desc": _t(
                    "settings.receipt.font_clear_desc",
                    default="Crisp, balanced spacing for 58mm and 80mm receipts",
                ),
            },
            {
                "id": cls.PRESET_COMPACT,
                "name": _t("settings.receipt.font_compact", default="Compact"),
                "family_info": "Yaldevi",
                "desc": _t(
                    "settings.receipt.font_compact_desc",
                    default="Narrower Sinhala font, fits up to 26% more text per line",
                ),
            },
        ]
        if cls.is_nirmala_available():
            presets.append(
                {
                    "id": cls.PRESET_NIRMALA,
                    "name": _t("settings.receipt.font_nirmala", default="Windows Nirmala UI"),
                    "family_info": "Nirmala UI",
                    "desc": _t(
                        "settings.receipt.font_nirmala_desc",
                        default="Windows built-in Indic font",
                    ),
                }
            )
        return presets

    @classmethod
    def get_font_families(cls, preset: str | None = None) -> list[str]:
        """Return font family fallback chain for Qt thermal rasterization.

        Args:
            preset: Optional preset override. If None, uses cls.current().
        """
        p = preset or cls.current()
        if p == cls.PRESET_COMPACT:
            return ["Yaldevi", "Noto Sans Tamil", "Noto Sans"]
        if p == cls.PRESET_NIRMALA and cls.is_nirmala_available():
            return ["Nirmala UI", "Noto Sans Sinhala", "Noto Sans Tamil", "Noto Sans"]
        # Default / clear
        return ["Noto Sans Sinhala", "Noto Sans Tamil", "Noto Sans"]

    @classmethod
    def get_pdf_font_name(cls, lang: str, bold: bool = False, preset: str | None = None) -> str:
        """Return ReportLab registered font name for vector PDF generation.

        Args:
            lang: Language code ('si', 'ta', or 'en').
            bold: Whether bold weight is requested.
            preset: Optional preset override. If None, uses cls.current().
        """
        p = preset or cls.current()
        if p == cls.PRESET_COMPACT and lang == "si":
            return "Yaldevi-Bold" if bold else "Yaldevi"
        if lang == "si":
            return "NotoSansSinhala-Bold" if bold else "NotoSansSinhala"
        if lang == "ta":
            return "NotoSansTamil-Bold" if bold else "NotoSansTamil"
        return "NotoSans-Bold" if bold else "NotoSans"
