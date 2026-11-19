"""Integration tests for receipt font raster and vector PDF rendering (Phase 10A #925).

Verifies:
1. render_text_line correctly renders Sinhala/Tamil lines using Clear (Noto) and Compact (Yaldevi).
2. Yaldevi character density is significantly higher than Noto Sans Sinhala.
3. Explicit font_families parameter in command or call overrides active preset.
4. ReportLab PDF shaping resolves Yaldevi and Yaldevi-Bold with complex script shaping (shaping=1).
"""

import io

from PIL import Image
from PyQt6.QtGui import QFont, QFontMetrics
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate

from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.receipt_font_service import ReceiptFontService
from cbpos.infrastructure.hardware.text_raster import render_text_line
from cbpos.infrastructure.pdf_fonts import font_for, make_shaped_paragraph, register_pdf_fonts
from cbpos.infrastructure.resource_loader import ResourceLoader


def test_thermal_raster_noto_vs_yaldevi_density(qapp):
    """Test that Yaldevi fits more Sinhala characters per line than Noto Sans Sinhala."""
    ResourceLoader.load_fonts()

    sinhala_text = "ශ්‍රී ලංකා ප්‍රජාතාන්ත්‍රික සමාජවාදී ජනරජය"

    # Measure advance using font metrics directly
    font_noto = QFont()
    font_noto.setFamilies(ReceiptFontService.get_font_families(ReceiptFontService.PRESET_CLEAR))
    font_noto.setPixelSize(20)
    noto_w = QFontMetrics(font_noto).horizontalAdvance(sinhala_text)

    font_yaldevi = QFont()
    font_yaldevi.setFamilies(ReceiptFontService.get_font_families(ReceiptFontService.PRESET_COMPACT))
    font_yaldevi.setPixelSize(20)
    yaldevi_w = QFontMetrics(font_yaldevi).horizontalAdvance(sinhala_text)

    # Yaldevi should be visibly narrower (higher character density)
    assert yaldevi_w < noto_w
    savings_pct = (noto_w - yaldevi_w) / noto_w * 100
    assert savings_pct > 10.0, f"Expected >10% narrower, got {savings_pct:.1f}%"


def test_render_text_line_with_presets(qapp):
    """Test render_text_line outputs valid mode '1' images with both presets."""
    cmd = {"type": "text", "val": "භාණ්ඩය A - රු. 150.00", "align": "left"}

    # 1. Clear preset on 80mm (576 dots)
    ReceiptFontService.set_preset(ReceiptFontService.PRESET_CLEAR)
    img_clear_80 = render_text_line(cmd, "80mm")
    assert isinstance(img_clear_80, Image.Image)
    assert img_clear_80.mode == "1"
    assert img_clear_80.width == 576

    # 2. Compact preset on 58mm (384 dots)
    ReceiptFontService.set_preset(ReceiptFontService.PRESET_COMPACT)
    img_compact_58 = render_text_line(cmd, "58mm")
    assert isinstance(img_compact_58, Image.Image)
    assert img_compact_58.mode == "1"
    assert img_compact_58.width == 384

    # 3. Explicit command-level font_families override
    custom_families = ["Noto Sans Sinhala", "Noto Sans"]
    cmd_override = dict(cmd, font_families=custom_families)
    img_custom = render_text_line(cmd_override, "80mm")
    assert img_custom.width == 576


def test_pdf_yaldevi_vector_shaping():
    """Test ReportLab PDF rendering with Yaldevi and HarfBuzz shaping."""
    register_pdf_fonts()

    # In compact mode, Sinhala text resolves to Yaldevi
    ConfigService.set("receipt_font_preset", "compact")
    assert font_for("ශ්‍රී ලංකා") == "Yaldevi"
    assert font_for("தமிழ்") == "NotoSansTamil"
    assert font_for("English Text") == "NotoSans"

    # Paragraph with normal weight
    style = ParagraphStyle("TestStyle", fontName="NotoSans", fontSize=10, leading=12)
    flowable = make_shaped_paragraph("ශ්‍රී ලංකා වෙළඳසැල", style)
    assert hasattr(flowable, "style")
    assert flowable.style.fontName == "Yaldevi"
    assert flowable.style.shaping == 1

    # Paragraph with bold weight
    style_bold = ParagraphStyle("TestStyleBold", fontName="NotoSans-Bold", fontSize=10, leading=12)
    flowable_bold = make_shaped_paragraph("ශ්‍රී ලංකා වෙළඳසැල", style_bold)
    assert flowable_bold.style.fontName == "Yaldevi-Bold"
    assert flowable_bold.style.shaping == 1

    # Build PDF successfully
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf)
    doc.build([flowable, flowable_bold])
    pdf_bytes = buf.getvalue()
    assert len(pdf_bytes) > 1000
    assert b"%PDF" in pdf_bytes
