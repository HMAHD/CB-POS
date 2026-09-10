"""
#330: browse_logo() never validated or reprocessed the selected image,
and the printer path did a width-only downscale with no grayscale
conversion or dithering of its own -- whatever monochrome conversion
happened was left entirely to python-escpos's internal image() call,
un-previewable and untunable. dither_for_thermal_print() is the shared
step both the printer and the preview now go through.
"""

from PIL import Image

from cbpos.core.utils.thermal_image import PAPER_DOT_WIDTH, dither_for_thermal_print


class TestDitherForThermalPrint:
    def test_returns_a_1_bit_image(self):
        img = Image.new("RGB", (100, 50), color=(255, 0, 0))
        result = dither_for_thermal_print(img, "80mm")
        assert result.mode == "1"

    def test_narrower_than_paper_width_is_not_upscaled(self):
        img = Image.new("RGB", (100, 50), color=(0, 255, 0))
        result = dither_for_thermal_print(img, "80mm")
        assert result.width == 100

    def test_wider_than_58mm_dot_width_is_downscaled_to_it(self):
        img = Image.new("RGB", (900, 300), color=(0, 0, 255))
        result = dither_for_thermal_print(img, "58mm")
        assert result.width == PAPER_DOT_WIDTH["58mm"]

    def test_wider_than_80mm_dot_width_is_downscaled_to_it(self):
        img = Image.new("RGB", (900, 300), color=(0, 0, 255))
        result = dither_for_thermal_print(img, "80mm")
        assert result.width == PAPER_DOT_WIDTH["80mm"]

    def test_58mm_and_80mm_have_different_dot_widths(self):
        assert PAPER_DOT_WIDTH["58mm"] != PAPER_DOT_WIDTH["80mm"]

    def test_aspect_ratio_is_preserved_when_downscaled(self):
        img = Image.new("RGB", (1000, 500), color=(10, 10, 10))
        result = dither_for_thermal_print(img, "80mm")
        expected_height = round(500 * (PAPER_DOT_WIDTH["80mm"] / 1000))
        assert result.height == expected_height
