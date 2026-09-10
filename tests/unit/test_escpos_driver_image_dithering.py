"""
#330: print_commands() only did a width-based downscale on the raw
color/greyscale image and handed it straight to python-escpos's
printer.image(), which does its own internal (uncontrolled,
unpreviewable) monochrome conversion. Route it through
dither_for_thermal_print() first, sized to the actual configured paper
width instead of one fixed pixel cap regardless of paper size.
"""

from unittest.mock import MagicMock

from PIL import Image
import pytest

from cbpos.infrastructure.hardware.escpos_driver import ESCPOSDriver
from cbpos.core.utils.thermal_image import PAPER_DOT_WIDTH


@pytest.fixture
def wide_logo_path(tmp_path):
    path = tmp_path / "logo.png"
    Image.new("RGB", (1200, 300), color=(200, 50, 50)).save(path)
    return str(path)


@pytest.fixture
def driver():
    d = ESCPOSDriver()
    d.printer = MagicMock()
    return d


class TestImageIsDitheredBeforePrinting:
    def test_printed_image_is_1_bit(self, driver, wide_logo_path):
        driver.print_commands([{"type": "image", "path": wide_logo_path}])
        printed_image = driver.printer.image.call_args[0][0]
        assert printed_image.mode == "1"


class TestImageWidthMatchesConfiguredPaperWidth:
    def test_58mm_paper_downscales_to_58mm_dot_width(self, driver, wide_logo_path, monkeypatch):
        from cbpos.core.services.config_service import ConfigService

        monkeypatch.setattr(ConfigService, "get", staticmethod(lambda key: "58mm"))
        driver.print_commands([{"type": "image", "path": wide_logo_path}])
        printed_image = driver.printer.image.call_args[0][0]
        assert printed_image.width == PAPER_DOT_WIDTH["58mm"]

    def test_80mm_paper_downscales_to_80mm_dot_width(self, driver, wide_logo_path, monkeypatch):
        from cbpos.core.services.config_service import ConfigService

        monkeypatch.setattr(ConfigService, "get", staticmethod(lambda key: "80mm"))
        driver.print_commands([{"type": "image", "path": wide_logo_path}])
        printed_image = driver.printer.image.call_args[0][0]
        assert printed_image.width == PAPER_DOT_WIDTH["80mm"]


def _make_temp_png(tmp_path, name="small.png"):
    path = tmp_path / name
    Image.new("RGB", (50, 50), color=(0, 0, 0)).save(path)
    return str(path)


class TestNoPrinterIsANoOp:
    def test_missing_printer_does_not_raise(self, tmp_path):
        d = ESCPOSDriver()
        d.printer = None
        d.print_commands([{"type": "image", "path": _make_temp_png(tmp_path)}])
