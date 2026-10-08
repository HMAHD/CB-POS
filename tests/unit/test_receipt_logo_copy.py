"""
#626: the receipt logo is copied into the data folder.

browse_logo() stored the path of the picked file (e.g. in Downloads). If
that file moved, or a backup was restored on another PC, the logo
silently vanished from receipts. The picked image is now copied to
DATA_DIR/assets/receipt_logo.<ext> and settings keep the path relative
to the data folder. DATA_DIR is a temp folder here; the printer a mock.
"""

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from cbpos.config import Config
from cbpos.core.models import Product, Sale, SaleItem
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.receipt_builder import ReceiptBuilder
from cbpos.core.services.receipt_logo_service import resolve_receipt_logo, store_receipt_logo
from cbpos.infrastructure.hardware.escpos_driver import ESCPOSDriver


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    folder = tmp_path / "data"
    folder.mkdir()
    monkeypatch.setattr(Config, "DATA_DIR", folder)
    return folder


@pytest.fixture
def picked_logo(tmp_path) -> Path:
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    path = downloads / "My Shop Logo.PNG"
    Image.new("RGB", (120, 60), "black").save(path, format="PNG")
    return path


def _sale() -> Sale:
    sale = Sale(
        id=1,
        document_number="INV-1",
        date=datetime(2026, 10, 7, 10, 0),
        total_amount=Decimal("50.00"),
        tax_vat=Decimal("0"),
        tax_sscl=Decimal("0"),
        net_revenue=Decimal("50.00"),
    )
    sale.items = [
        SaleItem(product=Product(name_en="Tea"), qty=Decimal("1"), unit_price=Decimal("50"), subtotal=Decimal("50"))
    ]
    sale.payments = []
    return sale


class TestStoreReceiptLogo:
    def test_copies_into_data_folder_and_returns_relative_path(self, data_dir, picked_logo):
        stored = store_receipt_logo(str(picked_logo))

        assert stored == "assets/receipt_logo.png"
        assert (data_dir / "assets" / "receipt_logo.png").read_bytes() == picked_logo.read_bytes()

    def test_logo_still_prints_after_original_is_deleted(self, data_dir, picked_logo, monkeypatch):
        settings = {**ConfigService.DEFAULTS, "receipt_logo_path": store_receipt_logo(str(picked_logo))}
        monkeypatch.setattr(ConfigService, "get", classmethod(lambda cls, k: settings.get(k)))
        picked_logo.unlink()

        commands = ReceiptBuilder.build_receipt(_sale())
        (logo_cmd,) = [c for c in commands if c["type"] == "image"]
        assert Path(logo_cmd["path"]) == data_dir / "assets" / "receipt_logo.png"

        driver = ESCPOSDriver()
        driver.printer = MagicMock()
        driver.print_commands([logo_cmd])
        driver.printer.image.assert_called_once()

    def test_new_logo_replaces_old_one(self, data_dir, picked_logo, tmp_path):
        store_receipt_logo(str(picked_logo))
        jpg = tmp_path / "new.jpg"
        Image.new("RGB", (40, 40), "white").save(jpg, format="JPEG")

        assert store_receipt_logo(str(jpg)) == "assets/receipt_logo.jpg"
        assert sorted(p.name for p in (data_dir / "assets").iterdir()) == ["receipt_logo.jpg"]

    def test_picking_the_stored_logo_again_keeps_it(self, data_dir, picked_logo):
        store_receipt_logo(str(picked_logo))
        stored_file = data_dir / "assets" / "receipt_logo.png"

        assert store_receipt_logo(str(stored_file)) == "assets/receipt_logo.png"
        assert stored_file.read_bytes() == picked_logo.read_bytes()

    def test_not_an_image_is_rejected(self, data_dir, tmp_path):
        bogus = tmp_path / "notes.png"
        bogus.write_text("not an image")

        with pytest.raises(ValueError):
            store_receipt_logo(str(bogus))
        assert not (data_dir / "assets" / "receipt_logo.png").exists()

    def test_missing_file_is_rejected(self, data_dir, tmp_path):
        with pytest.raises(FileNotFoundError):
            store_receipt_logo(str(tmp_path / "gone.png"))


class TestResolveReceiptLogo:
    def test_relative_path_is_inside_data_folder(self, data_dir):
        assert Path(resolve_receipt_logo("assets/receipt_logo.png")) == data_dir / "assets" / "receipt_logo.png"

    def test_old_absolute_path_is_kept(self, data_dir, picked_logo):
        assert resolve_receipt_logo(str(picked_logo)) == str(picked_logo)

    def test_no_logo(self, data_dir):
        assert resolve_receipt_logo("") == ""
        assert resolve_receipt_logo(None) == ""


class TestBrowseLogo:
    @pytest.fixture
    def page(self, qapp, monkeypatch):
        from cbpos.ui.views.settings_pages import ReceiptPage

        settings = dict(ConfigService.DEFAULTS)
        monkeypatch.setattr(ConfigService, "get", classmethod(lambda cls, k: settings.get(k)))
        monkeypatch.setattr(ConfigService, "get_all", classmethod(lambda cls: dict(settings)))
        p = ReceiptPage()
        yield p
        p._refresh_timer.stop()
        p.deleteLater()

    def test_browse_stores_the_copy(self, page, data_dir, picked_logo):
        with patch("cbpos.ui.views.settings_pages.QFileDialog.getOpenFileName", return_value=(str(picked_logo), "")):
            page.browse_logo()

        assert page.input_logo_path.text() == "assets/receipt_logo.png"
        assert (data_dir / "assets" / "receipt_logo.png").exists()

    def test_bad_file_warns_and_keeps_old_logo(self, page, data_dir, tmp_path):
        bogus = tmp_path / "bad.png"
        bogus.write_text("nope")
        page.input_logo_path.setText("assets/receipt_logo.png")

        with (
            patch("cbpos.ui.views.settings_pages.QFileDialog.getOpenFileName", return_value=(str(bogus), "")),
            patch("cbpos.ui.views.settings_pages.QMessageBox") as mock_box,
        ):
            page.browse_logo()

        mock_box.warning.assert_called_once()
        assert page.input_logo_path.text() == "assets/receipt_logo.png"
