"""PDF font management and shaping infrastructure (#806).

Registers bundled Noto Sans fonts (Latin, Sinhala, Tamil) into ReportLab,
configures font families for bold/italic resolution, and provides helpers
for script detection, XML escaping, and shaped Paragraph generation.
"""

import logging
import sys
import xml.sax.saxutils
from pathlib import Path
from typing import Any

from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics, ttfonts
from reportlab.platypus import Paragraph

logger = logging.getLogger(__name__)

_FONTS_REGISTERED = False


def is_shaping_available() -> bool:
    """Return True if uharfbuzz is importable and ReportLab can shape."""
    try:
        import uharfbuzz  # noqa: F401

        return True
    except ImportError:
        return False


def _get_font_dir() -> Path:
    """Resolve font directory in local development or PyInstaller bundle."""
    if hasattr(sys, "_MEIPASS"):
        bundle_dir = Path(sys._MEIPASS) / "cbpos" / "assets" / "fonts"
        if bundle_dir.exists():
            return bundle_dir
    # Local development
    here = Path(__file__).resolve().parent.parent / "assets" / "fonts"
    return here


def register_pdf_fonts() -> None:
    """Register Noto Sans (Latin, Sinhala, Tamil) and their font families in ReportLab.

    Idempotent: runs once per process.
    """
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return

    font_dir = _get_font_dir()
    if not font_dir.exists():
        logger.warning("Font directory %s does not exist; skipping font registration", font_dir)
        return

    font_defs = [
        # (Font name, relative path)
        ("NotoSans", "Noto_Sans/static/NotoSans-Regular.ttf"),
        ("NotoSans-Bold", "Noto_Sans/static/NotoSans-Bold.ttf"),
        ("NotoSansSinhala", "Noto_Sans_Sinhala/static/NotoSansSinhala-Regular.ttf"),
        ("NotoSansSinhala-Bold", "Noto_Sans_Sinhala/static/NotoSansSinhala-Bold.ttf"),
        ("NotoSansTamil", "Noto_Sans_Tamil/static/NotoSansTamil-Regular.ttf"),
        ("NotoSansTamil-Bold", "Noto_Sans_Tamil/static/NotoSansTamil-Bold.ttf"),
    ]

    for name, rel_path in font_defs:
        path = font_dir / rel_path
        if path.exists():
            try:
                # TTFont accepts shapable=True when ReportLab >= 4.0
                tt = ttfonts.TTFont(name, str(path))
                pdfmetrics.registerFont(tt)
            except Exception as e:
                logger.error("Failed to register font %s from %s: %s", name, path, e)
        else:
            logger.warning("Font file not found: %s", path)

    # Register font families so <b> tags and paragraph parsers map correctly
    families = [
        ("NotoSans", "NotoSans", "NotoSans-Bold"),
        ("NotoSansSinhala", "NotoSansSinhala", "NotoSansSinhala-Bold"),
        ("NotoSansTamil", "NotoSansTamil", "NotoSansTamil-Bold"),
    ]
    registered_names = set(pdfmetrics.getRegisteredFontNames())
    for family, normal, bold in families:
        if normal in registered_names:
            bold_name = bold if bold in registered_names else normal
            try:
                pdfmetrics.registerFontFamily(family, normal=normal, bold=bold_name)
            except Exception as e:
                logger.debug("Font family %s registration note: %s", family, e)

    _FONTS_REGISTERED = True


def font_for(text: str) -> str:
    """Return the registered font name appropriate for the scripts found in text.

    Checks Unicode blocks:
    - Sinhala: U+0D80 to U+0DFF
    - Tamil:   U+0B80 to U+0BFF
    - Default: NotoSans (bundled with standard Latin / numbers)
    """
    if not text:
        return "NotoSans"

    has_sinhala = False
    has_tamil = False

    for ch in text:
        cp = ord(ch)
        if 0x0D80 <= cp <= 0x0DFF:
            has_sinhala = True
            break
        if 0x0B80 <= cp <= 0x0BFF:
            has_tamil = True
            break

    if has_sinhala:
        return "NotoSansSinhala"
    if has_tamil:
        return "NotoSansTamil"
    return "NotoSans"


def escape_text(val: Any) -> str:
    """Sanitize and XML-escape cell content for safe ReportLab Paragraph parsing."""
    if val is None:
        return "—"

    # Handle pandas / numpy NaN
    try:
        import pandas as pd

        if pd.isna(val):
            return "—"
    except Exception:
        pass

    text = str(val).strip()
    if not text:
        return ""

    return xml.sax.saxutils.escape(text)


def create_cell_paragraph(
    val: Any,
    bold: bool = False,
    align: str = "left",
    font_size: int = 8,
    leading: int | None = None,
) -> Paragraph:
    """Build a styled, shaped ReportLab Paragraph for a table cell."""
    register_pdf_fonts()
    raw_str = "" if val is None else str(val)
    escaped = escape_text(val)

    font_base = font_for(raw_str)
    font_name = f"{font_base}-Bold" if bold else font_base

    # Alignments
    align_code = TA_LEFT
    if align.lower() == "right":
        align_code = TA_RIGHT
    elif align.lower() == "center":
        align_code = TA_CENTER

    lead = leading if leading is not None else font_size + 2
    shaping_val = 1 if is_shaping_available() else 0

    style = ParagraphStyle(
        name=f"Cell_{font_name}_{align}_{font_size}",
        fontName=font_name,
        fontSize=font_size,
        leading=lead,
        alignment=align_code,
        shaping=shaping_val,
    )

    return Paragraph(escaped, style)
