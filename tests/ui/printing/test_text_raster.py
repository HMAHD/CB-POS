"""Tests for issue #877: wrapping long Sinhala and Tamil text lines on 58mm receipts.

When text exceeds the paper width at the minimum font size (_MIN_PIXEL_SIZE=14),
it wraps onto multiple lines and grows the image height instead of clipping.
"""

import pytest

from cbpos.infrastructure.hardware.text_raster import render_text_line
from cbpos.infrastructure.resource_loader import ResourceLoader

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture(autouse=True)
def _ensure_fonts_loaded():
    ResourceLoader.load_fonts()


def _black_pixels(img) -> int:
    """Return count of black (ink) pixels in mode 1 image (0 is black)."""
    return img.convert("L").histogram()[0]


def test_issue_877_sinhala_address_wraps_on_58mm():
    """53-code-point Sinhala address wraps taller than 1 line on 58mm without edge clipping."""
    # Typical 53-code-point Sinhala shop address
    address = "නො. 123, ගාලු පාර, කොල්ලුපිටිය, කොළඹ 03, ශ්‍රී ලංකාව."
    assert len(address) == 53

    img = render_text_line({"type": "text", "val": address, "align": "center"}, "58mm")

    assert img.width == 384
    # Height must be taller than 1 line (1 line at 14px + padding is ~22-24px)
    assert img.height > 26

    # Verify no clipped ink in column 0 or column 383
    col0_black = [img.getpixel((0, y)) for y in range(img.height)].count(0)
    col_last_black = [img.getpixel((img.width - 1, y)) for y in range(img.height)].count(0)

    assert col0_black == 0, f"Expected no ink in column 0, found {col0_black} black pixels"
    assert col_last_black == 0, f"Expected no ink in column 383, found {col_last_black} black pixels"

    # Verify valid glyph ink was rendered
    assert _black_pixels(img) > 100


def test_issue_877_tamil_line_wraps():
    """Long Tamil address wraps taller than 1 line on 58mm without edge clipping."""
    tamil_addr = "எண். 123, காலி வீதி, கொள்ளுப்பிட்டி, கொழும்பு 03, இலங்கை."

    img = render_text_line({"type": "text", "val": tamil_addr, "align": "center"}, "58mm")

    assert img.width == 384
    assert img.height > 26

    col0_black = [img.getpixel((0, y)) for y in range(img.height)].count(0)
    col_last_black = [img.getpixel((img.width - 1, y)) for y in range(img.height)].count(0)

    assert col0_black == 0, f"Expected no ink in column 0, found {col0_black} black pixels"
    assert col_last_black == 0, f"Expected no ink in column 383, found {col_last_black} black pixels"
    assert _black_pixels(img) > 100


def test_issue_877_short_line_unchanged():
    """Short Sinhala text renders as a single-line image without unnecessary height."""
    short_text = "මුළු එකතුව"
    img = render_text_line({"type": "text", "val": short_text, "align": "center"}, "58mm")

    assert img.width == 384
    # Single line height stays around 35px (font size 24 + padding)
    assert img.height <= 36
    assert _black_pixels(img) > 50


def test_issue_877_sinhala_conjunct_cluster_preserved():
    """Wrapping preserves grapheme clusters and does not break inside a Sinhala conjunct."""
    from PyQt6.QtGui import QTextLayout

    from cbpos.infrastructure.hardware.text_raster import _font

    # Text with conjuncts 'ප්‍ර' (\u0DB4\u0DCA\u200D\u0DBB) and 'ර්‍ශ' (\u0DBB\u0DCA\u200D\u0DC1)
    text = "ප්‍රධාන ශාඛාව සහ ප්‍රදර්ශනාගාරය, කොළඹ පාර, කුරුණෑගල"

    # Verify wrapping logic directly with QTextLayout on 58mm (384 dots)
    font = _font(False, 14)
    layout = QTextLayout(text, font)
    layout.beginLayout()
    line_segments = []
    while True:
        line = layout.createLine()
        if not line.isValid():
            break
        line.setLineWidth(384)
        line_segments.append(text[line.textStart() : line.textStart() + line.textLength()].strip())
    layout.endLayout()

    # Must wrap into multiple lines on 58mm
    assert len(line_segments) >= 2, f"Expected multi-line wrap, got {line_segments}"

    # Assert wrap boundaries never isolate a virama (\u0DCA) or zero-width joiner (\u200D)
    for seg in line_segments:
        assert not seg.endswith("\u0dca"), f"Line segment ends with isolated virama: {seg!r}"
        assert not seg.endswith("\u200d"), f"Line segment ends with isolated ZWJ: {seg!r}"
        assert not seg.startswith("\u0dca"), f"Line segment starts with isolated virama: {seg!r}"
        assert not seg.startswith("\u200d"), f"Line segment starts with isolated ZWJ: {seg!r}"

    # Words with complex conjuncts must remain intact within their respective lines
    assert any("ප්‍රධාන" in seg for seg in line_segments)
    assert any("ප්‍රදර්ශනාගාරය" in seg for seg in line_segments)

    # Rendered bitmap check
    img = render_text_line({"type": "text", "val": text, "align": "left"}, "58mm")
    assert img.width == 384
    assert img.height > 26
    assert _black_pixels(img) > 150


def test_issue_877_two_column_wrapped_left_val():
    """Two-column receipt lines wrap long descriptions without clipping or overlapping amount."""
    long_desc = "දිගු භාණ්ඩ විස්තරය සහ නාමය කුළුබඩු මිශ්‍රණය 500g විශේෂ ඇසුරුම"
    amount = "1,500.00"
    cmd = {
        "type": "text",
        "left_val": long_desc,
        "right_val": amount,
        "bold": False,
    }
    img = render_text_line(cmd, "58mm")
    assert img.width == 384
    # Multi-line height must be greater than single-line (~35px)
    assert img.height > 36

    # Verify right side has ink for the amount
    col_last_black = [img.getpixel((img.width - 2, y)) for y in range(img.height)].count(0)
    assert col_last_black > 0, "Right-aligned amount must have ink near the right margin"
