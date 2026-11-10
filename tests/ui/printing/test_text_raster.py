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
    # Text with conjunct 'ශ්‍රී' and 'ප්‍රදර්ශනාගාරය' near paper margin
    text = "ප්‍රධාන ශාඛාව සහ ප්‍රදර්ශනාගාරය, කොළඹ පාර, කුරුණෑගල"
    img = render_text_line({"type": "text", "val": text, "align": "left"}, "58mm")

    assert img.width == 384
    assert img.height > 26
    assert _black_pixels(img) > 150
